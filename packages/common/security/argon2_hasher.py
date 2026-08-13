import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def generate_api_key(prefix: str = "aip_live_", master_pepper: str = "") -> tuple[str, str]:
    if not prefix.endswith("_"):
        prefix = f"{prefix}_"
    raw_entropy = secrets.token_urlsafe(32)
    raw_key = f"{prefix}{raw_entropy}"
    hashed_key = hash_api_key(raw_key, master_pepper=master_pepper)
    return raw_key, hashed_key


def hash_api_key(raw_key: str, master_pepper: str = "") -> str:
    peppered_input = f"{raw_key}:{master_pepper}" if master_pepper else raw_key
    return ph.hash(peppered_input)


def verify_api_key(raw_key: str, hashed_key: str, master_pepper: str = "") -> bool:
    try:
        peppered_input = f"{raw_key}:{master_pepper}" if master_pepper else raw_key
        return ph.verify(hashed_key, peppered_input)
    except (VerifyMismatchError, VerificationError):
        return False
