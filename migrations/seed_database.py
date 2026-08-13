import argparse
import asyncio
import logging
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aip-migrations")

# Mapped to existing lightweight local HuggingFace cache models
DEFAULT_ALIASES = [
    {
        "alias_name": "chat-general-standard",
        "physical_model": "Qwen/Qwen2.5-1.5B-Instruct",
        "hf_repo_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "runtime_type": "vllm",
        "min_vram_gb": 4,
        "is_active": True,
        "version": "v1.0",
        "target_url": "http://localhost:8000/v1",
    },
    {
        "alias_name": "embed-standard",
        "physical_model": "sentence-transformers/all-MiniLM-L6-v2",
        "hf_repo_id": "sentence-transformers/all-MiniLM-L6-v2",
        "runtime_type": "tei",
        "min_vram_gb": 1,
        "is_active": True,
        "version": "v1.0",
        "target_url": "http://localhost:8080/v1",
    },
    {
        "alias_name": "stt-vn-standard",
        "physical_model": "Systran/faster-whisper-small",
        "hf_repo_id": "Systran/faster-whisper-small",
        "runtime_type": "faster-whisper",
        "min_vram_gb": 2,
        "is_active": True,
        "version": "v1.0",
        "target_url": "http://localhost:8002/v1",
    },
    {
        "alias_name": "spelling-vi-precision",
        "physical_model": "vinai/phobert-base",
        "hf_repo_id": "vinai/phobert-base",
        "runtime_type": "triton",
        "min_vram_gb": 2,
        "is_active": True,
        "version": "v1.0",
        "target_url": "http://localhost:8003/v1",
    },
]


async def seed_database(mongo_uri: str, db_name: str, dry_run: bool = False):
    logger.info(f"Starting MongoDB Migration & Seeding for DB: '{db_name}' (Dry-run: {dry_run})")
    
    if dry_run:
        logger.info("[Dry-run] Would create indexes for collections: api_keys, aliases, jobs, usage_records, audit_logs")
        logger.info(f"[Dry-run] Would seed {len(DEFAULT_ALIASES)} local cached model aliases.")
        return

    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]

    # 1. Create Indexes
    logger.info("Creating MongoDB Indexes...")
    await db.api_keys.create_index("hashed_key", unique=True)
    await db.api_keys.create_index("tenant_id")
    await db.aliases.create_index("alias_name", unique=True)
    await db.jobs.create_index("job_id", unique=True)
    await db.jobs.create_index([("tenant_id", 1), ("status", 1)])
    await db.usage_records.create_index([("tenant_id", 1), ("created_at", -1)])
    await db.audit_logs.create_index("timestamp")

    # 2. Seed Default Aliases
    logger.info("Seeding Default Local Model Aliases...")
    for alias in DEFAULT_ALIASES:
        alias["updated_at"] = datetime.utcnow()
        await db.aliases.update_one(
            {"alias_name": alias["alias_name"]},
            {"$set": alias},
            upsert=True
        )

    logger.info("Database Seeding & Migration Completed Successfully!")
    client.close()


def main():
    parser = argparse.ArgumentParser(description="AIP Database Seed Script")
    parser.add_argument("--mongo-uri", default="mongodb://root:example@localhost:27017", help="MongoDB Connection URI")
    parser.add_argument("--db-name", default="aip_platform", help="MongoDB Database Name")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without executing DB writes")
    args = parser.parse_args()

    asyncio.run(seed_database(args.mongo_uri, args.db_name, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
