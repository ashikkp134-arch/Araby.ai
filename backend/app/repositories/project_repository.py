"""Project repository for MongoDB access."""

from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.models.base import serialize_doc, utc_now
from app.models.project import build_project_document
from app.schemas.project import WorkspaceType


class ProjectRepository:
    """Data-access layer for the projects collection."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        """Initialize the repository.

        Args:
            db: MongoDB database handle.
        """
        self._collection = db.projects

    async def create(
        self,
        user_id: ObjectId,
        name: str,
        description: str,
        workspace_type: WorkspaceType,
    ) -> Dict[str, Any]:
        """Insert a new project.

        Args:
            user_id: Owner user id.
            name: Project name.
            description: Project description.
            workspace_type: Workspace type.

        Returns:
            Serialized project document.
        """
        doc = build_project_document(user_id, name, description, workspace_type)
        result = await self._collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return serialize_doc(doc)  # type: ignore[return-value]

    async def find_by_id(self, project_id: ObjectId) -> Optional[Dict[str, Any]]:
        """Find a project by id.

        Args:
            project_id: Project ObjectId.

        Returns:
            Raw project document or None.
        """
        return await self._collection.find_one({"_id": project_id})

    async def list_for_user(
        self,
        user_id: ObjectId,
        workspace_type: Optional[str],
        skip: int,
        limit: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List projects for a user with optional workspace filter.

        Args:
            user_id: Owner user id.
            workspace_type: Optional workspace filter.
            skip: Number of documents to skip.
            limit: Max documents to return.

        Returns:
            Tuple of serialized items and total count.
        """
        query: Dict[str, Any] = {"user_id": user_id}
        if workspace_type:
            query["workspace_type"] = workspace_type
        total = await self._collection.count_documents(query)
        cursor = (
            self._collection.find(query)
            .sort("updated_at", -1)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [serialize_doc(doc) for doc in docs], total  # type: ignore[misc]

    async def update(
        self,
        project_id: ObjectId,
        user_id: ObjectId,
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Update a project owned by the user.

        Args:
            project_id: Project ObjectId.
            user_id: Owner user id.
            updates: Fields to update.

        Returns:
            Serialized updated document or None.
        """
        updates = {**updates, "updated_at": utc_now()}
        doc = await self._collection.find_one_and_update(
            {"_id": project_id, "user_id": user_id},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return serialize_doc(doc)

    async def delete(self, project_id: ObjectId, user_id: ObjectId) -> bool:
        """Delete a project owned by the user.

        Args:
            project_id: Project ObjectId.
            user_id: Owner user id.

        Returns:
            True if a document was deleted.
        """
        result = await self._collection.delete_one({"_id": project_id, "user_id": user_id})
        return result.deleted_count > 0

    async def touch(self, project_id: ObjectId) -> None:
        """Update the project updated_at timestamp.

        Args:
            project_id: Project ObjectId.
        """
        await self._collection.update_one(
            {"_id": project_id},
            {"$set": {"updated_at": utc_now()}},
        )
