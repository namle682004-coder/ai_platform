from fastapi import APIRouter
from .resource_manager_service import resource_manager
from .telemetry import get_gpu_telemetry

router = APIRouter(prefix="/admin/v1/resources", tags=["Admin - Hardware & Node Resources"])


@router.get("/gpu", summary="Get Live GPU Hardware Telemetry")
async def get_gpu_resources():
    return get_gpu_telemetry()


@router.get("/capacity", summary="Get Cluster Node Capacity & Workload Allocations")
async def get_cluster_capacity():
    return resource_manager.get_hardware_status()
