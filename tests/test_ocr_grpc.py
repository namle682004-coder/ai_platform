"""
Test for dedicated OcrService gRPC Server (:50054).
"""

import asyncio
import os
import sys

BASE_DIR = "/home/namle/AI-Projects/llm-apps/ai_platform"
sys.path.insert(0, os.path.join(BASE_DIR, "packages/common"))
sys.path.insert(0, os.path.join(BASE_DIR, "packages/contracts"))
sys.path.insert(0, os.path.join(BASE_DIR, "apps/data-plane/ocr-server"))

import grpc
from contracts.generated import ocr_pb2_grpc, common_pb2
import importlib.util

_spec = importlib.util.spec_from_file_location("ocr_grpc_server_test_mod", os.path.join(BASE_DIR, "apps/data-plane/ocr-server/grpc_server.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
create_ocr_grpc_server = _mod.create_ocr_grpc_server


async def main():
    os.environ["TEST_MODE"] = "true"
    port = 50064
    server = await create_ocr_grpc_server(host="127.0.0.1", port=port)
    await server.start()
    print(f"Dedicated OcrService running on 127.0.0.1:{port}")

    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    stub = ocr_pb2_grpc.OcrServiceStub(channel)

    try:
        # Health
        health = await stub.GetHealth(common_pb2.HealthRequest(service="ocr"))
        print(f"[Health] status={health.status}")
        assert health.status == "SERVING"

        # Cancel
        cancel_resp = await stub.Cancel(
            common_pb2.CancelRequest(task_id="ocr_task_test", reason="User cancel")
        )
        print(f"[Cancel] success={cancel_resp.success}")

        print("✔ Dedicated OcrService PASSED all tests!")
    finally:
        await channel.close()
        await server.stop(grace=0.5)


if __name__ == "__main__":
    asyncio.run(main())
