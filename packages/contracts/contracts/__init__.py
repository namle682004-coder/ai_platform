"""
AIP Canonical Contracts and Protocol Buffer Definitions.
Provides contract-first gRPC and OpenAPI interface schemas.
"""

from .generated import (
    inference_pb2,
    inference_pb2_grpc,
    jobs_pb2,
    jobs_pb2_grpc,
)

__all__ = [
    "inference_pb2",
    "inference_pb2_grpc",
    "jobs_pb2",
    "jobs_pb2_grpc",
]
