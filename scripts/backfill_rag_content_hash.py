"""
Give documents uploaded before upload de-duplication their content fingerprint, and report (optionally
remove) the copies that are already indexed twice in one knowledge base.

New uploads are compared by `content_sha256`; records written before that field existed are invisible to
the comparison until this script fills it in from the raw file in MinIO.

    # report only (default): fills nothing, deletes nothing
    python scripts/backfill_rag_content_hash.py
    # store the fingerprint on the records that lack it
    python scripts/backfill_rag_content_hash.py --write-hash
    # also delete the newer copies of each duplicate group (vectors, raw file, images, record)
    python scripts/backfill_rag_content_hash.py --write-hash --delete-duplicates

Duplicates are grouped like the upload check: same tenant, same bytes, same allowed roles; the oldest
indexed record is kept. Run inside the RAG container or with the same environment (MONGO_URI, MinIO, Qdrant).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from solutions.rag.config import rag_settings  # noqa: E402
from solutions.rag.domain.entities import normalize_tenant_id  # noqa: E402
from solutions.rag.infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter  # noqa: E402
from solutions.rag.infrastructure.adapters.storage_adapter import MinioStorageAdapter  # noqa: E402
from solutions.rag.infrastructure.repositories.mongo_document_repo import MongoDocumentRepositoryAdapter  # noqa: E402
from solutions.rag.application.use_cases.knowledge_use_case import KnowledgeManagementUseCase  # noqa: E402


def _group_key(doc: Dict[str, Any]) -> Tuple[str, str, Tuple[str, ...]]:
    roles = tuple(sorted(set(doc.get("allowed_roles") or ["*"])))
    return normalize_tenant_id(doc.get("tenant_id")), doc["content_sha256"], roles


async def main(write_hash: bool, delete_duplicates: bool) -> int:
    repo = MongoDocumentRepositoryAdapter(mongo_uri=rag_settings.mongo_uri)
    storage = MinioStorageAdapter(
        endpoint=rag_settings.minio_endpoint,
        access_key=rag_settings.minio_root_user,
        secret_key=rag_settings.minio_root_password,
    )
    coll = repo._get_collection()
    docs: List[Dict[str, Any]] = [d async for d in coll.find({}, {"_id": 0})]
    missing = 0
    for doc in docs:
        if doc.get("content_sha256") or doc.get("status") == "FAILED":
            continue
        data = storage.download_bytes(doc.get("s3_bucket", "aip-data"), doc.get("s3_object_name") or "")
        if not data:
            print(f"  ! no raw file for {doc['doc_id']} ({doc.get('filename')}), skipped")
            continue
        doc["content_sha256"] = hashlib.sha256(data).hexdigest()
        missing += 1
        if write_hash:
            await coll.update_one({"doc_id": doc["doc_id"]}, {"$set": {"content_sha256": doc["content_sha256"]}})
    print(f"documents: {len(docs)} | fingerprint computed for {missing} ({'stored' if write_hash else 'not stored'})")

    # Raw file not reachable from here (another MinIO): same tenant + file name + size is only a likely copy,
    # reported for a person to check and never deleted.
    likely: Dict[Tuple, List[Dict[str, Any]]] = defaultdict(list)
    for doc in docs:
        if not doc.get("content_sha256") and doc.get("status") != "FAILED":
            likely[(normalize_tenant_id(doc.get("tenant_id")), doc.get("filename"), doc.get("file_size_bytes"))].append(doc)
    for (tenant, filename, size), items in likely.items():
        if len(items) > 1:
            ids = ", ".join(f"{d['doc_id']}({d.get('status')})" for d in items)
            print(f"? likely duplicates without raw file: tenant={tenant} {filename} {size}B: {ids}")

    groups: Dict[Tuple, List[Dict[str, Any]]] = defaultdict(list)
    for doc in docs:
        if doc.get("content_sha256") and doc.get("status") != "FAILED":
            groups[_group_key(doc)].append(doc)
    duplicates = {k: sorted(v, key=lambda d: d.get("created_at", 0)) for k, v in groups.items() if len(v) > 1}
    print(f"duplicate groups: {len(duplicates)}")
    for (tenant, sha, roles), items in duplicates.items():
        keep = next((d for d in items if d.get("status") == "INDEXED"), items[0])
        print(f"- tenant={tenant} roles={list(roles)} sha256={sha[:12]}… keep {keep['doc_id']} ({keep.get('filename')})")
        for d in items:
            if d is not keep:
                print(f"    duplicate {d['doc_id']} status={d.get('status')} filename={d.get('filename')}")

    if delete_duplicates and duplicates:
        uc = KnowledgeManagementUseCase(
            doc_repo=repo,
            storage=storage,
            vector_store=QdrantVectorStoreAdapter(base_url=rag_settings.qdrant_url, collection_name=rag_settings.collection_name),
            embedding_service=None,
        )
        for (tenant, _, _), items in duplicates.items():
            keep = next((d for d in items if d.get("status") == "INDEXED"), items[0])
            for d in items:
                if d is not keep:
                    ok = await uc.delete_document(d["doc_id"], tenant)
                    print(f"  deleted {d['doc_id']}: {ok}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write-hash", action="store_true", help="store content_sha256 on records lacking it")
    parser.add_argument("--delete-duplicates", action="store_true", help="delete the newer copies of each duplicate group")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.write_hash, args.delete_duplicates)))
