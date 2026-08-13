from common.security.argon2_hasher import generate_api_key, verify_api_key


def test_argon2_key_generation_and_verification():
    raw_key, hashed_key = generate_api_key(prefix="aip_test", master_pepper="secret_pepper")
    assert raw_key.startswith("aip_test_")
    assert len(hashed_key) > 0
    assert verify_api_key(raw_key, hashed_key, master_pepper="secret_pepper") is True
    assert verify_api_key(raw_key, hashed_key, master_pepper="wrong_pepper") is False
