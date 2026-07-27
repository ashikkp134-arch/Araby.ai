"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.auth.router import router as auth_router
from app.api.v1.chat.router import router as chat_router
from app.api.v1.files.router import router as files_router
from app.api.v1.projects.router import router as projects_router
from app.api.v1.workspace.router import router as workspace_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(projects_router)
api_v1_router.include_router(files_router)
api_v1_router.include_router(chat_router)
api_v1_router.include_router(workspace_router)
