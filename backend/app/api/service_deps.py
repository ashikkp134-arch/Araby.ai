"""Service-layer dependency providers."""

from fastapi import Depends

from app.ai.pipelines.chat_pipeline import AIPipeline
from app.api.deps import (
    get_cache,
    get_chat_repository,
    get_file_repository,
    get_folder_repository,
    get_project_repository,
    get_refresh_token_repository,
    get_user_repository,
)
from app.core.redis import RedisCache
from app.repositories.chat_repository import ChatRepository
from app.repositories.file_repository import FileRepository, FolderRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.file_service import FileService
from app.services.project_service import ProjectService
from app.services.workspace_service import WorkspaceService


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),
    refresh_repo: RefreshTokenRepository = Depends(get_refresh_token_repository),
    cache: RedisCache = Depends(get_cache),
) -> AuthService:
    """Provide AuthService.

    Args:
        user_repo: User repository.
        refresh_repo: Refresh token repository.
        cache: Redis cache.

    Returns:
        AuthService instance.
    """
    return AuthService(user_repo, refresh_repo, cache)


def get_project_service(
    project_repo: ProjectRepository = Depends(get_project_repository),
    file_repo: FileRepository = Depends(get_file_repository),
    folder_repo: FolderRepository = Depends(get_folder_repository),
    chat_repo: ChatRepository = Depends(get_chat_repository),
    cache: RedisCache = Depends(get_cache),
) -> ProjectService:
    """Provide ProjectService.

    Args:
        project_repo: Project repository.
        file_repo: File repository.
        folder_repo: Folder repository.
        chat_repo: Chat repository.
        cache: Redis cache.

    Returns:
        ProjectService instance.
    """
    return ProjectService(project_repo, file_repo, folder_repo, chat_repo, cache)


def get_file_service(
    file_repo: FileRepository = Depends(get_file_repository),
    folder_repo: FolderRepository = Depends(get_folder_repository),
    project_repo: ProjectRepository = Depends(get_project_repository),
    project_service: ProjectService = Depends(get_project_service),
    cache: RedisCache = Depends(get_cache),
) -> FileService:
    """Provide FileService.

    Args:
        file_repo: File repository.
        folder_repo: Folder repository.
        project_repo: Project repository.
        project_service: Project service.
        cache: Redis cache.

    Returns:
        FileService instance.
    """
    return FileService(file_repo, folder_repo, project_repo, project_service, cache)


def get_ai_pipeline(
    project_service: ProjectService = Depends(get_project_service),
    file_service: FileService = Depends(get_file_service),
    file_repo: FileRepository = Depends(get_file_repository),
    folder_repo: FolderRepository = Depends(get_folder_repository),
    chat_repo: ChatRepository = Depends(get_chat_repository),
    cache: RedisCache = Depends(get_cache),
) -> AIPipeline:
    """Provide AIPipeline.

    Args:
        project_service: Project service.
        file_service: File service.
        file_repo: File repository.
        folder_repo: Folder repository.
        chat_repo: Chat repository.
        cache: Redis cache.

    Returns:
        AIPipeline instance.
    """
    return AIPipeline(
        project_service=project_service,
        file_service=file_service,
        file_repo=file_repo,
        folder_repo=folder_repo,
        chat_repo=chat_repo,
        cache=cache,
    )


def get_chat_service(
    chat_repo: ChatRepository = Depends(get_chat_repository),
    project_service: ProjectService = Depends(get_project_service),
    ai_pipeline: AIPipeline = Depends(get_ai_pipeline),
) -> ChatService:
    """Provide ChatService.

    Args:
        chat_repo: Chat repository.
        project_service: Project service.
        ai_pipeline: AI pipeline.

    Returns:
        ChatService instance.
    """
    return ChatService(chat_repo, project_service, ai_pipeline)


def get_workspace_service() -> WorkspaceService:
    """Provide WorkspaceService.

    Returns:
        WorkspaceService instance.
    """
    return WorkspaceService()
