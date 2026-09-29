"""
Automated unit tests for AIP Control Plane gRPC Client Manager.
Verifies channel normalization, stub generation, options, and graceful shutdown.
"""

import pytest
from src.grpc_helpers.client import GrpcClientManager
from contracts.generated.inference_pb2_grpc import InferenceServiceStub
from contracts.generated.jobs_pb2_grpc import JobServiceStub
from contracts.generated import inference_pb2, jobs_pb2


def test_grpc_client_manager_normalize_target():
    manager = GrpcClientManager()
    assert manager._normalize_target("http://vllm-engine:50051/") == "vllm-engine:50051"
    assert manager._normalize_target("https://secure-target:443") == "secure-target:443"
    assert manager._normalize_target("localhost:50053") == "localhost:50053"


@pytest.mark.anyio
async def test_grpc_client_manager_stub_creation():
    manager = GrpcClientManager()
    target = "localhost:50053"
    
    # 1. Inference stub
    stub = manager.get_inference_stub(target)
    assert isinstance(stub, InferenceServiceStub)
    # Channel should be pooled
    assert target in manager._channels
    assert target in manager._inference_stubs

    # 2. Job stub
    job_stub = manager.get_job_stub("localhost:50055")
    assert isinstance(job_stub, JobServiceStub)
    assert "localhost:50055" in manager._job_stubs

    await manager.close()


def test_grpc_protobuf_messages():
    """Verify generated Protobuf messages can be constructed correctly."""
    # Translation request/response
    req = inference_pb2.TranslationRequest(
        text="Xin chào",
        source_lang="vi",
        target_lang="en",
        model_alias="translate-vi-standard",
    )
    assert req.text == "Xin chào"
    assert req.source_lang == "vi"

    # Chat request
    chat_req = inference_pb2.ChatRequest(
        model="chat-general-standard",
        messages=[inference_pb2.ChatMessage(role="user", content="Hello AI")],
        temperature=0.7,
        max_tokens=256,
    )
    assert len(chat_req.messages) == 1
    assert chat_req.messages[0].content == "Hello AI"

    # Job status response
    job_resp = jobs_pb2.JobStatusResponse(
        job_id="job_01HXTEST",
        status="completed",
        progress=100,
        result_urls=["https://minio/artifacts/output.mp4"],
    )
    assert job_resp.job_id == "job_01HXTEST"
    assert job_resp.progress == 100


@pytest.mark.anyio
async def test_grpc_client_manager_graceful_close():
    manager = GrpcClientManager()
    # Instantiate a dummy channel
    _ = manager.get_inference_stub("localhost:59999")
    assert len(manager._channels) == 1
    
    # Graceful shutdown
    await manager.close()
    assert len(manager._channels) == 0
    assert len(manager._inference_stubs) == 0
