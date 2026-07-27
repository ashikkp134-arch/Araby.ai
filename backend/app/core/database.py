"""MongoDB connection management using Motor."""

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncIOMotorClient] = None
_database: Optional[AsyncIOMotorDatabase] = None


async def connect_to_mongo() -> None:
    """Establish a connection to MongoDB and create indexes.

    Raises:
        Exception: Propagated connection failures after logging.
    """
    global _client, _database
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.mongo_uri)
    _database = _client[settings.database_name]
    await _client.admin.command("ping")
    await _ensure_indexes(_database)
    logger.info("Connected to MongoDB database '%s'", settings.database_name)


async def close_mongo_connection() -> None:
    """Close the active MongoDB client connection."""
    global _client, _database
    if _client is not None:
        _client.close()
        _client = None
        _database = None
        logger.info("MongoDB connection closed")


def get_database() -> AsyncIOMotorDatabase:
    """Return the active database instance.

    Returns:
        AsyncIOMotorDatabase bound to the configured database.

    Raises:
        RuntimeError: If the database has not been initialized.
    """
    if _database is None:
        raise RuntimeError("Database is not initialized")
    return _database


async def _ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create required collection indexes.

    Args:
        db: Active MongoDB database handle.
    """
    await db.users.create_index("email", unique=True)
    await db.projects.create_index([("user_id", 1), ("workspace_type", 1)])
    await db.projects.create_index([("user_id", 1), ("updated_at", -1)])
    await db.files.create_index([("project_id", 1), ("path", 1)], unique=True)
    await db.files.create_index([("project_id", 1), ("folder_id", 1)])
    await db.folders.create_index([("project_id", 1), ("path", 1)], unique=True)
    await db.chat_sessions.create_index([("project_id", 1)], unique=True)
    await db.chat_messages.create_index([("session_id", 1), ("created_at", 1)])
    await db.refresh_tokens.create_index("token_hash", unique=True)
    await db.refresh_tokens.create_index("expires_at", expireAfterSeconds=0)
