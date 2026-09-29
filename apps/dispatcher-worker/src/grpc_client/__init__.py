"""
AIP Dispatcher gRPC Client package.
Connects Worker directly to Data Plane runtimes via high-performance binary gRPC.
"""

from .inference_client import InferenceGrpcClient, inference_grpc_client

__all__ = ["InferenceGrpcClient", "inference_grpc_client"]
