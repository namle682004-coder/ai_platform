"""
Trial read of a source for the configuration screen (POST /v1/knowledge/sources/preview). Nothing is stored.

JSON API: the first page only — where the record lists are in the response, the fields of the records with a
sample value (so an administrator picks the id / grouping / columns instead of writing paths), whether the id
field is present and unique, the documents the grouping would produce, and the start of the first document.
Website: the first pages of the crawl with what each holds (tables, size) and the start of the first page.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ...application.use_cases.source_sync_use_case import flatten_record, render_records
from ...config import rag_settings
from ..parsers.html_parser import decode_html, html_to_markdown
from .http import ConnectorError, SourceHttp
from .json_api import dig, partition_of
from .web import WebConnector

PAGING_HEADER = re.compile(r"(cursor|next|^link$|continuation)", re.IGNORECASE)
PREVIEW_PAGES = 8
SAMPLE_RECORDS = 5
MAX_FIELDS = 80


def record_lists(body: Any, path: str = "", depth: int = 0) -> List[Tuple[str, int]]:
    """Dotted paths of the lists of objects in a response: where the records may be."""
    if isinstance(body, list):
        return [(path, len(body))] if body and all(isinstance(x, dict) for x in body[:20]) else []
    out: List[Tuple[str, int]] = []
    if isinstance(body, dict) and depth < 4:
        for k, v in body.items():
            out += record_lists(v, f"{path}.{k}" if path else str(k), depth + 1)
    return out


def _table_count(markdown: str) -> int:
    return sum(1 for line in markdown.splitlines() if line.replace(" ", "").startswith("|---"))


async def preview_json(source: Dict[str, Any], transport: Optional[httpx.AsyncBaseTransport] = None) -> Dict[str, Any]:
    cfg = source.get("config") or {}
    page_cfg = cfg.get("pagination") or {}
    kind = (page_cfg.get("type") or "none").lower()
    params: Dict[str, Any] = dict(cfg.get("params") or {})
    if page_cfg.get("size_param"):
        params[page_cfg["size_param"]] = int(page_cfg.get("size") or 100)
    if kind in ("page", "offset"):
        params[page_cfg.get("param") or kind] = int(page_cfg.get("start", 1 if kind == "page" else 0))
    http = SourceHttp(source, transport)
    try:
        res = await http.get(str(cfg.get("url") or ""), params=params)
    finally:
        await http.close()
    try:
        body = res.json()
    except ValueError as exc:
        raise ConnectorError("the response is not JSON") from exc

    out: Dict[str, Any] = {
        "ok": True, "type": "json_api", "first_page_only": kind != "none",
        "list_paths": [{"path": p, "count": n} for p, n in record_lists(body)][:10],
        # Response headers that look like paging (x-next-cursor, link…): offered as the way to the next page.
        "paging_headers": [{"header": k, "value": str(v)[:80]} for k, v in res.headers.items()
                           if PAGING_HEADER.search(k)][:5],
    }
    path = cfg.get("records_path") or ""
    records = dig(body, path)
    if not isinstance(records, list):
        out.update(ok=False, error=f"records_path {path!r} is not a list in the response")
        return out
    recs = [r for r in records if isinstance(r, dict)]
    fields: Dict[str, str] = {}
    for r in recs[:50]:
        for k, v in flatten_record(r).items():
            if not fields.get(k) and v not in (None, ""):
                fields[k] = " ".join(str(v).split())[:80]
            fields.setdefault(k, "")
    out["records"] = len(recs)
    out["fields"] = [{"path": k, "sample": v} for k, v in list(fields.items())[:MAX_FIELDS]]
    if cfg.get("id_field"):
        ids = [dig(r, cfg["id_field"]) for r in recs]
        present = [str(i) for i in ids if i not in (None, "")]
        out["id_check"] = {"missing": len(ids) - len(present), "duplicates": len(present) - len(set(present))}
    out["partitions"] = [{"partition": p, "records": n}
                         for p, n in Counter(partition_of(r, cfg) for r in recs).most_common(10)]
    out["sample_markdown"] = render_records(source.get("name") or "Xem trước", recs[:SAMPLE_RECORDS], cfg.get("columns"),
                                            cfg.get("timezone") or rag_settings.connector_timezone)
    return out


async def preview_web(source: Dict[str, Any], transport: Optional[httpx.AsyncBaseTransport] = None) -> Dict[str, Any]:
    cfg = dict(source.get("config") or {})
    cfg["max_pages"] = min(int(cfg.get("max_pages") or PREVIEW_PAGES), PREVIEW_PAGES)
    res = await WebConnector(transport).fetch({**source, "config": cfg}, {})
    items: List[Dict[str, Any]] = []
    sample: Optional[Dict[str, str]] = None
    sample_has_table = False
    for it in res.items:
        entry: Dict[str, Any] = {"title": it.title, "url": it.url, "kind": it.kind, "filename": it.filename,
                                 "bytes": len(it.content)}
        if it.kind == "page":
            _title, md, _links = html_to_markdown(decode_html(it.content), it.url)
            entry.update(tables=_table_count(md), chars=len(md))
            # The first page holding a table shows best how the site will be read; else the first page.
            if md.strip() and (sample is None or (entry["tables"] and not sample_has_table)):
                sample, sample_has_table = {"url": it.url, "markdown": md[:3000]}, bool(entry["tables"])
        items.append(entry)
    out: Dict[str, Any] = {"ok": bool(items), "type": "web", "items": items, "errors": res.errors[:10],
                           "limited": len(items) >= cfg["max_pages"], "sample": sample}
    if not items:
        out["error"] = res.errors[0] if res.errors else "no page could be read from the start URLs"
    return out


async def preview_source(source: Dict[str, Any], transport: Optional[httpx.AsyncBaseTransport] = None) -> Dict[str, Any]:
    try:
        if source.get("type") == "json_api":
            return await preview_json(source, transport)
        return await preview_web(source, transport)
    except ConnectorError as exc:
        return {"ok": False, "type": source.get("type"), "error": str(exc)}
