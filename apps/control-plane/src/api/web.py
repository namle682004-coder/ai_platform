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
    _repository_root / "apps" / "frontend",
    Path.cwd() / "apps" / "frontend",
    Path("/opt/render/project/src/apps/frontend"),
]
FRONTEND_DIR: Path = next(
    (directory for directory in _candidates if (directory / "staff" / "api_detail_routes.json").is_file()),
    _candidates[0],
)
STAFF_DIR: Path = FRONTEND_DIR / "staff"
ADMIN_DIR: Path = FRONTEND_DIR / "admin"
AUTH_DIR: Path = FRONTEND_DIR / "auth"
API_ROUTE_CONFIG = json.loads(
    (STAFF_DIR / "api_detail_routes.json").read_text(encoding="utf-8")
)
SERVICE_LEGACY_TO_UUID = API_ROUTE_CONFIG["legacyAliases"]
API_UUID_TO_LEGACY_PAGE = API_ROUTE_CONFIG["apiPages"]
DEFAULT_PROJECT_ID = API_ROUTE_CONFIG["defaultProjectId"]


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


# --- 1. ENTERPRISE FPT.AI-COMPLIANT PROJECT & APIS URL ROUTES ---
# Example: /project/{project_id}/apis/{api_id}

@router.get("/project/{project_id}/apis/{api_id}", include_in_schema=False)
@router.get("/project/{project_id}/apis/{api_id}/", include_in_schema=False)
@router.get("/staff/project/{project_id}/apis/{api_id}", include_in_schema=False)
@router.get("/staff/project/{project_id}/apis/{api_id}/", include_in_schema=False)
async def serve_project_api_detail(project_id: str, api_id: str):
    page_name = API_UUID_TO_LEGACY_PAGE.get(api_id.lower())
    if not page_name:
        raise HTTPException(status_code=404, detail="API detail page not found")

    service_page = STAFF_DIR / page_name
    if service_page.is_file():
        return FileResponse(service_page)
    raise HTTPException(status_code=404, detail="Service detail page not found")


@router.get("/project/{project_id}/apis", include_in_schema=False)
@router.get("/project/{project_id}/apis/", include_in_schema=False)
@router.get("/staff/project/{project_id}/apis", include_in_schema=False)
@router.get("/staff/project/{project_id}/apis/", include_in_schema=False)
async def serve_project_apis_catalog(project_id: str):
    apis_html = STAFF_DIR / "apis.html"
    if apis_html.exists():
        return FileResponse(apis_html)
    raise HTTPException(status_code=404, detail="APIs catalog page not found")


@router.get("/project/{project_id}", include_in_schema=False)
@router.get("/project/{project_id}/", include_in_schema=False)
@router.get("/project/{project_id}/dashboard", include_in_schema=False)
@router.get("/staff/project/{project_id}", include_in_schema=False)
@router.get("/staff/project/{project_id}/dashboard", include_in_schema=False)
async def serve_project_dashboard(project_id: str):
    dash = STAFF_DIR / "dashboard.html"
    if dash.exists():
        return FileResponse(dash)
    raise HTTPException(status_code=404, detail="Project dashboard not found")


# --- 2. STAFF PORTAL ROOT & CONVENIENCE ROUTES ---

@router.get("/staff", include_in_schema=False)
@router.get("/staff/", include_in_schema=False)
@router.get("/portal", include_in_schema=False)
async def serve_staff_root():
    dash = STAFF_DIR / "dashboard.html"
    if dash.exists():
        return FileResponse(dash)
    return RedirectResponse(url="/staff/apis")


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
async def serve_staff_page(page: str):
    clean_page = page.strip("/").lower()
    # Check if page is legacy named service (e.g. service-llm, service-stt)
    # Redirect cleanly to /project/{project_id}/apis/{api_id}
    clean_without_ext = clean_page.replace(".html", "")
    if clean_without_ext in SERVICE_LEGACY_TO_UUID:
        target_uuid = SERVICE_LEGACY_TO_UUID[clean_without_ext]
        return RedirectResponse(url=f"/project/{DEFAULT_PROJECT_ID}/apis/{target_uuid}", status_code=302)

    found = _resolve_page(STAFF_DIR, page)
    if found:
        return FileResponse(found)
    raise HTTPException(status_code=404, detail=f"Staff page '{page}' not found")


# --- 3. ADMIN CONSOLE ROUTES ---

@router.get("/admin", include_in_schema=False)
@router.get("/admin/", include_in_schema=False)
async def serve_admin_root():
    dash = ADMIN_DIR / "dashboard.html"
    if dash.exists():
        return FileResponse(dash)
    raise HTTPException(status_code=404, detail="Admin dashboard not found")


@router.get("/admin/{page:path}", include_in_schema=False)
async def serve_admin_page(page: str):
    # Safety guard: Skip /admin/v1 API routes
    if page.startswith("v1") or page.startswith("v1/"):
        raise HTTPException(status_code=404, detail="Not Found")
    found = _resolve_page(ADMIN_DIR, page)
    if found:
        return FileResponse(found)
    raise HTTPException(status_code=404, detail=f"Admin page '{page}' not found")


# --- 4. AUTH & PUBLIC STATUS PAGES ---

@router.get("/login", include_in_schema=False)
@router.get("/auth/login", include_in_schema=False)
@router.get("/auth/login.html", include_in_schema=False)
async def serve_login():
    login_html = AUTH_DIR / "login.html"
    if login_html.exists():
        return FileResponse(login_html)
    raise HTTPException(status_code=404, detail="Login page not found")


@router.get("/signup", include_in_schema=False)
@router.get("/auth/signup", include_in_schema=False)
@router.get("/auth/signup.html", include_in_schema=False)
async def serve_signup():
    signup_html = AUTH_DIR / "signup.html"
    if signup_html.exists():
        return FileResponse(signup_html)
    raise HTTPException(status_code=404, detail="Signup page not found")


@router.get("/status", include_in_schema=False)
async def serve_status(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        status_html = FRONTEND_DIR / "status.html"
        if status_html.exists():
            return FileResponse(status_html)
    status_html = FRONTEND_DIR / "status.html"
    if status_html.exists():
        return FileResponse(status_html)
    raise HTTPException(status_code=404, detail="Status page not found")
