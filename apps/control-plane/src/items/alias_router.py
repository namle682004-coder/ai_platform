"""
Enterprise Model Alias Resolution & Routing Service.
Compliant with SRS Section 6 (Model Catalog & Alias System).
"""

from __future__ import annotations
import asyncio
from typing import Optional
from common.models.catalog import AIP_MODEL_CATALOG
from common.repositories.mongo_repositories import alias_repository
from src.db.redis import redis_service


class AliasRouterService:
    UPDATE_CHANNEL = "aip:aliases:updated"
    """
    Resolves client logical aliases into concrete runtime targets and policy metadata.
    Includes support for canary split, version pinning, and active/deprecated statuses.
    """

    def __init__(self):
        # The catalog is the offline fallback; MongoDB is the runtime source of truth.
        self._registry: dict[str, dict] = {}
        for alias_id, model in AIP_MODEL_CATALOG.items():
            self._registry[alias_id] = self._catalog_entry(model)

    @staticmethod
    def _catalog_entry(model) -> dict:
        return {
            "alias": model.id,
            "physical_model": model.physical_model,
            "runtime": model.runtime,
            "namespace": model.namespace,
            "min_vram_gb": model.min_vram_gb,
            "timeout_seconds": model.timeout_seconds,
            "version": model.active_version,
            "stream_capable": model.stream_capable,
            "category": model.category,
            "description": model.description,
            "target_url": model.target_url,
            "status": model.status,
        }

    @staticmethod
    def _normalize_runtime(runtime: str, fallback_runtime: str) -> str:
        if runtime.casefold() == fallback_runtime.casefold():
            return fallback_runtime
        return runtime

    async def refresh(self) -> None:
        """Load MongoDB aliases while retaining catalog metadata as a fallback."""
        aliases = await alias_repository.list_aliases()
        if not aliases:
            return

        refreshed: dict[str, dict] = {}
        for alias_name, fallback in self._registry.items():
            document = aliases.get(alias_name)
            if not document:
                refreshed[alias_name] = fallback
                continue

            item = dict(fallback)
            item.update({
                "alias": document.get("alias_name", alias_name),
                "physical_model": document.get("physical_model", document.get("model_name", fallback["physical_model"])),
                "runtime": self._normalize_runtime(
                    document.get("runtime", fallback["runtime"]),
                    fallback["runtime"],
                ),
                "target_url": document.get("target_url", fallback["target_url"]),
                "min_vram_gb": document.get("min_vram_gb", fallback["min_vram_gb"]),
                "timeout_seconds": document.get("timeout_seconds", fallback["timeout_seconds"]),
                "category": document.get("category", fallback["category"]),
                "description": document.get("description", fallback["description"]),
                "status": document.get("status", fallback["status"]),
            })
            refreshed[alias_name] = item

        for alias_name, document in aliases.items():
            if alias_name in refreshed:
                continue
            refreshed[alias_name] = {
                "alias": document.get("alias_name", alias_name),
                "physical_model": document.get("physical_model", document.get("model_name", alias_name)),
                "runtime": document.get("runtime", "unknown"),
                "namespace": document.get("namespace", ""),
                "min_vram_gb": document.get("min_vram_gb", 0),
                "timeout_seconds": document.get("timeout_seconds", 60),
                "version": document.get("version", "v1.0"),
                "stream_capable": document.get("stream_capable", False),
                "category": document.get("category", "llm"),
                "description": document.get("description", ""),
                "target_url": document.get("target_url", ""),
                "status": document.get("status", "disabled"),
            }

        self._registry = refreshed

    async def listen_for_updates(self) -> None:
        """Refresh every gateway replica when an admin changes an alias."""
        pubsub = redis_service.get_client().pubsub()
        try:
            await pubsub.subscribe(self.UPDATE_CHANNEL)
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    await self.refresh()
        except asyncio.CancelledError:
            raise
        except Exception:
            return
        finally:
            await pubsub.close()

    ALIAS_SYNONYMS = {
        "tts-vn-standard": "tts-vi-standard",
        "stt-vi-standard": "stt-vn-standard",
    }

    async def resolve_alias(self, alias_name: str) -> Optional[dict]:
        """
        Resolves a logical alias name to its active runtime target configuration.
        Returns None if alias is unknown or status == 'disabled'.
        """
        canonical_name = self.ALIAS_SYNONYMS.get(alias_name, alias_name)
        item = self._registry.get(canonical_name)
        if not item or item.get("status") in ("disabled", "inactive"):
            return None
        res = dict(item)
        if item.get("status") == "deprecated":
            res["is_deprecated"] = True
        return res

    async def resolve_target_url(self, alias_name: str, fallback_url: str) -> Optional[str]:
        resolved = await self.resolve_alias(alias_name)
        if not resolved:
            return None
        target_url = resolved.get("target_url") or ""
        # Older persisted aliases used host.docker.internal. Inside the Compose
        # network the service hostname is authoritative and comes from config.
        if "host.docker.internal" in target_url:
            return fallback_url
        return target_url or fallback_url

    async def list_aliases(self, allowed_aliases: list[str] | None = None) -> list[dict]:
        """
        Returns list of all active aliases visible to the given tenant/key.
        """
        results = []
        is_wildcard = allowed_aliases is None or "*" in allowed_aliases
        for alias, item in self._registry.items():
            if item.get("status") not in ("enabled", "active"):
                continue
            if is_wildcard or alias in allowed_aliases:
                results.append({
                    "id": item["alias"],
                    "object": "model",
                    "created": 1770970000,
                    "owned_by": "aip-platform",
                    "runtime": f"{item['runtime']} ({item['physical_model']})",
                    "min_vram_gb": item["min_vram_gb"],
                    "status": item["status"],
                    "version": item["version"],
                    "category": item["category"],
                    "description": item["description"],
                })
        return results

    async def update_alias_status(self, alias_name: str, new_status: str) -> bool:
        canonical_name = self.ALIAS_SYNONYMS.get(alias_name, alias_name)
        if canonical_name in self._registry:
            self._registry[canonical_name]["status"] = new_status
            return True
        return False


alias_router = AliasRouterService()
