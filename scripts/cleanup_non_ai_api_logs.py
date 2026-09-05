import argparse
import asyncio
import sys

sys.path.insert(0, "packages")

from common.database.mongodb import mongo_manager
from common.repositories.api_log_repository import AI_API_LOG_PATHS


async def cleanup_logs(apply: bool) -> None:
    await mongo_manager.connect()
    db = mongo_manager.get_database()
    if db is None:
        raise RuntimeError("MongoDB is not available")

    query = {"path": {"$nin": AI_API_LOG_PATHS}}
    count = await db.api_logs.count_documents(query)
    print(f"Non-AI api_logs records: {count}")

    if apply and count:
        result = await db.api_logs.delete_many(query)
        print(f"Deleted: {result.deleted_count}")
    elif not apply:
        print("Dry run only. Re-run with --apply to delete these records.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove non-AI request records from api_logs")
    parser.add_argument("--apply", action="store_true", help="Actually delete non-AI records")
    args = parser.parse_args()
    asyncio.run(cleanup_logs(args.apply))