"""
Data sources read directly by connectors (internal websites, JSON APIs), as opposed to uploaded files.

A connector turns a source into `SourceItem`s; the sync use case turns those into ordinary documents of the
knowledge base. See solutions/rag/CONNECTORS.md.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Dict, List, Optional

_OFFSET = re.compile(r"^(?:UTC|GMT)?\s*([+-])(\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE)
_ISO_WITH_ZONE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})$")


def resolve_timezone(name: Optional[str]) -> Optional[tzinfo]:
    """'+07:00', 'UTC+7' or an IANA name ('Asia/Ho_Chi_Minh', needs tz data); None when not understood."""
    text = (name or "").strip()
    if not text:
        return None
    m = _OFFSET.match(text)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0)))
    if text.upper() in ("UTC", "Z", "GMT"):
        return timezone.utc
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(text)
    except Exception:  # noqa: BLE001 - unknown name or no tz data in the image
        return None


def local_datetime(value: Any, tz: Optional[tzinfo]) -> Optional[datetime]:
    """An ISO-8601 date-time that states its zone, in `tz`; None for anything else (left as it is)."""
    if tz is None or not isinstance(value, str) or not _ISO_WITH_ZONE.match(value.strip()):
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).astimezone(tz)
    except ValueError:
        return None


@dataclass
class SourceItem:
    """One unit read from a source, with a key that stays the same across syncs."""

    key: str  # stable identity in the source (record id, canonical URL)
    kind: str  # "record" (structured row) | "page" (HTML) | "file" (pdf / docx / xlsx …)
    title: str = ""
    url: str = ""
    data: Dict[str, Any] = field(default_factory=dict)  # kind == "record"
    content: bytes = b""  # kind in ("page", "file")
    filename: str = ""  # kind in ("page", "file"): name the parser dispatches on (extension)
    partition: str = ""  # kind == "record": records of one partition form one document


@dataclass
class FetchResult:
    items: List[SourceItem]
    cursor: Dict[str, Any] = field(default_factory=dict)  # persisted, handed back on the next sync
    complete: bool = False  # the whole source was read: what is missing has been removed from it
    errors: List[str] = field(default_factory=list)


class ConnectorPort(ABC):
    @abstractmethod
    async def fetch(self, source: Dict[str, Any], cursor: Dict[str, Any]) -> FetchResult:
        ...


class SourceRepositoryPort(ABC):
    """Source configurations, their records (structured sources) and their sync runs."""

    @abstractmethod
    async def create(self, source: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def get(self, source_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def list(self, tenant_id: str) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def update(self, source_id: str, tenant_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def delete(self, source_id: str, tenant_id: str) -> bool: ...

    @abstractmethod
    async def due(self, now: float, limit: int = 20) -> List[Dict[str, Any]]:
        """Enabled sources whose next sync time has passed."""

    @abstractmethod
    async def acquire(self, source_id: str, owner: str, now: float, ttl: float) -> bool:
        """Take the sync lease of a source; False when another process holds it."""

    @abstractmethod
    async def release(self, source_id: str, owner: str, fields: Dict[str, Any]) -> None:
        """Give the lease back and store the run's outcome (cursor, last run, next sync time)."""

    @abstractmethod
    async def upsert_records(self, source_id: str, items: List[SourceItem], hashes: Dict[str, str]) -> Dict[str, str]:
        """Store records; returns {key: partition} of the records that are new or changed."""

    @abstractmethod
    async def remove_records_except(self, source_id: str, keep: List[str]) -> Dict[str, str]:
        """Delete the records not in `keep`; returns {key: partition} of those removed."""

    @abstractmethod
    async def records_of(self, source_id: str, partition: str) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def add_run(self, run: Dict[str, Any]) -> None: ...

    @abstractmethod
    async def runs(self, source_id: str, limit: int = 20) -> List[Dict[str, Any]]: ...
