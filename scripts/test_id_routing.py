import asyncio
from common.repositories.endpoint_repository import endpoint_repository, DEFAULT_ENDPOINTS
from fastapi.testclient import TestClient
from src.main import app

def test_repo():
    asyncio.run(_test_repo())

async def _test_repo():
    print("=== 1. DEFAULT_ENDPOINTS UUID VERIFICATION ===")
    print(f"Total default endpoints: {len(DEFAULT_ENDPOINTS)}")
    for ep in DEFAULT_ENDPOINTS:
        print(f"  {ep.get('id')} -> {ep.get('name')} [{ep.get('api_id')}]")

    print("\n=== 2. RETRIEVAL BY UUID efb24a03-059d-440c-bd35-0b5b3a776983 ===")
    target_uuid = "efb24a03-059d-440c-bd35-0b5b3a776983"
    found = await endpoint_repository.get_endpoint_by_id(target_uuid)
    assert found is not None, f"Could not find endpoint with UUID {target_uuid}"
    print(f"  [OK] Name: {found.get('name')}")
    print(f"  [OK] Endpoint: {found.get('endpoint_id')}")
    print(f"  [OK] API ID: {found.get('api_id')}")
    print(f"  [OK] Status: {found.get('status')}")

    print("\n=== 3. RETRIEVAL OF ALL 13 APIS BY UUID ===")
    for ep in DEFAULT_ENDPOINTS:
        ep_id = ep.get('id')
        retrieved = await endpoint_repository.get_endpoint_by_id(ep_id)
        assert retrieved is not None, f"Failed lookup for {ep_id}"
        assert retrieved.get('name') == ep.get('name'), f"Mismatch for {ep_id}"
    print("  [OK] All 13 APIs successfully verified by unique UUID!")


def test_http_routes():
    print("
=== 4. HTTP ROUTING: /projects/{project}/services/{service} ===")
    client = TestClient(app)

    canonical = "/projects/shared/services/llm-chat"
    res1 = client.get(canonical)
    print(f"  GET {canonical} -> Status: {res1.status_code}")
    assert res1.status_code == 200 and "text/html" in res1.headers.get("content-type")

    # Former scheme (project UUID + endpoint UUID) answers 301 to the canonical URL.
    legacy = "/project/global/apis/efb24a03-059d-440c-bd35-0b5b3a776983"
    res2 = client.get(legacy, follow_redirects=False)
    print(f"  GET {legacy} -> {res2.status_code} {res2.headers.get('location')}")
    assert res2.status_code == 301 and res2.headers.get("location") == canonical

    catalog = "/projects/shared/services"
    assert client.get(catalog).status_code == 200

    legacy_name = "/staff/service-llm"
    res4 = client.get(legacy_name, follow_redirects=False)
    print(f"  GET {legacy_name} (Legacy) -> {res4.status_code} {res4.headers.get('location')}")
    assert res4.status_code == 301 and res4.headers.get("location") == "/services/llm-chat"

    print("
[ALL TESTS PASSED SUCCESSFULLY!]")


if __name__ == "__main__":
    test_repo()
    test_http_routes()
