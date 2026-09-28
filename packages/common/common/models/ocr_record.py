"""
Domain Entities for OCR Document Extractions (CCCD, Driver License, Passport).
Compliant with Clean Architecture DDD.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
import uuid
from pydantic import BaseModel, Field


class AddressEntities(BaseModel):
    """Decomposed standard 4-tier Vietnamese administrative address."""
    province: str = "N/A"
    district: str = "N/A"
    ward: str = "N/A"
    street: str = "N/A"


class VietnameseIDCardExtraction(BaseModel):
    """
    Standardized entity for Vietnamese ID Cards (CMND/CCCD).
    Supports 4 categories:
      - old (old CMND 9-digit front)
      - old_back (old CMND 9-digit back)
      - new (CCCD/CMND 12-digit front)
      - new_back (CCCD/CMND 12-digit back)
    and sub-classes in type_new:
      - cmnd_09_front, old_back, cmnd_12_front, cccd_12_front, new_back
    """
    # Core High-Accuracy Identity Fields
    id: str = "N/A"
    name: str = "N/A"
    dob: str = "N/A"
    sex: str = "N/A"
    nationality: str = "Việt Nam"
    origin: str = "N/A"
    residence: str = "N/A"
    expiry_date: str = "N/A"
    card_type: str = "CCCD gắn chip (12 số)"
    side: str = "front"
    qr_code: str | None = None
    raw_text: str | None = None

    # Legacy fields & probabilities (for backward compatibility)
    id_prob: str = "99.85"
    name_prob: str = "99.72"
    dob_prob: str = "99.90"
    sex_prob: str = "99.80"
    nationality_prob: str = "99.95"
    home: str = "N/A"
    home_prob: str = "98.75"
    address: str = "N/A"
    address_prob: str = "98.92"
    address_entities: AddressEntities = Field(default_factory=AddressEntities)
    doe: str = "N/A"
    doe_prob: str = "99.10"

    # Back-side fields & probabilities
    ethnicity: str = "N/A"
    ethnicity_prob: str = "N/A"
    religion: str = "N/A"
    religion_prob: str = "N/A"
    features: str = "N/A"
    features_prob: str = "N/A"
    issue_date: str = "N/A"
    issue_date_prob: str = "N/A"
    issue_loc: str = "N/A"
    issue_loc_prob: str = "N/A"
    signer: str = "N/A"
    signer_prob: str = "N/A"

    # Digital / Machine-readable data
    mrz: str | None = None
    mrz_prob: str | None = None
    qr_code: str | None = None

    # Card classification
    type: Literal["new", "new_back", "old", "old_back"] = "new"
    type_new: Literal["cccd_12_front", "cmnd_12_front", "cmnd_09_front", "new_back", "old_back"] = "cccd_12_front"



class VietnameseIDCardResponse(BaseModel):
    """Standardized Vietnamese ID Reader response envelope."""
    errorCode: int = 0
    errorMessage: str = ""
    data: list[VietnameseIDCardExtraction] = Field(default_factory=list)


class OCRDocumentRecord(BaseModel):
    """Entity storing OCR document image and extracted structured fields."""
    record_id: str = Field(default_factory=lambda: f"ocr_{uuid.uuid4().hex[:12]}")
    user_id: str = Field(default="admin@company.com")
    tenant_id: str = Field(default="default")
    doc_type: Literal["id_card", "driver_license", "passport", "invoice", "general"] = "id_card"
    image_url: str
    cropped_portrait_url: str | None = None
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    confidence_scores: dict[str, float] = Field(default_factory=dict)
    is_tampered: bool = False
    tamper_warning: str | None = None
    latency_ms: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

