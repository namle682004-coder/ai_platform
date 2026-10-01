"""
Unit & Integration Test for dedicated TranslationService gRPC Server (:50053).
"""

import asyncio
import os
import sys

BASE_DIR = "/home/namle/AI-Projects/llm-apps/ai_platform"
sys.path.insert(0, os.path.join(BASE_DIR, "packages/common"))
sys.path.insert(0, os.path.join(BASE_DIR, "packages/contracts"))
sys.path.insert(0, os.path.join(BASE_DIR, "apps/data-plane/translation-server"))

import grpc
from contracts.generated import translation_pb2, translation_pb2_grpc, common_pb2
import importlib.util

_spec = importlib.util.spec_from_file_location("trans_grpc_server_test_mod", os.path.join(BASE_DIR, "apps/data-plane/translation-server/grpc_server.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
create_grpc_server = _mod.create_grpc_server
from translation_engine import translation_engine


async def main():
    os.environ["TEST_MODE"] = "true"
    print("--- 1. Initializing Translation Engine ---")
    translation_engine.initialize()
    print("Engine initialized successfully.")

    print("\n--- 2. Starting TranslationService on port 50059 ---")
    test_port = 50059
    server = await create_grpc_server(host="127.0.0.1", port=test_port)
    await server.start()
    print(f"Dedicated TranslationService running on 127.0.0.1:{test_port}")

    channel = grpc.aio.insecure_channel(f"127.0.0.1:{test_port}")
    stub = translation_pb2_grpc.TranslationServiceStub(channel)

    try:
        print("\n--- 3. Testing GetHealth ---")
        health_req = common_pb2.HealthRequest(service="translation-server")
        health_resp = await stub.GetHealth(health_req, timeout=5.0)
        print(f"Health Response: status={health_resp.status}, active_tasks={health_resp.active_tasks}")
        assert health_resp.status == "SERVING"

        print("\n--- 4. Testing Translate ---")
        trans_req = translation_pb2.TranslationRequest(
            text="Xin chào thế giới",
            source_lang="vi",
            target_lang="en",
            model_alias="translate-vi-standard",
        )
        trans_resp = await stub.Translate(trans_req, timeout=10.0)
        print(f"Translation Response: status={trans_resp.status}, text='{trans_resp.translated_text}', latency={trans_resp.latency_ms}ms")
        assert trans_resp.status == "success"

        print("\n--- 5. Testing Cancel ---")
        cancel_req = common_pb2.CancelRequest(
            task_id="test_nonexistent_task_123",
            reason="User requested abort",
        )
        cancel_resp = await stub.Cancel(cancel_req, timeout=5.0)
        print(f"Cancel Response: success={cancel_resp.success}")
        assert cancel_resp.task_id == "test_nonexistent_task_123"

        print("\n✔ Dedicated TranslationService PASSED all tests!")
    finally:
        await channel.close()
        await server.stop(grace=0.5)


if __name__ == "__main__":
    asyncio.run(main())
