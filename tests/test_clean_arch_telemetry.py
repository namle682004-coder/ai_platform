"""
Unit and Integration Tests for Clean Architecture Telemetry Control Plane.
"""

from datetime import datetime, timezone, timedelta
from common.interfaces.telemetry import TimeWindow, TelemetrySeriesDTO
from common.repositories.telemetry_repository import MongoTelemetryRepository
from src.services.telemetry_service import TelemetryService


def test_time_window_creation():
    now = datetime.now(timezone.utc)
    tw = TimeWindow(
        start_time=now - timedelta(days=1),
        end_time=now,
        interval_unit="hour",
        step_seconds=3600,
        label_format="%H:00",
        display_range="last 1 day",
        mode="quick",
    )
    assert tw.interval_unit == "hour"
    assert tw.step_seconds == 3600
    assert (tw.end_time - tw.start_time).total_seconds() == 86400


def test_telemetry_service_quick_resolution():
    svc = TelemetryService()
    tw_today = svc.resolve_time_window(range_val="today", mode="quick")
    assert tw_today.interval_unit == "hour"

    tw_month = svc.resolve_time_window(range_val="this month", mode="quick")
    assert tw_month.interval_unit == "day"

    tw_year = svc.resolve_time_window(range_val="last 12 months", mode="quick")
    assert tw_year.interval_unit == "month"


def test_telemetry_service_interval_resolution():
    svc = TelemetryService()
    tw_min = svc.resolve_time_window(range_val="last 1 hour", interval_val="1 minute", mode="interval")
    assert tw_min.interval_unit == "minute"
    assert tw_min.step_seconds == 60

    tw_day = svc.resolve_time_window(range_val="last 14 days", interval_val="1 day", mode="interval")
    assert tw_day.interval_unit == "day"
    assert tw_day.step_seconds == 86400


def test_telemetry_repository_mock_or_live():
    import asyncio
    repo = MongoTelemetryRepository()
    svc = TelemetryService(repo=repo)
    dto = asyncio.run(svc.get_dashboard_telemetry(range_val="last 1 day", interval_val="1 hour", mode="quick"))

    assert isinstance(dto, TelemetrySeriesDTO)
    assert dto.range == "last 1 day"
    assert len(dto.labels) > 0
    assert len(dto.traffic) == len(dto.labels)
    assert len(dto.errors) == len(dto.labels)
    assert len(dto.latency) == len(dto.labels)
    assert dto.total_traffic >= 0
    assert dto.total_errors >= 0
