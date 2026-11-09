"""
Console URLs: /projects/{project-slug}/services/{service-slug}[/view...].

One route table (frontend/shared/api_detail_routes.json) drives the gateway and vite; the browser side
(frontend/staff/project_routes.js) must agree with it and with the gateway's project slugs. Links of the
former scheme (/project/{uuid}/apis/{uuid}) answer 301 to the new one.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import web
from src.api.project_slugs import assign_slugs, new_project_slug, slugify

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
ROUTES = json.loads((FRONTEND / "shared" / "api_detail_routes.json").read_text(encoding="utf-8"))
ROUTES_JS = FRONTEND / "staff" / "project_routes.js"
RAG = "rag-chat-enterprise-kb"
LLM_UUID = "efb24a03-059d-440c-bd35-0b5b3a776983"


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(web.router)
    return TestClient(app)


# ---------------------------------------------------------------- slugs
def test_project_slugs_are_readable_unique_and_stable():
    assert slugify("Khảo thí Đắk Lắk") == "khao-thi-dak-lak"
    assert slugify("  AI / Lớp 10 — Đề cương!! ") == "ai-lop-10-de-cuong"
    assert slugify("!!!") == "project"
    projects = [
        {"project_id": "b", "project_name": "Dự án A", "created_at": "2026-02-01"},
        {"project_id": "a", "project_name": "Dự án A", "created_at": "2026-01-01"},
        {"project_id": "c", "project_name": "Shared", "created_at": "2026-03-01"},  # reserved word
        {"project_id": "d", "project_name": "Kept", "slug": "custom", "created_at": "2026-04-01"},
    ]
    by_id = {p["project_id"]: p["slug"] for p in assign_slugs([dict(p) for p in projects])}
    assert by_id == {"a": "du-an-a", "b": "du-an-a-2", "c": "shared-2", "d": "custom"}  # oldest keeps the plain slug
    assert {p["project_id"]: p["slug"] for p in assign_slugs([dict(p) for p in reversed(projects)])} == by_id
    assert new_project_slug("Dự án A", projects) == "du-an-a-3"


# ---------------------------------------------------------------- gateway routes
@pytest.mark.parametrize("path, page", [
    ("/projects/du-an-a", "dashboard"),
    ("/projects/du-an-a/dashboard", "dashboard"),
    ("/projects", "dashboard"),
    ("/projects/shared/services", "services"),
])
def test_console_pages(client, path, page):
    res = client.get(path)
    expected = (FRONTEND / ROUTES["pages"][page]).read_text(encoding="utf-8")
    assert res.status_code == 200 and res.text == expected


def test_a_service_and_its_views_serve_the_service_page(client):
    rag_page = (FRONTEND / "solutions/rag/index.html").read_text(encoding="utf-8")
    for path in ("/projects/shared/services/rag-chatbot", "/projects/du-an-a/services/rag-chatbot/chat/sess_1",
                 "/projects/du-an-a/services/rag-chatbot/knowledge/qa", "/services/rag-chatbot"):
        res = client.get(path)
        assert res.status_code == 200 and res.text == rag_page, path
    assert "/staff/project_routes.js" in rag_page  # the page resolves the project before its scripts run


def test_a_service_not_live_yet_answers_with_the_in_development_page(client):
    res = client.get("/projects/shared/services/translation")
    assert res.status_code == 200
    assert res.text == (FRONTEND / ROUTES["pages"]["underDevelopment"]).read_text(encoding="utf-8")


def test_unknown_service_is_404(client):
    assert client.get("/projects/shared/services/nope").status_code == 404


@pytest.mark.parametrize("old, new", [
    (f"/project/global/apis/{RAG}", "/projects/shared/services/rag-chatbot"),
    (f"/staff/project/f40b6a70-ea64-4d01-90dc-53a2d7a81395/apis/{LLM_UUID}",
     "/projects/f40b6a70-ea64-4d01-90dc-53a2d7a81395/services/llm-chat"),
    ("/project/global/apis", "/projects/shared/services"),
    ("/project/global/dashboard", "/projects/shared"),
    (f"/projects/du-an-a/services/{LLM_UUID}/x", "/projects/du-an-a/services/llm-chat/x"),
    ("/staff/service-llm", "/services/llm-chat"),
    ("/rag", "/services/rag-chatbot"),
])
def test_former_links_redirect_permanently(client, old, new):
    res = client.get(old, follow_redirects=False)
    assert res.status_code == 301 and res.headers["location"] == new


# ---------------------------------------------------------------- browser side agrees with the table
def _js_object(name: str) -> dict:
    source = ROUTES_JS.read_text(encoding="utf-8")
    body = re.search(rf"const {name} = \{{(.*?)\n    \}};", source, re.S).group(1)
    return dict(re.findall(r"'([^']+)':\s*'([^']+)'", body))


def test_browser_service_table_matches_the_route_table():
    services = ROUTES["services"]
    assert _js_object("SERVICES") == {slug: s["legacyIds"][0] for slug, s in services.items()}
    live = set(re.search(r"LIVE_SERVICES = new Set\(\[(.*?)\]\)", ROUTES_JS.read_text(encoding="utf-8")).group(1)
               .replace("'", "").replace(" ", "").split(","))
    assert live == {slug for slug, s in services.items() if s["live"]}
    for copy in ("shared/project_routes.js", "shared/applications_nav.js", "shared/staff_layout.js"):
        twin = "staff/" + copy.split("/")[1]
        assert (FRONTEND / copy).read_bytes() == (FRONTEND / twin).read_bytes(), copy


NODE_HARNESS = r"""
const fs = require('fs');
const store = {};
const localStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); },
                       removeItem: k => { delete store[k]; } };
const listeners = {};
const location = { pathname: '', search: '', hash: '', href: '' };
const pushed = [];
const history = { state: null,
  pushState(s, t, url) { pushed.push(url); location.pathname = url.split('?')[0]; },
  replaceState(s, t, url) { location.pathname = url.split('?')[0]; } };
const window = { localStorage, location, history, addEventListener: (n, f) => { (listeners[n] = listeners[n] || []).push(f); } };
global.localStorage = localStorage;
const run = (path) => { location.pathname = path; delete window.AipRoutes;
  new Function('window', 'localStorage', fs.readFileSync(process.argv[2], 'utf8'))(window, localStorage); return window.AipRoutes; };

localStorage.setItem('aip_projects', JSON.stringify([
  { project_id: 'p1', project_name: 'Khảo thí Đắk Lắk', created_at: '2026-01-01' },
  { project_id: 'p2', project_name: 'Dự án B', slug: 'du-an-b', created_at: '2026-02-01' }]));
const out = {};
let R = run('/projects/khao-thi-dak-lak/services/rag-chatbot/chat/sess_1');
out.activeFromSlug = [localStorage.getItem('aip_active_project_id'), location.pathname];
R = run('/projects/p2/services/efb24a03-059d-440c-bd35-0b5b3a776983');
out.idToSlug = [localStorage.getItem('aip_active_project_id'), location.pathname];
R = run('/services/rag-chatbot/knowledge/qa');
out.floating = location.pathname;
R = run('/projects/global/services/rag-chatbot');
out.shared = [localStorage.getItem('aip_active_project_id'), location.pathname];
R = run('/projects/du-an-b/services/rag-chatbot/chat/sess_9');
listeners['aip-project-changed'].forEach(f => f({ detail: { project_id: 'p1', project_name: 'Khảo thí Đắk Lắk' } }));
out.switched = location.pathname;
R.setView(['knowledge', 'inbox']);
out.view = [location.pathname, R.currentView()];
out.samePage = R.isSamePage({ pathname: '/projects/khao-thi-dak-lak/services/rag-chatbot/chat/x' });
out.otherPage = R.isSamePage({ pathname: '/projects/du-an-b/services/rag-chatbot' });
out.href = R.serviceHref('3a72d1f9-46c8-472e-8395-cb091a136701');
out.slugify = R.slugify('  AI / Lớp 10 — Đề cương!! ');
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_browser_routes_follow_the_url(tmp_path):
    harness = tmp_path / "harness.js"
    harness.write_text(NODE_HARNESS, encoding="utf-8")
    out = json.loads(subprocess.run(["node", str(harness), str(ROUTES_JS)], capture_output=True, text=True,
                                    check=True, timeout=30).stdout)
    assert out["activeFromSlug"] == ["p1", "/projects/khao-thi-dak-lak/services/rag-chatbot/chat/sess_1"]
    assert out["idToSlug"] == ["p2", "/projects/du-an-b/services/llm-chat"]  # canonical form replaces ids
    assert out["floating"] == "/projects/du-an-b/services/rag-chatbot/knowledge/qa"  # the active project
    assert out["shared"] == ["global", "/projects/shared/services/rag-chatbot"]
    assert out["switched"] == "/projects/khao-thi-dak-lak/services/rag-chatbot"  # a conversation belongs to its project
    assert out["view"] == ["/projects/khao-thi-dak-lak/services/rag-chatbot/knowledge/inbox", ["knowledge", "inbox"]]
    assert out["samePage"] is True and out["otherPage"] is False
    assert out["href"] == "/projects/khao-thi-dak-lak/services/speech-to-text"
    assert out["slugify"] == slugify("  AI / Lớp 10 — Đề cương!! ")


# ---------------------------------------------------------------- clean extensionless URLs
@pytest.mark.parametrize("path", [
    "/dashboard",
    "/keys",
    "/apis",
    "/report",
    "/payment",
    "/profile",
    "/auth/login",
    "/auth/signup",
    "/auth/register",
    "/status",
])
def test_clean_urls_serve_ok(client, path):
    res = client.get(path)
    assert res.status_code == 200


@pytest.mark.parametrize("html_path, target_path", [
    ("/dashboard.html", "/dashboard"),
    ("/projects.html", "/projects"),
    ("/projects/index.html", "/projects"),
    ("/keys.html", "/keys"),
    ("/apis.html", "/apis"),
    ("/report.html", "/report"),
    ("/payment.html", "/payment"),
    ("/profile.html", "/profile"),
    ("/auth/login.html", "/auth/login"),
    ("/login.html", "/auth/login"),
    ("/auth/signup.html", "/auth/signup"),
    ("/auth/register.html", "/auth/signup"),
    ("/signup.html", "/auth/signup"),
    ("/status.html", "/status"),
    ("/staff/keys.html", "/staff/keys"),
    ("/admin/users.html", "/admin/users"),
])
def test_html_urls_redirect_to_clean_urls(client, html_path, target_path):
    res = client.get(html_path, follow_redirects=False)
    assert res.status_code == 301
    assert res.headers["location"] == target_path
