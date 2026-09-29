import json
import logging
from typing import Any, Optional
import redis.asyncio as aioredis
from src.configs.settings import gateway_settings

logger = logging.getLogger("aip-redis")


class RedisService:
    def __init__(self):
        self._client: Optional[aioredis.Redis] = None

    def get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(
                gateway_settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._client

    async def get_json(self, key: str) -> Optional[dict]:
        try:
            client = self.get_client()
            val = await client.get(key)
            if val:
                return json.loads(val)
        except Exception as e:
            logger.warning(f"Redis GET failed for key {key}: {e}")
        return None

    async def set_json(self, key: str, value: Any, ttl_seconds: Optional[int] = None, nx: bool = False) -> bool:
        try:
            client = self.get_client()
            serialized = json.dumps(value, ensure_ascii=False)
            result = await client.set(key, serialized, ex=ttl_seconds, nx=nx)
            return result is not None if nx else True
        except Exception as e:
            logger.warning(f"Redis SET failed for key {key}: {e}")
            return False

    async def increment(self, key: str, ttl_seconds: Optional[int] = None) -> int:
        try:
            client = self.get_client()
            val = await client.incr(key)
            if val == 1 and ttl_seconds:
                await client.expire(key, ttl_seconds)
            return val
        except Exception as e:
            logger.warning(f"Redis INCR failed for key {key}: {e}")
            return 1

    async def publish(self, channel: str, message: str) -> bool:
        try:
            await self.get_client().publish(channel, message)
            return True
        except Exception as e:
            logger.warning(f"Redis PUBLISH failed for channel {channel}: {e}")
            return False


redis_service = RedisService()
