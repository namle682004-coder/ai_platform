"""
Domain Interface / Port for Telemetry and Metric Aggregation.
Part of the AIP Platform Control Plane Observability Fabric.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class TimeWindow:
    """Domain Value Object defining a continuous time query window."""

    start_time: datetime
    end_time: datetime
    interval_unit: str  # "minute" | "hour" | "day" | "week" | "month" | "year"
    step_seconds: int
    label_format: str
    display_range: str
    mode: str = "quick"


@dataclass
class TelemetrySeriesDTO:
    """Domain Data Transfer Object for time-series charts."""

    range: str
    interval: str
    mode: str
    labels: List[str] = field(default_factory=list)
    traffic: List[int] = field(default_factory=list)
    errors: List[int] = field(default_factory=list)
    latency: List[float] = field(default_factory=list)
    total_traffic: int = 0
    total_errors: int = 0
    avg_latency: float = 0.0


class ITelemetryRepository(ABC):
    """Abstract Repository Port for Telemetry and Observability Metrics."""

    @abstractmethod
    async def get_time_series_metrics(
        self,
        window: TimeWindow,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> TelemetrySeriesDTO:
        """Aggregate traffic, errors, and latency within window with continuous zero-filling."""
        pass

