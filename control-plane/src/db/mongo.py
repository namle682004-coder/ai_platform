import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from src.configs.settings import gateway_settings

logger = logging.getLogger("aip-mongo")


class MongoManager:
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None

    def connect(self) -> AsyncIOMotorDatabase:
        if self.client is None:
            self.client = AsyncIOMotorClient(
                gateway_settings.mongo_uri,
                serverSelectionTimeoutMS=5000,
            )
            self.db = self.client[gateway_settings.mongo_database]
            logger.info("Connected to MongoDB Atlas / Local")
        return self.db

    def get_database(self) -> AsyncIOMotorDatabase:
        if self.db is None:
            return self.connect()
        return self.db

    def close(self):
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            logger.info("Closed MongoDB client")


mongo_manager = MongoManager()

def get_db() -> AsyncIOMotorDatabase:
    return mongo_manager.get_database()
