import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
load_dotenv(".env")
from common.database.mongodb import mongo_manager

async def compute_timeseries(range_opt="last 1 day", interval_opt="1 hour", mode="quick", from_date=None, to_date=None):
    await mongo_manager.connect()
    db = mongo_manager.get_database()
    now = datetime.now(timezone.utc)
    
    # 1. Determine start_time, end_time, bucket_delta, format string
    if mode == "absolute" and from_date and to_date:
        try:
            start_time = datetime.fromisoformat(from_date.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            start_time = datetime.strptime(from_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        try:
            end_time = datetime.fromisoformat(to_date.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            end_time = datetime.strptime(to_date[:10], "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
    else:
        # Quick or Interval mode
        ro = range_opt.lower().strip()
        if ro == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif ro == "this week":
            start_time = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif ro == "this month":
            start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif ro == "this year":
            start_time = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif ro == "last 5 minutes":
            start_time = now - timedelta(minutes=5)
            end_time = now
        elif ro == "last 15 minutes":
            start_time = now - timedelta(minutes=15)
            end_time = now
        elif ro == "last 30 minutes":
            start_time = now - timedelta(minutes=30)
            end_time = now
        elif ro == "last 45 minutes":
            start_time = now - timedelta(minutes=45)
            end_time = now
        elif ro == "last 1 hour":
            start_time = now - timedelta(hours=1)
            end_time = now
        elif ro == "last 2 hours":
            start_time = now - timedelta(hours=2)
            end_time = now
        elif ro == "last 6 hours":
            start_time = now - timedelta(hours=6)
            end_time = now
        elif ro == "last 12 hours":
            start_time = now - timedelta(hours=12)
            end_time = now
        elif ro in ("last 1 day", "last 24 hours"):
            start_time = now - timedelta(days=1)
            end_time = now
        elif ro == "last 3 days":
            start_time = now - timedelta(days=3)
            end_time = now
        elif ro == "last 7 days":
            start_time = now - timedelta(days=7)
            end_time = now
        elif ro == "last 14 days":
            start_time = now - timedelta(days=14)
            end_time = now
        elif ro in ("last 1 month", "last 30 days"):
            start_time = now - timedelta(days=30)
            end_time = now
        elif ro == "last 3 months":
            start_time = now - timedelta(days=90)
            end_time = now
        elif ro == "last 6 months":
            start_time = now - timedelta(days=180)
            end_time = now
        elif ro in ("last 12 months", "last 1 year"):
            start_time = now - timedelta(days=365)
            end_time = now
        else:
            start_time = now - timedelta(days=1)
            end_time = now

    total_seconds = (end_time - start_time).total_seconds()

    # Determine interval / unit
    io = interval_opt.lower().strip() if interval_opt else ""
    if "min" in io:
        unit = "minute"
        step_seconds = 60
        label_fmt = "%H:%M"
    elif "hour" in io:
        unit = "hour"
        step_seconds = 3600
        label_fmt = "%H:00"
    elif "day" in io:
        unit = "day"
        step_seconds = 86400
        label_fmt = "%d/%m"
    elif "week" in io:
        unit = "week"
        step_seconds = 86400 * 7
        label_fmt = "Wk %W %d/%m"
    elif "month" in io:
        unit = "month"
        step_seconds = 86400 * 30
        label_fmt = "%m/%Y"
    elif "year" in io:
        unit = "year"
        step_seconds = 86400 * 365
        label_fmt = "%Y"
    else:
        # Auto pick interval based on duration
        if total_seconds <= 3600: # <= 1h
            unit = "minute"
            step_seconds = 60
            label_fmt = "%H:%M"
        elif total_seconds <= 86400 * 2: # <= 2 days
            unit = "hour"
            step_seconds = 3600
            label_fmt = "%H:00"
        elif total_seconds <= 86400 * 45: # <= 45 days
            unit = "day"
            step_seconds = 86400
            label_fmt = "%d/%m"
        elif total_seconds <= 86400 * 180: # <= 6 months
            unit = "week"
            step_seconds = 86400 * 7
            label_fmt = "%d/%m"
        else:
            unit = "month"
            step_seconds = 86400 * 30
            label_fmt = "%m/%Y"

    # Query MongoDB aggregation with dateTrunc
    start_iso = start_time.isoformat()
    end_iso = end_time.isoformat()
    
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

    cursor = db.api_logs.aggregate(pipeline)
    buckets_data = await cursor.to_list(length=None)
    data_map = {b["_id"].replace(tzinfo=timezone.utc): b for b in buckets_data}

    # Generate continuous timeline slots
    labels = []
    traffic = []
    errors = []
    latency = []

    curr = start_time
    # Align curr to unit boundary
    if unit == "minute":
        curr = curr.replace(second=0, microsecond=0)
    elif unit == "hour":
        curr = curr.replace(minute=0, second=0, microsecond=0)
    elif unit == "day":
        curr = curr.replace(hour=0, minute=0, second=0, microsecond=0)
    elif unit == "month":
        curr = curr.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Max points cap (e.g. 60 points) so chart is clean
    points_count = 0
    while curr <= end_time and points_count < 100:
        # Match closest bucket within half step
        matched_bucket = None
        for b_time, b_val in data_map.items():
            if abs((b_time - curr).total_seconds()) < step_seconds / 2:
                matched_bucket = b_val
                break

        # Time label formatted for Vietnam timezone UTC+7
        local_curr = curr.astimezone(timezone(timedelta(hours=7)))
        label_str = local_curr.strftime(label_fmt)
        labels.append(label_str)

        if matched_bucket:
            traffic.append(matched_bucket["traffic"])
            errors.append(matched_bucket["errors"])
            latency.append(round(matched_bucket["avg_latency"] or 0, 1))
        else:
            traffic.append(0)
            errors.append(0)
            latency.append(0)

        points_count += 1
        if unit == "month":
            # Advance 1 month
            new_month = curr.month + 1
            new_year = curr.year
            if new_month > 12:
                new_month = 1
                new_year += 1
            curr = curr.replace(year=new_year, month=new_month)
        else:
            curr += timedelta(seconds=step_seconds)

    print(f"--- Range: {range_opt} | Interval: {interval_opt} (Unit: {unit}) ---")
    print(f"Total buckets: {len(labels)}")
    print(f"Labels: {labels[:8]}... (total {len(labels)})")
    print(f"Traffic: {traffic[:8]}... (sum: {sum(traffic)})")
    print(f"Errors: {errors[:8]}... (sum: {sum(errors)})")
    print(f"Latency: {latency[:8]}...")

async def main():
    await compute_timeseries(range_opt="last 1 day", interval_opt="1 hour")
    print("\n")
    await compute_timeseries(range_opt="this month", interval_opt="1 day")
    print("\n")
    await compute_timeseries(range_opt="last 12 months", interval_opt="1 month")

asyncio.run(main())
