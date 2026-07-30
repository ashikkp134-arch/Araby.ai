"""LangGraph state for the agentic website builder."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from app.ai.agents.website_builder.schemas import (
    BuilderEvent,
    CompileReport,
    ParsedRequirements,
    SitePlan,
)
from app.schemas.chat import FileChangeProposal


def _merge_changes(
    left: List[FileChangeProposal],
    right: List[FileChangeProposal],
) -> List[FileChangeProposal]:
    """Reducer: append file changes, latest path wins."""
    by_path: Dict[str, FileChangeProposal] = {c.path: c for c in (left or [])}
    for change in right or []:
        by_path[change.path] = change
    return list(by_path.values())


def _append_events(
    left: List[BuilderEvent],
    right: List[BuilderEvent],
) -> List[BuilderEvent]:
    return list(left or []) + list(right or [])


def _append_messages(left: List[str], right: List[str]) -> List[str]:
    return list(left or []) + list(right or [])


class WebsiteBuilderState(TypedDict, total=False):
    """Shared graph state across all website-builder agents."""

    # Inputs
    user_request: str
    project_id: str
    workspace_type: str
    project_name: str
    existing_paths: List[str]

    # Agent artifacts
    requirements: Optional[ParsedRequirements]
    plan: Optional[SitePlan]
    image_section: str
    image_assets: Dict[str, List[str]]
    image_subjects: Dict[str, str]

    # Stage control
    current_stage: str
    stages_done: Annotated[List[str], _append_messages]
    repair_count: int
    max_repair: int
    needs_images: bool
    preview_ready: bool
    level3_background: bool
    # Snapshot of Home-stage files used as reference for L2/L3 generation.
    code_cache: Dict[str, str]
    background_complete: bool

    # Outputs
    applied_changes: Annotated[List[FileChangeProposal], _merge_changes]
    compile_report: Optional[CompileReport]
    feature_gaps: List[str]
    progress_messages: Annotated[List[str], _append_messages]
    events: Annotated[List[BuilderEvent], _append_events]
    assistant_notes: Annotated[List[str], _append_messages]
    error: str

    # Runtime deps injected once (not serialized across checkpoints)
    _runtime: Dict[str, Any]
