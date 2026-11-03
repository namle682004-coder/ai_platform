"""
MongoDB Atlas Implementation for Telemetry and Observability Metrics Repository.
Part of the AIP Platform Control Plane.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from common.database.mongodb import mongo_manager
from common.interfaces.telemetry import ITelemetryRepository, TimeWindow, TelemetrySeriesDTO

VN_TIMEZONE = timezone(timedelta(hours=7))


class MongoTelemetryRepository(ITelemetryRepository):
    """Aggregates real-time telemetry time-series from MongoDB api_logs collection."""

    async def get_time_series_metrics(
        self,
        window: TimeWindow,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> TelemetrySeriesDTO:
        db = mongo_manager.get_database()
        data_map: Dict[datetime, dict] = {}

        if db is not None:
            try:
                start_iso = window.start_time.isoformat()
                end_iso = window.end_time.isoformat()

                match_stage: Dict = {
                    "timestamp": {"$gte": start_iso, "$lte": end_iso}
                }
                if tenant_id and tenant_id not in ("global", "all"):
                    match_stage["tenant_id"] = tenant_id
                if user_id and user_id not in ("global", "all"):
                    match_stage["user_id"] = user_id

                pipeline = [
                    {"$match": match_stage},
                    {
                        "$project": {
                            "bucket": {
                                "$dateTrunc": {
                                    "date": {"$toDate": "$timestamp"},
                                    "unit": window.interval_unit,
                                }
                            },
                            "status_code": {"$ifNull": ["$status_code", 200]},
                            "latency_ms": {"$ifNull": ["$latency_ms", 0.0]},
                        }
                    },
                    {
                        "$group": {
                            "_id": "$bucket",
                            "traffic": {"$sum": 1},
                            "errors": {
                                "$sum": {
                                    "$cond": [
                                        {"$gte": ["$status_code", 400]},
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "avg_latency": {"$avg": "$latency_ms"},
                        }
                    },
                    {"$sort": {"_id": 1}},
                ]

                buckets_data = await db.api_logs.aggregate(pipeline).to_list(None)
                for b in buckets_data:
                    b_dt = b["_id"]
                    if b_dt.tzinfo is None:
                        b_dt = b_dt.replace(tzinfo=timezone.utc)
                    data_map[b_dt] = b
            except Exception:
                pass

        # Discrete Continuous Timeline Synthesis (Zero-Filling)
        labels = []
        traffic = []
        errors = []
        latency = []

        curr = window.start_time
        if window.interval_unit == "minute":
            curr = curr.replace(second=0, microsecond=0)
        elif window.interval_unit == "hour":
            curr = curr.replace(minute=0, second=0, microsecond=0)
        elif window.interval_unit == "day":
            curr = curr.replace(hour=0, minute=0, second=0, microsecond=0)
        elif window.interval_unit == "month":
            curr = curr.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        loop_count = 0
        while curr <= window.end_time and loop_count < 100:
            matched = None
            for b_time, b_val in data_map.items():
                if abs((b_time - curr).total_seconds()) < window.step_seconds / 2:
                    matched = b_val
                    break

            local_curr = curr.astimezone(VN_TIMEZONE)
            labels.append(local_curr.strftime(window.label_format))

            if matched:
                traffic.append(matched["traffic"])
                errors.append(matched["errors"])
                latency.append(round(matched["avg_latency"] or 0, 1))
            else:
                traffic.append(0)
                errors.append(0)
                latency.append(0)

            loop_count += 1
            if window.interval_unit == "month":
                new_month = curr.month + 1
                new_year = curr.year
                if new_month > 12:
                    new_month = 1
                    new_year += 1
                curr = curr.replace(year=new_year, month=new_month)
            else:
                curr += timedelta(seconds=window.step_seconds)

        total_traffic = sum(traffic)
        total_errors = sum(errors)
        positive_latencies = [lat for lat in latency if lat > 0]
        avg_latency = (
            round(sum(positive_latencies) / len(positive_latencies), 1)
            if positive_latencies
            else 0.0
        )

        return TelemetrySeriesDTO(
            range=window.display_range,
            interval=window.interval_unit,
            mode=window.mode,
            labels=labels,
            traffic=traffic,
            errors=errors,
            latency=latency,
            total_traffic=total_traffic,
            total_errors=total_errors,
            avg_latency=avg_latency,
        )


telemetry_repository = MongoTelemetryRepository()

