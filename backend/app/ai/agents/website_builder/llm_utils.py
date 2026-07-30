"""Shared LLM + apply helpers for website-builder nodes."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.ai.pipelines.response_parser import ResponseParser
from app.ai.providers.base import LLMMessage, LLMProvider
from app.schemas.chat import FileChangeProposal

logger = logging.getLogger(__name__)
_parser = ResponseParser()


def extract_json_object(text: str) -> Dict[str, Any]:
    """Best-effort extraction of a JSON object from model output."""
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        logger.info("Failed to parse JSON from agent output")
        return {}


async def llm_complete(
    provider: LLMProvider,
    *,
    system: str,
    user: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 7000,
) -> str:
    """Run a single non-streaming completion and return text."""
    response = await provider.complete(
        [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=user),
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        model=model,
    )
    return response.content or ""


async def generate_and_apply(
    *,
    provider: LLMProvider,
    file_modifier: Any,
    project_id: str,
    workspace_type: str,
    system: str,
    user: str,
    model: Optional[str] = None,
    max_tokens: int = 7000,
) -> tuple[str, List[FileChangeProposal]]:
    """Generate ```file``` blocks, apply them, and return (note, applied)."""
    content = await llm_complete(
        provider,
        system=system,
        user=user,
        model=model,
        max_tokens=max_tokens,
    )
    parsed = _parser.parse(content)
    applied: List[FileChangeProposal] = []
    if parsed.file_changes:
        applied, _reverse = await file_modifier.apply(
            project_id,
            parsed.file_changes,
            workspace_type=workspace_type,
        )
    note = parsed.message or f"Applied {len(applied)} file change(s)."
    return note, applied
