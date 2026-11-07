"""
Re-index documents already in the knowledge base, so that parser / chunker / table-store changes apply to them.

Each selected document is sent again to the ingestion worker queue, exactly as an upload does. The worker
re-reads the raw file from MinIO, re-parses and re-chunks it, upserts the chunks in place (deterministic point
ids per chunk), removes the tail of a previous longer version and replaces the document's stored tables.
The document stays searchable throughout.

    # list what would be re-indexed (default: nothing is sent)
    python scripts/reindex_rag_documents.py [--tenant <id>] [--doc <doc_id> ...] [--status INDEXED FAILED]
    # send them to the worker, spaced to keep the embedding runtime responsive
    python scripts/reindex_rag_documents.py --apply [--delay 2]

Run with the RAG service environment (MONGO_URI, RabbitMQ). Documents whose raw file is missing from MinIO
fail in the worker and are reported with status FAILED; they must be uploaded again.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from solutions.rag.config import rag_settings  # noqa: E402
from solutions.rag.domain.entities import normalize_tenant_id  # noqa: E402
from solutions.rag.infrastructure.adapters.rabbitmq_adapter import rabbitmq_broker  # noqa: E402
from solutions.rag.infrastructure.repositories.mongo_document_repo import MongoDocumentRepositoryAdapter  # noqa: E402


async def main(args: argparse.Namespace) -> int:
    repo = MongoDocumentRepositoryAdapter(mongo_uri=rag_settings.mongo_uri)
    query: Dict[str, Any] = {"status": {"$in": args.status}}
    if args.tenant:
        query["tenant_id"] = normalize_tenant_id(args.tenant)
    if args.doc:
        query["doc_id"] = {"$in": args.doc}
    docs: List[Dict[str, Any]] = [d async for d in repo._get_collection().find(query, {"_id": 0}).sort("created_at", 1)]
    print(f"{len(docs)} document(s) selected (status in {args.status})")
    for d in docs:
        print(f"  {d['doc_id']}  tenant={d.get('tenant_id')}  chunks={d.get('total_chunks')}  {d.get('filename')}")
    if not args.apply or not docs:
        print("dry run: nothing sent (use --apply)" if docs else "")
        return 0

    sent = 0
    for d in docs:
        ok = await rabbitmq_broker.publish(queue_name=rag_settings.rag_queue, payload={"payload": d}, max_retries=3)
        sent += ok
        print(f"  {'queued' if ok else 'FAILED to queue'}: {d['doc_id']}")
        await asyncio.sleep(args.delay)
    await rabbitmq_broker.close()
    print(f"{sent}/{len(docs)} queued for re-indexing on '{rag_settings.rag_queue}'")
    return 0 if sent == len(docs) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tenant")
    ap.add_argument("--doc", nargs="*")
    ap.add_argument("--status", nargs="*", default=["INDEXED"])
    ap.add_argument("--apply", action="store_true", help="send the documents to the ingestion queue")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between two documents")
    sys.exit(asyncio.run(main(ap.parse_args())))
