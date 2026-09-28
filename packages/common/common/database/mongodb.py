import logging
import os
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional

logger = logging.getLogger("aip-mongodb")

class MongoDBManager:
    """
    Async MongoDB Connection Manager using Motor AsyncIOMotorClient.
    Connects to MongoDB Atlas / Local MongoDB for real data persistence.
    """

    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None

    async def connect(self, uri: str | None = None, db_name: str = "ai_platform"):
        uri = uri or os.getenv("MONGO_URI")
        if not uri:
            raise RuntimeError("MONGO_URI must be configured before connecting to MongoDB")
        if not self.client:
            try:
                logger.info(f"Connecting to MongoDB Atlas Database '{db_name}'...")
                self.client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
                self.db = self.client[db_name]
                # Ping database
                await self.client.admin.command('ping')
                logger.info("Successfully connected to MongoDB Atlas!")
            except Exception as e:
                logger.warning(f"MongoDB Atlas connection warning: {e}")

    def get_database(self) -> Optional[AsyncIOMotorDatabase]:
        if self.db is None and self.client is None:
            try:
                uri = os.getenv("MONGO_URI")
                if not uri:
                    logger.error("MONGO_URI is not configured; MongoDB lazy connection skipped")
                    return self.db
                self.client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
                self.db = self.client["ai_platform"]
            except Exception as e:
                logger.warning(f"Lazy MongoDB connection error: {e}")
        return self.db


mongo_manager = MongoDBManager()
