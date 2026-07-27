"""WebSocket endpoint for AI streaming responses."""

import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError

from app.ai.context.builder import ContextBuilder
from app.ai.pipelines.response_parser import ResponseParser
from app.ai.prompts.builder import PromptBuilder
from app.ai.providers.factory import get_llm_provider
from app.core.database import get_database
from app.core.jwt import decode_access_token
from app.core.redis import RedisCache, get_redis
from app.repositories.chat_repository import ChatRepository
from app.repositories.file_repository import FileRepository, FolderRepository
from app.repositories.project_repository import ProjectRepository
from app.utils.object_id import parse_object_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websockets"])


@router.websocket("/ws/chat/{project_id}")
async def chat_stream(websocket: WebSocket, project_id: str) -> None:
    """Stream AI chat responses over WebSocket.

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

        db = get_database()
        cache = RedisCache(get_redis())
        projects = ProjectRepository(db)
        files_repo = FileRepository(db)
        folders_repo = FolderRepository(db)
        chat_repo = ChatRepository(db)

        project = await projects.find_by_id(parse_object_id(project_id, "project_id"))
        if not project or str(project["user_id"]) != user_id:
            await websocket.send_json({"type": "error", "message": "Forbidden"})
            await websocket.close()
            return

        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            content = data.get("content", "").strip()
            if not content:
                continue

            project_oid = parse_object_id(project_id, "project_id")
            session = await chat_repo.get_or_create_session(
                project_oid,
                parse_object_id(user_id, "user_id"),
            )
            session_oid = parse_object_id(session["id"], "session_id")
            await chat_repo.add_message(session_oid, project_oid, "user", content)

            files = await files_repo.list_for_project(project_oid)
            folders = await folders_repo.list_for_project(project_oid)
            history = await chat_repo.recent_messages(session_oid, limit=20)
            context = await ContextBuilder(cache).build(
                project=project,
                files=files,
                folders=folders,
                chat_history=history[:-1],
                current_file_path=data.get("current_file_path"),
                selected_code=data.get("selected_code"),
            )
            messages = PromptBuilder().build(context, content)
            provider = get_llm_provider()
            await websocket.send_json({"type": "start"})
            chunks: list[str] = []
            async for delta in provider.stream(messages):
                chunks.append(delta)
                await websocket.send_json({"type": "delta", "content": delta})
            full = "".join(chunks)
            parsed = ResponseParser().parse(full)
            await chat_repo.add_message(
                session_oid,
                project_oid,
                "assistant",
                parsed.message,
                model=getattr(provider, "_model", None),
            )
            await websocket.send_json(
                {
                    "type": "done",
                    "content": parsed.message,
                    "file_changes": [c.model_dump() for c in parsed.file_changes],
                }
            )
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for project %s", project_id)
    except JWTError:
        await websocket.send_json({"type": "error", "message": "Unauthorized"})
        await websocket.close()
    except Exception as exc:
        logger.exception("WebSocket chat failed: %s", exc)
        try:
            await websocket.send_json({"type": "error", "message": "Stream failed"})
            await websocket.close()
        except Exception:
            pass
