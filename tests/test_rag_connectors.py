"""
Connectors (solutions/rag/CONNECTORS.md): HTML conversion, the guarded HTTP client, the JSON API and web
connectors, and the sync use case (stable documents, change detection, removals only after complete reads,
lease). HTTP goes through httpx.MockTransport; nothing leaves the process.
"""

import asyncio
import json

import httpx
import pytest

from solutions.rag.application.components.table_query import Condition as C
from solutions.rag.application.components.table_query import TableQuery as Q
from solutions.rag.application.components.table_query import run_query
from solutions.rag.application.components.table_store import extract_tables
from solutions.rag.application.use_cases.source_sync_use_case import SourceSyncUseCase, stable_doc_id
from solutions.rag.config import rag_settings
from solutions.rag.infrastructure.connectors import build_connector
from solutions.rag.infrastructure.connectors.http import ConnectorError, SourceHttp, auth_headers
from solutions.rag.infrastructure.parsers.factory import parser_factory
from solutions.rag.infrastructure.parsers.html_parser import html_to_markdown
from solutions.rag.infrastructure.repositories.mongo_source_repo import InMemorySourceRepository
from solutions.rag.interfaces.api.sources_router import _validate


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(rag_settings, "connector_min_delay_seconds", 0.0)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- HTML
PAGE = """<html><head><title>Thống kê tháng</title><script>var x=1</script></head><body>
<nav><a href="/menu">Menu</a></nav>
<h1>Báo cáo</h1><p>Đoạn mở đầu.</p>
<ul><li>Mục một</li><li>Mục hai</li></ul>
<table><caption>BẢNG 1</caption>
<tr><th rowspan="2">Nguồn</th><th colspan="3">Sắc thái</th></tr>
<tr><th>Tích cực</th><th>Tiêu cực</th><th>Trung tính</th></tr>
<tr><td>Báo A</td><td></td><td></td><td>1</td></tr>
<tr><td>Báo B</td><td>1</td><td></td><td></td></tr>
</table>
<a href="page2.html#x">Trang 2</a> <a href="https://other.example/x">Ngoài</a>
<footer>© 2026</footer></body></html>"""


def test_html_becomes_markdown_with_real_tables_and_absolute_links():
    title, md, links = html_to_markdown(PAGE, "https://intra.local/bc/index.html")
    assert title == "Thống kê tháng"
    assert "# Báo cáo" in md and "- Mục một" in md and "var x" not in md and "Menu" not in md and "2026" not in md
    assert "**BẢNG 1**" in md and "| Nguồn | Sắc thái / Tích cực | Sắc thái / Tiêu cực | Sắc thái / Trung tính |" in md
    assert links == ["https://intra.local/bc/page2.html", "https://other.example/x"]
    tables = extract_tables(parser_factory.parse(PAGE.encode(), "p.html").pages, "d", "t")
    assert run_query(tables, Q([0], "count", [C("Trung tính", "nonempty")])).value == 1


# ---------------------------------------------------------------- guarded HTTP
def _src(**cfg):
    return {"source_id": "s1", "tenant_id": "t1", "name": "Nguồn", "type": cfg.pop("type", "json_api"),
            "config": {"allowed_hosts": ["api.local"], **cfg}, "auth": cfg.pop("auth", {"type": "none"})}


def test_http_refuses_hosts_and_redirects_outside_the_source():
    def handler(req):
        if req.url.path == "/redirect":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})
        return httpx.Response(200, json={})

    http = SourceHttp(_src(), httpx.MockTransport(handler))
    with pytest.raises(ConnectorError, match="not in config.allowed_hosts"):
        run(http.get("http://evil.local/x"))
    with pytest.raises(ConnectorError, match="not in config.allowed_hosts"):
        run(http.get("http://api.local/redirect"))
    with pytest.raises(ConnectorError, match="only http"):
        run(http.get("file:///etc/passwd"))


def test_secrets_come_only_from_prefixed_environment_variables(monkeypatch):
    monkeypatch.setenv("AIP_SOURCE_SECRET_FBX", "tok")
    monkeypatch.setenv("AIP_MINIO_PASSWORD", "do-not-leak")
    assert auth_headers({"type": "bearer", "token_env": "AIP_SOURCE_SECRET_FBX"}) == {"Authorization": "Bearer tok"}
    with pytest.raises(ConnectorError, match="must name an environment variable"):
        auth_headers({"type": "bearer", "token_env": "AIP_MINIO_PASSWORD"})
    with pytest.raises(ConnectorError, match="is not set"):
        auth_headers({"type": "header", "header": "X-API-Key", "token_env": "AIP_SOURCE_SECRET_MISSING"})


def test_http_retries_busy_responses_and_limits_size(monkeypatch):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if req.url.path == "/big":
            return httpx.Response(200, content=b"x" * 2000)
        return httpx.Response(503, headers={"retry-after": "0"}) if calls["n"] == 1 else httpx.Response(200, json={"ok": 1})

    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    http = SourceHttp(_src(max_response_bytes=1000), httpx.MockTransport(handler))
    assert run(http.get("http://api.local/data")).json() == {"ok": 1} and calls["n"] == 2
    with pytest.raises(ConnectorError, match="> limit 1000"):
        run(http.get("http://api.local/big"))


async def _no_sleep(*_a, **_k):
    return None


# ---------------------------------------------------------------- JSON API
POSTS = [
    {"id": f"p{i}", "day": f"2026-11-0{1 + i // 3}T08:00:00", "source": {"name": f"Báo {i % 2}"},
     "title": f"Bài {i}", "sentiment": s, "updated": f"2026-11-0{1 + i // 3}T09:0{i}"}
    for i, s in enumerate(["Tích cực", "Trung tính", "Trung tính", "Tiêu cực", "Trung tính", "Trung tính"])
]


def _api(posts):
    def handler(req):
        page = int(req.url.params.get("page", "1"))
        size = int(req.url.params.get("limit", "100"))
        since = req.url.params.get("since")
        rows = [p for p in posts if not since or p["updated"] > since]
        return httpx.Response(200, json={"data": {"items": rows[(page - 1) * size: page * size]}})
    return httpx.MockTransport(handler)


def _json_source(**over):
    cfg = {"url": "http://api.local/v1/posts", "allowed_hosts": ["api.local"], "records_path": "data.items",
           "id_field": "id", "partition_field": "day", "updated_field": "updated",
           "pagination": {"type": "page", "param": "page", "size_param": "limit", "size": 2},
           "columns": [{"field": "source.name", "label": "Nguồn"}, {"field": "title", "label": "Tiêu đề"},
                       {"field": "sentiment", "label": "Sắc thái"}]}
    cfg.update(over)
    return {"source_id": "srcdef_api", "tenant_id": "t1", "name": "Bản tin MXH", "type": "json_api", "config": cfg,
            "auth": {"type": "none"}, "schedule_minutes": 60, "enabled": True, "allowed_roles": ["*"]}


def test_json_api_reads_every_page_and_partitions_records():
    res = run(build_connector("json_api", _api(POSTS)).fetch(_json_source(), {}))
    assert len(res.items) == 6 and res.complete
    assert {it.partition for it in res.items} == {"2026-11-01", "2026-11-02"}
    assert res.cursor == {"since": "2026-11-02T09:05"}


def test_incremental_read_is_never_complete():
    src = _json_source(since_param="since")
    res = run(build_connector("json_api", _api(POSTS)).fetch(src, {"since": "2026-11-02T09:03"}))
    assert [it.key for it in res.items] == ["p4", "p5"] and not res.complete


# ---------------------------------------------------------------- web
SITE = {
    "/bc/index.html": ("text/html", PAGE),
    "/bc/page2.html": ("text/html", "<h1>Trang 2</h1><p>Nội dung</p><a href='/bc/bang.xlsx'>Bảng</a>"
                                    "<a href='/bc/logout'>Thoát</a><a href='/bc/deep.html'>Sâu</a>"),
    "/bc/deep.html": ("text/html", "<p>Quá sâu</p>"),
    "/bc/bang.xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "XLSX"),
}


def _site(extra=None):
    pages = dict(SITE, **(extra or {}))

    def handler(req):
        if req.url.path not in pages:
            return httpx.Response(404)
        ctype, body = pages[req.url.path]
        return httpx.Response(200, headers={"content-type": ctype}, content=body.encode())
    return httpx.MockTransport(handler)


def _web_source(**over):
    cfg = {"start_urls": ["https://intra.local/bc/index.html"], "allowed_hosts": ["intra.local"], "max_depth": 1,
           "exclude_patterns": ["/logout"]}
    cfg.update(over)
    return {"source_id": "srcdef_web", "tenant_id": "t1", "name": "Intranet", "type": "web", "config": cfg,
            "auth": {"type": "none"}, "schedule_minutes": 0, "enabled": True}


def test_web_crawl_stays_in_scope_and_takes_linked_files():
    res = run(build_connector("web", _site()).fetch(_web_source(), {}))
    keys = [it.key for it in res.items]
    assert keys == ["https://intra.local/bc/index.html", "https://intra.local/bc/page2.html"]  # depth 1
    deeper = run(build_connector("web", _site()).fetch(_web_source(max_depth=2), {}))
    assert {it.filename for it in deeper.items} >= {"bang.xlsx", "deep.html"}
    assert not any("logout" in it.key or "other.example" in it.key for it in deeper.items) and deeper.complete


def test_downloads_are_recognised_from_their_name_or_bytes_whatever_the_content_type():
    from solutions.rag.infrastructure.connectors.web import file_kind

    xlsx = _xlsx([["A"], [1]], 0)
    octet = "application/octet-stream"
    assert file_kind(octet, {"content-disposition": 'attachment; filename="Bao cao Q3.xlsx"'},
                     "https://intra.local/download?id=5", xlsx) == (".xlsx", "Bao cao Q3.xlsx")
    assert file_kind(octet, {"content-disposition": "attachment; filename*=UTF-8''B%C3%A1o%20c%C3%A1o.pdf"},
                     "https://intra.local/dl?id=6", b"%PDF-1.7 ...") == (".pdf", "Báo cáo.pdf")
    assert file_kind(octet, {}, "https://intra.local/dl?id=7", b"%PDF-1.4 ...")[0] == ".pdf"
    assert file_kind(octet, {}, "https://intra.local/dl?id=8", xlsx)[0] == ".xlsx"
    assert file_kind(octet, {}, "https://intra.local/dl?id=9", b"\x89PNG....") == ("", "")


def test_web_crawl_with_a_failed_page_is_not_complete():
    broken = _web_source(start_urls=["https://intra.local/bc/index.html", "https://intra.local/bc/missing.html"])
    res = run(build_connector("web", _site()).fetch(broken, {}))
    assert res.errors and not res.complete


# ---------------------------------------------------------------- sync use case
class Docs:
    def __init__(self):
        self.docs = {}

    async def get_document(self, doc_id):
        return dict(self.docs[doc_id]) if doc_id in self.docs else None

    async def create_document(self, rec):
        self.docs[rec["doc_id"]] = dict(rec)
        return rec["doc_id"]

    async def find_by_source(self, tenant_id, source_id):
        return [d for d in self.docs.values() if d.get("source_id") == source_id]


class Storage:
    def __init__(self):
        self.objects = {}

    def upload_bytes(self, bucket, object_name, data):
        self.objects[object_name] = data
        return f"s3://{bucket}/{object_name}"


def _sync(source, transport):
    repo, docs, storage, tables, indexed = InMemorySourceRepository(), Docs(), Storage(), {}, []

    async def ingest(rec):  # the real pipeline parses the stored file; tables are what matters here
        content = storage.objects[rec["s3_object_name"]]
        tables[rec["doc_id"]] = extract_tables(parser_factory.parse(content, rec["filename"]).pages, rec["doc_id"], rec["title"])
        docs.docs[rec["doc_id"]]["status"] = "INDEXED"
        indexed.append(rec["doc_id"])
        return {"status": "completed"}

    async def delete(doc_id, tenant_id):
        tables.pop(doc_id, None)
        return docs.docs.pop(doc_id, None) is not None

    uc = SourceSyncUseCase(repo, lambda t: build_connector(t, transport), docs, storage, ingest, delete)
    run(repo.create(source))
    return uc, repo, docs, tables, indexed


def test_records_become_one_table_document_per_partition_and_counts_are_exact():
    uc, repo, docs, tables, _ = _sync(_json_source(), _api(POSTS))
    r = run(uc.sync("srcdef_api"))
    assert r["status"] == "success" and r["created"] == 2 and r["fetched"] == 6
    day2 = tables[stable_doc_id("srcdef_api", "partition:2026-11-02")]
    assert run_query(day2, Q([0], "count", [C("Sắc thái", "=", "Trung tính")])).value == 2
    assert docs.docs[stable_doc_id("srcdef_api", "partition:2026-11-01")]["source_id"] == "srcdef_api"
    assert repo.sources["srcdef_api"]["next_sync_at"] > r["finished_at"]


def test_resync_reindexes_only_what_changed_and_removes_what_disappeared():
    posts = [dict(p) for p in POSTS]
    uc, repo, docs, tables, indexed = _sync(_json_source(), _api(posts))
    run(uc.sync("srcdef_api"))
    indexed.clear()
    assert run(uc.sync("srcdef_api"))["unchanged"] == 2 and not indexed  # nothing changed: nothing re-indexed
    posts[4]["sentiment"] = "Tích cực"  # one record of day 2 edited at the source
    r = run(uc.sync("srcdef_api"))
    assert r["updated"] == 1 and indexed == [stable_doc_id("srcdef_api", "partition:2026-11-02")]
    del posts[3:]  # day 2 disappears from the source
    r = run(uc.sync("srcdef_api"))
    assert r["deleted"] == 1 and stable_doc_id("srcdef_api", "partition:2026-11-02") not in docs.docs


def test_web_sync_removes_vanished_pages_only_after_a_complete_crawl():
    uc, _repo, docs, _tables, _ = _sync(_web_source(), _site())
    assert run(uc.sync("srcdef_web"))["created"] == 2
    page2 = stable_doc_id("srcdef_web", "https://intra.local/bc/page2.html")
    uc.connector_for = lambda t: build_connector(t, _site({"/bc/page2.html": ("text/html", "")}))  # page2 empty → skipped
    r = run(uc.sync("srcdef_web"))
    assert r["complete"] and r["deleted"] == 1 and page2 not in docs.docs
    uc.connector_for = lambda t: build_connector(t, httpx.MockTransport(lambda req: httpx.Response(500)))
    r = run(uc.sync("srcdef_web"))  # source down: nothing is removed
    assert r["status"] == "partial" and r["deleted"] == 0 and docs.docs


def _xlsx(rows, when):
    import io
    from datetime import datetime

    from openpyxl import Workbook

    wb = Workbook()
    wb.properties.created = wb.properties.modified = datetime(2026, 11, 1, 8, 0, when)
    for r in rows:
        wb.active.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_files_generated_on_each_download_are_not_reindexed_unless_their_content_changes():
    from solutions.rag.application.use_cases.source_sync_use_case import content_fingerprint

    a, b = _xlsx([["Đơn vị", "Đạt"], ["P1", 9]], 1), _xlsx([["Đơn vị", "Đạt"], ["P1", 9]], 2)
    assert a != b and content_fingerprint("x.xlsx", a) == content_fingerprint("x.xlsx", b)
    assert content_fingerprint("x.xlsx", _xlsx([["Đơn vị", "Đạt"], ["P1", 8]], 1)) != content_fingerprint("x.xlsx", a)
    pdf = b"%PDF-1.7 BT (Noi dung) ET /CreationDate (D:20261101) /ModDate (D:20261101) /ID [<ab><cd>]"
    later = pdf.replace(b"20261101", b"20261107").replace(b"<ab>", b"<ef>")
    assert content_fingerprint("r.pdf", pdf) == content_fingerprint("r.pdf", later)
    assert content_fingerprint("r.pdf", pdf.replace(b"Noi dung", b"Noi dung moi")) != content_fingerprint("r.pdf", pdf)

    version = {"n": 1}

    def handler(req):
        if req.url.path.endswith(".xlsx"):
            return httpx.Response(200, headers={"content-type": "application/octet-stream"},
                                  content=_xlsx([["Đơn vị", "Đạt"], ["P1", 9]], version["n"]))
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<a href='/f/bang.xlsx'>x</a><p>Trang</p>")

    src = _web_source(start_urls=["https://intra.local/f/index.html"], include_prefixes=["https://intra.local/f/"])
    uc, _repo, _docs, _tables, indexed = _sync(src, httpx.MockTransport(handler))
    run(uc.sync("srcdef_web"))
    indexed.clear()
    version["n"] = 2  # the export is produced again: new bytes, same content
    r = run(uc.sync("srcdef_web"))
    assert r["unchanged"] == 2 and not indexed, (r, indexed)


def test_a_source_is_never_synced_twice_at_once():
    uc, repo, *_ = _sync(_json_source(), _api(POSTS))
    run(repo.acquire("srcdef_api", "other-worker", 1e12, 60))
    assert run(uc.sync("srcdef_api"))["status"] == "busy"


def test_source_configuration_is_validated():
    ok = _validate("json_api", {"url": "http://api.local/x", "allowed_hosts": ["api.local"], "id_field": "id"},
                   {"type": "bearer", "token_env": "AIP_SOURCE_SECRET_X"})
    assert ok == []
    bad = _validate("web", {"start_urls": ["http://other.local/"], "allowed_hosts": ["intra.local"]},
                    {"type": "bearer", "token_env": "MONGO_URI", "token": "plain-secret"})
    assert any("allowed_hosts" in p for p in bad) and any("token_env" in p for p in bad)
    assert any("not accepted" in p for p in bad)
    assert json.dumps(bad)  # serialisable (returned as the 422 detail)
    no_id = {"url": "http://api.local/x", "allowed_hosts": ["api.local"]}
    assert _validate("json_api", no_id, {}) == ["config.id_field is required"]
    assert _validate("json_api", no_id, {}, preview=True) == []  # the trial read is how the id field is found


# ---------------------------------------------------------------- trial read for the configuration screen
def test_preview_of_a_json_api_finds_the_record_list_and_checks_the_id():
    from solutions.rag.infrastructure.connectors.preview import preview_source

    src = _json_source(records_path="", id_field="")
    r = run(preview_source(src, _api(POSTS)))
    assert not r["ok"] and r["list_paths"] == [{"path": "data.items", "count": 2}]  # page size 2
    src = _json_source(pagination={"type": "none"})
    r = run(preview_source(src, _api(POSTS)))
    assert r["ok"] and r["records"] == 6 and r["id_check"] == {"missing": 0, "duplicates": 0}
    assert {"path": "source.name", "sample": "Báo 0"} in r["fields"]
    assert [p["partition"] for p in r["partitions"]] == ["2026-11-01", "2026-11-02"]
    assert "| Nguồn | Tiêu đề | Sắc thái |" in r["sample_markdown"]
    dup = run(preview_source(_json_source(pagination={"type": "none"}, id_field="sentiment"), _api(POSTS)))
    assert dup["id_check"]["duplicates"] == 3  # 6 records, 3 distinct sentiments: not an id


def test_preview_of_a_website_lists_pages_and_their_tables_and_reports_failures():
    from solutions.rag.infrastructure.connectors.preview import preview_source

    r = run(preview_source(_web_source(), _site()))
    assert r["ok"] and [it["url"].rsplit("/", 1)[-1] for it in r["items"]] == ["index.html", "page2.html"]
    assert r["items"][0]["tables"] == 1 and "Sắc thái / Tiêu cực" in r["sample"]["markdown"]
    down = run(preview_source(_web_source(), httpx.MockTransport(lambda req: httpx.Response(500))))
    assert not down["ok"] and "HTTP 500" in down["error"]
    outside = run(preview_source(_web_source(start_urls=["https://elsewhere.local/"]), _site()))
    assert not outside["ok"] and "allowed_hosts" in outside["error"]


# ---------------------------------------------------------------- shapes met on a real collector API (fbx)
FBX_POSTS = [
    {"id": f"p{i}", "published_at": t, "author": {"display_name": f"Trang {i % 2}"}, "body": f"Nội dung {i}"}
    for i, t in enumerate(["2026-11-01T02:00:00+00:00", "2026-11-01T10:00:00+00:00", "2026-11-01T18:30:00+00:00",
                           "2026-11-02T23:43:34+00:00", "2026-11-02T05:00:00.945000+00:00"])
]


def _fbx(posts, page=2):
    """A bare list per page; the next page's cursor in the x-next-cursor response header."""
    def handler(req):
        start = int(req.url.params.get("cursor") or 0)
        rows = posts[start:start + page]
        headers = {"x-next-cursor": str(start + page)} if start + page < len(posts) else {}
        return httpx.Response(200, json=rows, headers=headers)
    return httpx.MockTransport(handler)


def _fbx_source(**over):
    cfg = {"url": "http://fbx.local/v1/posts", "allowed_hosts": ["fbx.local"], "records_path": "", "id_field": "id",
           "partition_field": "published_at",
           "pagination": {"type": "cursor", "cursor_param": "cursor", "cursor_path": "header:x-next-cursor"},
           "columns": [{"field": "published_at", "label": "Thời gian"}, {"field": "author.display_name", "label": "Trang"}]}
    cfg.update(over)
    return {"source_id": "srcdef_fbx", "tenant_id": "t1", "name": "Bài đăng", "type": "json_api", "config": cfg,
            "auth": {"type": "none"}, "schedule_minutes": 0, "enabled": True}


def test_cursor_sent_in_a_response_header_reads_every_page():
    res = run(build_connector("json_api", _fbx(FBX_POSTS)).fetch(_fbx_source(), {}))
    assert [it.key for it in res.items] == ["p0", "p1", "p2", "p3", "p4"] and res.complete


def test_days_are_the_users_days_not_utc_days():
    from solutions.rag.domain.sources import resolve_timezone

    assert resolve_timezone("+07:00").utcoffset(None).total_seconds() == 7 * 3600
    assert resolve_timezone("UTC+7").utcoffset(None).total_seconds() == 7 * 3600
    assert resolve_timezone("not a zone") is None
    res = run(build_connector("json_api", _fbx(FBX_POSTS)).fetch(_fbx_source(timezone="+07:00"), {}))
    days = {it.key: it.partition for it in res.items}
    # 18:30 UTC on the 1st is 01:30 on the 2nd in Vietnam; 23:43 UTC on the 2nd is 06:43 on the 3rd
    assert days == {"p0": "2026-11-01", "p1": "2026-11-01", "p2": "2026-11-02", "p3": "2026-11-03", "p4": "2026-11-02"}
    utc = run(build_connector("json_api", _fbx(FBX_POSTS)).fetch(_fbx_source(timezone="UTC"), {}))
    assert {it.key: it.partition for it in utc.items}["p3"] == "2026-11-02"


def test_times_in_documents_are_shown_in_the_users_zone():
    from solutions.rag.application.use_cases.source_sync_use_case import render_records

    cols = [{"field": "published_at", "label": "Thời gian"}, {"field": "body", "label": "Nội dung"}]
    md = render_records("Bài đăng – 2026-11-03", [FBX_POSTS[3]], cols, "+07:00")
    assert "| 2026-11-03 06:43 | Nội dung 3 |" in md and "múi giờ +07:00" in md
    plain = render_records("x", [{"body": "Nội dung 3"}], [{"field": "body"}], "+07:00")
    assert "| Nội dung 3 |" in plain and "múi giờ" not in plain


def test_preview_points_at_paging_headers():
    from solutions.rag.infrastructure.connectors.preview import preview_source

    r = run(preview_source(_fbx_source(pagination={"type": "none"}), _fbx(FBX_POSTS)))
    assert r["ok"] and r["list_paths"] == [{"path": "", "count": 2}]
    assert r["paging_headers"] == [{"header": "x-next-cursor", "value": "2"}]
