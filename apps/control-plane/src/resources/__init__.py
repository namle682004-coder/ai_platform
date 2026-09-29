from .telemetry import get_gpu_telemetry
from .resource_manager_service import resource_manager, ResourceManagerService
from .routes import router as resources_router

__all__ = [
    "get_gpu_telemetry",
    "resource_manager",
    "ResourceManagerService",
    "resources_router",
]
