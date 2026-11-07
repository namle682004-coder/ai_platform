"""
Synchronises a data source into the knowledge base (see solutions/rag/CONNECTORS.md).

One sync: take the source's lease → read it with its connector → turn what changed into documents → store each
in object storage and index it with the ordinary ingestion pipeline → remove the documents of what disappeared
from the source (only after a complete read) → record the run and schedule the next one.

Documents of a source have stable ids (source + partition / URL): a re-sync updates them in place, an unchanged
document (same content hash) is not re-indexed.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import time
import uuid
import zipfile
from datetime import tzinfo
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from ...domain.entities import DocumentStatus, normalize_tenant_id
from ...domain.ports import DocumentRepositoryPort, StoragePort
from ...domain.sources import (
    ConnectorPort,
    FetchResult,
    SourceRepositoryPort,
    local_datetime,
    resolve_timezone,
)

logger = logging.getLogger("aip-rag.source_sync")

MAX_TABLE_COLUMNS = 30
MAX_CELL_CHARS = 2000
RETRY_AFTER_FAILURE_SECONDS = 900


def stable_doc_id(source_id: str, key: str) -> str:
    return "src_" + hashlib.sha1(f"{source_id}|{key}".encode("utf-8")).hexdigest()[:16]


def record_hash(data: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


_PDF_VOLATILE = re.compile(rb"/(?:CreationDate|ModDate)\s*\([^)]*\)|/ID\s*\[[^\]]*\]")
_OFFICE_ZIP = (".docx", ".xlsx", ".pptx")


def content_fingerprint(filename: str, content: bytes) -> str:
    """
    Hash used to decide whether a fetched file changed. Files generated on request (exports) carry the time they
    were produced — Office documents in docProps/ and in their zip entries, PDFs in CreationDate / ModDate / ID —
    so their bytes differ on every download while their content does not. Those parts are left out.
    """
    name = filename.lower()
    try:
        if name.endswith(_OFFICE_ZIP):
            h = hashlib.sha256()
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                for entry in sorted(z.namelist()):
                    if not entry.startswith("docProps/"):
                        h.update(entry.encode() + b"\x00" + z.read(entry) + b"\x00")
            return h.hexdigest()
        if name.endswith(".pdf"):
            return hashlib.sha256(_PDF_VOLATILE.sub(b"", content)).hexdigest()
    except Exception:  # noqa: BLE001 - unreadable as its format: compare the bytes
        pass
    return hashlib.sha256(content).hexdigest()


def flatten_record(data: Dict[str, Any], prefix: str = "", depth: int = 0) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in data.items():
        name = f"{prefix}{k}"
        if isinstance(v, dict) and depth < 1:
            out.update(flatten_record(v, f"{name}.", depth + 1))
        elif isinstance(v, list):
            if all(not isinstance(x, (dict, list)) for x in v):
                out[name] = ", ".join(str(x) for x in v)
        elif not isinstance(v, dict):
            out[name] = v
    return out


def _cell(value: Any, tz: Optional[tzinfo] = None) -> str:
    local = local_datetime(value, tz)
    if local is not None:  # a moment with a zone: shown in the users' time, as partitions are cut
        return local.strftime("%Y-%m-%d %H:%M")
    text = "" if value is None else str(value)
    text = " ".join(text.split()).replace("|", "\\|")
    return text[:MAX_CELL_CHARS]


def render_records(title: str, records: List[Dict[str, Any]], columns: Optional[List[Dict[str, str]]],
                   timezone_name: Optional[str] = None) -> str:
    """Records of one partition as a Markdown document holding one table (one row per record)."""
    tz = resolve_timezone(timezone_name)
    flat = [flatten_record(r) for r in records]
    if columns:
        fields = [(c["field"], c.get("label") or c["field"]) for c in columns]
    else:
        names: List[str] = []
        for f in flat:
            names += [k for k in f if k not in names]
        fields = [(n, n) for n in names[:MAX_TABLE_COLUMNS]]
    cells = [[_cell(f.get(field), tz) for field, _ in fields] for f in flat]
    converted = tz is not None and any(local_datetime(f.get(field), tz) for f in flat for field, _ in fields)
    lines = [f"# {title}", "", f"{len(records)} bản ghi."
             + (f" Thời gian theo múi giờ {timezone_name}." if converted else ""), "",
             "| " + " | ".join(_cell(label) for _, label in fields) + " |",
             "| " + " | ".join("---" for _ in fields) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in cells]
    return "\n".join(lines) + "\n"


def _slug(text: str) -> str:
    return re.sub(r"[^\w.\- ]+", "_", text).strip()[:100] or "document"


class SourceSyncUseCase:
    def __init__(
        self,
        sources: SourceRepositoryPort,
        connector_for: Callable[[str], ConnectorPort],
        doc_repo: DocumentRepositoryPort,
        storage: StoragePort,
        ingest: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
        delete_document: Callable[[str, str], Awaitable[bool]],
        bucket: str = "aip-data",
        lease_seconds: float = 3600.0,
        owner: Optional[str] = None,
        default_timezone: str = "+07:00",
    ) -> None:
        self.default_timezone = default_timezone
        self.sources = sources
        self.connector_for = connector_for
        self.doc_repo = doc_repo
        self.storage = storage
        self.ingest = ingest
        self.delete_document = delete_document
        self.bucket = bucket
        self.lease_seconds = lease_seconds
        self.owner = owner or f"sync-{uuid.uuid4().hex[:8]}"

    # ------------------------------------------------------------------ scheduling
    async def run_due(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """Sync every source whose time has come (called periodically by the worker)."""
        runs = []
        for source in await self.sources.due(now or time.time()):
            runs.append(await self.sync(source["source_id"], trigger="schedule"))
        return runs

    # ------------------------------------------------------------------ one sync
    async def sync(self, source_id: str, trigger: str = "manual") -> Dict[str, Any]:
        source = await self.sources.get(source_id)
        started = time.time()
        run: Dict[str, Any] = {
            "run_id": uuid.uuid4().hex[:12], "source_id": source_id, "trigger": trigger, "started_at": started,
            "status": "running", "fetched": 0, "created": 0, "updated": 0, "unchanged": 0, "deleted": 0,
            "failed": 0, "complete": False, "errors": [],
        }
        if not source:
            return {**run, "status": "not_found"}
        run["tenant_id"] = source["tenant_id"]
        if not await self.sources.acquire(source_id, self.owner, started, self.lease_seconds):
            return {**run, "status": "busy"}
        fields: Dict[str, Any] = {}
        try:
            result = await self.connector_for(source["type"]).fetch(source, dict(source.get("cursor") or {}))
            run["fetched"], run["complete"] = len(result.items), result.complete
            run["errors"] += result.errors[:20]
            if source["type"] == "json_api":
                await self._sync_records(source, result, run)
            else:
                await self._sync_documents(source, result, run)
            run["status"] = "success" if not run["errors"] and not run["failed"] else "partial"
            fields["cursor"] = result.cursor or source.get("cursor") or {}
            fields["consecutive_failures"] = 0
        except Exception as exc:  # noqa: BLE001 - recorded on the run; the source stays usable
            logger.exception("Source %s sync failed", source_id)
            run["status"] = "failed"
            run["errors"].append(f"{type(exc).__name__}: {exc}"[:500])
            fields["consecutive_failures"] = int(source.get("consecutive_failures") or 0) + 1
        finally:
            run["finished_at"] = time.time()
            run["duration_s"] = round(run["finished_at"] - started, 2)
            run["errors"] = run["errors"][:20]
            every = float(source.get("schedule_minutes") or 0) * 60
            if every:
                delay = every if run["status"] != "failed" else min(every, RETRY_AFTER_FAILURE_SECONDS)
                fields["next_sync_at"] = run["finished_at"] + delay
            fields["last_run"] = {k: run[k] for k in ("run_id", "status", "started_at", "finished_at", "fetched",
                                                      "created", "updated", "unchanged", "deleted", "failed",
                                                      "complete")}
            fields["last_run"]["error"] = run["errors"][0] if run["errors"] else ""
            await self.sources.release(source_id, self.owner, fields)
            await self.sources.add_run(run)
        logger.info("Source %s synced (%s): %s", source_id, trigger,
                    {k: run[k] for k in ("status", "fetched", "created", "updated", "unchanged", "deleted", "failed")})
        return run

    # ------------------------------------------------------------------ structured sources
    async def _sync_records(self, source: Dict[str, Any], result: FetchResult, run: Dict[str, Any]) -> None:
        sid = source["source_id"]
        hashes = {it.key: record_hash(it.data) for it in result.items}
        changed = await self.sources.upsert_records(sid, result.items, hashes)
        touched: Set[str] = set(changed.values())
        if result.complete:
            touched |= set((await self.sources.remove_records_except(sid, [it.key for it in result.items])).values())
        run["unchanged"] += len({it.partition for it in result.items} - touched)  # partitions left as they were
        cfg = source.get("config") or {}
        for partition in sorted(touched):
            records = [r["data"] for r in await self.sources.records_of(sid, partition)]
            doc_id = stable_doc_id(sid, f"partition:{partition}")
            if not records:
                if await self.delete_document(doc_id, source["tenant_id"]):
                    run["deleted"] += 1
                continue
            title = source["name"] if partition == "all" else f"{source['name']} – {partition}"
            content = render_records(title, records, cfg.get("columns"),
                                     cfg.get("timezone") or self.default_timezone).encode("utf-8")
            await self._index(source, doc_id, title, f"{_slug(title)}.md", content, run,
                              url=cfg.get("url", ""), key=f"partition:{partition}")

    # ------------------------------------------------------------------ pages / files
    async def _sync_documents(self, source: Dict[str, Any], result: FetchResult, run: Dict[str, Any]) -> None:
        produced: Set[str] = set()
        for it in result.items:
            doc_id = stable_doc_id(source["source_id"], it.key)
            produced.add(doc_id)
            await self._index(source, doc_id, it.title or it.url, it.filename, it.content, run, url=it.url, key=it.key)
        if result.complete:
            for doc in await self.doc_repo.find_by_source(source["tenant_id"], source["source_id"]):
                if doc["doc_id"] not in produced and await self.delete_document(doc["doc_id"], source["tenant_id"]):
                    run["deleted"] += 1

    # ------------------------------------------------------------------ one document
    async def _index(self, source: Dict[str, Any], doc_id: str, title: str, filename: str, content: bytes,
                     run: Dict[str, Any], url: str = "", key: str = "") -> None:
        tenant_id = normalize_tenant_id(source["tenant_id"])
        digest = hashlib.sha256(content).hexdigest()  # exact bytes: duplicate detection against uploads
        fingerprint = content_fingerprint(filename, content)  # content only: change detection between syncs
        existing = await self.doc_repo.get_document(doc_id)
        if (existing and existing.get("status") == DocumentStatus.INDEXED.value
                and fingerprint in (existing.get("source_fingerprint"), existing.get("content_sha256"))):
            run["unchanged"] += 1
            return
        try:
            object_name = f"documents/{tenant_id}/{doc_id}_{filename}"
            s3_uri = self.storage.upload_bytes(bucket=self.bucket, object_name=object_name, data=content)
            now = int(time.time())
            record = {
                "doc_id": doc_id, "tenant_id": tenant_id, "title": title[:300], "filename": filename,
                "file_type": filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt",
                "file_size_bytes": len(content), "content_sha256": digest, "source_fingerprint": fingerprint,
                "status": DocumentStatus.PENDING.value, "total_chunks": (existing or {}).get("total_chunks", 0),
                "total_pages": 0, "department": source.get("department") or "GENERAL",
                "allowed_roles": source.get("allowed_roles") or ["*"],
                "s3_bucket": self.bucket, "s3_object_name": object_name, "s3_uri": s3_uri,
                "effective_status": "ACTIVE", "effective_date": None, "expiry_date": None,
                "source_id": source["source_id"], "source_type": source["type"], "source_url": url, "source_key": key,
                "created_at": (existing or {}).get("created_at", now), "updated_at": now,
            }
            await self.doc_repo.create_document(record)
            outcome = await self.ingest(record)
            if outcome.get("status") in ("failed", "FAILED"):
                run["failed"] += 1
                run["errors"].append(f"{filename}: {outcome.get('error', 'indexing failed')}"[:300])
            else:
                run["updated" if existing else "created"] += 1
        except Exception as exc:  # noqa: BLE001 - one bad page / partition does not stop the sync
            logger.warning("Source %s: %s not indexed: %s", source["source_id"], filename, exc)
            run["failed"] += 1
            run["errors"].append(f"{filename}: {type(exc).__name__}: {exc}"[:300])
