"""
Comprehensive Tests for Vietnamese ID Card Recognition (CCCD/CMND).
Verifies:
1. All extracted fields from Vietnamese ID Card Recognition (Front & Back, 12-digit & 9-digit).
2. Probabilities (_prob) on every recognized field.
3. 4-tier Address Normalization (address_entities: province, district, ward, street).
4. Error codes (errorCode 0, 400 validation).
"""

import io
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)
VALID_KEY = "aip_live_valid_test_key_12345"
AUTH_HEADERS = {"Authorization": f"Bearer {VALID_KEY}"}

# Realistic minimal 1x1 PNG bytes
VALID_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_cccd_12_front_side_fields():
    """Verify all front-side CCCD fields and probabilities."""
    files = {"image": ("cccd_front.png", io.BytesIO(VALID_PNG_BYTES + b"_front_cccd"), "image/png")}
    data = {"side": "front", "card_type": "new"}

    resp = client.post("/v1/ocr/id-card", files=files, data=data, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    res = resp.json()
    assert res["errorCode"] == 0
    assert res["errorMessage"] == ""

    card = res["data"]
    # Check Core Fields
    assert card["id"] == "001095012345"
    assert float(card["id_prob"]) > 90
    assert card["name"] == "TRẦN THỊ B"
    assert float(card["name_prob"]) > 90
    assert card["dob"] == "15/08/1995"
    assert float(card["dob_prob"]) > 90
    assert card["sex"] == "NỮ"
    assert float(card["sex_prob"]) > 90
    assert card["nationality"] == "Việt Nam"
    assert float(card["nationality_prob"]) > 90
    assert "Duy Tân" in card["address"]
    assert float(card["address_prob"]) > 90
    assert float(card["home_prob"]) > 90
    assert card["doe"] == "15/08/2035"
    assert float(card["doe_prob"]) > 90

    # Check 4-tier Address Entities
    addr_entities = card["address_entities"]
    assert "Hà Nội" in addr_entities["province"]
    assert "Cầu Giấy" in addr_entities["district"]
    assert "Dịch Vọng Hậu" in addr_entities["ward"]
    assert "Duy Tân" in addr_entities["street"]

    # Check Card Classification
    assert card["type"] == "new"
    assert card["type_new"] == "cccd_12_front"

    # Check Backward Compatibility legacy fields
    assert card["id_number"] == card["id"]
    assert card["full_name"] == card["name"]


def test_cccd_12_back_side_fields():
    """Verify all back-side CCCD fields (features, issue_date, MRZ)."""
    files = {"image": ("cccd_back.png", io.BytesIO(VALID_PNG_BYTES + b"_back_cccd"), "image/png")}
    data = {"side": "back", "card_type": "new"}

    resp = client.post("/v1/ocr/id-card", files=files, data=data, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    res = resp.json()
    assert res["errorCode"] == 0

    card = res["data"]
    assert card["type"] == "new_back"
    assert card["type_new"] == "new_back"
    assert "Nốt ruồi" in card["features"]
    assert float(card["features_prob"]) > 90
    assert card["issue_date"] == "10/10/2021"
    assert float(card["issue_date_prob"]) > 90
    assert "CẢNH SÁT" in card["issue_loc"]

    # In new CCCD back side, ethnicity & religion are N/A (chip-embedded)
    assert card["ethnicity"] == "N/A"
    assert card["religion"] == "N/A"

    # MRZ check
    assert card["mrz"] is not None
    assert "IDVNM" in card["mrz"]
    assert float(card["mrz_prob"]) > 90


def test_old_cmnd_09_front_and_back():
    """Verify 9-digit old CMND front & back specific field rules."""
    # 1. Old Front: sex, nationality, doe are N/A in old 9-digit CMND
    files_front = {"image": ("cmnd_old_front.png", io.BytesIO(VALID_PNG_BYTES + b"_old_f"), "image/png")}
    resp_front = client.post(
        "/v1/ocr/id-card",
        files=files_front,
        data={"side": "front", "card_type": "old"},
        headers=AUTH_HEADERS,
    )
    assert resp_front.status_code == 200
    card_front = resp_front.json()["data"]
    assert card_front["type"] == "old"
    assert card_front["type_new"] == "cmnd_09_front"
    assert len(card_front["id"]) == 9
    assert card_front["sex"] == "N/A"
    assert card_front["nationality"] == "N/A"
    assert card_front["doe"] == "N/A"

    # 2. Old Back: ethnicity & religion are present on the back
    files_back = {"image": ("cmnd_old_back.png", io.BytesIO(VALID_PNG_BYTES + b"_old_b"), "image/png")}
    resp_back = client.post(
        "/v1/ocr/id-card",
        files=files_back,
        data={"side": "back", "card_type": "old"},
        headers=AUTH_HEADERS,
    )
    assert resp_back.status_code == 200
    card_back = resp_back.json()["data"]
    assert card_back["type"] == "old_back"
    assert card_back["type_new"] == "old_back"
    assert card_back["ethnicity"] == "Kinh"
    assert float(card_back["ethnicity_prob"]) > 90
    assert card_back["religion"] == "Không"
    assert float(card_back["religion_prob"]) > 90
    assert card_back["issue_date"] == "20/04/2012"
    assert "HÀ NAM" in card_back["issue_loc"]


def test_error_handling():
    """Verify validation and error handling."""
    # Invalid image file (text file passed instead of image) -> errorCode 7
    invalid_file = {"image": ("test.txt", io.BytesIO(b"Hello this is not an image"), "text/plain")}
    resp = client.post("/v1/ocr/id-card", files=invalid_file, headers=AUTH_HEADERS)
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == 7
    assert resp.json()["data"] == []
