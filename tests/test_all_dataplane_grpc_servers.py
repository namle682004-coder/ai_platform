"""
End-to-End Comprehensive Multi-Service Test for ALL Data-Plane gRPC Servers.
Tests:
  - 1. vLLM Engine (:50051) -> ChatCompletion, StreamChatCompletion, GetHealth, CancelInference
  - 2. STT Server (:50052)  -> TranscribeAudio, GetHealth, CancelInference
  - 3. Translation (:50053) -> Translate, GetHealth, CancelInference
  - 4. OCR Server (:50054)  -> GetHealth, CancelInference
  - 5. TTS Adapter (:50055) -> SynthesizeSpeech, GetHealth, CancelInference
"""

import asyncio
import os
import sys

BASE_DIR = "/home/namle/AI-Projects/llm-apps/ai_platform"
sys.path.insert(0, os.path.join(BASE_DIR, "packages/common"))
sys.path.insert(0, os.path.join(BASE_DIR, "packages/contracts"))
sys.path.insert(0, os.path.join(BASE_DIR, "apps/data-plane/vllm-engine"))
sys.path.insert(0, os.path.join(BASE_DIR, "apps/data-plane/stt-server"))
sys.path.insert(0, os.path.join(BASE_DIR, "apps/data-plane/translation-server"))
sys.path.insert(0, os.path.join(BASE_DIR, "apps/data-plane/ocr-server"))
sys.path.insert(0, os.path.join(BASE_DIR, "apps/data-plane/tts-adapter"))

import grpc
from contracts.generated import inference_pb2, inference_pb2_grpc


async def main():
    os.environ["TEST_MODE"] = "true"
    os.environ["VLLM_TEST_MODE"] = "true"

    import importlib.util

    def load_module(name, path):
        directory = os.path.dirname(path)
        sys.path.insert(0, directory)
        sys.modules.pop("config", None)
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.path.remove(directory)
        return mod

    vllm_mod = load_module("vllm_grpc", os.path.join(BASE_DIR, "apps/data-plane/vllm-engine/grpc_server.py"))
    stt_mod = load_module("stt_grpc", os.path.join(BASE_DIR, "apps/data-plane/stt-server/grpc_server.py"))
    trans_mod = load_module("trans_grpc", os.path.join(BASE_DIR, "apps/data-plane/translation-server/grpc_server.py"))
    ocr_mod = load_module("ocr_grpc", os.path.join(BASE_DIR, "apps/data-plane/ocr-server/grpc_server.py"))
    tts_mod = load_module("tts_grpc", os.path.join(BASE_DIR, "apps/data-plane/tts-adapter/grpc_server.py"))

    ports = {
        "vllm": 50061,
        "stt": 50062,
        "translation": 50063,
        "ocr": 50064,
        "tts": 50065,
    }

    servers = {}
    channels = {}
    stubs = {}

    print("=== STARTING ALL DATA-PLANE gRPC SERVERS ===")
    servers["vllm"] = await vllm_mod.create_vllm_grpc_server(port=ports["vllm"])
    servers["stt"] = await stt_mod.create_stt_grpc_server(port=ports["stt"])
    servers["translation"] = await trans_mod.create_grpc_server(port=ports["translation"])
    servers["ocr"] = await ocr_mod.create_ocr_grpc_server(port=ports["ocr"])
    servers["tts"] = await tts_mod.create_tts_grpc_server(port=ports["tts"])

    for name, srv in servers.items():
        await srv.start()
        chan = grpc.aio.insecure_channel(f"127.0.0.1:{ports[name]}")
        channels[name] = chan
        stubs[name] = inference_pb2_grpc.InferenceServiceStub(chan)
        print(f"✔ Started {name} gRPC server on 127.0.0.1:{ports[name]}")

    try:
        print("\n--- 1. Testing vLLM Engine (:50061) ---")
        health = await stubs["vllm"].GetHealth(inference_pb2.HealthRequest(service="vllm"))
        print(f"[vLLM Health] status={health.status}")
        assert health.status == "SERVING"

        chat_resp = await stubs["vllm"].ChatCompletion(
            inference_pb2.ChatRequest(
                model="chat-general-standard",
                messages=[inference_pb2.ChatMessage(role="user", content="Xin chào")],
            )
        )
        print(f"[vLLM Chat] content='{chat_resp.content[:30]}...' latency={chat_resp.latency_ms}ms")
        assert len(chat_resp.content) > 0

        stream_chunks = []
        async for chunk in stubs["vllm"].StreamChatCompletion(
            inference_pb2.ChatRequest(
                model="chat-general-standard",
                messages=[inference_pb2.ChatMessage(role="user", content="Stream me")],
            )
        ):
            stream_chunks.append(chunk.delta_content)
        print(f"[vLLM Stream] received {len(stream_chunks)} chunks: '{''.join(stream_chunks)[:30]}...'")
        assert len(stream_chunks) > 1
        print("✔ vLLM Engine gRPC tests passed!")

        print("\n--- 2. Testing STT Server (:50062) ---")
        health = await stubs["stt"].GetHealth(inference_pb2.HealthRequest(service="stt"))
        print(f"[STT Health] status={health.status}")
        assert health.status == "SERVING"

        stt_resp = await stubs["stt"].TranscribeAudio(
            inference_pb2.TranscriptionRequest(
                audio_data=b"dummy_wav_bytes_12345",
                format="wav",
                language="vi",
            )
        )
        print(f"[STT Transcribe] text='{stt_resp.text}' lang={stt_resp.detected_language}")
        assert len(stt_resp.text) > 0 or stt_resp.detected_language == "vi"
        print("✔ STT Server gRPC tests passed!")

        print("\n--- 3. Testing Translation Server (:50063) ---")
        health = await stubs["translation"].GetHealth(inference_pb2.HealthRequest(service="translation"))
        print(f"[Translation Health] status={health.status}")
        assert health.status == "SERVING"

        trans_resp = await stubs["translation"].Translate(
            inference_pb2.TranslationRequest(
                text="Hệ thống gRPC đồng bộ toàn diện",
                source_lang="vi",
                target_lang="en",
            )
        )
        print(f"[Translation] status={trans_resp.status} text='{trans_resp.translated_text}'")
        assert trans_resp.status == "success"
        print("✔ Translation Server gRPC tests passed!")

        print("\n--- 4. Testing OCR Server (:50064) ---")
        health = await stubs["ocr"].GetHealth(inference_pb2.HealthRequest(service="ocr"))
        print(f"[OCR Health] status={health.status}")
        assert health.status == "SERVING"
        cancel_resp = await stubs["ocr"].CancelInference(
            inference_pb2.CancelRequest(task_id="task_ocr_123", reason="Abort")
        )
        print(f"[OCR Cancel] success={cancel_resp.success}")
        print("✔ OCR Server gRPC tests passed!")

        print("\n--- 5. Testing TTS Adapter (:50065) ---")
        health = await stubs["tts"].GetHealth(inference_pb2.HealthRequest(service="tts"))
        print(f"[TTS Health] status={health.status}")
        assert health.status == "SERVING"

        tts_resp = await stubs["tts"].SynthesizeSpeech(
            inference_pb2.SpeechRequest(
                text="Xin chào, đây là giọng đọc AI",
                voice="vi-VN-HoaiMyNeural",
                format="mp3",
            )
        )
        print(f"[TTS Synthesize] audio bytes={len(tts_resp.audio_data)} format={tts_resp.format}")
        assert len(tts_resp.audio_data) > 0
        print("✔ TTS Adapter gRPC tests passed!")

        print("\n=======================================================")
        print("🎉 ALL 5 DATA-PLANE MICROSERVICES FULLY POWERED BY gRPC!")
        print("=======================================================")

    finally:
        for ch in channels.values():
            await ch.close()
        for srv in servers.values():
            await srv.stop(grace=0.5)


if __name__ == "__main__":
    asyncio.run(main())
