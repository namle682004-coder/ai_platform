"""Enterprise MongoDB Migration Runner for AIP Platform."""
import asyncio
import importlib
import logging
import os
import sys
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("aip-migrations.runner")

MIGRATIONS = [
    ("001_initial_mongo_indexes", "migrations.001_initial_mongo_indexes"),
    ("002_seed_catalogs", "migrations.002_seed_catalogs"),
]


async def run_migrations(mongo_uri: str | None = None, db_name: str = "ai_platform") -> None:
    uri = mongo_uri or os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    db = client[db_name]

    logger.info(f"Connecting to MongoDB at {uri.split('@')[-1] if '@' in uri else uri}, db='{db_name}'...")
    meta_coll = db["_migrations_meta"]

    for name, module_path in MIGRATIONS:
        record = await meta_coll.find_one({"migration": name})
        if record and record.get("status") == "applied":
            logger.info(f"Migration '{name}' already applied at {record.get('applied_at')}. Skipping.")
            continue

        logger.info(f"Running migration '{name}'...")
        mod = importlib.import_module(module_path)
        try:
            await mod.upgrade(db)
            await meta_coll.update_one(
                {"migration": name},
                {"$set": {"status": "applied", "applied_at": datetime.now(timezone.utc)}},
                upsert=True,
            )
            logger.info(f"Migration '{name}' applied successfully.")
        except Exception as e:
            logger.error(f"Migration '{name}' failed with error: {e}", exc_info=True)
            await meta_coll.update_one(
                {"migration": name},
                {"$set": {"status": "failed", "failed_at": datetime.now(timezone.utc), "error": str(e)}},
                upsert=True,
            )
            raise

    logger.info("All pending migrations applied successfully.")


if __name__ == "__main__":
    uri = os.getenv("MONGO_URI") or (sys.argv[1] if len(sys.argv) > 1 else None)
    asyncio.run(run_migrations(mongo_uri=uri))
