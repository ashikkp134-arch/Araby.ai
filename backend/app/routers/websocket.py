"""WebSocket endpoint for AI streaming responses."""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError

from app.ai.pipelines.chat_pipeline import AIPipeline
from app.core.database import get_database
from app.core.jwt import decode_access_token
from app.core.redis import RedisCache, get_redis
from app.repositories.chat_repository import ChatRepository
from app.repositories.file_repository import FileRepository, FolderRepository
from app.repositories.project_repository import ProjectRepository
from app.services.file_service import FileService
from app.services.project_service import ProjectService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websockets"])


def _build_pipeline() -> AIPipeline:
    """Construct an AIPipeline for the WebSocket request scope.

    Returns:
        Wired AIPipeline instance.
    """
    db = get_database()
    cache = RedisCache(get_redis())
    projects = ProjectRepository(db)
    files_repo = FileRepository(db)
    folders_repo = FolderRepository(db)
    chat_repo = ChatRepository(db)
    project_service = ProjectService(projects, files_repo, folders_repo, chat_repo, cache)
    file_service = FileService(files_repo, folders_repo, projects, project_service, cache)
    return AIPipeline(
        project_service=project_service,
        file_service=file_service,
        file_repo=files_repo,
        folder_repo=folders_repo,
        chat_repo=chat_repo,
        cache=cache,
    )


@router.websocket("/ws/chat/{project_id}")
async def chat_stream(websocket: WebSocket, project_id: str) -> None:
    """Stream AI chat responses over WebSocket via AIPipeline.

    Args:
        websocket: Active WebSocket connection.
        project_id: Target project id.
    """
    await websocket.accept()
    try:
        auth_msg = await websocket.receive_text()
        payload = json.loads(auth_msg)
        token = payload.get("token", "")
        user_payload = decode_access_token(token)
        user_id = user_payload["sub"]

        pipeline = _build_pipeline()

        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            if data.get("type") == "cancel":
                # Client cancellation: acknowledge and continue listening.
                await websocket.send_json({"type": "cancelled"})
                continue
            content = (data.get("content") or "").strip()
            if not content:
                continue

            apply_changes = data.get("apply_changes", True)
            open_tabs = data.get("open_tabs") or []
            async for event in pipeline.run_stream(
                user_id=user_id,
                project_id=project_id,
                content=content,
                current_file_path=data.get("current_file_path"),
                selected_code=data.get("selected_code"),
                apply_changes=bool(apply_changes),
                open_tabs=list(open_tabs) if isinstance(open_tabs, list) else [],
            ):
                if event.type == "start":
                    await websocket.send_json({"type": "start", "metadata": event.metadata})
                elif event.type == "delta":
                    await websocket.send_json({"type": "delta", "content": event.content})
                elif event.type == "error":
                    await websocket.send_json({"type": "error", "message": event.content})
                elif event.type == "done":
                    await websocket.send_json(
                        {
                            "type": "done",
                            "content": event.content,
                            "file_changes": [c.model_dump() for c in event.file_changes],
                            "metadata": event.metadata,
                        }
                    )
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for project %s", project_id)
    except JWTError:
        try:
            await websocket.send_json({"type": "error", "message": "Unauthorized"})
            await websocket.close()
        except Exception:
            pass
    except Exception as exc:
        logger.exception("WebSocket chat failed: %s", exc)
        try:
            await websocket.send_json({"type": "error", "message": str(exc) or "Stream failed"})
            await websocket.close()
        except Exception:
            pass
