"""
Telemetry Application Service / Use Case.
Orchestrates domain time window resolution and delegates aggregation to Telemetry Repository.
Part of the AIP Platform Control Plane.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from common.interfaces.telemetry import TimeWindow, TelemetrySeriesDTO, ITelemetryRepository
from common.repositories.telemetry_repository import telemetry_repository

VN_TZ = timezone(timedelta(hours=7))


class TelemetryService:
    """Application Use Case for Dashboard Telemetry & Metric Observability."""

    def __init__(self, repo: Optional[ITelemetryRepository] = None):
        self._repo = repo or telemetry_repository

    def resolve_time_window(
        self,
        range_val: Optional[str] = "last 1 day",
        interval_val: Optional[str] = None,
        mode: str = "quick",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> TimeWindow:
        now_utc = datetime.now(timezone.utc)
        now_vn = now_utc.astimezone(VN_TZ)

        # 1. Resolve Start & End Datetime
        if mode == "absolute" and from_date and to_date:
            try:
                start_dt = (
                    datetime.strptime(from_date.strip()[:10], "%Y-%m-%d")
                    .replace(tzinfo=VN_TZ)
                    .astimezone(timezone.utc)
                )
            except Exception:
                start_dt = now_utc - timedelta(days=1)
            try:
                end_dt = (
                    datetime.strptime(to_date.strip()[:10], "%Y-%m-%d")
                    .replace(hour=23, minute=59, second=59, tzinfo=VN_TZ)
                    .astimezone(timezone.utc)
                )
            except Exception:
                end_dt = now_utc
            display_range = f"{from_date} - {to_date}"
        else:
            r = (range_val or "last 1 day").lower().strip()
            display_range = range_val or "last 1 day"
            if r == "today":
                start_dt = now_vn.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
                end_dt = now_utc
            elif r == "this week":
                start_dt = (now_vn - timedelta(days=now_vn.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
                end_dt = now_utc
            elif r == "this month":
                start_dt = now_vn.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
                end_dt = now_utc
            elif r == "this year":
                start_dt = now_vn.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
                end_dt = now_utc
            elif r == "last 5 minutes":
                start_dt = now_utc - timedelta(minutes=5)
                end_dt = now_utc
            elif r == "last 15 minutes":
                start_dt = now_utc - timedelta(minutes=15)
                end_dt = now_utc
            elif r == "last 30 minutes":
                start_dt = now_utc - timedelta(minutes=30)
                end_dt = now_utc
            elif r == "last 45 minutes":
                start_dt = now_utc - timedelta(minutes=45)
                end_dt = now_utc
            elif r == "last 1 hour":
                start_dt = now_utc - timedelta(hours=1)
                end_dt = now_utc
            elif r == "last 2 hours":
                start_dt = now_utc - timedelta(hours=2)
                end_dt = now_utc
            elif r == "last 6 hours":
                start_dt = now_utc - timedelta(hours=6)
                end_dt = now_utc
            elif r == "last 12 hours":
                start_dt = now_utc - timedelta(hours=12)
                end_dt = now_utc
            elif r in ("last 1 day", "last 24 hours"):
                start_dt = now_utc - timedelta(hours=24)
                end_dt = now_utc
            elif r == "last 3 days":
                start_dt = now_utc - timedelta(days=3)
                end_dt = now_utc
            elif r == "last 7 days":
                start_dt = now_utc - timedelta(days=7)
                end_dt = now_utc
            elif r == "last 14 days":
                start_dt = now_utc - timedelta(days=14)
                end_dt = now_utc
            elif r in ("last 1 month", "last 30 days"):
                start_dt = now_utc - timedelta(days=30)
                end_dt = now_utc
            elif r == "last 3 months":
                start_dt = now_utc - timedelta(days=90)
                end_dt = now_utc
            elif r == "last 6 months":
                start_dt = now_utc - timedelta(days=180)
                end_dt = now_utc
            elif r in ("last 12 months", "last 1 year"):
                start_dt = now_utc - timedelta(days=365)
                end_dt = now_utc
            else:
                start_dt = now_utc - timedelta(hours=24)
                end_dt = now_utc

        duration_sec = max(1.0, (end_dt - start_dt).total_seconds())

        # 2. Resolve Interval Unit & Step
        iv = (interval_val or "").lower().strip()
        if "min" in iv:
            unit = "minute"
            step_sec = 60
            fmt = "%H:%M"
        elif "hour" in iv:
            unit = "hour"
            step_sec = 3600
            fmt = "%H:00"
        elif "day" in iv:
            unit = "day"
            step_sec = 86400
            fmt = "%d/%m"
        elif "week" in iv:
            unit = "week"
            step_sec = 86400 * 7
            fmt = "%d/%m"
        elif "month" in iv:
            unit = "month"
            step_sec = 86400 * 30
            fmt = "%m/%Y"
        elif "year" in iv:
            unit = "year"
            step_sec = 86400 * 365
            fmt = "%Y"
        else:
            if duration_sec <= 3600:
                unit = "minute"
                step_sec = 60
                fmt = "%H:%M"
            elif duration_sec <= 86400 * 2:
                unit = "hour"
                step_sec = 3600
                fmt = "%H:00"
            elif duration_sec <= 86400 * 45:
                unit = "day"
                step_sec = 86400
                fmt = "%d/%m"
            elif duration_sec <= 86400 * 180:
                unit = "week"
                step_sec = 86400 * 7
                fmt = "%d/%m"
            else:
                unit = "month"
                step_sec = 86400 * 30
                fmt = "%m/%Y"

        return TimeWindow(
            start_time=start_dt,
            end_time=end_dt,
            interval_unit=unit,
            step_seconds=step_sec,
            label_format=fmt,
            display_range=display_range,
            mode=mode,
        )

    async def get_dashboard_telemetry(
        self,
        range_val: Optional[str] = "last 1 day",
        interval_val: Optional[str] = None,
        mode: str = "quick",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> TelemetrySeriesDTO:
        window = self.resolve_time_window(
            range_val=range_val,
            interval_val=interval_val,
            mode=mode,
            from_date=from_date,
            to_date=to_date,
        )
        return await self._repo.get_time_series_metrics(
            window=window,
            tenant_id=tenant_id,
            user_id=user_id,
        )


telemetry_service = TelemetryService()
