"""Refresh token repository."""

from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.base import utc_now


class RefreshTokenRepository:
    """Data-access layer for refresh_tokens collection."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        """Initialize the repository.

        Args:
            db: MongoDB database handle.
        """
        self._collection = db.refresh_tokens

    async def create(
        self,
        user_id: ObjectId,
        token_hash: str,
        jti: str,
        expires_at: datetime,
    ) -> Dict[str, Any]:
        """Store a refresh token hash.

        Args:
            user_id: Owner user id.
            token_hash: SHA-256 hash of the token.
            jti: Unique JWT id.
            expires_at: Absolute expiry timestamp.

        Returns:
            Inserted document with id.
        """
        doc = {
            "user_id": user_id,
            "token_hash": token_hash,
            "jti": jti,
            "expires_at": expires_at,
            "created_at": utc_now(),
            "revoked": False,
        }
        result = await self._collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    async def find_valid(self, token_hash: str) -> Optional[Dict[str, Any]]:
        """Find a non-revoked refresh token by hash.

        Args:
            token_hash: SHA-256 token hash.

        Returns:
            Token document or None.
        """
        return await self._collection.find_one(
            {
                "token_hash": token_hash,
                "revoked": False,
                "expires_at": {"$gt": utc_now()},
            }
        )

    async def revoke(self, token_hash: str) -> None:
        """Revoke a refresh token by hash.

        Args:
            token_hash: SHA-256 token hash.
        """
        await self._collection.update_one(
            {"token_hash": token_hash},
            {"$set": {"revoked": True}},
        )

    async def revoke_all_for_user(self, user_id: ObjectId) -> None:
        """Revoke all refresh tokens for a user.

        Args:
            user_id: Owner user id.
        """
        await self._collection.update_many(
            {"user_id": user_id, "revoked": False},
            {"$set": {"revoked": True}},
        )
