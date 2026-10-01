"""
Test for dedicated TtsService gRPC Server (:50055).
"""

import asyncio
import os
import sys

BASE_DIR = "/home/namle/AI-Projects/llm-apps/ai_platform"
sys.path.insert(0, os.path.join(BASE_DIR, "packages/common"))
sys.path.insert(0, os.path.join(BASE_DIR, "packages/contracts"))
sys.path.insert(0, os.path.join(BASE_DIR, "apps/data-plane/tts-adapter"))

import grpc
from contracts.generated import tts_pb2, tts_pb2_grpc, common_pb2
import importlib.util

_spec = importlib.util.spec_from_file_location("tts_grpc_server_test_mod", os.path.join(BASE_DIR, "apps/data-plane/tts-adapter/grpc_server.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
create_tts_grpc_server = _mod.create_tts_grpc_server


async def main():
    os.environ["TEST_MODE"] = "true"
    port = 50065
    server = await create_tts_grpc_server(host="127.0.0.1", port=port)
    await server.start()
    print(f"Dedicated TtsService running on 127.0.0.1:{port}")

    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    stub = tts_pb2_grpc.TtsServiceStub(channel)

    try:
        # Health
        health = await stub.GetHealth(common_pb2.HealthRequest(service="tts"))
        print(f"[Health] status={health.status}")
        assert health.status == "SERVING"

        # Synthesize
        req = tts_pb2.SpeechRequest(
            text="Xin chào, đây là giọng đọc AI",
            voice="vi-VN-HoaiMyNeural",
            format="mp3",
            model_alias="tts-vi-standard",
        )
        resp = await stub.SynthesizeSpeech(req, timeout=5.0)
        print(f"[Synthesize] audio bytes={len(resp.audio_data)} format={resp.format}")
        assert len(resp.audio_data) > 0

        # Cancel
        cancel_resp = await stub.Cancel(common_pb2.CancelRequest(task_id="tts_test_123", reason="Abort"))
        print(f"[Cancel] success={cancel_resp.success}")

        print("✔ Dedicated TtsService PASSED all tests!")
    finally:
        await channel.close()
        await server.stop(grace=0.5)


if __name__ == "__main__":
    asyncio.run(main())
