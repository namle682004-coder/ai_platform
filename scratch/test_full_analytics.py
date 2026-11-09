import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
load_dotenv(".env")
from common.database.mongodb import mongo_manager

VN_TZ = timezone(timedelta(hours=7))

async def get_analytics_timeseries_logic(
    range_val: str = "last 1 day",
    interval_val: str = None,
    mode: str = "quick",
    from_date: str = None,
    to_date: str = None
):
    await mongo_manager.connect()
    db = mongo_manager.get_database()
    now_utc = datetime.now(timezone.utc)
    now_vn = now_utc.astimezone(VN_TZ)

    # 1. Determine start and end
    if mode == "absolute" and from_date and to_date:
        try:
            start_dt = datetime.strptime(from_date.strip()[:10], "%Y-%m-%d").replace(tzinfo=VN_TZ).astimezone(timezone.utc)
        except Exception:
            start_dt = now_utc - timedelta(days=1)
        try:
            end_dt = datetime.strptime(to_date.strip()[:10], "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=VN_TZ).astimezone(timezone.utc)
        except Exception:
            end_dt = now_utc
    else:
        r = (range_val or "last 1 day").lower().strip()
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

    # 2. Determine Interval unit
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

    # 3. Query Mongo DB
    start_iso = start_dt.isoformat()
    end_iso = end_dt.isoformat()

    pipeline = [
        {"$match": {
            "timestamp": {"$gte": start_iso, "$lte": end_iso}
        }},
        {"$project": {
            "bucket": {
                "$dateTrunc": {
                    "date": {"$toDate": "$timestamp"},
                    "unit": unit
                }
            },
            "status_code": {"$ifNull": ["$status_code", 200]},
            "latency_ms": {"$ifNull": ["$latency_ms", 0.0]}
        }},
        {"$group": {
            "_id": "$bucket",
            "traffic": {"$sum": 1},
            "errors": {
                "$sum": {
                    "$cond": [{"$gte": ["$status_code", 400]}, 1, 0]
                }
            },
            "avg_latency": {"$avg": "$latency_ms"}
        }},
        {"$sort": {"_id": 1}}
    ]

    buckets_data = await db.api_logs.aggregate(pipeline).to_list(None)
    data_map = {}
    for b in buckets_data:
        b_dt = b["_id"]
        if b_dt.tzinfo is None:
            b_dt = b_dt.replace(tzinfo=timezone.utc)
        data_map[b_dt] = b

    # 4. Generate discrete continuous points
    labels = []
    traffic = []
    errors = []
    latency = []

    curr = start_dt
    if unit == "minute":
        curr = curr.replace(second=0, microsecond=0)
    elif unit == "hour":
        curr = curr.replace(minute=0, second=0, microsecond=0)
    elif unit == "day":
        curr = curr.replace(hour=0, minute=0, second=0, microsecond=0)
    elif unit == "month":
        curr = curr.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    loop_count = 0
    while curr <= end_dt and loop_count < 100:
        # Match bucket within half-step tolerance
        matched = None
        for b_time, b_val in data_map.items():
            if abs((b_time - curr).total_seconds()) < step_sec / 2:
                matched = b_val
                break

        vn_curr = curr.astimezone(VN_TZ)
        labels.append(vn_curr.strftime(fmt))

        if matched:
            traffic.append(matched["traffic"])
            errors.append(matched["errors"])
            latency.append(round(matched["avg_latency"] or 0, 1))
        else:
            traffic.append(0)
            errors.append(0)
            latency.append(0)

        loop_count += 1
        if unit == "month":
            nm = curr.month + 1
            ny = curr.year
            if nm > 12:
                nm = 1
                ny += 1
            curr = curr.replace(year=ny, month=nm)
        else:
            curr += timedelta(seconds=step_sec)

    return {
        "range": range_val,
        "interval": interval_val or unit,
        "mode": mode,
        "labels": labels,
        "traffic": traffic,
        "errors": errors,
        "latency": latency,
        "total_traffic": sum(traffic),
        "total_errors": sum(errors),
        "avg_latency": round(sum(latency) / max(1, sum(1 for l in latency if l > 0)), 1)
    }

async def run_checks():
    r1 = await get_analytics_timeseries_logic(range_val="today", interval_val="1 hour")
    print("TODAY:", r1["labels"][:5], "total traffic:", r1["total_traffic"], "total errors:", r1["total_errors"])

    r2 = await get_analytics_timeseries_logic(range_val="last 1 day", interval_val="1 hour")
    print("LAST 1 DAY:", len(r2["labels"]), "buckets. Total traffic:", r2["total_traffic"], "errors:", r2["total_errors"])

    r3 = await get_analytics_timeseries_logic(range_val="last 7 days", interval_val="1 day")
    print("LAST 7 DAYS:", r3["labels"], "traffic:", r3["traffic"])

    r4 = await get_analytics_timeseries_logic(mode="absolute", from_date="2026-09-01", to_date="2026-11-03", interval_val="1 day")
    print("ABSOLUTE 9/1 to 11/3:", len(r4["labels"]), "days. Total traffic:", r4["total_traffic"])

asyncio.run(run_checks())
