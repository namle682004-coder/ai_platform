"""RabbitMQ topology constants and queue configurations for AIP task dispatch.

Enterprise Quorum Queue topology with physical priority separation (high, normal, batch),
dead-letter exchange governance (TTL, max storage), and Raft-backed reliability.
Compliant with DCP architectural principles and SRS Section 7.4.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Final, Optional

import aio_pika
from aio_pika import ExchangeType

logger = logging.getLogger("aip-messaging.topology")

# ── Exchange Names ───────────────────────────────────────────────────
EXCHANGE_TASKS: Final[str] = "aip.tasks"
EXCHANGE_JOBS: Final[str] = "aip.jobs"
EXCHANGE_RETRIES: Final[str] = "aip.retries"
EXCHANGE_JOBS_RETRY: Final[str] = "aip.jobs.retry"
EXCHANGE_EVENTS: Final[str] = "aip.events"
EXCHANGE_DLX: Final[str] = "aip.dlx"
EXCHANGE_JOBS_DLX: Final[str] = "aip.jobs.dlx"

# ── Core Task Domains ────────────────────────────────────────────────
CORE_TASK_DOMAINS: Final[tuple[str, ...]] = (
    "chat",
    "completion",
    "embedding",
    "translation",
    "stt",
    "tts",
    "ocr",
    "moderation",
    "image",
    "video",
    "lipsync",
    "batch",
    "general",
)

# ── Priority Tiers (Physical Queue Matrix) ───────────────────────────
PRIORITIES: Final[list[str]] = ["high", "normal", "batch"]

DOMAIN_ALIASES: Final[dict[str, str]] = {
    "llm": "chat",
    "idp": "ocr",
    "image_gen": "image",
    "video_gen": "video",
    "speech": "stt",
    "audio": "stt",
    "low": "batch",
}

# ── Queue Limits & Quorum Configuration (DCP standard) ───────────────
QUEUE_TYPE_QUORUM: Final[str] = "quorum"
TASK_QUEUE_MAX_LENGTH: Final[int] = 100_000
TASK_QUEUE_DELIVERY_LIMIT: Final[int] = 4
DLQ_MESSAGE_TTL_MS: Final[int] = 1_209_600_000       # 14 days (ms)
DLQ_MAX_LENGTH_BYTES: Final[int] = 10_737_418_240    # 10 GB
CALLBACK_MESSAGE_TTL_MS: Final[int] = 3_600_000      # 1 hour (ms)

QUEUE_PREFIX: Final[str] = "q.aip.tasks"
QUEUE_DLQ: Final[str] = f"{QUEUE_PREFIX}.dlq"
QUEUE_CALLBACKS: Final[str] = "q.aip.events.callbacks"

SRS_JOB_TYPES: Final[tuple[str, ...]] = (
    "llm_inference",
    "stt_transcription",
    "tts_synthesis",
    "ocr_extraction",
    "translation",
    "image_generation",
    "video_generation",
    "lipsync_generation",
    "embedding",
    "audio_transcription",
    "lip_sync",
    "idp_batch",
    "embedding_batch",
    "translation_batch",
)


@dataclass(frozen=True, slots=True)
class TaskQueueConfig:
    queue_name: str
    exchange: str
    routing_key: str
    dlx_exchange: str
    dlx_routing_key: str
    max_length: int = TASK_QUEUE_MAX_LENGTH
    delivery_limit: int = TASK_QUEUE_DELIVERY_LIMIT
    queue_type: str = QUEUE_TYPE_QUORUM


def task_queue_name(domain: str, priority: str = "normal") -> str:
    clean_domain = DOMAIN_ALIASES.get(domain, domain)
    clean_prio = "batch" if priority == "low" else (priority if priority in PRIORITIES else "normal")
    return f"{QUEUE_PREFIX}.{clean_domain}.{clean_prio}"


def queue_name(domain: str, priority: str = "normal") -> str:
    return task_queue_name(domain, priority)


def dlq_queue_name() -> str:
    return QUEUE_DLQ


def callbacks_queue_name() -> str:
    return QUEUE_CALLBACKS


def task_routing_key(domain: str, priority: str = "normal") -> str:
    clean_domain = DOMAIN_ALIASES.get(domain, domain)
    clean_prio = "batch" if priority == "low" else (priority if priority in PRIORITIES else "normal")
    return f"aip.tasks.{clean_domain}.{clean_prio}"


def dead_routing_key(domain: str) -> str:
    clean_domain = DOMAIN_ALIASES.get(domain, domain)
    return f"aip.dlx.{clean_domain}.failed"


def resolve_task_domain(
    alias_name: Optional[str] = None,
    task_type: Optional[str] = None,
) -> str:
    if alias_name:
        clean_alias = alias_name.lower()
        if "stt" in clean_alias or "whisper" in clean_alias or "speech" in clean_alias:
            return "stt"
        if "tts" in clean_alias or "voice" in clean_alias or "neural" in clean_alias:
            return "tts"
        if "translat" in clean_alias or "marian" in clean_alias:
            return "translation"
        if "ocr" in clean_alias or "easyocr" in clean_alias:
            return "ocr"
        if "moderat" in clean_alias or "phobert" in clean_alias:
            return "moderation"
        if "image" in clean_alias or "flux" in clean_alias or "sdxl" in clean_alias:
            return "image"
        if "video" in clean_alias or "wan" in clean_alias:
            return "video"
        if "lipsync" in clean_alias or "portrait" in clean_alias:
            return "lipsync"
        if "embed" in clean_alias or "bge" in clean_alias:
            return "embedding"
        if "chat" in clean_alias or "qwen" in clean_alias or "llm" in clean_alias:
            return "chat"

    if task_type:
        clean = task_type.lower().strip()
        if clean.startswith("aip.tasks."):
            clean = clean[len("aip.tasks."):]
        elif clean.startswith("tasks."):
            clean = clean[len("tasks."):]

        resolved = DOMAIN_ALIASES.get(clean, clean)
        if resolved in CORE_TASK_DOMAINS:
            return resolved

        for d in CORE_TASK_DOMAINS:
            if d in clean:
                return d

        return f"custom.{clean}"

    return "general"


def get_all_task_queue_configs() -> list[TaskQueueConfig]:
    return [
        TaskQueueConfig(
            queue_name=task_queue_name(domain, priority),
            exchange=EXCHANGE_TASKS,
            routing_key=task_routing_key(domain, priority),
            dlx_exchange=EXCHANGE_DLX,
            dlx_routing_key=dead_routing_key(domain),
        )
        for domain in CORE_TASK_DOMAINS
        for priority in PRIORITIES
    ]


async def setup_rabbitmq_topology(rabbitmq_url: str) -> None:
    logger.info("Setting up DCP-grade Quorum Queue topology for AIP platform...")
    if os.getenv("TEST_MODE") == "true":
        logger.warning("RabbitMQ connection skipped in TEST_MODE")
        return

    connection = await aio_pika.connect_robust(rabbitmq_url)
    channel = await connection.channel()

    try:
        tasks_exchange = await channel.declare_exchange(
            EXCHANGE_TASKS, ExchangeType.TOPIC, durable=True
        )
        retries_exchange = await channel.declare_exchange(
            EXCHANGE_RETRIES,
            type="x-delayed-message",
            durable=True,
            arguments={"x-delayed-type": "topic"},
        )
        jobs_exchange = await channel.declare_exchange(
            EXCHANGE_JOBS, ExchangeType.TOPIC, durable=True
        )
        events_exchange = await channel.declare_exchange(
            EXCHANGE_EVENTS, ExchangeType.TOPIC, durable=True
        )
        dlx_exchange = await channel.declare_exchange(
            EXCHANGE_DLX, ExchangeType.TOPIC, durable=True
        )
        jobs_dlx_exchange = await channel.declare_exchange(
            EXCHANGE_JOBS_DLX, ExchangeType.TOPIC, durable=True
        )

        dlq_args = {
            "x-queue-type": QUEUE_TYPE_QUORUM,
            "x-message-ttl": DLQ_MESSAGE_TTL_MS,
            "x-max-length-bytes": DLQ_MAX_LENGTH_BYTES,
            "x-delivery-limit": TASK_QUEUE_DELIVERY_LIMIT,
        }
        dlq = await channel.declare_queue(QUEUE_DLQ, durable=True, arguments=dlq_args)
        await dlq.bind(dlx_exchange, routing_key="aip.dlx.#")
        await dlq.bind(jobs_dlx_exchange, routing_key="aip.jobs.dlq.#")

        for config in get_all_task_queue_configs():
            q_args = {
                "x-queue-type": config.queue_type,
                "x-dead-letter-exchange": config.dlx_exchange,
                "x-dead-letter-routing-key": config.dlx_routing_key,
                "x-delivery-limit": config.delivery_limit,
                "x-max-length": config.max_length,
            }
            q = await channel.declare_queue(
                config.queue_name, durable=True, arguments=q_args
            )
            await q.bind(tasks_exchange, routing_key=config.routing_key)
            await q.bind(retries_exchange, routing_key=config.routing_key)
            domain_part = config.routing_key.split(".")[-2]
            await q.bind(jobs_exchange, routing_key=f"aip.jobs.{domain_part}.#")

        callback_args = {
            "x-queue-type": QUEUE_TYPE_QUORUM,
            "x-dead-letter-exchange": EXCHANGE_DLX,
            "x-dead-letter-routing-key": "aip.dlx.callbacks.dead",
            "x-delivery-limit": TASK_QUEUE_DELIVERY_LIMIT,
            "x-message-ttl": CALLBACK_MESSAGE_TTL_MS,
        }
        q_callbacks = await channel.declare_queue(
            QUEUE_CALLBACKS, durable=True, arguments=callback_args
        )
        await q_callbacks.bind(events_exchange, routing_key="aip.events.callback.#")
        await q_callbacks.bind(events_exchange, routing_key="aip.events.job.#")

        logger.info("DCP-grade Quorum Queue topology setup successfully declared.")
    finally:
        await channel.close()
        await connection.close()
