"""
End-to-end check of the connectors in the loadtest stack (deploy/docker-compose/docker-compose.connectors-e2e.yml).

Runs inside the rag-api container (`docker exec -i aip-loadtest-rag-api python - < scripts/e2e_connectors.py`):
drives the real API, lets the real worker sync from scripts/fake_source.py, and checks what reached Mongo,
Qdrant and the table store. Prints one line per check and exits 1 if any failed.
"""

import asyncio
import sys
import time

import httpx

sys.path.insert(0, "/app")

from solutions.rag.application.components.table_query import Condition, TableQuery, run_query  # noqa: E402
from solutions.rag.application.components.table_store import TableRecord  # noqa: E402
from solutions.rag.config import rag_settings  # noqa: E402
from solutions.rag.infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter  # noqa: E402
from solutions.rag.infrastructure.repositories.mongo_document_repo import MongoDocumentRepositoryAdapter  # noqa: E402
from solutions.rag.infrastructure.repositories.mongo_table_repo import MongoTableStore  # noqa: E402

API = "http://localhost:8010/v1/knowledge/sources"
SRC = "http://fakesource:8099"
TENANT = "tenant_e2e"
ADMIN = {"X-Tenant-ID": TENANT, "X-User-Role": "admin", "X-User-ID": "e2e"}
RESULTS = []

docs = MongoDocumentRepositoryAdapter(rag_settings.mongo_uri)
tables = MongoTableStore(rag_settings.mongo_uri)
qdrant = QdrantVectorStoreAdapter(base_url=rag_settings.qdrant_url, collection_name=rag_settings.collection_name,
                                  dim=rag_settings.embedding_dim)


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""), flush=True)


async def control(c, op):
    (await c.post(f"{SRC}/_control", json={"op": op})).raise_for_status()


async def sync(c, sid, timeout=300):
    before = len((await c.get(f"{API}/{sid}/runs", headers=ADMIN)).json()["items"])
    r = await c.post(f"{API}/{sid}/sync", headers=ADMIN)
    assert r.status_code == 202, r.text
    deadline = time.time() + timeout
    while time.time() < deadline:
        runs = (await c.get(f"{API}/{sid}/runs", headers=ADMIN)).json()["items"]
        if len(runs) > before:
            return runs[0]
        await asyncio.sleep(2)
    raise TimeoutError(f"no run of {sid} within {timeout}s")


async def source_docs(sid):
    return {d["source_key"]: d for d in await docs.find_by_source(TENANT, sid)}


async def table_records(doc_id):
    return [TableRecord.from_dict(t) for t in await tables.list_tables(TENANT, "user", doc_ids=[doc_id])]


async def count(doc_id, column, value, op="="):
    res = run_query(await table_records(doc_id), TableQuery([0], "count", [Condition(column, op, value)]))
    return res.value if res else None


async def chunks(doc_id):
    return len(await qdrant.fetch_document_chunks(doc_id, TENANT, "user"))


async def ready(c, timeout=180):
    """A fresh stack: the API is up before Mongo answers and the fake source may still be starting."""
    deadline = time.time() + timeout
    while True:
        try:
            await control(c, "reset")
            if (await c.get(API, headers=ADMIN)).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        if time.time() > deadline:
            raise TimeoutError("stack not ready")
        await asyncio.sleep(3)


async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        await ready(c)

        # ---------------------------------------------------------------- configuration is guarded
        api_cfg = {
            "url": f"{SRC}/api/posts", "allowed_hosts": ["fakesource"], "records_path": "data.items", "id_field": "id",
            "partition_field": "published_at", "updated_field": "updated_at",
            "pagination": {"type": "page", "param": "page", "size_param": "limit", "size": 10},
            "columns": [{"field": "published_at", "label": "Thời gian"}, {"field": "source.name", "label": "Nguồn"},
                        {"field": "source.type", "label": "Loại nguồn"}, {"field": "title", "label": "Tiêu đề"},
                        {"field": "sentiment", "label": "Sắc thái"}],
        }
        bearer = {"type": "bearer", "token_env": "AIP_SOURCE_SECRET_DEMO"}
        body = {"name": "Bản tin MXH", "type": "json_api", "config": api_cfg, "auth": bearer, "schedule_minutes": 0}
        r = await c.post(API, json=body, headers={**ADMIN, "X-User-Role": "user"})
        check("a non-admin cannot create a source", r.status_code == 403, r.status_code)
        r = await c.post(API, json={**body, "auth": {"type": "bearer", "token_env": "MONGO_URI"}}, headers=ADMIN)
        check("a secret outside AIP_SOURCE_SECRET_* is refused", r.status_code == 422, r.json().get("detail"))
        r = await c.post(API, json={**body, "auth": {"type": "bearer", "token": "plain"}}, headers=ADMIN)
        check("a secret written into the source is refused", r.status_code == 422)
        r = await c.post(API, json={**body, "config": {**api_cfg, "url": "http://169.254.169.254/latest"}}, headers=ADMIN)
        check("a URL outside allowed_hosts is refused", r.status_code == 422)

        r = await c.post(API, json=body, headers=ADMIN)
        api_src = r.json()
        sid = api_src["source_id"]
        check("JSON API source created, its secret is present in the worker env", r.status_code == 201
              and api_src["missing_secrets"] == [], api_src.get("missing_secrets"))
        r = await c.get(f"{API}/{sid}", headers={**ADMIN, "X-Tenant-ID": "other_tenant"})
        check("another tenant cannot see the source", r.status_code == 404)

        # ---------------------------------------------------------------- first sync of the JSON API
        run = await sync(c, sid)
        check("first sync: 42 records → 3 day documents", run["status"] == "success" and run["fetched"] == 42
              and run["created"] == 3, {k: run[k] for k in ("status", "fetched", "created", "failed")} | {"err": run["errors"][:2]})
        by_key = await source_docs(sid)
        check("the 3 documents are INDEXED", sorted(d["status"] for d in by_key.values()) == ["INDEXED"] * 3,
              {k: d["status"] for k, d in by_key.items()})
        day2 = by_key.get("partition:2026-11-02", {}).get("doc_id")
        day3 = by_key.get("partition:2026-11-03", {}).get("doc_id")
        n_chunks = [await chunks(d["doc_id"]) for d in by_key.values()]
        check("each document has chunks in Qdrant", all(n > 0 for n in n_chunks), n_chunks)
        got = (await count(day2, "Sắc thái", "Trung tính"), await count(day2, "Sắc thái", "Tích cực"))
        check("table store counts exactly (day 2: 10 neutral, 2 positive)", got == (10, 2), got)
        hidden = await tables.list_tables("other_tenant", "admin", doc_ids=[day2])
        check("another tenant gets none of the tables", hidden == [], len(hidden))

        # ---------------------------------------------------------------- change detection
        run = await sync(c, sid)
        check("re-sync with nothing changed re-indexes nothing", run["unchanged"] == 3 and run["created"] == 0
              and run["updated"] == 0, {k: run[k] for k in ("unchanged", "created", "updated")})
        await control(c, "edit")
        run = await sync(c, sid)
        check("one edited record re-indexes only its day", run["updated"] == 1 and run["unchanged"] == 2,
              {k: run[k] for k in ("unchanged", "updated")})
        got = (await count(day2, "Sắc thái", "Trung tính"), await count(day2, "Sắc thái", "Tích cực"))
        check("the edit is visible to table questions (9 neutral, 3 positive)", got == (9, 3), got)
        await control(c, "drop_day")
        run = await sync(c, sid)
        gone = day3 not in {d["doc_id"] for d in (await source_docs(sid)).values()}
        check("a day removed at the source is removed from the knowledge base", run["deleted"] == 1 and gone,
              run["deleted"])
        check("… with its chunks and tables", await chunks(day3) == 0 and await table_records(day3) == [])

        # ---------------------------------------------------------------- website
        web_body = {"name": "Cổng nội bộ", "type": "web", "schedule_minutes": 0, "config": {
            "start_urls": [f"{SRC}/site/index.html"], "allowed_hosts": ["fakesource"], "max_depth": 2,
            "exclude_patterns": ["/logout"]}}
        r = await c.post(API, json=web_body, headers=ADMIN)
        wid = r.json()["source_id"]
        run = await sync(c, wid)
        by_key = await source_docs(wid)
        names = sorted(k.rsplit("/", 1)[-1] for k in by_key)
        check("crawl: 3 pages + the linked xlsx, all INDEXED", names == ["bang.xlsx", "index.html", "notes.html", "report.html"]
              and all(d["status"] == "INDEXED" for d in by_key.values()), {"names": names, "run": run["status"],
                                                                             "err": run["errors"][:2]})
        hits = (await c.get(f"{SRC}/_control")).json()["hits"]
        check("excluded and outside links are never requested", "/site/logout" not in hits, sorted(set(hits)))
        report = next((d["doc_id"] for k, d in by_key.items() if k.endswith("report.html")), None)
        cols = [t.columns for t in await table_records(report)]
        check("merged HTML headers are flattened", any("Số lượng / Thực hiện" in cs for cs in cols), cols)
        xlsx = next((d["doc_id"] for k, d in by_key.items() if k.endswith(".xlsx")), None)
        xcols = [t.columns for t in await table_records(xlsx)]
        check("the linked xlsx reaches the table store", any("Chỉ tiêu" in cs for cs in xcols), xcols)

        run = await sync(c, wid)  # the xlsx is generated again on this download: new bytes, same content
        check("re-crawl with nothing changed re-indexes nothing", run["unchanged"] == 4 and run["updated"] == 0,
              {k: run[k] for k in ("unchanged", "updated")})
        await control(c, "down")
        run = await sync(c, wid)
        check("source down: nothing is removed", run["deleted"] == 0 and len(await source_docs(wid)) == 4
              and run["status"] in ("partial", "failed"), run["status"])
        await control(c, "up")
        await control(c, "unlink_notes")
        run = await sync(c, wid)
        left = sorted(k.rsplit("/", 1)[-1] for k in await source_docs(wid))
        check("a page no longer linked is removed after a complete crawl", run["deleted"] == 1
              and "notes.html" not in left and run["updated"] == 1 and run["unchanged"] == 2,  # index.html lost a link
              {"left": left, "updated": run["updated"], "unchanged": run["unchanged"]})

        # ---------------------------------------------------------------- scheduler
        await c.patch(f"{API}/{wid}", json={"schedule_minutes": 1}, headers=ADMIN)
        deadline, scheduled = time.time() + 60, False
        while time.time() < deadline and not scheduled:
            await asyncio.sleep(3)
            scheduled = any(r["trigger"] == "schedule" for r in (await c.get(f"{API}/{wid}/runs", headers=ADMIN)).json()["items"])
        check("the worker's scheduler syncs a due source", scheduled)
        await c.patch(f"{API}/{wid}", json={"schedule_minutes": 0}, headers=ADMIN)

        # ---------------------------------------------------------------- removal
        for s, n in ((sid, 2), (wid, 3)):
            r = (await c.delete(f"{API}/{s}?purge=true", headers=ADMIN)).json()
            check(f"deleting the source with purge removes its {n} documents", r.get("documents_deleted") == n
                  and await source_docs(s) == {}, r)

    print(f"\n{sum(RESULTS)}/{len(RESULTS)} checks passed")
    sys.exit(0 if all(RESULTS) else 1)


asyncio.run(main())
