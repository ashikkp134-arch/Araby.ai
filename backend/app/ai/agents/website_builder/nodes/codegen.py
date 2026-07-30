"""Codegen agents — home-first production generation + code cache for L2/L3."""

from __future__ import annotations

from typing import Any, Dict, List

from app.ai.agents.website_builder.llm_utils import generate_and_apply
from app.ai.agents.website_builder.prompts import (
    HOME_SYSTEM,
    LEVEL2_SYSTEM,
    LEVEL3_SYSTEM,
    SCAFFOLD_SYSTEM,
)
from app.ai.agents.website_builder.schemas import BuilderEvent, ParsedRequirements, SitePlan
from app.ai.agents.website_builder.state import WebsiteBuilderState
from app.utils.object_id import parse_object_id

# Paths prioritised in the home code cache sent to later agents.
_CACHE_PRIORITY = (
    "src/App.tsx",
    "src/main.tsx",
    "src/index.css",
    "src/pages/Home.tsx",
    "src/components/Navbar.tsx",
    "src/components/Footer.tsx",
    "src/components/Hero.tsx",
    "src/components/Button.tsx",
    "src/data/cars.ts",
    "src/data/items.ts",
    "index.html",
)
_CACHE_MAX_CHARS = 60_000
_CACHE_FILE_MAX = 6_000


def _format_code_cache(cache: Dict[str, str]) -> str:
    if not cache:
        return ""
    parts = [
        "CACHED HOME CODEBASE (SOURCE OF TRUTH — match style, imports, routes, "
        "component APIs; extend do not rewrite from scratch):"
    ]
    # Priority files first, then the rest.
    ordered = [p for p in _CACHE_PRIORITY if p in cache]
    ordered.extend(sorted(p for p in cache if p not in ordered))
    used = 0
    for path in ordered:
        body = cache[path]
        block = f"\n### {path}\n```tsx\n{body}\n```\n"
        if used + len(block) > _CACHE_MAX_CHARS:
            parts.append(f"\n### {path}\n(omitted — cache budget reached)\n")
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)


def _context_blob(state: WebsiteBuilderState, *, include_cache: bool = False) -> str:
    req: ParsedRequirements = state["requirements"]  # type: ignore[assignment]
    plan: SitePlan = state["plan"]  # type: ignore[assignment]
    paths = state.get("existing_paths") or []
    applied = state.get("applied_changes") or []
    applied_paths = sorted({c.path for c in applied})
    features = "\n".join(
        f"- [{f.id}] {f.description} (level={f.page_level})" for f in req.features
    )
    pages = "\n".join(
        f"- {p.level}: {p.title} route={p.route} sections={p.sections}" for p in plan.pages
    )
    blob = (
        f"PROJECT: {state.get('project_name') or req.title}\n"
        f"STACK: {', '.join(req.stack)}\n"
        f"THEME: {req.theme}\n"
        f"NAVIGATION: {req.navigation}\n"
        f"CONSTRAINTS: {req.constraints}\n"
        f"FEATURES (MUST ALL BE SATISFIED — DO NOT DROP ANY):\n{features}\n"
        f"PAGES:\n{pages}\n"
        f"DATA FILES: {plan.data_files}\n"
        f"SHARED COMPONENTS: {plan.shared_components}\n"
        f"EXISTING PROJECT PATHS: {paths[:80]}\n"
        f"ALREADY GENERATED THIS RUN: {applied_paths}\n"
        f"USER BRIEF:\n{req.raw_brief or state.get('user_request')}\n\n"
        f"{state.get('image_section') or ''}\n"
    )
    if include_cache:
        blob += "\n" + _format_code_cache(state.get("code_cache") or {})
    return blob


async def _run_stage(
    state: WebsiteBuilderState,
    *,
    stage: str,
    system: str,
    user_extra: str,
    include_cache: bool = False,
    max_tokens: int = 9000,
) -> Dict[str, Any]:
    runtime = state.get("_runtime") or {}
    token_budget = int(runtime.get("coding_max_tokens") or max_tokens)
    note, applied = await generate_and_apply(
        provider=runtime["provider"],
        file_modifier=runtime["file_modifier"],
        project_id=state["project_id"],
        workspace_type=state.get("workspace_type") or "website",
        system=system,
        user=_context_blob(state, include_cache=include_cache) + "\n" + user_extra,
        model=runtime.get("coding_model"),
        max_tokens=token_budget,
    )
    return {
        "applied_changes": applied,
        "current_stage": stage,
        "stages_done": [stage],
        "repair_count": 0,
        "progress_messages": [f"{stage}: {note}"],
        "events": [
            BuilderEvent(
                type="progress",
                stage=stage,
                message=f"{stage} generated ({len(applied)} files)",
                meta={"files": [c.path for c in applied]},
            )
        ],
        "assistant_notes": [f"**{stage}** — applied {len(applied)} file(s). {note}"],
    }


async def home_foundation_node(state: WebsiteBuilderState) -> Dict[str, Any]:
    """Pass 1: runnable foundation + navbar/footer + router shell."""
    plan: SitePlan = state["plan"]  # type: ignore[assignment]
    return await _run_stage(
        state,
        stage="home_foundation",
        system=SCAFFOLD_SYSTEM,
        max_tokens=8000,
        user_extra=(
            "HOME FOUNDATION TASK:\n"
            "Create a complete runnable shell with MemoryRouter, Navbar links to every "
            f"planned page ({[p.route for p in plan.pages]}), Footer, theme CSS, and "
            "createRoot entry. Do not leave BrowserRouter or ReactDOM.render.\n"
            "Home.tsx may be a temporary shell — the next pass fills production Home."
        ),
    )


async def home_page_node(state: WebsiteBuilderState) -> Dict[str, Any]:
    """Pass 2: full production Home page the user can Live Preview now."""
    plan: SitePlan = state["plan"]  # type: ignore[assignment]
    home_pages = [p for p in plan.pages if p.level == "home"]
    level2 = [p for p in plan.pages if p.level == "level2"]
    return await _run_stage(
        state,
        stage="home",
        system=HOME_SYSTEM,
        max_tokens=10000,
        user_extra=(
            "HOME PAGE TASK (PRODUCTION — USER WILL PREVIEW THIS NEXT):\n"
            f"Home specs: {home_pages}\n"
            f"Level2 routes for CTA/nav: {level2}\n"
            "Build a complete premium Home: Hero, Featured cards (4–6+), Why Choose Us, "
            "Gallery, Footer, working Navbar links, real images from ASSET CONTEXT, "
            "and data modules for featured items.\n"
            "FORBIDDEN: stub Home with only a heading. The page must look like a real "
            "product landing page.\n"
            "Update App.tsx/main.tsx if needed so Live Preview mounts Home correctly."
        ),
    )


async def cache_home_node(state: WebsiteBuilderState) -> Dict[str, Any]:
    """Snapshot generated Home-stage files for later agents to reference."""
    runtime = state.get("_runtime") or {}
    file_repo = runtime["file_repo"]
    project_id = state["project_id"]
    files = await file_repo.list_for_project(parse_object_id(project_id, "project_id"))
    cache: Dict[str, str] = {}
    for item in files:
        path = str(item.get("path") or "")
        content = str(item.get("content") or "")
        if not path or not content:
            continue
        # Prefer source files; skip huge binaries/noise.
        if path.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico")):
            continue
        if len(content) > _CACHE_FILE_MAX:
            content = content[:_CACHE_FILE_MAX] + "\n/* …truncated for agent cache… */\n"
        cache[path] = content

    return {
        "code_cache": cache,
        "current_stage": "cache_home",
        "stages_done": ["cache_home"],
        "progress_messages": [f"Cached {len(cache)} home-stage file(s) for L2/L3 reference."],
        "events": [
            BuilderEvent(
                type="progress",
                stage="cache_home",
                message=f"Cached {len(cache)} files",
                meta={"cached_files": list(cache.keys())[:40]},
            )
        ],
        "assistant_notes": [
            f"**Home code cached** ({len(cache)} files) — using as reference for "
            "background Level-2 / Level-3 generation."
        ],
    }


async def level2_node(state: WebsiteBuilderState) -> Dict[str, Any]:
    plan: SitePlan = state["plan"]  # type: ignore[assignment]
    pages = [p for p in plan.pages if p.level == "level2"]
    return await _run_stage(
        state,
        stage="level2",
        system=LEVEL2_SYSTEM,
        include_cache=True,
        max_tokens=10000,
        user_extra=(
            "LEVEL-2 BACKGROUND TASK:\n"
            f"Page specs: {pages}\n"
            "Extend the cached Home app. Fill the full catalogue/data, search, filters, "
            "and card grid. Keep Navbar/Footer/theme identical."
        ),
    )


async def level3_node(state: WebsiteBuilderState) -> Dict[str, Any]:
    plan: SitePlan = state["plan"]  # type: ignore[assignment]
    pages = [p for p in plan.pages if p.level == "level3"]
    return await _run_stage(
        state,
        stage="level3",
        system=LEVEL3_SYSTEM,
        include_cache=True,
        max_tokens=9000,
        user_extra=(
            "LEVEL-3 BACKGROUND TASK:\n"
            f"Page specs: {pages}\n"
            "Build detail pages using cached data shapes and Home styling."
        ),
    )


# Back-compat aliases (older graph imports / tests).
scaffold_node = home_foundation_node
home_node = home_page_node
