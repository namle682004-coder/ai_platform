"""Migration 002: Seed Initial Model Aliases and Admin Tenant."""
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from common.models.catalog import AIP_MODEL_CATALOG

logger = logging.getLogger("aip-migrations.002")


async def upgrade(db: AsyncIOMotorDatabase) -> None:
    """Seeds verified model aliases into MongoDB."""
    logger.info("Applying Migration 002: Seeding initial model aliases and defaults...")

    # 1. Model Aliases
    aliases_coll = db["model_aliases"]
    for alias_id, alias_obj in AIP_MODEL_CATALOG.items():
        doc = alias_obj.model_dump()
        doc["alias"] = alias_id
        doc["is_active"] = alias_obj.status == "active"
        await aliases_coll.update_one(
            {"alias": alias_id},
            {"$set": doc},
            upsert=True
        )
    logger.info(f"Seeded {len(AIP_MODEL_CATALOG)} verified model aliases into MongoDB.")

    # 2. System Tenant & Admin User (if not exist)
    tenants_coll = db["tenants"]
    await tenants_coll.update_one(
        {"tenant_id": "default"},
        {
            "$setOnInsert": {
                "tenant_id": "default",
                "name": "Default Enterprise Tenant",
                "tier": "enterprise",
                "is_active": True,
            }
        },
        upsert=True
    )

    logger.info("Migration 002 completed successfully.")


async def downgrade(db: AsyncIOMotorDatabase) -> None:
    """Reverts seed operations if needed."""
    logger.info("Downgrading Migration 002...")
    await db["model_aliases"].delete_many({})
    logger.info("Migration 002 downgraded.")
