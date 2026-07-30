"""Images Agent — conditional asset resolution before page codegen."""

from __future__ import annotations

from typing import Any, Dict

from app.ai.agents.website_builder.schemas import BuilderEvent, ParsedRequirements
from app.ai.agents.website_builder.state import WebsiteBuilderState


async def images_node(state: WebsiteBuilderState) -> Dict[str, Any]:
    """Retrieve & validate external image assets when required."""
    runtime = state.get("_runtime") or {}
    resolver = runtime.get("image_resolver")
    req: ParsedRequirements = state.get("requirements")  # type: ignore[assignment]
    user_request = state.get("user_request") or ""

    if not state.get("needs_images", True) or resolver is None:
        return {
            "image_section": "ASSET RESOLUTION: skipped (images not required).",
            "image_assets": {},
            "image_subjects": {},
            "current_stage": "images",
            "stages_done": ["images_skipped"],
            "progress_messages": ["Images: skipped (not required)."],
            "events": [
                BuilderEvent(type="progress", stage="images", message="Image retrieval skipped")
            ],
        }

    discovery = await resolver.discover(
        user_request,
        semantic_context=(req.summary if req else "") or "",
    )
    section = discovery.to_prompt_section()
    return {
        "image_section": section,
        "image_assets": dict(discovery.assets or {}),
        "image_subjects": dict(discovery.asset_subjects or {}),
        "current_stage": "images",
        "stages_done": ["images"],
        "progress_messages": [
            f"Images: resolved {discovery.url_count} validated URL(s) "
            f"across {len(discovery.assets)} subject groups."
        ],
        "events": [
            BuilderEvent(
                type="progress",
                stage="images",
                message=f"Resolved {discovery.url_count} image assets",
                meta={"url_count": discovery.url_count, "domain": discovery.domain},
            )
        ],
        "assistant_notes": [
            f"Retrieved **{discovery.url_count}** validated images "
            f"(domain={discovery.domain})."
        ],
    }
