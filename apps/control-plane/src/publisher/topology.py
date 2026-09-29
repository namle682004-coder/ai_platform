"""
RabbitMQ Topology Setup for AIP Control Plane.

Domain & Alias-based queue routing with Native RabbitMQ Priority Queues:
- Workers subscribe to domain-specific queues (chat, stt, tts, ocr, translation, image, video, lipsync, vision, embedding, moderation, general).
- Native RabbitMQ priority (x-max-priority: 10):
    * high   -> priority 9-10
    * normal -> priority 5
    * batch  -> priority 1
  Tasks with higher priority are consumed FIRST by workers.
- Displays 'Pri' badge in RabbitMQ Management UI.
- Catch-all 'general' queue binds 'aip.tasks.custom.#' for arbitrary custom tasks outside catalog.
"""

from __future__ import annotations

import logging
from typing import Optional

import aio_pika
from aio_pika import ExchangeType

from common.models.catalog import AIP_MODEL_CATALOG

logger = logging.getLogger("aip-messaging.topology")

# ── Exchange names ──────────────────────────────────────────────────
EXCHANGE_TASKS = "aip.tasks"
EXCHANGE_DLX = "aip.dlx"
EXCHANGE_EVENTS = "aip.events"
QUEUE_CALLBACKS = "q.aip.events.callbacks"

# ── Priority tiers ──────────────────────────────────────────────────
PRIORITIES = ("high", "normal", "batch")
MAX_PRIORITY = 10

# ── Canonical Intuitive Service Domains ──────────────────────────────
CORE_TASK_DOMAINS: tuple[str, ...] = (
    "chat",         # LLM text, conversational, summarization, classification
    "stt",          # Speech-to-Text transcription
    "tts",          # Text-to-Speech synthesis & voice cloning
    "ocr",          # IDP, document parsing, invoice & license OCR
    "translation",  # Neural machine translation, grammar & spell check
    "image",        # Diffusion image generation (FLUX, SDXL)
    "video",        # Text-to-Video generation (Wan2.2)
    "lipsync",      # Audio-driven avatar & lipsync animation (LivePortrait)
    "vision",       # Visual question answering, VLM
    "embedding",    # Vector embeddings & cross-encoder reranking
    "moderation",   # Content safety moderation
    "general",      # Catch-all for arbitrary external / custom tasks
)

# Domain aliases for backward compatibility or alternate naming
DOMAIN_ALIASES: dict[str, str] = {
    "llm": "chat",
    "idp": "ocr",
    "image_gen": "image",
    "video_gen": "video",
    "speech": "stt",
    "audio": "stt",
}

# ── Alias to Domain Resolution Map ──────────────────────────────────
_ALIAS_TO_DOMAIN_MAP: dict[str, str] = {}
for _alias_id, _model in AIP_MODEL_CATALOG.items():
    _cat = _model.category
    _resolved_domain = DOMAIN_ALIASES.get(_cat, _cat)
    _ALIAS_TO_DOMAIN_MAP[_alias_id] = _resolved_domain

# Canonical sorted tuple of all recognized domains
TASK_DOMAINS: tuple[str, ...] = CORE_TASK_DOMAINS

# ── Queue naming ───────────────────────────────────────────────────
QUEUE_PREFIX = "q.aip.tasks"
QUEUE_DLQ = f"{QUEUE_PREFIX}.dlq"


def queue_name(domain: str) -> str:
    """Return the canonical queue name for a task domain (e.g. q.aip.tasks.chat)."""
    clean_domain = DOMAIN_ALIASES.get(domain, domain)
    return f"{QUEUE_PREFIX}.{clean_domain}"


def resolve_task_domain(
    alias_name: Optional[str] = None,
    task_type: Optional[str] = None,
) -> str:
    """
    Intelligently resolves task domain from alias_name or task_type.
    """
    # 1. Try resolving via model catalog alias
    if alias_name and alias_name in _ALIAS_TO_DOMAIN_MAP:
        return _ALIAS_TO_DOMAIN_MAP[alias_name]

    # 2. Check task_type string
    if task_type:
        clean = task_type.lower().strip()
        if clean.startswith("aip.tasks."):
            clean = clean[len("aip.tasks."):]
        elif clean.startswith("tasks."):
            clean = clean[len("tasks."):]

        resolved = DOMAIN_ALIASES.get(clean, clean)
        if resolved in CORE_TASK_DOMAINS:
            return resolved

        # Prefix / partial match
        if "chat" in clean or "llm" in clean or "summar" in clean:
            return "chat"
        if "stt" in clean or "transcrib" in clean or "speech" in clean:
            return "stt"
        if "tts" in clean or "synthes" in clean or "voice" in clean:
            return "tts"
        if "ocr" in clean or "idp" in clean or "document" in clean:
            return "ocr"
        if "translat" in clean:
            return "translation"
        if "image" in clean or "diffusion" in clean:
            return "image"
        if "video" in clean:
            return "video"
        if "lipsync" in clean or "avatar" in clean:
            return "lipsync"
        if "vision" in clean or "vlm" in clean:
            return "vision"
        if "embed" in clean or "rerank" in clean:
            return "embedding"
        if "moderat" in clean or "safety" in clean:
            return "moderation"

        # Custom arbitrary task (e.g. 'crawler', 'report_gen') -> custom.<name>
        return f"custom.{clean}"

    return "general"


# ── Topology bootstrap ────────────────────────────────────────────

async def setup_rabbitmq_topology(rabbitmq_url: str) -> None:
    """
    Declare all exchanges, domain queues, DLQ, and bindings.
    Enables x-max-priority: 10 so RabbitMQ natively prioritizes urgent tasks.
    """
    logger.info("Setting up RabbitMQ alias/domain priority topology for AIP platform...")
    import os
    try:
        connection = await aio_pika.connect_robust(rabbitmq_url)
    except Exception as exc:
        if os.getenv("TEST_MODE") == "true":
            logger.warning(f"RabbitMQ connection skipped in TEST_MODE: {exc}")
            return
        raise
    channel = await connection.channel()

    try:
        # 1. Dead-Letter Exchange & Queue
        dlx_exchange = await channel.declare_exchange(
            EXCHANGE_DLX,
            ExchangeType.TOPIC,
            durable=True,
        )
        dlq = await channel.declare_queue(QUEUE_DLQ, durable=True)
        await dlq.bind(dlx_exchange, routing_key="aip.dlx.#")

        # 2. Main Tasks Topic Exchange
        tasks_exchange = await channel.declare_exchange(
            EXCHANGE_TASKS,
            ExchangeType.TOPIC,
            durable=True,
        )

        # 3. One durable queue per canonical domain with DLX + Native Priority (x-max-priority: 10)
        queue_args = {
            "x-dead-letter-exchange": EXCHANGE_DLX,
            "x-dead-letter-routing-key": "aip.dlx.failed",
            "x-max-priority": MAX_PRIORITY,
        }

        created_queues: list[str] = []
        for domain in CORE_TASK_DOMAINS:
            q_name = queue_name(domain)
            q = await channel.declare_queue(
                q_name,
                durable=True,
                arguments=queue_args,
            )

            # Primary binding: aip.tasks.<domain>.* (e.g. aip.tasks.chat.normal, aip.tasks.chat.high)
            await q.bind(tasks_exchange, routing_key=f"aip.tasks.{domain}.*")

            # Also bind legacy/synonym keys if applicable
            for alias_key, target_domain in DOMAIN_ALIASES.items():
                if target_domain == domain:
                    await q.bind(tasks_exchange, routing_key=f"aip.tasks.{alias_key}.*")

            created_queues.append(q_name)

        # Catch-all: general queue also binds any unmapped custom tasks (aip.tasks.custom.#)
        q_general = await channel.declare_queue(
            queue_name("general"),
            durable=True,
            arguments=queue_args,
        )
        await q_general.bind(tasks_exchange, routing_key="aip.tasks.custom.#")
        await q_general.bind(tasks_exchange, routing_key="aip.tasks.custom.*")

        # 4. Outbound Event & Callback Queue (for dedicated Callback-Worker)
        events_exchange = await channel.declare_exchange(
            EXCHANGE_EVENTS,
            ExchangeType.TOPIC,
            durable=True,
        )
        callback_args = {
            "x-dead-letter-exchange": EXCHANGE_DLX,
            "x-dead-letter-routing-key": "aip.dlx.callback_failed",
        }
        q_callbacks = await channel.declare_queue(
            QUEUE_CALLBACKS,
            durable=True,
            arguments=callback_args,
        )
        await q_callbacks.bind(events_exchange, routing_key="aip.events.callback.#")
        await q_callbacks.bind(events_exchange, routing_key="aip.events.job.#")

        logger.info(
            "RabbitMQ topology setup complete: "
            f"Exchanges: [{EXCHANGE_TASKS}, {EXCHANGE_EVENTS}, {EXCHANGE_DLX}], "
            f"Queues ({len(created_queues)}): {created_queues} with x-max-priority={MAX_PRIORITY}, "
            f"Callbacks: [{QUEUE_CALLBACKS}], "
            f"DLQ: [{QUEUE_DLQ}]"
        )
    finally:
        await channel.close()
        await connection.close()
