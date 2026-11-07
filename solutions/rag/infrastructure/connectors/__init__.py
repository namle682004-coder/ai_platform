"""Connectors reading data sources directly (see solutions/rag/CONNECTORS.md)."""

from typing import Optional

import httpx

from ...domain.sources import ConnectorPort
from .http import ConnectorError
from .json_api import JsonApiConnector
from .web import WebConnector

SOURCE_TYPES = ("json_api", "web")


def build_connector(source_type: str, transport: Optional[httpx.AsyncBaseTransport] = None) -> ConnectorPort:
    if source_type == "json_api":
        return JsonApiConnector(transport)
    if source_type == "web":
        return WebConnector(transport)
    raise ConnectorError(f"unknown source type {source_type!r} (expected one of {SOURCE_TYPES})")


__all__ = ["SOURCE_TYPES", "ConnectorError", "JsonApiConnector", "WebConnector", "build_connector"]
