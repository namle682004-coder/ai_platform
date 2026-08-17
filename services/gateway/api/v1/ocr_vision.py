from typing import Optional, List
from fastapi import APIRouter, File, UploadFile, Form, Header, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1", tags=["OCR, Vision & NLP Extensions"])

class SummarizationRequest(BaseModel):
    document: str
    ratio: Optional[float] = 0.2

class TranslationRequest(BaseModel):
    text: str
    source_lang: str
    target_lang: str

@router.post("/ocr/driver-license")
async def ocr_driver_license(
    image: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):
    """Mock Driver License OCR Recognition."""
    return {
        "status": "success",
        "data": {
            "license_number": "120398401923",
            "full_name": "NGUYEN VAN A",
            "dob": "10/12/1990",
            "nationality": "VNM",
            "class": "A1",
            "expires": "2035/12/10"
        }
    }

@router.post("/ocr/id-card")
async def ocr_id_card(
    image: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):
    """Mock ID Card (CCCD) OCR Recognition."""
    return {
        "status": "success",
        "data": {
            "id_number": "001095012345",
            "full_name": "TRAN THI B",
            "dob": "15/08/1995",
            "gender": "Female",
            "nationality": "Vietnamese",
            "place_of_origin": "Ha Noi",
            "place_of_residence": "Cau Giay, Ha Noi",
            "expires": "15/08/2035"
        }
    }

@router.post("/ocr/passport")
async def ocr_passport(
    image: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):
    """Mock Passport OCR Recognition."""
    return {
        "status": "success",
        "data": {
            "passport_number": "B1234567",
            "nationality": "VNM",
            "full_name": "PHAM VAN C",
            "dob": "20/05/1988",
            "gender": "Male",
            "place_of_birth": "Da Nang",
            "date_of_issue": "12/04/2021",
            "date_of_expiry": "12/04/2031"
        }
    }

@router.post("/vision/facematch")
async def vision_facematch(
    image_cccd: UploadFile = File(...),
    image_selfie: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):
    """Mock FaceMatch Verification."""
    return {
        "status": "success",
        "matched": True,
        "confidence": 0.942,
        "message": "Biometric match verified successfully"
    }

@router.post("/vision/liveness-v3")
async def vision_liveness_v3(
    video: UploadFile = File(...),
    mode: Optional[str] = Form("passive"),
    authorization: Optional[str] = Header(None)
):
    """Mock Liveness v3 Recognition."""
    return {
        "status": "success",
        "is_live": True,
        "score": 0.991,
        "details": "No digital replay, mask or printed photo attack detected"
    }

@router.post("/nlp/summarization")
async def nlp_summarization(
    req: SummarizationRequest,
    authorization: Optional[str] = Header(None)
):
    """Mock Text Summarization."""
    return {
        "status": "success",
        "summary": "Tóm tắt: Everwin AI Platform cung cấp bộ 13 API dịch vụ trí tuệ nhân tạo toàn diện bao gồm OCR, Vision và xử lý ngôn ngữ tự nhiên tối ưu."
    }

@router.post("/nlp/translation")
async def nlp_translation(
    req: TranslationRequest,
    authorization: Optional[str] = Header(None)
):
    """Mock Language Translation."""
    translated = "Welcome to Everwin AI Platform." if "chào" in req.text.lower() else "Đây là bản dịch mẫu."
    return {
        "status": "success",
        "translated_text": translated
    }
