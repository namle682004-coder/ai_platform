"""Migration 001: Initial MongoDB Indexes for Production Workloads."""
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
import pymongo

logger = logging.getLogger("aip-migrations.001")


async def upgrade(db: AsyncIOMotorDatabase) -> None:
    """Creates enterprise indexes on MongoDB collections."""
    logger.info("Applying Migration 001: Creating initial MongoDB indexes...")

    # 1. API Keys
    await db["api_keys"].create_index([("key_hash", pymongo.ASCENDING)], unique=True, name="idx_api_keys_hash_unique")
    await db["api_keys"].create_index([("tenant_id", pymongo.ASCENDING)], name="idx_api_keys_tenant")
    await db["api_keys"].create_index([("created_at", pymongo.DESCENDING)], name="idx_api_keys_created")

    # 2. Users & RBAC
    await db["users"].create_index([("email", pymongo.ASCENDING)], unique=True, name="idx_users_email_unique")
    await db["users"].create_index([("role", pymongo.ASCENDING)], name="idx_users_role")

    # 3. Model Aliases
    await db["model_aliases"].create_index([("alias", pymongo.ASCENDING)], unique=True, name="idx_model_aliases_unique")
    await db["model_aliases"].create_index([("is_active", pymongo.ASCENDING)], name="idx_model_aliases_active")

    # 4. Async Jobs & TTL
    await db["jobs"].create_index([("job_id", pymongo.ASCENDING)], unique=True, name="idx_jobs_id_unique")
    await db["jobs"].create_index([("tenant_id", pymongo.ASCENDING), ("status", pymongo.ASCENDING)], name="idx_jobs_tenant_status")
    await db["jobs"].create_index([("created_at", pymongo.DESCENDING)], name="idx_jobs_created")
    # TTL Index: Expire completed/failed jobs after expires_at if field is set
    await db["jobs"].create_index([("expires_at", pymongo.ASCENDING)], expireAfterSeconds=0, name="idx_jobs_ttl")

    # 5. Audit Logs
    await db["audit_logs"].create_index([("timestamp", pymongo.DESCENDING)], name="idx_audit_logs_timestamp")
    await db["audit_logs"].create_index([("tenant_id", pymongo.ASCENDING)], name="idx_audit_logs_tenant")
    await db["audit_logs"].create_index([("actor", pymongo.ASCENDING)], name="idx_audit_logs_actor")

    # 6. Usage Records
    await db["usage_records"].create_index([("timestamp", pymongo.DESCENDING)], name="idx_usage_timestamp")
    await db["usage_records"].create_index([("tenant_id", pymongo.ASCENDING), ("model_alias", pymongo.ASCENDING)], name="idx_usage_tenant_alias")

    # 7. API Logs
    await db["api_logs"].create_index([("created_at", pymongo.DESCENDING)], name="idx_api_logs_created")
    await db["api_logs"].create_index([("tenant_id", pymongo.ASCENDING)], name="idx_api_logs_tenant")
    await db["api_logs"].create_index([("request_id", pymongo.ASCENDING)], name="idx_api_logs_request_id")

    logger.info("Migration 001 completed successfully.")


async def downgrade(db: AsyncIOMotorDatabase) -> None:
    """Drops created indexes."""
    logger.info("Downgrading Migration 001: Dropping indexes...")
    for collection in ["api_keys", "users", "model_aliases", "jobs", "audit_logs", "usage_records", "api_logs"]:
        await db[collection].drop_indexes()
    logger.info("Migration 001 downgraded.")
