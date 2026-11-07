"""
HTTP access of connectors to a customer's systems, with the guard rails a server-side fetcher needs:

- only the hosts declared for the source (and http / https) are contacted; redirects are followed by hand
  and refused when they leave those hosts (no SSRF through an open redirect);
- credentials come from environment variables whose name starts with the configured prefix, never from the
  database, so a source configuration cannot read the service's own secrets;
- every response is read with a size limit and a timeout; requests to one source are spaced;
- 429 / 503 / 5xx are retried with back-off, honouring Retry-After.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlsplit

import httpx

from ...config import rag_settings

logger = logging.getLogger("aip-rag.connector.http")

USER_AGENT = "AIP-RAG-Connector/1.0"
RETRY_STATUSES = {429, 502, 503, 504}
MAX_REDIRECTS = 5


class ConnectorError(Exception):
    """A source cannot be read (configuration, access, limits)."""


@dataclass
class FetchedResponse:
    url: str
    status: int
    headers: Dict[str, str]
    content: bytes

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()

    def json(self) -> Any:
        import json

        return json.loads(self.content.decode("utf-8"))


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def auth_headers(auth: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Headers for the source's credentials, read from the environment (see module docstring)."""
    auth = auth or {}
    kind = (auth.get("type") or "none").lower()
    if kind == "none":
        return {}
    prefix = rag_settings.connector_secret_env_prefix

    def secret(name_key: str) -> str:
        name = str(auth.get(name_key) or "")
        if not name.startswith(prefix):
            raise ConnectorError(f"auth.{name_key} must name an environment variable starting with {prefix}")
        value = os.getenv(name, "")
        if not value:
            raise ConnectorError(f"environment variable {name} is not set on this server")
        return value

    if kind == "bearer":
        return {"Authorization": f"Bearer {secret('token_env')}"}
    if kind == "header":
        header = str(auth.get("header") or "").strip()
        if not header or header.lower() in ("host", "cookie", "content-length"):
            raise ConnectorError("auth.header must name a request header")
        return {header: secret("token_env")}
    if kind == "basic":
        user = str(auth.get("username") or "")
        pair = f"{user}:{secret('password_env')}".encode()
        return {"Authorization": "Basic " + base64.b64encode(pair).decode()}
    if kind == "cookie":
        return {"Cookie": secret("token_env")}
    raise ConnectorError(f"unknown auth.type {kind!r}")


class SourceHttp:
    """One source's HTTP session (allowed hosts, credentials, pacing, limits)."""

    def __init__(self, source: Dict[str, Any], transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        cfg = source.get("config") or {}
        self.allowed_hosts = {h.lower() for h in cfg.get("allowed_hosts") or []}
        if not self.allowed_hosts:
            raise ConnectorError("config.allowed_hosts is required")
        self.headers = {"User-Agent": USER_AGENT, **auth_headers(source.get("auth"))}
        self.headers.update({k: str(v) for k, v in (cfg.get("headers") or {}).items()
                             if k.lower() not in ("authorization", "cookie", "host")})
        self.delay = max(float(cfg.get("delay_seconds") or 0), rag_settings.connector_min_delay_seconds)
        self.max_bytes = min(int(cfg.get("max_response_bytes") or rag_settings.connector_max_response_bytes),
                             rag_settings.connector_max_response_bytes)
        self.retries = max(0, min(5, int(cfg.get("retries", 2))))
        self.client = httpx.AsyncClient(
            timeout=rag_settings.connector_timeout_seconds, follow_redirects=False,
            verify=bool(cfg.get("verify_tls", True)), transport=transport,
        )
        if not cfg.get("verify_tls", True):
            logger.warning("Source %s: TLS certificate verification is disabled", source.get("source_id"))
        self._last = 0.0
        self.requests = 0

    def check(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            raise ConnectorError(f"only http / https URLs are read: {url}")
        if host_of(url) not in self.allowed_hosts:
            raise ConnectorError(f"host {host_of(url)!r} is not in config.allowed_hosts")

    async def _pace(self) -> None:
        wait = self._last + self.delay - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = time.monotonic()

    async def get(self, url: str, params: Optional[Dict[str, Any]] = None,
                  accept: Optional[List[str]] = None) -> FetchedResponse:
        """GET with redirects checked against the allowed hosts; raises ConnectorError on failure."""
        current, attempt, redirects = url, 0, 0
        while True:
            self.check(current)
            await self._pace()
            self.requests += 1
            try:
                async with self.client.stream("GET", current, params=params, headers=self.headers) as res:
                    if res.status_code in (301, 302, 303, 307, 308) and res.headers.get("location"):
                        redirects += 1
                        if redirects > MAX_REDIRECTS:
                            raise ConnectorError(f"{url}: more than {MAX_REDIRECTS} redirects")
                        current, params = urljoin(current, res.headers["location"]), None
                        continue
                    if res.status_code in RETRY_STATUSES and attempt < self.retries:
                        attempt += 1
                        try:
                            retry_after = float(res.headers.get("retry-after", "") or 0)
                        except ValueError:
                            retry_after = 0.0
                        await asyncio.sleep(min(60.0, max(retry_after, 2.0 ** attempt)))
                        continue
                    ctype = res.headers.get("content-type", "").split(";")[0].strip().lower()
                    if accept and res.status_code == 200 and not any(ctype.startswith(a) for a in accept):
                        return FetchedResponse(str(res.url), res.status_code, dict(res.headers), b"")
                    declared = int(res.headers.get("content-length") or 0)
                    if declared > self.max_bytes:
                        raise ConnectorError(f"{current}: {declared} bytes > limit {self.max_bytes}")
                    body = bytearray()
                    async for chunk in res.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self.max_bytes:
                            raise ConnectorError(f"{current}: response larger than {self.max_bytes} bytes")
                    if res.status_code >= 400:
                        raise ConnectorError(f"{current}: HTTP {res.status_code}")
                    return FetchedResponse(str(res.url), res.status_code, {k.lower(): v for k, v in res.headers.items()},
                                           bytes(body))
            except httpx.HTTPError as exc:
                if attempt < self.retries:
                    attempt += 1
                    await asyncio.sleep(2.0 ** attempt)
                    continue
                raise ConnectorError(f"{current}: {type(exc).__name__}: {exc}") from exc

    async def close(self) -> None:
        await self.client.aclose()
