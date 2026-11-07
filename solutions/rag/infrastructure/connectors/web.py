"""
Connector for internal websites: pages reachable from start URLs, plus the documents they link to.

config:
  start_urls          pages the crawl starts from (required)
  allowed_hosts       hosts that may be contacted (required)
  include_prefixes    only URLs starting with one of these are read (default: the start URLs' folders)
  exclude_patterns    regular expressions of URLs never read (logout, print views, calendars…)
  max_depth           link distance from a start URL (default 3)
  max_pages           pages + files per sync (also capped by the service setting)
  follow_links        false = read only the start URLs (default true)
  include_files       read linked pdf / docx / xlsx (default true); a download's kind is taken from its
                      content type, its Content-Disposition name, its URL or its bytes (/download?id=… links)
  delay_seconds       pause between two requests (at least the service minimum)

A crawl that exhausted every reachable page without error is complete: pages that disappeared from the site are
removed from the knowledge base. A truncated or partly failed crawl removes nothing.
"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import unquote, urldefrag, urlsplit, urlunsplit

import httpx

from ...config import rag_settings
from ...domain.sources import ConnectorPort, FetchResult, SourceItem
from ..parsers.html_parser import decode_html, html_to_markdown
from .http import ConnectorError, SourceHttp

HTML_TYPES = ("text/html", "application/xhtml+xml")
FILE_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}
FILE_EXTENSIONS = tuple(FILE_TYPES.values())
# Types servers use for downloads whatever the file is; the file kind is then found from the name or the bytes.
DOWNLOAD_TYPES = ("application/octet-stream", "binary/octet-stream", "application/download",
                  "application/force-download", "application/x-download")
SKIP_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".css", ".js", ".zip", ".rar", ".mp4",
                   ".mp3", ".avi", ".exe", ".doc", ".xls", ".ppt", ".pptx")


def canonical(url: str) -> str:
    """Scheme and host lower-cased, fragment dropped, empty path as '/'."""
    url = urldefrag(url)[0]
    p = urlsplit(url)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", p.query, ""))


def _folder(url: str) -> str:
    p = urlsplit(canonical(url))
    path = p.path if p.path.endswith("/") else posixpath.dirname(p.path) + "/"
    return urlunsplit((p.scheme, p.netloc, path, "", ""))


def _filename(url: str, ext: str) -> str:
    name = unquote(posixpath.basename(urlsplit(url).path)) or "index"
    name = re.sub(r"[^\w.\- ]+", "_", name)[:120]
    return name if name.lower().endswith(ext) else f"{name}{ext}"


def _disposition_name(headers: Dict[str, str]) -> str:
    """File name given by Content-Disposition (RFC 6266 filename* first), or ''."""
    value = headers.get("content-disposition", "")
    m = re.search(r"filename\*\s*=\s*[^']*'[^']*'([^;]+)", value) or re.search(r'filename\s*=\s*"?([^";]+)"?', value)
    return posixpath.basename(unquote(m.group(1).strip())) if m else ""


def _sniff(content: bytes) -> str:
    """Extension of a supported file recognised from its bytes, or ''."""
    if content[:5] == b"%PDF-":
        return ".pdf"
    if content[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                names = set(z.namelist())
        except zipfile.BadZipFile:
            return ""
        if "word/document.xml" in names:
            return ".docx"
        if "xl/workbook.xml" in names:
            return ".xlsx"
    return ""


def file_kind(content_type: str, headers: Dict[str, str], url: str, content: bytes) -> Tuple[str, str]:
    """(extension, file name) of a supported file response, or ('', '') when it is not one."""
    named = _disposition_name(headers)
    candidates = (FILE_TYPES.get(content_type, ""), posixpath.splitext(named.lower())[1],
                  posixpath.splitext(urlsplit(url).path.lower())[1])
    ext = next((e for e in candidates if e in FILE_EXTENSIONS), "") or _sniff(content)
    if not ext:
        return "", ""
    return ext, _filename(f"/{named}" if named else url, ext)


class WebConnector(ConnectorPort):
    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self.transport = transport

    async def fetch(self, source: Dict[str, Any], cursor: Dict[str, Any]) -> FetchResult:
        cfg = source.get("config") or {}
        starts = [canonical(u) for u in cfg.get("start_urls") or []]
        if not starts:
            raise ConnectorError("config.start_urls is required")
        prefixes = [canonical(p) for p in cfg.get("include_prefixes") or []] or [_folder(u) for u in starts]
        excludes = [re.compile(p) for p in cfg.get("exclude_patterns") or []]
        max_depth = max(0, int(cfg.get("max_depth", 3)))
        max_pages = min(int(cfg.get("max_pages") or rag_settings.connector_max_pages), rag_settings.connector_max_pages)
        follow = bool(cfg.get("follow_links", True))
        include_files = bool(cfg.get("include_files", True))

        def wanted(url: str) -> bool:
            low = urlsplit(url).path.lower()
            if low.endswith(SKIP_EXTENSIONS) or (low.endswith(FILE_EXTENSIONS) and not include_files):
                return False
            return any(url.startswith(p) for p in prefixes) and not any(x.search(url) for x in excludes)

        http = SourceHttp(source, self.transport)
        for u in starts:
            http.check(u)  # a start URL outside the allowed hosts is a configuration error, not a skip
        queue: deque[Tuple[str, int]] = deque((u, 0) for u in starts)
        queued: Set[str] = set(starts)
        items: List[SourceItem] = []
        errors: List[str] = []
        truncated = False
        try:
            while queue:
                if len(items) >= max_pages:
                    truncated = True
                    break
                url, depth = queue.popleft()
                try:
                    res = await http.get(url, accept=[*HTML_TYPES, *FILE_TYPES, *DOWNLOAD_TYPES])
                except ConnectorError as exc:
                    errors.append(str(exc)[:300])
                    continue
                final = canonical(res.url)
                if final != url and not wanted(final):
                    continue  # redirected somewhere outside the crawl's scope
                ctype = res.content_type
                if ctype in HTML_TYPES or (not ctype and not urlsplit(final).path.lower().endswith(FILE_EXTENSIONS)):
                    if not res.content:
                        continue
                    title, _md, links = html_to_markdown(decode_html(res.content), final)
                    items.append(SourceItem(key=final, kind="page", title=title or final, url=final,
                                            content=res.content, filename=_filename(final, ".html")))
                    if follow and depth < max_depth:
                        for link in links:
                            link = canonical(link)
                            if link not in queued and urlsplit(link).hostname in http.allowed_hosts and wanted(link):
                                queued.add(link)
                                queue.append((link, depth + 1))
                elif include_files and res.content:
                    ext, name = file_kind(ctype, res.headers, final, res.content)
                    if not ext:
                        continue  # a download of a kind the knowledge base does not read
                    items.append(SourceItem(key=final, kind="file", title=posixpath.splitext(name)[0], url=final,
                                            content=res.content, filename=name))
        finally:
            await http.close()
        return FetchResult(items=items, cursor={}, complete=not truncated and not errors, errors=errors)
