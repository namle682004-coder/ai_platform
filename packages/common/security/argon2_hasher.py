import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32)


def generate_api_key(prefix: str = "aip_live", master_pepper: str = "") -> tuple[str, str]:
    entropy = secrets.token_hex(32)
    raw_key = f"{prefix}_{entropy}"
    peppered_input = f"{raw_key}:{master_pepper}" if master_pepper else raw_key
    hashed_key = ph.hash(peppered_input)
    return raw_key, hashed_key


def verify_api_key(raw_key: str, hashed_key: str, master_pepper: str = "") -> bool:
    try:
        peppered_input = f"{raw_key}:{master_pepper}" if master_pepper else raw_key
        return ph.verify(hashed_key, peppered_input)
    except (VerifyMismatchError, Exception):
        return False
