from aip_sdk import AIPClient


def test_sdk_client_initialization():
    client = AIPClient(api_key="aip_live_testkey123", base_url="http://localhost:8000")
    assert client.api_key == "aip_live_testkey123"
    assert client.headers["Authorization"] == "Bearer aip_live_testkey123"
