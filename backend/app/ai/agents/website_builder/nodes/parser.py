"""Parser Agent — turn the user brief into structured requirements."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from app.ai.agents.website_builder.llm_utils import extract_json_object, llm_complete
from app.ai.agents.website_builder.prompts import PARSER_SYSTEM
from app.ai.agents.website_builder.schemas import (
    BuilderEvent,
    FeatureSpec,
    PageSpec,
    ParsedRequirements,
)
from app.ai.agents.website_builder.state import WebsiteBuilderState


def _fallback_requirements(user_request: str) -> ParsedRequirements:
    """Heuristic parse when the LLM JSON is empty — never drop the brief."""
    text = user_request or ""
    lower = text.lower()
    title_match = re.search(r"(?:build|create)\s+(?:a\s+)?(.+?)(?:\n|$)", text, re.I)
    title = (title_match.group(1).strip(" *#") if title_match else "Website")[:80]
    nav = []
    for label in ("Home", "Cars", "Products", "Gallery", "About", "Contact"):
        if label.lower() in lower:
            nav.append(label)
    if "home" not in [n.lower() for n in nav]:
        nav = ["Home"] + nav
    pages = [
        PageSpec(id="home", title="Home", route="/", level="home", sections=["hero", "featured"]),
    ]
    if any(k in lower for k in ("cars", "products", "catalogue", "catalog", "list")):
        pages.append(
            PageSpec(
                id="list",
                title=nav[1] if len(nav) > 1 else "Browse",
                route="/cars" if "car" in lower else "/browse",
                level="level2",
                sections=["search", "filters", "grid"],
            )
        )
        pages.append(
            PageSpec(
                id="detail",
                title="Details",
                route="/cars/:slug" if "car" in lower else "/browse/:slug",
                level="level3",
                sections=["hero", "gallery", "specs"],
            )
        )
    features: List[FeatureSpec] = []
    # Capture explicit counts like "12 vehicles" / "6 premium cards".
    for match in re.finditer(r"(\d+)\s+([A-Za-z][A-Za-z\s-]{2,40})", text):
        count, noun = match.group(1), match.group(2).strip()
        features.append(
            FeatureSpec(
                id=f"count_{count}_{re.sub(r'[^a-z0-9]+', '_', noun.lower())}",
                description=f"Include at least {count} {noun}",
                page_level="level2" if int(count) >= 8 else "home",
                keywords=[count, noun.lower()],
            )
        )
    if "dark" in lower:
        features.append(
            FeatureSpec(id="dark_ui", description="Dark UI theme", page_level="scaffold", keywords=["dark"])
        )
    if "framer" in lower or "animation" in lower:
        features.append(
            FeatureSpec(
                id="motion",
                description="Framer Motion animations",
                page_level="home",
                keywords=["framer-motion", "motion"],
            )
        )
    if "image" in lower or "photo" in lower or "car" in lower:
        features.append(
            FeatureSpec(
                id="real_images",
                description="High-quality real images matching subjects",
                page_level="home",
                keywords=["img", "unsplash", "heroImage"],
            )
        )
    stack = ["react", "typescript", "tailwind"]
    if "framer" in lower:
        stack.append("framer-motion")
    if "lucide" in lower:
        stack.append("lucide-react")
    if "router" in lower or "react" in lower:
        stack.append("react-router-dom")
    return ParsedRequirements(
        title=title or "Website",
        summary=text[:500],
        stack=stack,
        theme={"primary": "#0B1F3A", "accent": "#F5B301", "font": "Inter"},
        navigation=nav or ["Home"],
        pages=pages,
        features=features,
        data_entities=["cars"] if "car" in lower else [],
        image_required=True,
        constraints=["frontend-only", "MemoryRouter", "no-auth"],
        raw_brief=text,
    )


def _coerce_theme(raw: Any) -> Dict[str, str]:
    """Normalize theme values to strings (LLMs often emit booleans/flags)."""
    if not isinstance(raw, dict):
        return {}
    theme: Dict[str, str] = {}
    for key, value in raw.items():
        name = str(key)
        if isinstance(value, bool):
            theme[name] = "true" if value else "false"
        elif value is None:
            continue
        elif isinstance(value, (list, dict)):
            theme[name] = str(value)
        else:
            theme[name] = str(value)
    return theme


def _theme_bool_features(theme: Dict[str, str]) -> List[FeatureSpec]:
    """Promote truthy theme flags into features so they are not dropped."""
    features: List[FeatureSpec] = []
    for key, value in theme.items():
        if value.lower() not in {"true", "1", "yes", "on"}:
            continue
        if key in {"primary", "accent", "font", "fontFamily", "background"}:
            continue
        features.append(
            FeatureSpec(
                id=f"theme_{re.sub(r'[^a-z0-9]+', '_', key.lower())}",
                description=f"Theme: {key}",
                page_level="scaffold",
                keywords=[key.lower().replace("_", "-"), key.lower()],
            )
        )
    return features


def _coerce_requirements(data: Dict[str, Any], user_request: str) -> ParsedRequirements:
    if not data:
        return _fallback_requirements(user_request)
    try:
        pages = []
        for item in data.get("pages") or []:
            if not isinstance(item, dict):
                continue
            try:
                pages.append(PageSpec.model_validate(item))
            except Exception:
                continue
        features = []
        for item in data.get("features") or []:
            if not isinstance(item, dict):
                continue
            try:
                features.append(FeatureSpec.model_validate(item))
            except Exception:
                continue
        theme = _coerce_theme(data.get("theme"))
        # Avoid duplicate theme_* features if the model already listed them.
        existing_ids = {f.id for f in features}
        for extra in _theme_bool_features(theme):
            if extra.id not in existing_ids:
                features.append(extra)
        stack_raw = data.get("stack") or ["react", "typescript", "tailwind"]
        stack = [str(item) for item in stack_raw if item is not None]
        nav_raw = data.get("navigation") or ["Home"]
        navigation = [str(item) for item in nav_raw if item is not None]
        entities_raw = data.get("data_entities") or []
        data_entities = [str(item) for item in entities_raw if item is not None]
        constraints_raw = data.get("constraints") or []
        constraints = [str(item) for item in constraints_raw if item is not None]

        req = ParsedRequirements(
            title=str(data.get("title") or "Website"),
            summary=str(data.get("summary") or "")[:800],
            stack=stack,
            theme=theme,
            navigation=navigation or ["Home"],
            pages=pages,
            features=features,
            data_entities=data_entities,
            image_required=bool(data.get("image_required", True)),
            constraints=constraints,
            raw_brief=user_request,
        )
    except Exception:
        return _fallback_requirements(user_request)

    if not req.pages or not req.features:
        fallback = _fallback_requirements(user_request)
        if not req.pages:
            req.pages = fallback.pages
        if not req.features:
            req.features = fallback.features
        if not req.theme:
            req.theme = fallback.theme
    return req


async def parse_node(state: WebsiteBuilderState) -> Dict[str, Any]:
    """Parser Agent node."""
    runtime = state.get("_runtime") or {}
    provider = runtime["provider"]
    model = runtime.get("light_model") or runtime.get("coding_model")
    user_request = state.get("user_request") or ""

    raw = await llm_complete(
        provider,
        system=PARSER_SYSTEM,
        user=f"USER BRIEF:\n{user_request}",
        model=model,
        temperature=0.1,
        max_tokens=3500,
    )
    requirements = _coerce_requirements(extract_json_object(raw), user_request)
    return {
        "requirements": requirements,
        "needs_images": bool(requirements.image_required),
        "current_stage": "parse",
        "stages_done": ["parse"],
        "progress_messages": [
            f"Parser: captured “{requirements.title}” with "
            f"{len(requirements.features)} required features and "
            f"{len(requirements.pages)} pages."
        ],
        "events": [
            BuilderEvent(
                type="progress",
                stage="parse",
                message=f"Parsed requirements for {requirements.title}",
                meta={
                    "feature_count": len(requirements.features),
                    "page_count": len(requirements.pages),
                },
            )
        ],
        "assistant_notes": [
            f"Parsed **{requirements.title}** — "
            f"{len(requirements.features)} features locked, "
            f"{len(requirements.pages)} pages planned."
        ],
    }
