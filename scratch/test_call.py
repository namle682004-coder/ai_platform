import requests

def test_api():
    url = "http://172.16.20.2:8000/v1/rag/chat"
    headers = {
        "Content-Type": "application/json",
        "X-User-Id": "user_staff_01",
        "Authorization": "Bearer aip_live_valid_test_key_12345"
    }
    payload = {
        "query": "kiem tra tru token",
        "model": "chat-general-standard"
    }
    r = requests.post(url, headers=headers, json=payload, timeout=10)
    print("Status code:", r.status_code)
    print("Response preview:", r.text[:150])

    # Check balance
    b = requests.get("http://172.16.20.2:8000/v1/user/balance", headers=headers, timeout=10)
    print("Balance after:", b.json())

if __name__ == "__main__":
    test_api()

