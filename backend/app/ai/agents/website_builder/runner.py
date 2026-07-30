"""Async runner that executes the LangGraph website builder and streams progress."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Set

from app.ai.agents.website_builder.graph import build_website_graph
from app.ai.agents.website_builder.schemas import BuilderEvent
from app.ai.pipelines.chat_pipeline import StreamEvent
from app.ai.pipelines.file_modifier import FileModifier
from app.ai.pipelines.image_discovery import ImageAssetResolver
from app.ai.providers.base import LLMProvider
from app.core.config import get_settings
from app.repositories.file_repository import FileRepository
from app.schemas.chat import FileChangeProposal

logger = logging.getLogger(__name__)


class WebsiteBuilderRunner:
    """Orchestrate the agentic website builder and yield chat StreamEvents."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        file_modifier: FileModifier,
        file_repo: FileRepository,
        image_resolver: Optional[ImageAssetResolver] = None,
    ) -> None:
        self._provider = provider
        self._file_modifier = file_modifier
        self._file_repo = file_repo
        self._image_resolver = image_resolver or ImageAssetResolver()
        self._graph = build_website_graph()

    async def run_stream(
        self,
        *,
        project_id: str,
        user_request: str,
        project_name: str = "",
        workspace_type: str = "website",
        existing_paths: Optional[List[str]] = None,
        coding_model: Optional[str] = None,
        light_model: Optional[str] = None,
    ) -> AsyncIterator[StreamEvent]:
        """Execute the full agent graph, streaming progress to the chat UI.

        Yields:
            StreamEvent deltas during stages, ``preview_ready`` after Home,
            ``stage_done`` when background L2/L3 finish, then final ``done``.
        """
        settings = get_settings()
        use_xai = settings.llm_provider.lower().strip() == "xai"
        coding = coding_model or (
            settings.xai_model_coding
            if use_xai
            else settings.openai_model_coding or settings.openai_model
        )
        light = light_model or (
            settings.xai_model_light
            if use_xai
            else settings.openai_model_light or settings.openai_model
        )
        max_repair = int(getattr(settings, "website_agentic_max_repair", 2) or 2)

        yield StreamEvent(
            type="start",
            metadata={
                "agentic": True,
                "builder": "langgraph_website",
                "model": coding,
                "flow": "home_first_then_background_l2_l3",
            },
        )
        yield StreamEvent(
            type="delta",
            content=(
                "Starting **Agentic Website Builder** (home-first):\n"
                "1. Parse → Plan → Images\n"
                "2. Build **production Home page**\n"
                "3. **Live Preview Home** (you can browse now)\n"
                "4. Background: Level-2 → Level-3 → notify when done\n\n"
            ),
        )

        initial: Dict[str, Any] = {
            "user_request": user_request,
            "project_id": project_id,
            "workspace_type": workspace_type,
            "project_name": project_name,
            "existing_paths": list(existing_paths or []),
            "needs_images": True,
            "repair_count": 0,
            "max_repair": max_repair,
            "preview_ready": False,
            "level3_background": False,
            "background_complete": False,
            "code_cache": {},
            "applied_changes": [],
            "progress_messages": [],
            "events": [],
            "assistant_notes": [],
            "feature_gaps": [],
            "stages_done": [],
            "_runtime": {
                "provider": self._provider,
                "file_modifier": self._file_modifier,
                "file_repo": self._file_repo,
                "image_resolver": self._image_resolver,
                "coding_model": coding,
                "light_model": light,
                "coding_max_tokens": settings.openai_coding_max_tokens,
            },
        }

        seen_notes = 0
        emitted_special: Set[str] = set()
        final_state: Dict[str, Any] = {}
        try:
            async for update in self._graph.astream(initial, stream_mode="values"):
                final_state = update
                notes: List[str] = list(update.get("assistant_notes") or [])
                if len(notes) > seen_notes:
                    for note in notes[seen_notes:]:
                        yield StreamEvent(type="delta", content=f"{note}\n\n")
                    seen_notes = len(notes)

                events: List[BuilderEvent] = list(update.get("events") or [])
                for event in events:
                    key = f"{event.type}:{event.stage}:{event.message[:80]}"
                    if key in emitted_special:
                        continue
                    if event.type == "preview_ready":
                        emitted_special.add(key)
                        yield StreamEvent(
                            type="preview_ready",
                            content=event.message,
                            file_changes=list(update.get("applied_changes") or []),
                            metadata={
                                "open_preview": True,
                                "stage": "home",
                                **(event.meta or {}),
                            },
                        )
                        yield StreamEvent(
                            type="delta",
                            content=(
                                "\n✅ **Home is ready — opening Live Preview.**\n"
                                "Browse the Home page now. Level-2 and Level-3 are "
                                "building in the background from the cached Home code…\n\n"
                            ),
                        )
                    elif event.type == "stage_done" and event.meta.get("notify"):
                        emitted_special.add(key)
                        yield StreamEvent(
                            type="stage_done",
                            content=event.message,
                            file_changes=list(update.get("applied_changes") or []),
                            metadata={
                                "background_complete": True,
                                "notify": True,
                                **(event.meta or {}),
                            },
                        )
                        yield StreamEvent(
                            type="delta",
                            content=f"\n🔔 **{event.message}**\n\n",
                        )
        except Exception as exc:
            logger.exception("Agentic website builder failed")
            yield StreamEvent(type="error", content=str(exc) or "Website builder failed")
            return

        applied: List[FileChangeProposal] = list(final_state.get("applied_changes") or [])
        gaps = list(final_state.get("feature_gaps") or [])
        summary_parts = [
            "Agentic website build finished.",
            f"Applied {len(applied)} file change(s).",
        ]
        if final_state.get("preview_ready"):
            summary_parts.append("Live Preview opened after the Home page.")
        if final_state.get("background_complete"):
            summary_parts.append("Level-2 and Level-3 background pages completed.")
        if gaps:
            summary_parts.append("Feature gaps still detected: " + "; ".join(gaps[:8]))
        else:
            summary_parts.append("All parsed features validated present.")

        content = "\n".join(summary_parts)
        yield StreamEvent(
            type="done",
            content=content,
            file_changes=applied,
            metadata={
                "agentic": True,
                "builder": "langgraph_website",
                "stages_done": list(final_state.get("stages_done") or []),
                "preview_ready": bool(final_state.get("preview_ready")),
                "background_complete": bool(final_state.get("background_complete")),
                "feature_gaps": gaps,
                "file_changes.applied": len(applied),
            },
        )
