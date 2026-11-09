import json
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from common.repositories.endpoint_repository import endpoint_repository

router = APIRouter(include_in_schema=False)

# Resolve candidates for frontend directory across local and container/cloud environments
_repository_root = Path(__file__).resolve().parents[4]
_candidates = [
    _repository_root / "frontend",
    Path.cwd() / "frontend",
    Path("/app/frontend"),
    Path("/opt/render/project/src/frontend"),
    _repository_root / "apps" / "frontend",
    Path.cwd() / "apps" / "frontend",
]
FRONTEND_DIR: Path = next(
    (directory for directory in _candidates if (directory / "staff" / "api_detail_routes.json").is_file() or (directory / "shared" / "api_detail_routes.json").is_file()),
    _candidates[0],
)
STAFF_DIR: Path = FRONTEND_DIR / "staff"
ADMIN_DIR: Path = FRONTEND_DIR / "admin"
AUTH_DIR: Path = FRONTEND_DIR / "auth"
SOLUTIONS_DIR: Path = FRONTEND_DIR / "solutions"
API_ROUTE_CONFIG = json.loads(
    (STAFF_DIR / "api_detail_routes.json").read_text(encoding="utf-8")
)
SERVICE_LEGACY_TO_UUID = API_ROUTE_CONFIG["legacyAliases"]


def _resolve_page(base_dir: Path, page_name: str) -> Optional[Path]:
    """Resolve page name with or without .html, supporting kebab-case and snake_case."""
    # Direct match
    p = base_dir / page_name
    if p.is_file():
        return p
    # Try .html extension
    p_html = base_dir / f"{page_name}.html"
    if p_html.is_file():
        return p_html
    # Try replacing '-' with '_'
    norm_name = page_name.replace("-", "_")
    p_norm = base_dir / f"{norm_name}.html"
    if p_norm.is_file():
        return p_norm
    return None


# --- 1. PROJECT CONSOLE ROUTES ---
# Canonical URLs (one table, frontend/shared/api_detail_routes.json, also read by vite in dev):
#   /projects/{project}                          project dashboard
#   /projects/{project}/services                 service catalog
#   /projects/{project}/services/{service}/...   service page; what follows the service is a view of the
#                                                page (e.g. rag-chatbot/chat/{session_id}, /knowledge/qa)
#   /services/{service}/...                      same page in the viewer's current project (the page
#                                                rewrites the URL to the canonical one)
# {project} is the project's slug ("shared" for the shared knowledge scope); the page checks it against
# the viewer's projects. Links of the former scheme (/project/{uuid}/apis/{uuid}) answer 301.

ROUTE_PAGES = API_ROUTE_CONFIG["pages"]
SERVICES = API_ROUTE_CONFIG["services"]
SHARED_PROJECT = API_ROUTE_CONFIG["sharedProject"]
SERVICE_BY_LEGACY_ID = {
    legacy.lower(): slug for slug, service in SERVICES.items() for legacy in service.get("legacyIds", [])
}


def _service_slug(value: str) -> Optional[str]:
    value = (value or "").lower()
    return value if value in SERVICES else SERVICE_BY_LEGACY_ID.get(value)


def _project_segment(project: str) -> str:
    return SHARED_PROJECT["slug"] if project.lower() == SHARED_PROJECT["id"] else project


def _frontend_page(relative: str) -> FileResponse:
    page = (FRONTEND_DIR / relative).resolve()
    if FRONTEND_DIR.resolve() in page.parents and page.is_file():
        return FileResponse(page, headers={"Cache-Control": "no-cache"})
    raise HTTPException(status_code=404, detail="Page not found")


def _service_response(project: Optional[str], service: str, view: str = "", query: str = ""):
    slug = _service_slug(service)
    if slug is None:
        raise HTTPException(status_code=404, detail="Service not found")
    if slug != service:  # a former id or different casing: one canonical URL per page
        base = f"/projects/{_project_segment(project)}" if project else ""
        target = f"{base}/services/{slug}" + (f"/{view.strip('/')}" if view.strip("/") else "")
        return RedirectResponse(url=target + (f"?{query}" if query else ""), status_code=301)
    entry = SERVICES[slug]
    return _frontend_page(entry["page"] if entry.get("live") else ROUTE_PAGES["underDevelopment"])


@router.get("/projects.html", include_in_schema=False)
@router.get("/projects/index.html", include_in_schema=False)
async def redirect_projects_html():
    return RedirectResponse(url="/projects", status_code=301)


@router.get("/projects", include_in_schema=False)
@router.get("/projects/", include_in_schema=False)
@router.get("/projects/{project}", include_in_schema=False)
@router.get("/projects/{project}/", include_in_schema=False)
@router.get("/projects/{project}/dashboard", include_in_schema=False)
async def serve_project_dashboard(project: str = ""):
    return _frontend_page(ROUTE_PAGES["dashboard"])


@router.get("/dashboard", include_in_schema=False)
@router.get("/dashboard/", include_in_schema=False)
@router.get("/console/dashboard", include_in_schema=False)
async def serve_dashboard():
    for cand in [FRONTEND_DIR / "console" / "dashboard.html", STAFF_DIR / "dashboard.html"]:
        if cand.is_file():
            return FileResponse(cand)
    return _frontend_page(ROUTE_PAGES["dashboard"])


@router.get("/dashboard.html", include_in_schema=False)
@router.get("/console/dashboard.html", include_in_schema=False)
async def redirect_dashboard_html():
    return RedirectResponse(url="/dashboard", status_code=301)


@router.get("/keys", include_in_schema=False)
@router.get("/keys/", include_in_schema=False)
@router.get("/console/keys", include_in_schema=False)
async def serve_keys():
    for cand in [FRONTEND_DIR / "console" / "keys.html", STAFF_DIR / "keys.html"]:
        if cand.is_file():
            return FileResponse(cand)
    raise HTTPException(status_code=404, detail="Keys page not found")


@router.get("/keys.html", include_in_schema=False)
@router.get("/console/keys.html", include_in_schema=False)
async def redirect_keys_html():
    return RedirectResponse(url="/keys", status_code=301)


@router.get("/apis", include_in_schema=False)
@router.get("/apis/", include_in_schema=False)
@router.get("/console/apis", include_in_schema=False)
async def serve_apis():
    for cand in [FRONTEND_DIR / "console" / "apis.html", STAFF_DIR / "apis.html"]:
        if cand.is_file():
            return FileResponse(cand)
    raise HTTPException(status_code=404, detail="APIs page not found")


@router.get("/apis.html", include_in_schema=False)
@router.get("/console/apis.html", include_in_schema=False)
async def redirect_apis_html():
    return RedirectResponse(url="/apis", status_code=301)


@router.get("/report", include_in_schema=False)
@router.get("/report/", include_in_schema=False)
@router.get("/console/report", include_in_schema=False)
async def serve_report():
    for cand in [FRONTEND_DIR / "console" / "report.html", STAFF_DIR / "report.html"]:
        if cand.is_file():
            return FileResponse(cand)
    raise HTTPException(status_code=404, detail="Report page not found")


@router.get("/report.html", include_in_schema=False)
@router.get("/console/report.html", include_in_schema=False)
async def redirect_report_html():
    return RedirectResponse(url="/report", status_code=301)


@router.get("/payment", include_in_schema=False)
@router.get("/payment/", include_in_schema=False)
@router.get("/console/payment", include_in_schema=False)
async def serve_payment():
    for cand in [FRONTEND_DIR / "console" / "payment.html", STAFF_DIR / "payment.html"]:
        if cand.is_file():
            return FileResponse(cand)
    raise HTTPException(status_code=404, detail="Payment page not found")


@router.get("/payment.html", include_in_schema=False)
@router.get("/console/payment.html", include_in_schema=False)
async def redirect_payment_html():
    return RedirectResponse(url="/payment", status_code=301)


@router.get("/projects/{project}/services", include_in_schema=False)
@router.get("/projects/{project}/services/", include_in_schema=False)
async def serve_project_services(project: str):
    return _frontend_page(ROUTE_PAGES["services"])


@router.get("/projects/{project}/services/{service}", include_in_schema=False)
@router.get("/projects/{project}/services/{service}/{view:path}", include_in_schema=False)
async def serve_project_service(request: Request, project: str, service: str, view: str = ""):
    return _service_response(project, service, view, request.url.query)


@router.get("/services/{service}", include_in_schema=False)
@router.get("/services/{service}/{view:path}", include_in_schema=False)
async def serve_current_project_service(request: Request, service: str, view: str = ""):
    return _service_response(None, service, view, request.url.query)


# Former scheme: permanent redirects keep bookmarks and shared links working.
@router.get("/project/{project_id}/apis/{api_id}", include_in_schema=False)
@router.get("/project/{project_id}/apis/{api_id}/", include_in_schema=False)
@router.get("/staff/project/{project_id}/apis/{api_id}", include_in_schema=False)
@router.get("/staff/project/{project_id}/apis/{api_id}/", include_in_schema=False)
async def redirect_legacy_project_api(project_id: str, api_id: str):
    slug = _service_slug(api_id)
    if slug is None:
        raise HTTPException(status_code=404, detail="API detail page not found")
    return RedirectResponse(url=f"/projects/{_project_segment(project_id)}/services/{slug}", status_code=301)


@router.get("/project/{project_id}/apis", include_in_schema=False)
@router.get("/project/{project_id}/apis/", include_in_schema=False)
@router.get("/staff/project/{project_id}/apis", include_in_schema=False)
@router.get("/staff/project/{project_id}/apis/", include_in_schema=False)
async def redirect_legacy_project_apis(project_id: str):
    return RedirectResponse(url=f"/projects/{_project_segment(project_id)}/services", status_code=301)


@router.get("/project/{project_id}", include_in_schema=False)
@router.get("/project/{project_id}/", include_in_schema=False)
@router.get("/project/{project_id}/dashboard", include_in_schema=False)
@router.get("/staff/project/{project_id}", include_in_schema=False)
@router.get("/staff/project/{project_id}/dashboard", include_in_schema=False)
async def redirect_legacy_project_dashboard(project_id: str):
    return RedirectResponse(url=f"/projects/{_project_segment(project_id)}", status_code=301)


# --- 2. STAFF PORTAL ROOT & CONVENIENCE ROUTES ---

@router.get("/staff", include_in_schema=False)
@router.get("/staff/", include_in_schema=False)
@router.get("/portal", include_in_schema=False)
async def serve_staff_root():
    dash = STAFF_DIR / "dashboard.html"
    if dash.exists():
        return FileResponse(dash)
    return RedirectResponse(url="/apis")


@router.get("/staff/apis", include_in_schema=False)
@router.get("/staff/apis/", include_in_schema=False)
async def serve_staff_apis(request: Request):
    accept = request.headers.get("accept", "")
    # If explicitly an API client asking only for JSON
    if "application/json" in accept and "text/html" not in accept:
        endpoints = await endpoint_repository.list_endpoints()
        return JSONResponse(content={"apis": jsonable_encoder(endpoints)})

    apis_html = STAFF_DIR / "apis.html"
    if apis_html.exists():
        return FileResponse(apis_html)
    raise HTTPException(status_code=404, detail="Staff APIs page not found")


@router.get("/staff/{page:path}", include_in_schema=False)
async def serve_staff_page(page: str, request: Request):
    clean_page = page.strip("/").lower()
    if clean_page.endswith(".html"):
        clean_name = clean_page[:-5]
        query = request.url.query
        target = f"/staff/{clean_name}" + (f"?{query}" if query else "")
        return RedirectResponse(url=target, status_code=301)

    # Check if page is legacy named service (e.g. service-llm, service-stt)
    # Redirect cleanly to /services/{service}
    clean_without_ext = clean_page.replace(".html", "")
    if clean_without_ext in SERVICE_LEGACY_TO_UUID:
        slug = _service_slug(SERVICE_LEGACY_TO_UUID[clean_without_ext])
        return RedirectResponse(url=f"/services/{slug}", status_code=301)

    found = _resolve_page(STAFF_DIR, page)
    if found:
        return FileResponse(found)
    raise HTTPException(status_code=404, detail=f"Staff page '{page}' not found")


@router.get("/console/{page:path}", include_in_schema=False)
async def serve_console_page(page: str, request: Request):
    clean_page = page.strip("/").lower()
    if clean_page.endswith(".html"):
        clean_name = clean_page[:-5]
        query = request.url.query
        target = f"/{clean_name}" + (f"?{query}" if query else "")
        return RedirectResponse(url=target, status_code=301)
    if clean_page in ("dashboard", "keys", "apis", "report", "payment", "profile"):
        query = request.url.query
        target = f"/{clean_page}" + (f"?{query}" if query else "")
        return RedirectResponse(url=target, status_code=301)
    found = _resolve_page(FRONTEND_DIR / "console", page)
    if found:
        return FileResponse(found)
    raise HTTPException(status_code=404, detail=f"Console page '{page}' not found")


# --- 3. ADMIN CONSOLE ROUTES ---

@router.get("/admin", include_in_schema=False)
@router.get("/admin/", include_in_schema=False)
async def serve_admin_root():
    dash = ADMIN_DIR / "dashboard.html"
    if dash.exists():
        return FileResponse(dash)
    raise HTTPException(status_code=404, detail="Admin dashboard not found")


@router.get("/admin/{page:path}", include_in_schema=False)
async def serve_admin_page(page: str, request: Request):
    # Safety guard: Skip /admin/v1 API routes
    if page.startswith("v1") or page.startswith("v1/"):
        raise HTTPException(status_code=404, detail="Not Found")
    clean_page = page.strip("/").lower()
    if clean_page.endswith(".html"):
        clean_name = clean_page[:-5]
        query = request.url.query
        target = f"/admin/{clean_name}" + (f"?{query}" if query else "")
        return RedirectResponse(url=target, status_code=301)
    found = _resolve_page(ADMIN_DIR, page)
    if found:
        return FileResponse(found)
    raise HTTPException(status_code=404, detail=f"Admin page '{page}' not found")


# --- 4. AUTH & PUBLIC STATUS PAGES ---

@router.get("/login", include_in_schema=False)
@router.get("/auth/login", include_in_schema=False)
async def serve_login():
    login_html = AUTH_DIR / "login.html"
    if login_html.exists():
        return FileResponse(login_html)
    raise HTTPException(status_code=404, detail="Login page not found")


@router.get("/login.html", include_in_schema=False)
@router.get("/auth/login.html", include_in_schema=False)
async def redirect_login_html(request: Request):
    query = request.url.query
    target = "/auth/login" + (f"?{query}" if query else "")
    return RedirectResponse(url=target, status_code=301)


@router.get("/signup", include_in_schema=False)
@router.get("/auth/signup", include_in_schema=False)
@router.get("/register", include_in_schema=False)
@router.get("/auth/register", include_in_schema=False)
async def serve_signup():
    signup_html = AUTH_DIR / "signup.html"
    if signup_html.exists():
        return FileResponse(signup_html)
    raise HTTPException(status_code=404, detail="Signup page not found")


@router.get("/signup.html", include_in_schema=False)
@router.get("/auth/signup.html", include_in_schema=False)
@router.get("/register.html", include_in_schema=False)
@router.get("/auth/register.html", include_in_schema=False)
async def redirect_signup_html(request: Request):
    query = request.url.query
    target = "/auth/signup" + (f"?{query}" if query else "")
    return RedirectResponse(url=target, status_code=301)


@router.get("/status", include_in_schema=False)
@router.get("/status/", include_in_schema=False)
async def serve_status(request: Request):
    status_html = FRONTEND_DIR / "status.html"
    if status_html.exists():
        return FileResponse(status_html)
    raise HTTPException(status_code=404, detail="Status page not found")


@router.get("/status.html", include_in_schema=False)
async def redirect_status_html():
    return RedirectResponse(url="/status", status_code=301)


@router.get("/profile", include_in_schema=False)
@router.get("/profile/", include_in_schema=False)
@router.get("/console/profile", include_in_schema=False)
@router.get("/user/profile", include_in_schema=False)
async def serve_profile():
    for cand in [STAFF_DIR / "profile.html", FRONTEND_DIR / "console" / "profile.html"]:
        if cand.is_file():
            return FileResponse(cand)
    raise HTTPException(status_code=404, detail="Profile page not found")


@router.get("/profile.html", include_in_schema=False)
@router.get("/console/profile.html", include_in_schema=False)
async def redirect_profile_html():
    return RedirectResponse(url="/profile", status_code=301)


# --- 5. SOLUTIONS ROUTES ---

@router.get("/rag", include_in_schema=False)
@router.get("/chat", include_in_schema=False)
async def serve_rag_alias():
    return RedirectResponse(url="/services/rag-chatbot", status_code=301)


@router.get("/solutions/{path:path}", include_in_schema=False)
async def serve_solutions(path: str, request: Request):
    clean = path.strip("/")
    if clean.endswith(".html"):
        clean_name = clean[:-5]
        query = request.url.query
        target = f"/solutions/{clean_name}" + (f"?{query}" if query else "")
        return RedirectResponse(url=target, status_code=301)
    target = SOLUTIONS_DIR / clean
    if target.is_dir() and (target / "index.html").is_file():
        return FileResponse(target / "index.html")
    if target.is_file():
        return FileResponse(target)
    if (SOLUTIONS_DIR / f"{clean}.html").is_file():
        return FileResponse(SOLUTIONS_DIR / f"{clean}.html")
    raise HTTPException(status_code=404, detail=f"Solution page '{path}' not found")

