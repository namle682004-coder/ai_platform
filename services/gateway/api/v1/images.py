
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1", tags=["Image Generations"])


class ImageGenerationRequest(BaseModel):
    model: str = Field("image-gen-standard", json_schema_extra={"example": "image-gen-standard"})
    prompt: str = Field(..., json_schema_extra={"example": "a high tech AI inference gateway in cyber style"})
    n: int | None = Field(1, ge=1, le=4)
    size: str | None = Field("1024x1024", json_schema_extra={"example": "1024x1024"})
    response_format: str | None = Field("url", json_schema_extra={"example": "url"})


class ImageData(BaseModel):
    url: str


class ImageGenerationResponse(BaseModel):
    created: int = 1770970000
    data: list[ImageData]


@router.post("/images/generations", response_model=ImageGenerationResponse)
async def generate_images(
    request: Request,
    payload: ImageGenerationRequest,
):
    items = [
        ImageData(url=f"https://minio.internal/aip-job-artifacts/images/generated_{i}.png")
        for i in range(payload.n or 1)
    ]
    return ImageGenerationResponse(created=1770970000, data=items)
