import requests

with open("/tmp/hop_ngay_310.txt", "rb") as f:
    files = {"file": ("hop_ngay_310_global.txt", f, "text/plain")}
    data = {"title": "họp ngày 3/10 - Tỉnh Cao Bằng (Toàn hệ thống)", "department": "GENERAL"}
    headers = {
        "Authorization": "Bearer aip_live_valid_test_key_12345",
        "X-Tenant-Id": "global",
        "X-Tenant-ID": "global"
    }

    res = requests.post("http://172.16.20.2:8000/v1/knowledge/documents/upload?wait_for_completion=true", files=files, data=data, headers=headers)
    print("Status:", res.status_code)
    print("Response:", res.text)

