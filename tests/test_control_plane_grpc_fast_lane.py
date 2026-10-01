"""
Integration Test for Điểm 14: Control Plane gRPC Fast-Lane.
Verifies that Control Plane routes real-time requests directly via gRPC instead of HTTP reverse proxy.
"""

import asyncio
import os
import sys

BASE_DIR = "/home/namle/AI-Projects/llm-apps/ai_platform"
sys.path.insert(0, os.path.join(BASE_DIR, "packages/common"))
sys.path.insert(0, os.path.join(BASE_DIR, "packages/contracts"))
sys.path.insert(0, os.path.join(BASE_DIR, "apps/control-plane"))
sys.path.insert(0, os.path.join(BASE_DIR, "apps/data-plane/translation-server"))

from fastapi import Request, Response
from unittest.mock import MagicMock
import importlib.util

_spec = importlib.util.spec_from_file_location("trans_grpc_fastlane_test_mod", os.path.join(BASE_DIR, "apps/data-plane/translation-server/grpc_server.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
create_grpc_server = _mod.create_grpc_server
from translation_engine import translation_engine
from src.api.nlp import nlp_translation, TranslationRequest


async def main():
    os.environ["TEST_MODE"] = "true"
    test_port = 50060
    os.environ["TRANSLATION_GRPC_URL"] = f"127.0.0.1:{test_port}"

    print("--- 1. Starting Translation gRPC Server on 127.0.0.1:50060 ---")
    translation_engine.initialize()
    server = await create_grpc_server(host="127.0.0.1", port=test_port)
    await server.start()
    print("gRPC server started successfully.")

    try:
        print("\n--- 2. Invoking Control Plane nlp_translation endpoint ---")
        mock_req = MagicMock(spec=Request)
        mock_req.state = MagicMock()
        mock_req.state.request_id = "test_req_fastlane"
        mock_req.headers = {"Authorization": "Bearer test-api-key"}

        mock_resp = MagicMock(spec=Response)
        mock_resp.headers = {}

        req_body = TranslationRequest(
            text="Hệ thống AI xử lý siêu tốc qua giao thức gRPC",
            source_lang="vi",
            target_lang="en",
        )

        result = await nlp_translation(
            request=mock_req,
            req=req_body,
            response=mock_resp,
            authorization="Bearer test-api-key",
        )

        print("\n--- 3. Verifying Response Telemetry ---")
        print(f"Status: {result.get('status')}")
        print(f"Translated text: '{result.get('translated_text')}'")
        metadata = result.get("metadata", {})
        protocol = metadata.get("protocol")
        cache_node = metadata.get("cache_node")
        print(f"Protocol: {protocol}, Cache Node: {cache_node}")

        assert protocol == "grpc_fast_lane", f"Expected 'grpc_fast_lane', got '{protocol}'"
        assert cache_node == "grpc-fast-lane", f"Expected 'grpc-fast-lane', got '{cache_node}'"
        print("\n[SUCCESS] Điểm 14 Verified: Control Plane successfully routed via gRPC Fast-Lane!")

    finally:
        print("\n--- 4. Shutting Down Cleanly ---")
        await server.stop(grace=1.0)
        from src.grpc_helpers.client import grpc_manager
        await grpc_manager.close()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
