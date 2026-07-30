"""Compiler + Repair + PreviewGate + Feature Validate nodes."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from app.ai.agents.website_builder.llm_utils import generate_and_apply
from app.ai.agents.website_builder.prompts import REPAIR_SYSTEM
from app.ai.agents.website_builder.schemas import (
    BuilderEvent,
    CompileReport,
    FeatureSpec,
    ParsedRequirements,
)
from app.ai.agents.website_builder.state import WebsiteBuilderState
from app.ai.pipelines.preview_integrity import find_asset_usage_issues, find_integrity_issues
from app.utils.object_id import parse_object_id


async def compile_node(state: WebsiteBuilderState) -> Dict[str, Any]:
    """Deterministic Live Preview integrity check after a codegen stage."""
    runtime = state.get("_runtime") or {}
    file_repo = runtime["file_repo"]
    project_id = state["project_id"]
    stage = state.get("current_stage") or ""
    files = await file_repo.list_for_project(parse_object_id(project_id, "project_id"))
    issues = find_integrity_issues(files)
    assets = state.get("image_assets") or {}
    subjects = state.get("image_subjects") or {}
    if assets:
        issues.extend(find_asset_usage_issues(files, assets, asset_subjects=subjects))

    # Reject empty/stub Home pages after the home stage.
    if (state.get("current_stage") or "") in {"home", "home_page", "home_foundation"}:
        home_body = ""
        for item in files:
            path = str(item.get("path") or "").replace("\\", "/")
            if path.endswith("pages/Home.tsx") or path.endswith("pages/Home.jsx"):
                home_body = str(item.get("content") or "")
                break
        stripped = re.sub(r"\s+", " ", home_body).strip()
        stub_signals = (
            "Welcome to Our Store",
            "Add more content as needed",
            "Coming soon",
            "Placeholder",
        )
        if len(stripped) < 400 or any(sig in home_body for sig in stub_signals):
            from app.ai.pipelines.preview_integrity import IntegrityIssue

            issues.append(
                IntegrityIssue(
                    importer="src/pages/Home.tsx",
                    specifier="production-home",
                    tried=("src/pages/Home.tsx",),
                    kind="stub_home",
                    detail=(
                        "Home page is a stub / too thin for production preview. "
                        "Rebuild src/pages/Home.tsx with Hero, featured cards, "
                        "stats/gallery, real images, and working CTAs."
                    ),
                )
            )

    report = CompileReport(
        ok=len(issues) == 0,
        stage=stage,
        issue_count=len(issues),
        issues=[issue.summary for issue in issues[:40]],
    )
    msg = (
        f"Compiler ({stage}): OK"
        if report.ok
        else f"Compiler ({stage}): {report.issue_count} issue(s)"
    )
    return {
        "compile_report": report,
        "progress_messages": [msg],
        "events": [
            BuilderEvent(
                type="compile",
                stage=stage,
                message=msg,
                meta={"ok": report.ok, "issue_count": report.issue_count},
            )
        ],
        "assistant_notes": [msg],
    }


async def repair_node(state: WebsiteBuilderState) -> Dict[str, Any]:
    """LLM repair loop driven by the latest compile report."""
    runtime = state.get("_runtime") or {}
    report: CompileReport = state.get("compile_report") or CompileReport(ok=True)
    repair_count = int(state.get("repair_count") or 0) + 1
    issue_text = "\n".join(f"- {item}" for item in report.issues) or "- unknown"
    note, applied = await generate_and_apply(
        provider=runtime["provider"],
        file_modifier=runtime["file_modifier"],
        project_id=state["project_id"],
        workspace_type=state.get("workspace_type") or "website",
        system=REPAIR_SYSTEM,
        user=(
            f"STAGE: {state.get('current_stage')}\n"
            f"REPAIR ATTEMPT: {repair_count}\n"
            f"ISSUES:\n{issue_text}\n"
            f"IMAGE CONTEXT:\n{state.get('image_section') or ''}\n"
            f"USER BRIEF:\n{state.get('user_request')}\n"
            "Fix every issue. Preserve all features."
        ),
        model=runtime.get("coding_model"),
        max_tokens=int(runtime.get("coding_max_tokens") or 6000),
    )
    return {
        "applied_changes": applied,
        "repair_count": repair_count,
        "progress_messages": [f"Repair #{repair_count}: {note}"],
        "events": [
            BuilderEvent(
                type="repair",
                stage=state.get("current_stage") or "",
                message=f"Repair attempt {repair_count} ({len(applied)} files)",
                meta={"attempt": repair_count},
            )
        ],
        "assistant_notes": [f"Repair attempt {repair_count}: {note}"],
    }


async def preview_gate_node(state: WebsiteBuilderState) -> Dict[str, Any]:
    """Open Live Preview as soon as the production Home page is ready."""
    cached = len(state.get("code_cache") or {})
    msg = (
        "Home page is ready for Live Preview. "
        f"Cached {cached} file(s) as reference. "
        "Building Level-2 and Level-3 pages in the background — you will be notified "
        "when they finish."
    )
    return {
        "preview_ready": True,
        "level3_background": True,
        "current_stage": "preview_ready",
        "stages_done": ["preview_ready"],
        "progress_messages": [msg],
        "events": [
            BuilderEvent(
                type="preview_ready",
                stage="preview_ready",
                message=msg,
                meta={
                    "levels": ["home"],
                    "open_preview": True,
                    "cached_files": cached,
                },
            )
        ],
        "assistant_notes": [
            f"**✅ Live Preview ready — open Home now.** {msg}"
        ],
    }


def _feature_satisfied(feature: FeatureSpec, corpus: str, paths: List[str]) -> tuple[bool, str]:
    """Heuristic feature presence check against generated file contents/paths."""
    hits: List[str] = []
    for path in feature.required_paths:
        if any(path.lower() in p.lower() for p in paths):
            hits.append(f"path:{path}")
    for keyword in feature.keywords:
        if keyword and keyword.lower() in corpus.lower():
            hits.append(f"kw:{keyword}")
    # Count features like "12 vehicles".
    count_match = re.search(r"at least\s+(\d+)", feature.description, re.I)
    if count_match:
        need = int(count_match.group(1))
        # Rough: count slug/id-like entries or repeated name patterns.
        approx = len(re.findall(r"\bid\s*:", corpus)) + len(re.findall(r"\bslug\s*:", corpus))
        if approx >= need:
            hits.append(f"count>={need}")
    if hits:
        return True, ", ".join(hits[:6])
    # Soft pass for scaffold-only features if theme tokens exist.
    if feature.page_level == "scaffold" and any(
        token in corpus.lower() for token in ("primary", "#0b1f3a", "tailwind", "inter")
    ):
        return True, "theme/scaffold signals"
    return False, ""


async def validate_node(state: WebsiteBuilderState) -> Dict[str, Any]:
    """Validate that every parser feature is present in generated files."""
    runtime = state.get("_runtime") or {}
    file_repo = runtime["file_repo"]
    project_id = state["project_id"]
    files = await file_repo.list_for_project(parse_object_id(project_id, "project_id"))
    paths = [str(item.get("path") or "") for item in files]
    corpus = "\n".join(str(item.get("content") or "") for item in files)
    req: ParsedRequirements = state.get("requirements")  # type: ignore[assignment]
    gaps: List[str] = []
    updated: List[FeatureSpec] = []
    for feature in (req.features if req else []):
        ok, evidence = _feature_satisfied(feature, corpus, paths)
        feature.satisfied = ok
        feature.evidence = evidence
        updated.append(feature)
        if not ok:
            gaps.append(f"{feature.id}: {feature.description}")

    if req:
        req.features = updated

    if gaps:
        msg = f"Feature validation: {len(gaps)} gap(s) remain."
    else:
        msg = f"Feature validation: all {len(updated)} required features present."

    return {
        "requirements": req,
        "feature_gaps": gaps,
        "current_stage": "validate",
        "stages_done": ["validate"],
        "progress_messages": [msg],
        "events": [
            BuilderEvent(
                type="validate",
                stage="validate",
                message=msg,
                meta={"gaps": gaps, "feature_count": len(updated)},
            )
        ],
        "assistant_notes": [msg],
    }


async def notify_done_node(state: WebsiteBuilderState) -> Dict[str, Any]:
    """Notify the user that background Level-2 / Level-3 pages finished."""
    gaps = list(state.get("feature_gaps") or [])
    applied = state.get("applied_changes") or []
    if gaps:
        msg = (
            f"Background pages finished with {len(gaps)} feature gap(s). "
            f"Total files touched this run: {len(applied)}. "
            "Refresh Live Preview to see Level-2 / Level-3."
        )
    else:
        msg = (
            "Background Level-2 and Level-3 pages finished successfully. "
            f"{len(applied)} file change(s) applied. "
            "Refresh Live Preview to browse the full site."
        )
    return {
        "background_complete": True,
        "current_stage": "notify_done",
        "stages_done": ["notify_done"],
        "progress_messages": [msg],
        "events": [
            BuilderEvent(
                type="stage_done",
                stage="notify_done",
                message=msg,
                meta={
                    "background_complete": True,
                    "notify": True,
                    "gaps": gaps[:12],
                    "file_count": len(applied),
                },
            )
        ],
        "assistant_notes": [f"**🔔 {msg}**"],
    }
