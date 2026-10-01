"""
Test for dedicated LlmService gRPC Server (:50051).
"""

import asyncio
import os
import sys

BASE_DIR = "/home/namle/AI-Projects/llm-apps/ai_platform"
sys.path.insert(0, os.path.join(BASE_DIR, "packages/common"))
sys.path.insert(0, os.path.join(BASE_DIR, "packages/contracts"))
sys.path.insert(0, os.path.join(BASE_DIR, "apps/data-plane/vllm-engine"))

import grpc
from contracts.generated import llm_pb2, llm_pb2_grpc, common_pb2
import importlib.util

_spec = importlib.util.spec_from_file_location("vllm_grpc_server_test_mod", os.path.join(BASE_DIR, "apps/data-plane/vllm-engine/grpc_server.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
create_vllm_grpc_server = _mod.create_vllm_grpc_server


async def main():
    os.environ["TEST_MODE"] = "true"
    os.environ["VLLM_TEST_MODE"] = "true"
    port = 50061
    server = await create_vllm_grpc_server(host="127.0.0.1", port=port)
    await server.start()
    print(f"Dedicated LlmService running on 127.0.0.1:{port}")

    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    stub = llm_pb2_grpc.LlmServiceStub(channel)

    try:
        # Health
        health = await stub.GetHealth(common_pb2.HealthRequest(service="vllm"))
        print(f"[Health] status={health.status}")
        assert health.status == "SERVING"

        # Chat
        chat_req = llm_pb2.ChatRequest(
            model="chat-general-standard",
            messages=[llm_pb2.ChatMessage(role="user", content="Xin chào")],
        )
        chat_resp = await stub.ChatCompletion(chat_req, timeout=5.0)
        print(f"[Chat] content='{chat_resp.content}'")
        assert len(chat_resp.content) > 0

        # Stream
        chunks = []
        async for chunk in stub.StreamChatCompletion(chat_req, timeout=5.0):
            chunks.append(chunk.delta_content)
        stream_text = "".join(chunks)
        print(f"[Stream] received {len(chunks)} chunks: '{stream_text}'")
        assert len(chunks) > 1

        # Cancel
        cancel_resp = await stub.Cancel(common_pb2.CancelRequest(task_id="chat_test_123", reason="Abort"))
        print(f"[Cancel] success={cancel_resp.success}")

        print("✔ Dedicated LlmService PASSED all tests!")
    finally:
        await channel.close()
        await server.stop(grace=0.5)


if __name__ == "__main__":
    asyncio.run(main())
