from typing import Dict, Optional


class AliasRouterService:
    """
    Alias Resolution Service mapped to existing lightweight cached local HuggingFace models.
    """

    def __init__(self):
        self._default_registry: Dict[str, Dict] = {
            "chat-general-standard": {
                "physical_model": "Qwen/Qwen2.5-1.5B-Instruct",
                "hf_cache_path": "~/.cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct",
                "runtime_type": "vllm",
                "min_vram_gb": 4,
                "target_url": "http://localhost:8000/v1",
                "version": "v1.0",
            },
            "embed-standard": {
                "physical_model": "sentence-transformers/all-MiniLM-L6-v2",
                "hf_cache_path": "~/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2",
                "runtime_type": "tei",
                "min_vram_gb": 1,
                "target_url": "http://localhost:8080/v1",
                "version": "v1.0",
            },
            "stt-vn-standard": {
                "physical_model": "Systran/faster-whisper-small",
                "hf_cache_path": "~/.cache/huggingface/hub/models--Systran--faster-whisper-small",
                "runtime_type": "faster-whisper",
                "min_vram_gb": 2,
                "target_url": "http://localhost:8002/v1",
                "version": "v1.0",
            },
            "spelling-vi-precision": {
                "physical_model": "vinai/phobert-base",
                "hf_cache_path": "~/.cache/huggingface/hub/models--vinai--phobert-base",
                "runtime_type": "triton",
                "min_vram_gb": 2,
                "target_url": "http://localhost:8003/v1",
                "version": "v1.0",
            },
        }

    async def resolve_alias(self, alias_name: str) -> Optional[Dict]:
        return self._default_registry.get(alias_name)


alias_router = AliasRouterService()
