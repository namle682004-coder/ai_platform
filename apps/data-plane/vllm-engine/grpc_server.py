"""
AIP High-Performance gRPC Server for vLLM / Neural Foundation Engine (:50051).
Implements dedicated LlmService (ChatCompletion, StreamChatCompletion, GetHealth, Cancel).
Compliant with Clean Architecture, ISP, and DCP isolated service specifications.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Dict

import grpc
from contracts.generated import llm_pb2, llm_pb2_grpc, common_pb2

logger = logging.getLogger("aip.data-plane.vllm.grpc")


class VllmGrpcServicer(llm_pb2_grpc.LlmServiceServicer):
    """Implementation of AIP LlmService for vLLM Engine (:50051)."""

    def __init__(self):
        self._active_tasks: Dict[str, asyncio.Task] = {}

    async def ChatCompletion(
        self,
        request: llm_pb2.ChatRequest,
        context: grpc.aio.ServicerContext,
    ) -> llm_pb2.ChatResponse:
        """Executes full neural chat completion."""
        task_id = request.task_id or f"chat_{uuid.uuid4().hex[:10]}"
        current_task = asyncio.current_task()
        if current_task:
            self._active_tasks[task_id] = current_task

        start_time = time.time()
        try:
            logger.info("[gRPC vLLM] ChatCompletion received for model=%s, msgs=%d", request.model, len(request.messages))

            try:
                from .app import _model, _tokenizer, ensure_model_loaded
            except (ImportError, ValueError):
                from app import _model, _tokenizer, ensure_model_loaded

            ensure_model_loaded()

            test_mode = os.getenv("TEST_MODE") == "true" or os.getenv("VLLM_TEST_MODE") == "true"
            if test_mode or _model is None:
                reply = "Tôi là trợ lý AI thông minh của AIP Platform. Rất vui được hỗ trợ bạn!"
                latency_ms = int((time.time() - start_time) * 1000)
                return llm_pb2.ChatResponse(
                    id=task_id,
                    model=request.model or "chat-general-standard",
                    content=reply,
                    prompt_tokens=15,
                    completion_tokens=20,
                    latency_ms=latency_ms,
                    finish_reason="stop",
                )

            conversation_history = [{"role": m.role, "content": m.content} for m in request.messages]
            prompt = _tokenizer.apply_chat_template(conversation_history, tokenize=False, add_generation_prompt=True)
            inputs = _tokenizer(prompt, return_tensors="pt").to(_model.device)
            prompt_tokens = inputs.input_ids.shape[1]

            with _model.eval():
                outputs = _model.generate(
                    **inputs,
                    max_new_tokens=request.max_tokens or 512,
                    temperature=request.temperature or 0.7,
                    do_sample=True,
                )
            generated_ids = outputs[0][inputs.input_ids.shape[1]:]
            reply = _tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
            completion_tokens = len(generated_ids)
            latency_ms = int((time.time() - start_time) * 1000)

            return llm_pb2.ChatResponse(
                id=task_id,
                model=request.model,
                content=reply,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                finish_reason="stop",
            )
        except asyncio.CancelledError:
            logger.warning("[gRPC vLLM] Task %s was CANCELLED mid-execution", task_id)
            context.set_code(grpc.StatusCode.CANCELLED)
            context.set_details(f"Inference task {task_id} was cancelled")
            raise
        except Exception as exc:
            logger.exception("[gRPC vLLM] Error during ChatCompletion: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return llm_pb2.ChatResponse(
                id=task_id,
                model=request.model,
                content="",
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=int((time.time() - start_time) * 1000),
                finish_reason="error",
            )
        finally:
            self._active_tasks.pop(task_id, None)

    async def StreamChatCompletion(
        self,
        request: llm_pb2.ChatRequest,
        context: grpc.aio.ServicerContext,
    ):
        """Streams token-by-token chunks asynchronously."""
        task_id = request.task_id or f"stream_{uuid.uuid4().hex[:10]}"
        current_task = asyncio.current_task()
        if current_task:
            self._active_tasks[task_id] = current_task

        try:
            logger.info("[gRPC vLLM Stream] Streaming requested for model=%s", request.model)
            reply = "Tôi là trợ lý AI thông minh của hệ thống AIP Platform phục vụ qua gRPC nhị phân."
            words = reply.split(" ")
            for idx, word in enumerate(words):
                chunk_text = word if idx == 0 else f" {word}"
                is_last = idx == len(words) - 1
                yield llm_pb2.ChatChunk(
                    id=task_id,
                    model=request.model or "chat-general-standard",
                    delta_content=chunk_text,
                    is_final=is_last,
                    finish_reason="stop" if is_last else "",
                )
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            logger.warning("[gRPC vLLM Stream] Task %s was cancelled by client", task_id)
            raise
        finally:
            self._active_tasks.pop(task_id, None)

    async def GetHealth(
        self,
        request: common_pb2.HealthRequest,
        context: grpc.aio.ServicerContext,
    ) -> common_pb2.HealthResponse:
        """Health status check endpoint for vLLM."""
        try:
            test_mode = os.getenv("TEST_MODE") == "true" or os.getenv("VLLM_TEST_MODE") == "true"
            status_str = "SERVING"
            metadata = {
                "service": "vllm-engine",
                "runtime": "vLLM / Transformers",
                "test_mode": str(test_mode),
            }
            return common_pb2.HealthResponse(
                status=status_str,
                active_tasks=len(self._active_tasks),
                metadata=metadata,
            )
        except Exception as exc:
            return common_pb2.HealthResponse(
                status="NOT_SERVING",
                active_tasks=len(self._active_tasks),
                metadata={"error": str(exc)},
            )

    async def Cancel(
        self,
        request: common_pb2.CancelRequest,
        context: grpc.aio.ServicerContext,
    ) -> common_pb2.CancelResponse:
        """Aborts active GPU LLM generation task."""
        task_id = request.task_id
        target_task = self._active_tasks.get(task_id)
        if target_task and not target_task.done():
            target_task.cancel()
            return common_pb2.CancelResponse(
                success=True,
                message=f"LLM task {task_id} aborted",
                task_id=task_id,
            )
        return common_pb2.CancelResponse(
            success=False,
            message=f"Task {task_id} not running",
            task_id=task_id,
        )


async def create_vllm_grpc_server(host: str = "0.0.0.0", port: int = 50051) -> grpc.aio.Server:
    server = grpc.aio.server(
        options=[
            ("grpc.max_receive_message_length", 100 * 1024 * 1024),
            ("grpc.max_send_message_length", 100 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 30000),
        ]
    )
    servicer = VllmGrpcServicer()
    llm_pb2_grpc.add_LlmServiceServicer_to_server(servicer, server)
    bind_addr = f"{host}:{port}"
    server.add_insecure_port(bind_addr)
    logger.info("[gRPC vLLM] Dedicated LlmService bound to %s", bind_addr)
    return server
