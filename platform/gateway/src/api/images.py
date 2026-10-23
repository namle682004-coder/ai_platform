from datetime import datetime, timezone
import time
import uuid
from typing import Optional
from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import BaseModel, Field
from common.storage.minio_client import minio_storage

router = APIRouter(prefix="/v1", tags=["Image Generations"])

# Minimal valid 1x1 PNG bytes for synthesized artifacts
_DEFAULT_CANVAS_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
)


class ImageGenerationRequest(BaseModel):
    model: str = Field("image-gen-standard", json_schema_extra={"example": "image-gen-standard"})
    prompt: str = Field(..., json_schema_extra={"example": "a high tech AI inference gateway in cyber style"})
    n: int | None = Field(1, ge=1, le=4)
    size: str | None = Field("1024x1024", json_schema_extra={"example": "1024x1024"})
    response_format: str | None = Field("url", json_schema_extra={"example": "url"})


class ImageData(BaseModel):
    url: str


class ImageGenerationResponse(BaseModel):
    created: int = Field(default_factory=lambda: int(time.time()))
    data: list[ImageData]


@router.post("/images/generations", response_model=ImageGenerationResponse, summary="Text to Image Generation (Timeout: 60s)")
async def generate_images(
    request: Request,
    payload: ImageGenerationRequest,
):
    # 0. Automatic Heavy Workload Offload to RabbitMQ (n > 1 or explicit async)
    from src.jobs.offloader import is_image_heavy, offload_job
    is_heavy, reason = is_image_heavy(payload.n or 1, request)
    if is_heavy:
        return await offload_job(
            request=request,
            domain="image",
            alias_name=payload.model,
            payload=payload.model_dump(),
            reason=reason,
        )

    tenant_id = getattr(request.state, "tenant_id", "TENANT_RETAIL_BANK") if hasattr(request, "state") else "TENANT_RETAIL_BANK"
    request_id = getattr(request.state, "request_id", None) if hasattr(request, "state") else f"req_{uuid.uuid4().hex[:12]}"
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    items = []
    count = payload.n or 1
    for i in range(count):
        obj_name = f"images/generations/{tenant_id}/{date_str}/{request_id}_{i}.png"
        uploaded = minio_storage.upload_bytes(
            bucket_name=minio_storage.BUCKET_JOB_ARTIFACTS,
            object_name=obj_name,
            data=_DEFAULT_CANVAS_PNG,
            content_type="image/png",
        )
        if uploaded:
            url = minio_storage.get_presigned_url(
                bucket_name=minio_storage.BUCKET_JOB_ARTIFACTS,
                object_name=obj_name,
                expiry_seconds=86400,
            ) or f"http://localhost:9000/aip-job-artifacts/{obj_name}"
        else:
            url = f"http://localhost:9000/aip-job-artifacts/{obj_name}"
        items.append(ImageData(url=url))

    return ImageGenerationResponse(created=int(time.time()), data=items)


@router.post("/images/edits", response_model=ImageGenerationResponse, summary="Image Inpainting & Edits (Timeout: 60s)")
async def edit_images(
    request: Request,
    image: UploadFile = File(...),
    prompt: str = Form(...),
    mask: Optional[UploadFile] = File(None),
    model: str = Form("image-gen-standard"),
    n: Optional[int] = Form(1),
    size: Optional[str] = Form("1024x1024"),
):
    tenant_id = getattr(request.state, "tenant_id", "TENANT_RETAIL_BANK") if request and hasattr(request, "state") else "TENANT_RETAIL_BANK"
    request_id = getattr(request.state, "request_id", None) if request and hasattr(request, "state") else f"req_{uuid.uuid4().hex[:12]}"
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    # 1. Upload source image to MinIO data bucket
    img_bytes = await image.read()
    inp_obj = f"images/inputs/{tenant_id}/{date_str}/{request_id}_{image.filename or 'input.png'}"
    minio_storage.upload_bytes(
        bucket_name=minio_storage.BUCKET_DATA,
        object_name=inp_obj,
        data=img_bytes,
        content_type=image.content_type or "image/png",
    )

    # 2. Generate result artifacts into MinIO job artifacts bucket
    items = []
    count = n or 1
    for i in range(count):
        obj_name = f"images/edits/{tenant_id}/{date_str}/{request_id}_{i}.png"
        uploaded = minio_storage.upload_bytes(
            bucket_name=minio_storage.BUCKET_JOB_ARTIFACTS,
            object_name=obj_name,
            data=_DEFAULT_CANVAS_PNG,
            content_type="image/png",
        )
        if uploaded:
            url = minio_storage.get_presigned_url(
                bucket_name=minio_storage.BUCKET_JOB_ARTIFACTS,
                object_name=obj_name,
                expiry_seconds=86400,
            ) or f"http://localhost:9000/aip-job-artifacts/{obj_name}"
        else:
            url = f"http://localhost:9000/aip-job-artifacts/{obj_name}"
        items.append(ImageData(url=url))

    return ImageGenerationResponse(created=int(time.time()), data=items)
