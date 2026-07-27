"""FastAPI dependency providers."""

from typing import Any, Dict

from fastapi import Depends, Request
from jose import JWTError
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.core.jwt import decode_access_token
from app.core.redis import RedisCache, get_redis
from app.repositories.chat_repository import ChatRepository
from app.repositories.file_repository import FileRepository, FolderRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.utils.exceptions import UnauthorizedError
from app.utils.object_id import parse_object_id


def get_db() -> AsyncIOMotorDatabase:
    """Provide the MongoDB database handle.

    Returns:
        Active AsyncIOMotorDatabase.
    """
    return get_database()


def get_cache() -> RedisCache:
    """Provide a Redis cache helper.

    Returns:
        RedisCache instance.
    """
    return RedisCache(get_redis())


def get_user_repository(db: AsyncIOMotorDatabase = Depends(get_db)) -> UserRepository:
    """Provide UserRepository.

    Args:
        db: Database dependency.

    Returns:
        UserRepository instance.
    """
    return UserRepository(db)


def get_refresh_token_repository(
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> RefreshTokenRepository:
    """Provide RefreshTokenRepository.

    Args:
        db: Database dependency.

    Returns:
        RefreshTokenRepository instance.
    """
    return RefreshTokenRepository(db)


def get_project_repository(db: AsyncIOMotorDatabase = Depends(get_db)) -> ProjectRepository:
    """Provide ProjectRepository.

    Args:
        db: Database dependency.

    Returns:
        ProjectRepository instance.
    """
    return ProjectRepository(db)


def get_file_repository(db: AsyncIOMotorDatabase = Depends(get_db)) -> FileRepository:
    """Provide FileRepository.

    Args:
        db: Database dependency.

    Returns:
        FileRepository instance.
    """
    return FileRepository(db)


def get_folder_repository(db: AsyncIOMotorDatabase = Depends(get_db)) -> FolderRepository:
    """Provide FolderRepository.

    Args:
        db: Database dependency.

    Returns:
        FolderRepository instance.
    """
    return FolderRepository(db)


def get_chat_repository(db: AsyncIOMotorDatabase = Depends(get_db)) -> ChatRepository:
    """Provide ChatRepository.

    Args:
        db: Database dependency.

    Returns:
        ChatRepository instance.
    """
    return ChatRepository(db)


async def get_current_user(
    request: Request,
    user_repo: UserRepository = Depends(get_user_repository),
    cache: RedisCache = Depends(get_cache),
) -> Dict[str, Any]:
    """Resolve the authenticated user from the Authorization header.

    Args:
        request: Incoming HTTP request.
        user_repo: User repository.
        cache: Redis cache for JWT blacklist checks.

    Returns:
        Serialized authenticated user document.

    Raises:
        UnauthorizedError: If authentication fails.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise UnauthorizedError("Missing access token")
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise UnauthorizedError("Missing access token")
    if await cache.exists(f"jwt:blacklist:{token}"):
        raise UnauthorizedError("Token has been revoked")
    try:
        payload = decode_access_token(token)
    except JWTError as exc:
        raise UnauthorizedError("Invalid or expired access token") from exc
    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Invalid access token")
    user = await user_repo.find_by_id(parse_object_id(user_id, "user_id"))
    if not user:
        raise UnauthorizedError("User not found")
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "full_name": user["full_name"],
        "created_at": user["created_at"],
    }
