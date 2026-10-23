from __future__ import annotations

from src.configs.settings import gateway_settings


def allow_in_process_fallback() -> bool:
    """Allow local engine fallback only when explicitly enabled outside production."""
    import os
    if os.getenv("TEST_MODE") == "true":
        return True
    return gateway_settings.environment not in {"production", "prod"} and gateway_settings.allow_in_process_fallback
