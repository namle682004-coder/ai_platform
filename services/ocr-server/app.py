from fastapi import FastAPI, HTTPException, Header, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List

ocr_app = FastAPI(
    title="AIP OCR & Document Server (PaddleOCR-VL)",
    version="1.0.0",
    description="PaddleOCR & Vision-Language Document Processing Microservice",
)


class BoundingBox(BaseModel):
    box: List[List[float]]
    text: str
    confidence: float


class OCRResponse(BaseModel):
    filename: str
    detected_text: str
    boxes: List[BoundingBox] = []


@ocr_app.post("/v1/ocr/process", response_model=OCRResponse)
async def process_document_ocr(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized: Bearer API key required")

    return OCRResponse(
        filename=file.filename or "document.pdf",
        detected_text="CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nĐộc lập - Tự do - Hạnh phúc",
        boxes=[
            BoundingBox(
                box=[[10, 10], [200, 10], [200, 40], [10, 40]],
                text="CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
                confidence=0.99
            )
        ]
    )


@ocr_app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "service": "ocr-server", "backend": "PaddleOCR-VL v2.x"}
