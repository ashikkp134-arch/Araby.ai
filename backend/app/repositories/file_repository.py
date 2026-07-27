"""File and folder repositories."""

from typing import Any, Dict, List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.models.base import serialize_doc, utc_now
from app.models.file import build_file_document, build_folder_document


class FolderRepository:
    """Data-access layer for the folders collection."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        """Initialize the repository.

        Args:
            db: MongoDB database handle.
        """
        self._collection = db.folders

    async def create(
        self,
        project_id: ObjectId,
        name: str,
        path: str,
        parent_id: Optional[ObjectId] = None,
    ) -> Dict[str, Any]:
        """Insert a folder.

        Args:
            project_id: Parent project id.
            name: Folder name.
            path: Full folder path.
            parent_id: Optional parent folder id.

        Returns:
            Serialized folder document.
        """
        doc = build_folder_document(project_id, name, path, parent_id)
        result = await self._collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return serialize_doc(doc)  # type: ignore[return-value]

    async def find_by_path(self, project_id: ObjectId, path: str) -> Optional[Dict[str, Any]]:
        """Find a folder by project and path.

        Args:
            project_id: Parent project id.
            path: Folder path.

        Returns:
            Raw folder document or None.
        """
        return await self._collection.find_one({"project_id": project_id, "path": path})

    async def list_for_project(self, project_id: ObjectId) -> List[Dict[str, Any]]:
        """List all folders for a project.

        Args:
            project_id: Parent project id.

        Returns:
            Serialized folder documents.
        """
        cursor = self._collection.find({"project_id": project_id}).sort("path", 1)
        docs = await cursor.to_list(length=5000)
        return [serialize_doc(doc) for doc in docs]  # type: ignore[misc]

    async def delete_by_prefix(self, project_id: ObjectId, path_prefix: str) -> int:
        """Delete folders under a path prefix.

        Args:
            project_id: Parent project id.
            path_prefix: Path prefix to match.

        Returns:
            Number of deleted documents.
        """
        if not path_prefix:
            result = await self._collection.delete_many({"project_id": project_id})
            return result.deleted_count
        result = await self._collection.delete_many(
            {
                "project_id": project_id,
                "$or": [
                    {"path": path_prefix},
                    {"path": {"$regex": f"^{path_prefix}/"}},
                ],
            }
        )
        return result.deleted_count

    async def delete_by_project(self, project_id: ObjectId) -> int:
        """Delete all folders for a project.

        Args:
            project_id: Parent project id.

        Returns:
            Number of deleted documents.
        """
        result = await self._collection.delete_many({"project_id": project_id})
        return result.deleted_count


class FileRepository:
    """Data-access layer for the files collection."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        """Initialize the repository.

        Args:
            db: MongoDB database handle.
        """
        self._collection = db.files

    async def create(
        self,
        project_id: ObjectId,
        name: str,
        path: str,
        content: str,
        language: str,
        folder_id: Optional[ObjectId] = None,
    ) -> Dict[str, Any]:
        """Insert a file.

        Args:
            project_id: Parent project id.
            name: File name.
            path: Full file path.
            content: File content.
            language: Language identifier.
            folder_id: Optional parent folder id.

        Returns:
            Serialized file document.
        """
        doc = build_file_document(project_id, name, path, content, language, folder_id)
        result = await self._collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return serialize_doc(doc)  # type: ignore[return-value]

    async def find_by_id(self, file_id: ObjectId) -> Optional[Dict[str, Any]]:
        """Find a file by id.

        Args:
            file_id: File ObjectId.

        Returns:
            Raw file document or None.
        """
        return await self._collection.find_one({"_id": file_id})

    async def find_by_path(self, project_id: ObjectId, path: str) -> Optional[Dict[str, Any]]:
        """Find a file by project and path.

        Args:
            project_id: Parent project id.
            path: File path.

        Returns:
            Raw file document or None.
        """
        return await self._collection.find_one({"project_id": project_id, "path": path})

    async def list_for_project(self, project_id: ObjectId) -> List[Dict[str, Any]]:
        """List all files for a project.

        Args:
            project_id: Parent project id.

        Returns:
            Serialized file documents.
        """
        cursor = self._collection.find({"project_id": project_id}).sort("path", 1)
        docs = await cursor.to_list(length=5000)
        return [serialize_doc(doc) for doc in docs]  # type: ignore[misc]

    async def update(
        self,
        file_id: ObjectId,
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Update a file document.

        Args:
            file_id: File ObjectId.
            updates: Fields to update.

        Returns:
            Serialized updated document or None.
        """
        updates = {**updates, "updated_at": utc_now()}
        doc = await self._collection.find_one_and_update(
            {"_id": file_id},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return serialize_doc(doc)

    async def delete(self, file_id: ObjectId) -> bool:
        """Delete a file by id.

        Args:
            file_id: File ObjectId.

        Returns:
            True if deleted.
        """
        result = await self._collection.delete_one({"_id": file_id})
        return result.deleted_count > 0

    async def delete_by_project(self, project_id: ObjectId) -> int:
        """Delete all files for a project.

        Args:
            project_id: Parent project id.

        Returns:
            Number of deleted documents.
        """
        result = await self._collection.delete_many({"project_id": project_id})
        return result.deleted_count

    async def delete_by_prefix(self, project_id: ObjectId, path_prefix: str) -> int:
        """Delete files under a path prefix.

        Args:
            project_id: Parent project id.
            path_prefix: Path prefix to match.

        Returns:
            Number of deleted documents.
        """
        result = await self._collection.delete_many(
            {
                "project_id": project_id,
                "$or": [
                    {"path": path_prefix},
                    {"path": {"$regex": f"^{path_prefix}/"}},
                ],
            }
        )
        return result.deleted_count
