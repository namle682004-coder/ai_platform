from __future__ import annotations

from src.configs.settings import gateway_settings


def runtime_headers(authorization: str | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
    if gateway_settings.runtime_token:
        headers["X-AIP-Runtime-Token"] = gateway_settings.runtime_token.get_secret_value()
    return headers


def runtime_token_headers() -> dict[str, str]:
    if gateway_settings.runtime_token:
        return {"X-AIP-Runtime-Token": gateway_settings.runtime_token.get_secret_value()}
    return {}