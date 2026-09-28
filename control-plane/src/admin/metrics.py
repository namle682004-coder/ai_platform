from datetime import datetime
from fastapi import APIRouter

router = APIRouter(prefix="/admin/v1", tags=["Admin - Realtime Metrics"])

_CALL_STATS = [
    {
        "alias_name": "chat-general-standard",
        "in_flight_requests": 3,
        "rps": 12.5,
        "avg_latency_ms": 124.5,
        "last_called_at": datetime.utcnow().isoformat(),
    },
    {
        "alias_name": "embed-standard",
        "in_flight_requests": 1,
        "rps": 45.0,
        "avg_latency_ms": 18.2,
        "last_called_at": datetime.utcnow().isoformat(),
    },
    {
        "alias_name": "stt-vn-standard",
        "in_flight_requests": 0,
        "rps": 0.0,
        "avg_latency_ms": 450.0,
        "last_called_at": datetime.utcnow().isoformat(),
    },
]


@router.get("/metrics", summary="Get Active In-Flight Calls & Realtime Traffic Metrics")
async def get_active_calls_metrics():
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "total_active_inflight": sum(item["in_flight_requests"] for item in _CALL_STATS),
        "data": _CALL_STATS,
    }
