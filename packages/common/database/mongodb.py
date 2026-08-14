import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional

logger = logging.getLogger("aip-mongodb")

DEFAULT_MONGO_URI = "mongodb+srv://namle:1234@namle.52nsi1k.mongodb.net/ai_platform?appName=namle"


class MongoDBManager:
    """
    Async MongoDB Connection Manager using Motor AsyncIOMotorClient.
    Connects to MongoDB Atlas / Local MongoDB for real data persistence.
    """

    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None

    async def connect(self, uri: str = DEFAULT_MONGO_URI, db_name: str = "ai_platform"):
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
                self.client = AsyncIOMotorClient(DEFAULT_MONGO_URI, serverSelectionTimeoutMS=5000)
                self.db = self.client["ai_platform"]
            except Exception as e:
                logger.warning(f"Lazy MongoDB connection error: {e}")
        return self.db


mongo_manager = MongoDBManager()
