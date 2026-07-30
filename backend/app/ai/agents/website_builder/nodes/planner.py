"""Planner Agent — task graph + optional public GitHub inspiration."""

from __future__ import annotations

from typing import Any, Dict, List

from app.ai.agents.website_builder.github_inspire import find_similar_public_repo
from app.ai.agents.website_builder.llm_utils import extract_json_object, llm_complete
from app.ai.agents.website_builder.prompts import PLANNER_SYSTEM
from app.ai.agents.website_builder.schemas import (
    BuilderEvent,
    PageSpec,
    ParsedRequirements,
    SitePlan,
)
from app.ai.agents.website_builder.state import WebsiteBuilderState


def _default_plan(req: ParsedRequirements) -> SitePlan:
    pages = list(req.pages) or [
        PageSpec(id="home", title="Home", route="/", level="home"),
        PageSpec(id="list", title="Browse", route="/browse", level="level2"),
        PageSpec(id="detail", title="Details", route="/browse/:slug", level="level3"),
    ]
    return SitePlan(
        architecture="react-memory-router",
        folder_tree=[
            "src/components",
            "src/pages",
            "src/layouts",
            "src/data",
            "src/types",
            "src/routes",
            "src/hooks",
            "src/utils",
        ],
        stages=["scaffold", "home", "level2", "level3"],
        pages=pages,
        shared_components=["Navbar", "Footer", "Button", "SearchBar", "Filter", "LoadingSkeleton"],
        data_files=[f"src/data/{entity}.ts" for entity in (req.data_entities or ["items"])],
        generation_chunks={
            "scaffold": ["vite/react entry", "theme css", "router shell"],
            "home": ["navbar/footer", "hero", "featured", "stats/gallery"],
            "level2": ["data module", "search/filter grid"],
            "level3": ["detail route", "gallery/specs"],
        },
        notes="Incremental IDE-style generation",
    )


async def plan_node(state: WebsiteBuilderState) -> Dict[str, Any]:
    """Planner Agent node."""
    runtime = state.get("_runtime") or {}
    provider = runtime["provider"]
    model = runtime.get("light_model") or runtime.get("coding_model")
    req: ParsedRequirements = state["requirements"]  # type: ignore[assignment]

    github = await find_similar_public_repo(req.title, req.summary)
    github_block = ""
    if github:
        github_block = (
            "\nPUBLIC GITHUB INSPIRATION (structure only — do not copy code):\n"
            f"- repo: {github.full_name} ({github.stars}★)\n"
            f"- url: {github.url}\n"
            f"- description: {github.description}\n"
            f"- root entries: {', '.join(github.structure_hints[:20])}\n"
            f"- readme excerpt:\n{github.readme_excerpt[:800]}\n"
        )

    raw = await llm_complete(
        provider,
        system=PLANNER_SYSTEM,
        user=(
            "PARSED REQUIREMENTS JSON:\n"
            f"{req.model_dump_json(indent=2)}\n"
            f"{github_block}\n"
            "Produce the site plan JSON now."
        ),
        model=model,
        temperature=0.2,
        max_tokens=4000,
    )
    data = extract_json_object(raw)
    plan = _default_plan(req)
    if data:
        pages: List[PageSpec] = []
        for item in data.get("pages") or []:
            if isinstance(item, dict):
                pages.append(PageSpec.model_validate(item))
        plan = SitePlan(
            architecture=str(data.get("architecture") or plan.architecture),
            folder_tree=list(data.get("folder_tree") or plan.folder_tree),
            stages=list(data.get("stages") or plan.stages),  # type: ignore[arg-type]
            pages=pages or plan.pages,
            shared_components=list(data.get("shared_components") or plan.shared_components),
            data_files=list(data.get("data_files") or plan.data_files),
            generation_chunks=dict(data.get("generation_chunks") or plan.generation_chunks),
            notes=str(data.get("notes") or ""),
            github=github,
        )
    else:
        plan.github = github

    note = (
        f"Planner: {len(plan.pages)} pages across stages "
        f"{' → '.join(plan.stages)}"
    )
    if github:
        note += f"; inspired by public repo {github.full_name}"

    return {
        "plan": plan,
        "current_stage": "plan",
        "stages_done": ["plan"],
        "progress_messages": [note],
        "events": [
            BuilderEvent(
                type="progress",
                stage="plan",
                message=note,
                meta={
                    "stages": plan.stages,
                    "github": github.full_name if github else None,
                },
            )
        ],
        "assistant_notes": [note],
    }
