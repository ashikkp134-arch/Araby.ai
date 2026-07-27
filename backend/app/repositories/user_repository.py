"""User repository for MongoDB access."""

from typing import Any, Dict, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.base import serialize_doc, utc_now
from app.models.user import build_user_document


class UserRepository:
    """Data-access layer for the users collection."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        """Initialize the repository.

        Args:
            db: MongoDB database handle.
        """
        self._collection = db.users

    async def create(self, email: str, password_hash: str, full_name: str) -> Dict[str, Any]:
        """Insert a new user.

        Args:
            email: User email.
            password_hash: Bcrypt hash.
            full_name: Display name.

        Returns:
            Serialized user document.
        """
        doc = build_user_document(email, password_hash, full_name)
        result = await self._collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return serialize_doc(doc)  # type: ignore[return-value]

    async def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Find a user by email.

        Args:
            email: Email address.

        Returns:
            Raw user document or None.
        """
        return await self._collection.find_one({"email": email.lower().strip()})

    async def find_by_id(self, user_id: ObjectId) -> Optional[Dict[str, Any]]:
        """Find a user by id.

        Args:
            user_id: User ObjectId.

        Returns:
            Raw user document or None.
        """
        return await self._collection.find_one({"_id": user_id})

    async def update_timestamp(self, user_id: ObjectId) -> None:
        """Touch the updated_at field for a user.

        Args:
            user_id: User ObjectId.
        """
        await self._collection.update_one(
            {"_id": user_id},
            {"$set": {"updated_at": utc_now()}},
        )
