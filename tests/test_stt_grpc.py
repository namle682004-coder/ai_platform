"""
Test for dedicated SttService gRPC Server (:50052).
"""

import asyncio
import os
import sys

BASE_DIR = "/home/namle/AI-Projects/llm-apps/ai_platform"
sys.path.insert(0, os.path.join(BASE_DIR, "packages/common"))
sys.path.insert(0, os.path.join(BASE_DIR, "packages/contracts"))
sys.path.insert(0, os.path.join(BASE_DIR, "apps/data-plane/stt-server"))

import grpc
from contracts.generated import stt_pb2, stt_pb2_grpc, common_pb2
import importlib.util

_spec = importlib.util.spec_from_file_location("stt_grpc_server_test_mod", os.path.join(BASE_DIR, "apps/data-plane/stt-server/grpc_server.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
create_stt_grpc_server = _mod.create_stt_grpc_server


async def main():
    os.environ["TEST_MODE"] = "true"
    port = 50062
    server = await create_stt_grpc_server(host="127.0.0.1", port=port)
    await server.start()
    print(f"Dedicated SttService running on 127.0.0.1:{port}")

    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    stub = stt_pb2_grpc.SttServiceStub(channel)

    try:
        # Health
        health = await stub.GetHealth(common_pb2.HealthRequest(service="stt"))
        print(f"[Health] status={health.status}")
        assert health.status == "SERVING"

        # Transcribe
        req = stt_pb2.TranscriptionRequest(
            audio_data=b"test_audio_wav_binary_data",
            format="wav",
            language="vi",
            model_alias="stt-vn-standard",
        )
        resp = await stub.TranscribeAudio(req, timeout=5.0)
        print(f"[Transcribe] text='{resp.text}' lang={resp.detected_language}")
        assert resp.detected_language == "vi"

        # Cancel
        cancel_resp = await stub.Cancel(common_pb2.CancelRequest(task_id="stt_test_123", reason="Abort"))
        print(f"[Cancel] success={cancel_resp.success}")

        print("✔ Dedicated SttService PASSED all tests!")
    finally:
        await channel.close()
        await server.stop(grace=0.5)


if __name__ == "__main__":
    asyncio.run(main())
