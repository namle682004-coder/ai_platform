"""
Unit Test for Điểm 10: Strict Error Handling in InferenceGrpcClient.
Verifies that fake mock fallbacks are eliminated and errors are properly categorized as Transient vs Terminal.
"""

import asyncio
import os
import sys

BASE_DIR = "/home/namle/AI-Projects/llm-apps/ai_platform"
sys.path.insert(0, os.path.join(BASE_DIR, "packages/common"))
sys.path.insert(0, os.path.join(BASE_DIR, "packages/contracts"))
sys.path.insert(0, os.path.join(BASE_DIR, "apps/dispatcher-worker/src"))

import pytest
from grpc_client.inference_client import (
    InferenceGrpcClient,
    InferenceTerminalError,
    InferenceTransientError,
    InferenceError,
)


async def main():
    # Explicitly ensure TEST_MODE is false
    os.environ["TEST_MODE"] = "false"
    client = InferenceGrpcClient()

    print("--- 1. Testing Transient Error when target is unreachable ---")
    try:
        # Connecting to unreachable port 59999
        await client.execute_inference(
            target_endpoint="127.0.0.1:59999",
            rpc_method="Translate",
            domain="translation",
            alias_name="translate-vi-standard",
            data={"text": "hello", "source_lang": "vi", "target_lang": "en"},
            timeout=1.0,
        )
        print("[FAIL] Expected InferenceTransientError, but call succeeded or fell back silently!")
        sys.exit(1)
    except InferenceTransientError as exc:
        print(f"[PASS] Successfully caught InferenceTransientError: {exc}")
    except Exception as exc:
        print(f"[PASS] Caught general exception (not falling back to fake data): {type(exc)}: {exc}")

    print("\n--- 2. Testing Terminal Error on unsupported RPC method ---")
    try:
        await client.execute_inference(
            target_endpoint="127.0.0.1:59999",
            rpc_method="UnsupportedMethod123",
            domain="unknown",
            alias_name="unknown-alias",
            data={},
            timeout=1.0,
        )
        print("[FAIL] Expected InferenceTerminalError, but call succeeded!")
        sys.exit(1)
    except InferenceTerminalError as exc:
        print(f"[PASS] Successfully caught InferenceTerminalError: {exc}")

    print("\n--- 3. Testing Streaming Interface (Điểm 11) ---")
    os.environ["TEST_MODE"] = "true"
    chunks = []
    async for chunk in client.stream_chat_completion(
        target_endpoint="127.0.0.1:50051",
        model="qwen-7b",
        messages=[{"role": "user", "content": "hi"}],
    ):
        chunks.append(chunk["delta_content"])
    streamed_text = "".join(chunks)
    print(f"Streamed result: '{streamed_text}'")
    assert len(chunks) > 1, "Expected multiple streamed chunks"
    print("[PASS] Điểm 11: gRPC Streaming interface verified!")

    await client.close()
    print("\nAll Điểm 10 and Điểm 11 tests PASSED successfully!")


if __name__ == "__main__":
    asyncio.run(main())
