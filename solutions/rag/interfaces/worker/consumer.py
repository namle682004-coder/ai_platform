"""
RabbitMQ Quorum Queue Consumer for AIP RAG Document Ingestion.
Coordinates message lifecycle, backpressure, and ingestion use case execution.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal

import aio_pika

from ...application.components.chunker import DocumentChunker
from ...application.use_cases.ingestion_use_case import DocumentIngestionUseCase
from ...config import rag_settings
from ...infrastructure.adapters.embedding_adapter import HttpEmbeddingAdapter
from ...infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter
from ...infrastructure.adapters.redis_cache_adapter import redis_cache
from ...infrastructure.adapters.storage_adapter import MinioStorageAdapter
from ...infrastructure.parsers.factory import parser_factory
from ...infrastructure.repositories.mongo_document_repo import MongoDocumentRepositoryAdapter
from .publisher import publish_callback_event

logger = logging.getLogger("aip-rag.worker.consumer")


class RagWorkerConsumer:
    """RabbitMQ worker consumer executing DocumentIngestionUseCase."""

    def __init__(self) -> None:
        self.doc_repo = MongoDocumentRepositoryAdapter(mongo_uri=rag_settings.mongo_uri)
        self.storage = MinioStorageAdapter(
            endpoint=rag_settings.minio_endpoint,
            access_key=rag_settings.minio_root_user,
            secret_key=rag_settings.minio_root_password,
        )
        self.parser = parser_factory
        self.chunker = DocumentChunker(
            child_chunk_size_chars=rag_settings.child_chunk_size_chars,
            child_overlap_chars=rag_settings.child_overlap_chars,
            parent_chunk_size_chars=rag_settings.parent_chunk_size_chars,
            mask_pii=rag_settings.mask_pii,
            hierarchical=True,
        )
        # Resolves the embed-standard alias (BAAI/bge-m3) from the model registry.
        self.embedding_service = HttpEmbeddingAdapter(dim=rag_settings.embedding_dim)
        self.vector_store = QdrantVectorStoreAdapter(
            base_url=rag_settings.qdrant_url,
            collection_name=rag_settings.collection_name,
            dim=rag_settings.embedding_dim,
        )
        self.cache_service = redis_cache
        from ...infrastructure.observability import rag_observability
        self.ingestion_use_case = DocumentIngestionUseCase(
            doc_repo=self.doc_repo,
            storage=self.storage,
            parser=self.parser,
            chunker=self.chunker,
            embedding_service=self.embedding_service,
            vector_store=self.vector_store,
            cache_service=self.cache_service,
            observability_service=rag_observability,
        )

    async def run(self) -> None:
        logger.info("Initializing AIP Distributed RAG Ingestion Worker...")
        logger.info("RabbitMQ URL: %s", rag_settings.rabbitmq_url.split("@")[-1])
        logger.info("Target Queue: %s | Qdrant: %s", rag_settings.rag_queue, rag_settings.qdrant_url)

        await self.vector_store.ensure_collection()

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                pass

        connection = await aio_pika.connect_robust(rag_settings.rabbitmq_url)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=rag_settings.prefetch_count)

        try:
            queue = await channel.declare_queue(rag_settings.rag_queue, passive=True)
        except Exception:
            q_args = {
                "x-queue-type": "quorum",
                "x-dead-letter-exchange": "aip.dlx",
                "x-dead-letter-routing-key": "aip.dlx.rag.failed",
                "x-delivery-limit": 4,
                "x-max-length": 100_000,
            }
            queue = await channel.declare_queue(rag_settings.rag_queue, durable=True, arguments=q_args)
        logger.info("Worker listening for ingestion jobs on '%s'...", rag_settings.rag_queue)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                if stop_event.is_set():
                    logger.info("Worker stopping; requeueing new messages")
                    await message.nack(requeue=True)
                    break

                async with message.process(requeue=False):
                    doc_id = "unknown"
                    try:
                        payload = json.loads(message.body.decode())
                        task_data = payload.get("payload", payload)
                        doc_id = task_data.get("doc_id", "unknown")

                        result = await self.ingestion_use_case.ingest_document(task_data)
                        await publish_callback_event(channel, doc_id, result.get("status", "completed"), result)
                    except Exception as exc:
                        logger.exception("Error processing document %s: %s", doc_id, exc)
                        await publish_callback_event(channel, doc_id, "failed", {"error": str(exc)})

        await self.embedding_service.close()
        await connection.close()
        logger.info("AIP RAG Ingestion Worker stopped successfully.")
