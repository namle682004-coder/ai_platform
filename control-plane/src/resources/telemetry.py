import logging
from typing import Dict, Any

logger = logging.getLogger("aip-resources")


def get_gpu_telemetry() -> Dict[str, Any]:
    # Reads real NVIDIA NVML if available, else graceful fallback
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0  # mW to Watts
        pynvml.nvmlShutdown()
        return {
            "status": "online",
            "gpu_name": name,
            "vram_total_mb": round(mem.total / (1024 * 1024), 1),
            "vram_used_mb": round(mem.used / (1024 * 1024), 1),
            "vram_free_mb": round(mem.free / (1024 * 1024), 1),
            "temperature_celsius": temp,
            "power_draw_watts": round(power, 1),
        }
    except Exception:
        return {
            "status": "simulated",
            "gpu_name": "NVIDIA GeForce RTX 3050 Laptop GPU (Simulated)",
            "vram_total_mb": 4096.0,
            "vram_used_mb": 1845.0,
            "vram_free_mb": 2251.0,
            "temperature_celsius": 52.0,
            "power_draw_watts": 45.0,
        }
