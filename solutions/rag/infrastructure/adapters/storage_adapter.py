"""
Object Storage (MinIO / S3) Adapter for AIP Enterprise RAG Solution.
Implements domain StoragePort.
"""

from __future__ import annotations

import io
import logging
import os
from typing import Optional

from minio import Minio
from ...domain.ports import StoragePort

logger = logging.getLogger("aip-rag.adapter.storage")


class MinioStorageAdapter(StoragePort):
    """MinIO S3 storage adapter."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        secure: bool = False,
    ) -> None:
        self.endpoint = (endpoint or os.getenv("MINIO_ENDPOINT", "http://localhost:9000")).replace("http://", "").replace("https://", "")
        self.access_key = access_key or os.getenv("MINIO_ROOT_USER", "minioadmin")
        self.secret_key = secret_key or os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
        self.secure = secure
        self._client: Optional[Minio] = None

    def _get_client(self) -> Minio:
        if self._client is None:
            self._client = Minio(
                endpoint=self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )
        return self._client

    def upload_bytes(
        self,
        bucket: str,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        client = self._get_client()
        try:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
        except Exception as exc:
            logger.debug("Bucket exists check notice: %s", exc)

        client.put_object(
            bucket_name=bucket,
            object_name=object_name,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return f"s3://{bucket}/{object_name}"

    def download_bytes(self, bucket: str, object_name: str) -> Optional[bytes]:
        client = self._get_client()
        try:
            response = client.get_object(bucket_name=bucket, object_name=object_name)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except Exception as exc:
            logger.error("Failed to download '%s' from bucket '%s': %s", object_name, bucket, exc)
            return None

    def delete_object(self, bucket: str, object_name: str) -> bool:
        client = self._get_client()
        try:
            client.remove_object(bucket_name=bucket, object_name=object_name)
            return True
        except Exception as exc:
            logger.warning("Failed to delete object '%s' in bucket '%s': %s", object_name, bucket, exc)
            return False
