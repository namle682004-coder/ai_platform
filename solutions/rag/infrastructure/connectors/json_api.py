"""
Connector for JSON APIs that list records (posts of a collector, rows of an internal system).

config:
  url                 endpoint returning records
  allowed_hosts       hosts that may be contacted (required)
  params              fixed query parameters
  records_path        dotted path of the record list in the response ("" = the response is the list)
  id_field            dotted path of a record's stable id (required)
  partition_field     dotted path grouping records into documents (e.g. a date: one document per day)
  partition_format    "date" (YYYY-MM-DD; a date-time with a zone is taken in `timezone`) | "value" (as is) |
                      "none" (single document)
  timezone            users' time zone ("+07:00", IANA name); default: the service setting connector_timezone
  pagination          {"type": "none" | "page" | "offset" | "cursor" | "next_url" | "link_header",
                       "param": "page", "start": 1, "size_param": "limit", "size": 100,
                       "cursor_param": "cursor", "cursor_path": "next_cursor" (or "header:x-next-cursor"),
                       "next_url_path": "next"}
  updated_field       dotted path of a record's modification time (enables incremental reads with since_param)
  since_param         query parameter receiving the last modification time seen
  max_pages / max_records   per-sync bounds (also capped by the service settings)

A read that went through every page without an incremental filter is complete: records the source no longer
returns are removed from the knowledge base. Incremental reads never remove.
"""

from __future__ import annotations

import re
from datetime import tzinfo
from typing import Any, Dict, List, Optional

import httpx

from ...config import rag_settings
from ...domain.sources import ConnectorPort, FetchResult, SourceItem, local_datetime, resolve_timezone
from .http import ConnectorError, SourceHttp


def dig(data: Any, path: str) -> Any:
    """Value at a dotted path ("a.b.0.c"); None when absent."""
    if not path:
        return data
    for part in path.split("."):
        if isinstance(data, dict):
            data = data.get(part)
        elif isinstance(data, list) and part.isdigit() and int(part) < len(data):
            data = data[int(part)]
        else:
            return None
    return data


def next_cursor(headers: Dict[str, str], body: Any, page_cfg: Dict[str, Any]) -> Any:
    """Cursor of the next page: a dotted path in the body, or 'header:<name>' for APIs that send it as a header."""
    path = str(page_cfg.get("cursor_path") or "next_cursor")
    if path.lower().startswith("header:"):
        return headers.get(path.split(":", 1)[1].strip().lower())
    return dig(body, path)


def source_timezone(cfg: Dict[str, Any]) -> Optional[tzinfo]:
    return resolve_timezone(cfg.get("timezone") or rag_settings.connector_timezone)


def partition_of(record: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    fmt = (cfg.get("partition_format") or ("date" if cfg.get("partition_field") else "none")).lower()
    if fmt == "none" or not cfg.get("partition_field"):
        return "all"
    value = dig(record, cfg["partition_field"])
    if value is None or value == "":
        return "unknown"
    text = str(value)
    if fmt == "date":
        local = local_datetime(text, source_timezone(cfg))  # the users' day, not the day in UTC
        if local is not None:
            return local.date().isoformat()
        m = re.match(r"\d{4}-\d{2}-\d{2}", text)
        return m.group(0) if m else text[:10]
    return re.sub(r"[^\w.-]+", "_", text)[:80]


class JsonApiConnector(ConnectorPort):
    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self.transport = transport

    async def fetch(self, source: Dict[str, Any], cursor: Dict[str, Any]) -> FetchResult:
        cfg = source.get("config") or {}
        url = cfg.get("url") or ""
        id_field = cfg.get("id_field") or ""
        if not url or not id_field:
            raise ConnectorError("config.url and config.id_field are required")
        page_cfg = cfg.get("pagination") or {"type": "none"}
        kind = (page_cfg.get("type") or "none").lower()
        max_pages = min(int(cfg.get("max_pages") or rag_settings.connector_max_pages), rag_settings.connector_max_pages)
        max_records = min(int(cfg.get("max_records") or rag_settings.connector_max_records),
                          rag_settings.connector_max_records)
        incremental = bool(cfg.get("since_param") and cfg.get("updated_field") and cursor.get("since"))

        params: Dict[str, Any] = dict(cfg.get("params") or {})
        if incremental:
            params[cfg["since_param"]] = cursor["since"]
        if page_cfg.get("size_param"):
            params[page_cfg["size_param"]] = int(page_cfg.get("size") or 100)
        page_no = int(page_cfg.get("start", 1 if kind == "page" else 0))
        if kind in ("page", "offset"):
            params[page_cfg.get("param") or kind] = page_no

        http = SourceHttp(source, self.transport)
        items: List[SourceItem] = []
        errors: List[str] = []
        seen: Dict[str, int] = {}
        newest = cursor.get("since") or ""
        truncated, next_url = False, url
        try:
            for pages in range(max_pages + 1):
                if pages == max_pages:
                    truncated = True
                    break
                res = await http.get(next_url, params=params)
                body = res.json()
                records = dig(body, cfg.get("records_path") or "")
                if not isinstance(records, list):
                    raise ConnectorError(f"config.records_path {cfg.get('records_path')!r} is not a list in the response")
                for rec in records:
                    if not isinstance(rec, dict):
                        continue
                    rid = dig(rec, id_field)
                    if rid in (None, ""):
                        errors.append(f"record without {id_field}")
                        continue
                    key = str(rid)
                    if key in seen:
                        items[seen[key]].data = rec  # the same record on two pages: keep the later copy
                        continue
                    seen[key] = len(items)
                    title = str(dig(rec, cfg["title_field"]) or "") if cfg.get("title_field") else ""
                    items.append(SourceItem(key=key, kind="record", title=title, data=rec,
                                            partition=partition_of(rec, cfg)))
                    updated = str(dig(rec, cfg.get("updated_field") or "") or "")
                    newest = max(newest, updated) if updated else newest
                if len(items) >= max_records:
                    # Whether more records exist is unknown: never treat the read as complete (no removals).
                    truncated = True
                    del items[max_records:]
                    break
                # next page
                if kind == "none" or not records:
                    break
                if kind == "page":
                    page_no += 1
                    params[page_cfg.get("param") or "page"] = page_no
                elif kind == "offset":
                    page_no += len(records)
                    params[page_cfg.get("param") or "offset"] = page_no
                elif kind == "cursor":
                    nxt = next_cursor(res.headers, body, page_cfg)
                    if not nxt:
                        break
                    params[page_cfg.get("cursor_param") or "cursor"] = nxt
                elif kind == "next_url":
                    nxt = dig(body, page_cfg.get("next_url_path") or "next")
                    if not nxt:
                        break
                    next_url, params = str(nxt), {}
                elif kind == "link_header":
                    m = re.search(r'<([^>]+)>\s*;\s*rel="?next"?', res.headers.get("link", ""))
                    if not m:
                        break
                    next_url, params = m.group(1), {}
                else:
                    raise ConnectorError(f"unknown pagination.type {kind!r}")
        finally:
            await http.close()
        return FetchResult(items=items, cursor={"since": newest} if newest else {},
                           complete=not incremental and not truncated, errors=errors)
