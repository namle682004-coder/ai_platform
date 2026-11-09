import requests
import json

payload = {
    "query": "tỉnh cao bằng kết hợp làm dự án có những mục tiêu nào",
    "model": "chat-general-standard",
    "stream": False
}
headers = {
    "Authorization": "Bearer aip_live_valid_test_key_12345",
    "Content-Type": "application/json"
}

res = requests.post("http://172.16.20.2:8000/v1/rag/chat", json=payload, headers=headers)
print("Status:", res.status_code)
print("Response:", res.text)
