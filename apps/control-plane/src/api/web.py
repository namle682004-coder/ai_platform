from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from common.repositories.endpoint_repository import endpoint_repository

router = APIRouter(include_in_schema=False)

DEFAULT_PROJECT_ID = "f40b6a70-ea64-4d01-90dc-53a2d7a81395"

SERVICE_LEGACY_TO_UUID = {
    "service-llm": "efb24a03-059d-440c-bd35-0b5b3a776983",
    "service_llm": "efb24a03-059d-440c-bd35-0b5b3a776983",
    "service-stt": "3a72d1f9-46c8-472e-8395-cb091a136701",
    "service_stt": "3a72d1f9-46c8-472e-8395-cb091a136701",
    "service-tts": "8b51ef94-912a-4367-bf16-36701a09cb12",
    "service_tts": "8b51ef94-912a-4367-bf16-36701a09cb12",
    "service-ocr-id": "c194a2b3-5710-4821-9472-a08361b09234",
    "service_ocr_id": "c194a2b3-5710-4821-9472-a08361b09234",
    "service-ocr-dl": "d285b3c4-6821-4932-a583-b19472c10345",
    "service_ocr_dl": "d285b3c4-6821-4932-a583-b19472c10345",
    "service-ocr-passport": "e396c4d5-7932-4a43-b694-c20583d21456",
    "service_ocr_passport": "e396c4d5-7932-4a43-b694-c20583d21456",
    "service-image": "f4a7d5e6-8043-4b54-c705-d31694e32567",
    "service_image": "f4a7d5e6-8043-4b54-c705-d31694e32567",
    "service-moderation": "a5b8e6f7-9154-4c65-d816-e42705f43678",
    "service_moderation": "a5b8e6f7-9154-4c65-d816-e42705f43678",
    "service-vision-facematch": "b6c9f7a8-0265-4d76-e927-f53816a54789",
    "service_vision_facematch": "b6c9f7a8-0265-4d76-e927-f53816a54789",
    "service-vision-liveness": "c7da08b9-1376-4e87-fa38-064927b65890",
    "service_vision_liveness": "c7da08b9-1376-4e87-fa38-064927b65890",
    "service-nlp-embeddings": "d8eb19ca-2487-4f98-0b49-175038c76901",
    "service_nlp_embeddings": "d8eb19ca-2487-4f98-0b49-175038c76901",
    "service-nlp-summarization": "fa0d3bec-46a9-41ba-2d6b-39725ae98123",
    "service_nlp_summarization": "fa0d3bec-46a9-41ba-2d6b-39725ae98123",
    "service-nlp-translation": "e9fc2adb-3598-40a9-1c5a-286149d87012",
    "service_nlp_translation": "e9fc2adb-3598-40a9-1c5a-286149d87012",
    "service-detail": "efb24a03-059d-440c-bd35-0b5b3a776983",
    "service_detail": "efb24a03-059d-440c-bd35-0b5b3a776983",
}

# Resolve candidates for frontend directory across local and container/cloud environments
_candidates = [
    Path(__file__).resolve().parent.parent.parent.parent / "apps" / "frontend",
    Path.cwd() / "apps" / "frontend",
    Path("/opt/render/project/src/apps/frontend"),
]
FRONTEND_DIR: Path = next((d for d in _candidates if d.exists()), _candidates[0])
STAFF_DIR: Path = FRONTEND_DIR / "staff"
ADMIN_DIR: Path = FRONTEND_DIR / "admin"
AUTH_DIR: Path = FRONTEND_DIR / "auth"


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
    svc_detail = STAFF_DIR / "service_detail.html"
    if svc_detail.exists():
        return FileResponse(svc_detail)
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
