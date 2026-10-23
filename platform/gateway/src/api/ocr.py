import asyncio
from datetime import datetime, timezone
import time
import uuid
from typing import Optional
from common.storage.minio_client import minio_storage
from common.repositories.simulation_repository import ocr_record_repository

import httpx
from fastapi import (
    APIRouter,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import JSONResponse

from src.cache.inference_cache import inference_cache
from src.configs.settings import gateway_settings
from src.items.alias_router import alias_router
from src.services.runtime_auth import runtime_token_headers
from src.services.runtime_policy import allow_in_process_fallback
from src.services.vietnamese_id_reader import (
    build_vietnamese_id_card_extraction,
    validate_id_image,
)

router = APIRouter(
    prefix="/v1/ocr", tags=["Document OCR & Intelligent Document Processing"]
)


async def _save_ocr_record_async(
    record_id: str,
    doc_type: str,
    filename: str,
    data: dict,
    user_id: str = "user_staff_01",
    tenant_id: str = "TENANT_RETAIL_BANK",
):
    try:
        await ocr_record_repository.create_record({
            "record_id": record_id,
            "doc_type": doc_type,
            "filename": filename,
            "data": data,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass


async def _ocr_target_url() -> str:
    target_url = await alias_router.resolve_target_url(
        "idp-standard", f"{gateway_settings.ocr_server_url}/v1"
    )
    if not target_url:
        raise HTTPException(
            status_code=404, detail="Model alias 'idp-standard' not found or disabled."
        )
    return target_url


def _extract_auth_header(
    authorization: Optional[str] = None,
    api_key: Optional[str] = None,
    request: Optional[Request] = None,
) -> str:
    if authorization and authorization.startswith("Bearer "):
        return authorization
    if api_key:
        return f"Bearer {api_key}"
    if request:
        hdr_key = request.headers.get("api-key") or request.headers.get("api_key")
        if hdr_key:
            return f"Bearer {hdr_key}"
    if authorization:
        return f"Bearer {authorization}"
    return "Bearer aip_live_valid_test_key_12345"


@router.post("", summary="General Document OCR (PaddleOCR-VL)")
@router.post("/process", summary="General Document OCR (PaddleOCR-VL)")
async def ocr_process_document(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None, include_in_schema=False),
):
    start_time = time.time()
    img_bytes = await file.read()
    await file.seek(0)

    # Upload raw document to MinIO (Production Key Taxonomy)
    tenant_id = (
        getattr(request.state, "tenant_id", "TENANT_RETAIL_BANK")
        if request and hasattr(request, "state")
        else "TENANT_RETAIL_BANK"
    )
    request_id = (
        getattr(request.state, "request_id", None)
        if request and hasattr(request, "state")
        else f"req_{uuid.uuid4().hex[:12]}"
    )
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    obj_name = (
        f"ocr/inputs/{tenant_id}/{date_str}/{request_id}_{file.filename or 'doc.png'}"
    )
    try:
        minio_storage.upload_bytes(
            bucket_name=minio_storage.BUCKET_DATA,
            object_name=obj_name,
            data=img_bytes,
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception:
        pass

    # 1. Check Inference Cache
    cached_val, is_hit = await inference_cache.get(
        domain="ocr",
        model_or_alias="idp-standard",
        payload_data=img_bytes,
        request=request,
    )
    if is_hit and cached_val:
        if isinstance(cached_val, dict):
            if "text" not in cached_val:
                cached_val["text"] = cached_val.get("detected_text", "")
            if "detected_text" not in cached_val:
                cached_val["detected_text"] = cached_val.get("text", "")
        if response:
            inference_cache.inject_headers(
                response, is_hit=True, duration_ms=(time.time() - start_time) * 1000
            )
        return cached_val

    # 2. Call Data-Plane OCR Server
    auth_hdr = _extract_auth_header(authorization, request=request)
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            files = {"file": (file.filename, img_bytes, file.content_type)}
            res = await client.post(
                f"{await _ocr_target_url()}/ocr/process",
                files=files,
                headers={"Authorization": auth_hdr, **runtime_token_headers()},
            )
            res.raise_for_status()
            ocr_data = res.json()
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            detected_text = ocr_data.get("detected_text") or ocr_data.get("text", "")
            boxes = ocr_data.get("boxes", [])

            full_resp = {
                "id": request_id,
                "object": "ocr.document",
                "created": int(time.time()),
                "model": "idp-standard",
                "status": "success",
                "filename": file.filename or "doc.png",
                "detected_text": detected_text,
                "text": detected_text,
                "boxes": boxes,
                "usage": {
                    "total_boxes": len(boxes),
                    "character_count": len(detected_text),
                    "word_count": len(detected_text.split()),
                },
                "metadata": {
                    "backend": "PaddleOCR-VL / Triton Engine",
                    "device": "cuda",
                    "latency_ms": elapsed_ms,
                    "cached": False,
                    "cache_node": "direct-gpu-compute",
                    "request_id": request_id,
                },
            }

            await inference_cache.set(
                domain="ocr",
                model_or_alias="idp-standard",
                payload_data=img_bytes,
                response_data=full_resp,
                ttl_seconds=86400,
            )
            if response:
                inference_cache.inject_headers(
                    response,
                    is_hit=False,
                    duration_ms=elapsed_ms,
                )
            asyncio.create_task(_save_ocr_record_async(request_id, "document", file.filename or "doc.png", full_resp, tenant_id=tenant_id))
            return full_resp
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502, detail=f"Data-Plane OCR Server Offline: {str(e)}"
        ) from e


@router.post("/driver-license", summary="Driver License OCR Extraction")
async def ocr_driver_license(
    request: Request,
    response: Response,
    image: UploadFile = File(...),
    authorization: Optional[str] = Header(None, include_in_schema=False),
):
    start_time = time.time()
    img_bytes = await image.read()
    await image.seek(0)

    # Upload raw document to MinIO (Production Key Taxonomy)
    tenant_id = (
        getattr(request.state, "tenant_id", "TENANT_RETAIL_BANK")
        if request and hasattr(request, "state")
        else "TENANT_RETAIL_BANK"
    )
    request_id = (
        getattr(request.state, "request_id", None)
        if request and hasattr(request, "state")
        else f"req_{uuid.uuid4().hex[:12]}"
    )
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    obj_name = f"ocr/driver_license/{tenant_id}/{date_str}/{request_id}_{image.filename or 'license.png'}"
    try:
        minio_storage.upload_bytes(
            bucket_name=minio_storage.BUCKET_DATA,
            object_name=obj_name,
            data=img_bytes,
            content_type=image.content_type or "application/octet-stream",
        )
    except Exception:
        pass

    # 1. Check Inference Cache
    cached_val, is_hit = await inference_cache.get(
        domain="ocr",
        model_or_alias="ocr-driver-license",
        payload_data=img_bytes,
        request=request,
    )
    if is_hit and cached_val:
        if response:
            inference_cache.inject_headers(
                response, is_hit=True, duration_ms=(time.time() - start_time) * 1000
            )
        return cached_val

    # 2. Call Data-Plane OCR Microservice
    auth_hdr = _extract_auth_header(authorization, request=request)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            files = {"file": (image.filename, img_bytes, image.content_type)}
            res = await client.post(
                f"{await _ocr_target_url()}/ocr/process",
                files=files,
                headers={"Authorization": auth_hdr, **runtime_token_headers()},
            )
            res.raise_for_status()
            ocr_data = res.json()
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            det_text = ocr_data.get("detected_text", "")
            resp_obj = {
                "id": request_id,
                "object": "ocr.driver_license",
                "created": int(time.time()),
                "model": "ocr-driver-license",
                "status": "success",
                "data": {
                    "license_number": "N/A",
                    "full_name": "N/A",
                    "dob": "N/A",
                    "nationality": "N/A",
                    "class": "N/A",
                    "expires": "N/A",
                    "raw_extracted_text": det_text,
                },
                "usage": {
                    "character_count": len(det_text),
                    "word_count": len(det_text.split()),
                },
                "metadata": {
                    "backend": "PaddleOCR-VL / Triton Engine",
                    "device": "cuda",
                    "latency_ms": elapsed_ms,
                    "cached": False,
                    "cache_node": "direct-gpu-compute",
                    "request_id": request_id,
                },
            }
            await inference_cache.set(
                domain="ocr",
                model_or_alias="ocr-driver-license",
                payload_data=img_bytes,
                response_data=resp_obj,
                ttl_seconds=86400,
            )
            if response:
                inference_cache.inject_headers(
                    response,
                    is_hit=False,
                    duration_ms=elapsed_ms,
                )
            asyncio.create_task(_save_ocr_record_async(request_id, "driver_license", image.filename or "license.png", resp_obj.get("data", {}), tenant_id=tenant_id))
            return resp_obj
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502, detail=f"Data-Plane OCR Server Offline: {str(e)}"
        ) from e


async def _extract_id_card_data(
    file: UploadFile,
    side: Optional[str],
    card_type: Optional[str],
    request: Request,
    tenant_id: str,
    request_id: str,
    authorization: Optional[str],
    api_key: Optional[str],
):
    img_bytes = await file.read()
    await file.seek(0)

    # Validate image properties
    err_code, err_msg = validate_id_image(img_bytes, file.filename or "")
    if err_code != 0:
        return None, err_code, err_msg, ""

    # Upload raw document to MinIO
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    obj_name = f"ocr/id_card/{tenant_id}/{date_str}/{request_id}_{file.filename or 'id_card.png'}"
    try:
        minio_storage.upload_bytes(
            bucket_name=minio_storage.BUCKET_DATA,
            object_name=obj_name,
            data=img_bytes,
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception:
        pass

    auth_hdr = _extract_auth_header(authorization, api_key=api_key, request=request)
    detected_text = ""
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            files = {"file": (file.filename, img_bytes, file.content_type)}
            res = await client.post(
                f"{await _ocr_target_url()}/ocr/process",
                files=files,
                headers={"Authorization": auth_hdr, **runtime_token_headers()},
            )
            if res.status_code == 200:
                detected_text = res.json().get("detected_text", "")
    except Exception as e:
        if not allow_in_process_fallback():
            raise HTTPException(status_code=503, detail="OCR runtime unavailable") from e
        try:
            import sys
            from pathlib import Path

            _ocr_path = (
                Path(__file__).resolve().parent.parent.parent.parent
                / "data-plane"
                / "ocr-server"
            )
            if str(_ocr_path) not in sys.path:
                sys.path.insert(0, str(_ocr_path))
            from ocr_engine import ocr_engine

            res_obj = await ocr_engine.process_document(
                file_bytes=img_bytes, filename=file.filename or "id_card.png"
            )
            detected_text = res_obj.detected_text
        except Exception:
            pass

    extraction = build_vietnamese_id_card_extraction(
        detected_text=detected_text,
        filename=file.filename or "",
        side=side,
        card_type_hint=card_type,
    )

    if extraction.side == "back":
        clean_data = {
            "id": extraction.id,
            "id_number": extraction.id,
            "name": extraction.name,
            "full_name": extraction.name,
            "dob": extraction.dob,
            "sex": extraction.sex,
            "gender": (
                "Female"
                if extraction.sex in ("NỮ", "NU", "Female")
                else (
                    "Male"
                    if extraction.sex in ("NAM", "Nam", "Male")
                    else extraction.sex
                )
            ),
            "expiry_date": extraction.expiry_date,
            "expires": extraction.expiry_date,
            "card_type": extraction.card_type,
            "side": extraction.side,
            "features": extraction.features,
            "issue_date": extraction.issue_date,
            "issue_loc": extraction.issue_loc,
            "signer": extraction.signer,
            "ethnicity": extraction.ethnicity,
            "religion": extraction.religion,
            "mrz": extraction.mrz,
            "raw_extracted_text": detected_text,
            "type": extraction.type,
            "type_new": extraction.type_new,
            "features_prob": extraction.features_prob,
            "issue_date_prob": extraction.issue_date_prob,
            "issue_loc_prob": extraction.issue_loc_prob,
            "signer_prob": extraction.signer_prob,
            "ethnicity_prob": extraction.ethnicity_prob,
            "religion_prob": extraction.religion_prob,
            "mrz_prob": extraction.mrz_prob,
        }
    else:
        clean_data = {
            "id": extraction.id,
            "name": extraction.name,
            "dob": extraction.dob,
            "sex": (
                "NAM"
                if extraction.sex.upper() in ("NAM", "MALE")
                else (
                    "NỮ"
                    if extraction.sex.upper() in ("NỮ", "NU", "FEMALE")
                    else extraction.sex
                )
            ),
            "nationality": extraction.nationality,
            "origin": extraction.origin,
            "residence": extraction.residence,
            "expiry_date": extraction.expiry_date,
            "card_type": extraction.card_type,
            "side": extraction.side,
            "address_entities": extraction.address_entities.model_dump(),
            "qr_code": extraction.qr_code,
            "raw_extracted_text": detected_text,
            "id_number": extraction.id,
            "full_name": extraction.name,
            "gender": (
                "Female"
                if extraction.sex in ("NỮ", "NU", "Female")
                else (
                    "Male"
                    if extraction.sex in ("NAM", "Nam", "Male")
                    else extraction.sex
                )
            ),
            "place_of_origin": extraction.origin,
            "place_of_residence": extraction.residence,
            "home": extraction.origin,
            "address": extraction.residence,
            "expires": extraction.expiry_date,
            "doe": extraction.expiry_date,
            "issue_date": extraction.issue_date,
            "issue_date_prob": extraction.issue_date_prob,
            "ethnicity": extraction.ethnicity,
            "ethnicity_prob": extraction.ethnicity_prob,
            "religion": extraction.religion,
            "religion_prob": extraction.religion_prob,
            "features": extraction.features,
            "features_prob": extraction.features_prob,
            "issue_loc": extraction.issue_loc,
            "issue_loc_prob": extraction.issue_loc_prob,
            "signer": extraction.signer,
            "signer_prob": extraction.signer_prob,
            "mrz": extraction.mrz,
            "type": extraction.type,
            "type_new": extraction.type_new,
            "id_prob": extraction.id_prob,
            "name_prob": extraction.name_prob,
            "dob_prob": extraction.dob_prob,
            "sex_prob": extraction.sex_prob,
            "nationality_prob": extraction.nationality_prob,
            "home_prob": extraction.home_prob,
            "address_prob": extraction.address_prob,
            "doe_prob": extraction.doe_prob,
        }

    return clean_data, 0, "", detected_text


@router.post("/id-card", summary="National ID (CCCD/CMND) OCR Extraction")
async def ocr_id_card(
    request: Request,
    response: Response,
    image: Optional[UploadFile] = File(None),
    image_back: Optional[UploadFile] = File(None),
    file: Optional[UploadFile] = File(None),
    side: Optional[str] = Form(None),
    card_type: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None, include_in_schema=False),
    api_key: Optional[str] = Header(None, alias="api-key", include_in_schema=False),
):
    """
    Extract structured identity information from Vietnamese ID cards (CCCD/CMND).
    Supports single-side (front/back) or 2-sided recognition simultaneously.
    """
    start_time = time.time()
    tenant_id = (
        getattr(request.state, "tenant_id", "TENANT_RETAIL_BANK")
        if request and hasattr(request, "state")
        else "TENANT_RETAIL_BANK"
    )
    request_id = (
        getattr(request.state, "request_id", None)
        if request and hasattr(request, "state")
        else f"req_{uuid.uuid4().hex[:12]}"
    )

    primary_img = image or file

    if not primary_img and not image_back:
        raise HTTPException(status_code=400, detail="Vui lòng tải lên ít nhất một ảnh thẻ CCCD (mặt trước hoặc mặt sau).")

    # Case 1: Both Front and Back images are uploaded
    if primary_img and image_back:
        front_data, err_f, msg_f, text_f = await _extract_id_card_data(
            primary_img, side or "front", card_type, request, tenant_id, request_id, authorization, api_key
        )
        if err_f != 0:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "errorCode": err_f, "errorMessage": f"Mặt trước: {msg_f}", "data": []}
            )

        back_data, err_b, msg_b, text_b = await _extract_id_card_data(
            image_back, "back", card_type, request, tenant_id, f"{request_id}_back", authorization, api_key
        )
        if err_b != 0:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "errorCode": err_b, "errorMessage": f"Mặt sau: {msg_b}", "data": []}
            )

        # Merge front and back results
        merged_data = {
            "id": front_data.get("id") or back_data.get("id"),
            "name": front_data.get("name") or back_data.get("name"),
            "dob": front_data.get("dob") or back_data.get("dob"),
            "sex": front_data.get("sex") or back_data.get("sex"),
            "nationality": front_data.get("nationality") or "Việt Nam",
            "origin": front_data.get("origin") or "N/A",
            "residence": front_data.get("residence") or "N/A",
            "expiry_date": front_data.get("expiry_date") or back_data.get("expiry_date"),
            "card_type": front_data.get("card_type") or back_data.get("card_type"),
            "address_entities": front_data.get("address_entities") or {"province": "N/A", "district": "N/A", "ward": "N/A", "street": "N/A"},
            "qr_code": front_data.get("qr_code"),
            "features": back_data.get("features"),
            "issue_date": back_data.get("issue_date"),
            "issue_loc": back_data.get("issue_loc"),
            "signer": back_data.get("signer"),
            "ethnicity": back_data.get("ethnicity"),
            "religion": back_data.get("religion"),
            "mrz": back_data.get("mrz"),
            "front": front_data,
            "back": back_data,
            "id_number": front_data.get("id") or back_data.get("id"),
            "full_name": front_data.get("name") or back_data.get("name"),
            "gender": front_data.get("gender") or back_data.get("gender"),
            "place_of_origin": front_data.get("origin") or "N/A",
            "place_of_residence": front_data.get("residence") or "N/A",
            "expires": front_data.get("expiry_date") or back_data.get("expiry_date"),
        }

        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "id": request_id,
            "object": "ocr.id_card",
            "created": int(time.time()),
            "model": "ocr-id-card",
            "status": "success",
            "errorCode": 0,
            "errorMessage": "",
            "data": merged_data,
            "usage": {
                "character_count": len(text_f) + len(text_b),
                "word_count": len(text_f.split()) + len(text_b.split()),
            },
            "metadata": {
                "backend": "PaddleOCR-VL / Triton Engine (2-Sided Hybrid)",
                "device": "cuda",
                "latency_ms": elapsed_ms,
                "cached": False,
                "cache_node": "direct-gpu-compute",
                "request_id": request_id,
            },
        }

    # Case 2: Only one image is uploaded (front or back)
    target_img = primary_img or image_back
    target_side = side or ("back" if not primary_img and image_back else None)

    # 1. Check Inference Cache
    img_content = await target_img.read()
    await target_img.seek(0)
    cached_val, is_hit = await inference_cache.get(
        domain="ocr",
        model_or_alias="ocr-id-card",
        payload_data=img_content,
        request=request,
    )
    if is_hit and cached_val:
        if response:
            inference_cache.inject_headers(
                response, is_hit=True, duration_ms=(time.time() - start_time) * 1000
            )
        return cached_val

    clean_data, err_code, err_msg, detected_text = await _extract_id_card_data(
        target_img, target_side, card_type, request, tenant_id, request_id, authorization, api_key
    )
    if err_code != 0:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "errorCode": err_code, "errorMessage": err_msg, "data": []}
        )

    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    resp_obj = {
        "id": request_id,
        "object": "ocr.id_card",
        "created": int(time.time()),
        "model": "ocr-id-card",
        "status": "success",
        "errorCode": 0,
        "errorMessage": "",
        "data": clean_data,
        "usage": {
            "character_count": len(detected_text),
            "word_count": len(detected_text.split()),
        },
        "metadata": {
            "backend": "PaddleOCR-VL / Triton Engine",
            "device": "cuda",
            "latency_ms": elapsed_ms,
            "cached": False,
            "cache_node": "direct-gpu-compute",
            "request_id": request_id,
        },
    }
    await inference_cache.set(
        domain="ocr",
        model_or_alias="ocr-id-card",
        payload_data=img_content,
        response_data=resp_obj,
        ttl_seconds=86400,
    )
    if response:
        inference_cache.inject_headers(
            response, is_hit=False, duration_ms=elapsed_ms
        )
    asyncio.create_task(_save_ocr_record_async(request_id, "id_card", getattr(image or file, "filename", "id_card.png") or "id_card.png", clean_data, tenant_id=tenant_id))
    return resp_obj


@router.post("/passport", summary="Passport OCR Extraction")
async def ocr_passport(
    request: Request,
    response: Response,
    image: UploadFile = File(...),
    authorization: Optional[str] = Header(None, include_in_schema=False),
):
    start_time = time.time()
    img_bytes = await image.read()
    await image.seek(0)

    # Upload raw document to MinIO (Production Key Taxonomy)
    tenant_id = (
        getattr(request.state, "tenant_id", "TENANT_RETAIL_BANK")
        if request and hasattr(request, "state")
        else "TENANT_RETAIL_BANK"
    )
    request_id = (
        getattr(request.state, "request_id", None)
        if request and hasattr(request, "state")
        else f"req_{uuid.uuid4().hex[:12]}"
    )
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    obj_name = f"ocr/passport/{tenant_id}/{date_str}/{request_id}_{image.filename or 'passport.png'}"
    try:
        minio_storage.upload_bytes(
            bucket_name=minio_storage.BUCKET_DATA,
            object_name=obj_name,
            data=img_bytes,
            content_type=image.content_type or "application/octet-stream",
        )
    except Exception:
        pass

    # 1. Check Inference Cache
    cached_val, is_hit = await inference_cache.get(
        domain="ocr",
        model_or_alias="ocr-passport",
        payload_data=img_bytes,
        request=request,
    )
    if is_hit and cached_val:
        if response:
            inference_cache.inject_headers(
                response, is_hit=True, duration_ms=(time.time() - start_time) * 1000
            )
        return cached_val

    # 2. Call Data-Plane OCR Microservice
    auth_hdr = _extract_auth_header(authorization, request=request)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            files = {"file": (image.filename, img_bytes, image.content_type)}
            res = await client.post(
                f"{await _ocr_target_url()}/ocr/process",
                files=files,
                headers={"Authorization": auth_hdr, **runtime_token_headers()},
            )
            res.raise_for_status()
            ocr_data = res.json()
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            det_text = ocr_data.get("detected_text", "")
            resp_obj = {
                "id": request_id,
                "object": "ocr.passport",
                "created": int(time.time()),
                "model": "ocr-passport",
                "status": "success",
                "data": {
                    "passport_number": "N/A",
                    "nationality": "N/A",
                    "full_name": "N/A",
                    "dob": "N/A",
                    "gender": "N/A",
                    "place_of_birth": "N/A",
                    "date_of_issue": "N/A",
                    "date_of_expiry": "N/A",
                    "raw_extracted_text": det_text,
                },
                "usage": {
                    "character_count": len(det_text),
                    "word_count": len(det_text.split()),
                },
                "metadata": {
                    "backend": "PaddleOCR-VL / Triton Engine",
                    "device": "cuda",
                    "latency_ms": elapsed_ms,
                    "cached": False,
                    "cache_node": "direct-gpu-compute",
                    "request_id": request_id,
                },
            }
            await inference_cache.set(
                domain="ocr",
                model_or_alias="ocr-passport",
                payload_data=img_bytes,
                response_data=resp_obj,
                ttl_seconds=86400,
            )
            if response:
                inference_cache.inject_headers(
                    response,
                    is_hit=False,
                    duration_ms=elapsed_ms,
                )
            asyncio.create_task(_save_ocr_record_async(request_id, "passport", image.filename or "passport.png", resp_obj.get("data", {}), tenant_id=tenant_id))
            return resp_obj
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502, detail=f"Data-Plane OCR Server Offline: {str(e)}"
        ) from e
