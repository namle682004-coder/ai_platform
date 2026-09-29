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
    print("\n=== 4. HTTP ROUTING BY PROJECT & API ID ===")
    client = TestClient(app)

    # 1. Exact URL from user's example
    user_url = "/project/f40b6a70-ea64-4d01-90dc-53a2d7a81395/apis/efb24a03-059d-440c-bd35-0b5b3a776983"
    res1 = client.get(user_url)
    print(f"  GET {user_url} -> Status: {res1.status_code}, Content-Type: {res1.headers.get('content-type')}")
    assert res1.status_code == 200
    assert "text/html" in res1.headers.get("content-type")

    # 2. Staff prefix variant
    staff_url = "/staff/project/f40b6a70-ea64-4d01-90dc-53a2d7a81395/apis/efb24a03-059d-440c-bd35-0b5b3a776983"
    res2 = client.get(staff_url)
    print(f"  GET {staff_url} -> Status: {res2.status_code}")
    assert res2.status_code == 200

    # 3. Project APIs catalog
    catalog_url = "/project/f40b6a70-ea64-4d01-90dc-53a2d7a81395/apis"
    res3 = client.get(catalog_url)
    print(f"  GET {catalog_url} -> Status: {res3.status_code}")
    assert res3.status_code == 200

    # 4. Backward-compatible redirect from old name to new ID format
    legacy_url = "/staff/service-llm"
    res4 = client.get(legacy_url, follow_redirects=False)
    target_loc = res4.headers.get("location")
    print(f"  GET {legacy_url} (Legacy) -> Status: {res4.status_code}, Redirects to: {target_loc}")
    assert res4.status_code == 302
    assert target_loc == user_url

    print("\n[ALL TESTS PASSED SUCCESSFULLY!]")


if __name__ == "__main__":
    test_repo()
    test_http_routes()
