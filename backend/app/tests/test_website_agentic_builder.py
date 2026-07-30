"""Unit tests for the LangGraph agentic website builder."""

from __future__ import annotations

from app.ai.agents.website_builder.graph import (
    _after_compile_home,
    _after_compile_level2,
    _after_plan,
    build_website_graph,
)
from app.ai.agents.website_builder.nodes.compiler import _feature_satisfied
from app.ai.agents.website_builder.nodes.parser import _fallback_requirements
from app.ai.agents.website_builder.schemas import CompileReport, FeatureSpec


def test_fallback_parser_captures_car_rental_features() -> None:
    brief = """
    # Build a Premium Car Rental Website
    React 18 TypeScript Vite Tailwind Framer Motion Lucide
    Dark UI Primary #0B1F3A Accent #F5B301
    Include at least 12 vehicles and 6 premium cards
    Home Cars Car Details
    """
    req = _fallback_requirements(brief)
    assert req.image_required is True
    assert any(p.level == "home" for p in req.pages)
    assert any(p.level == "level2" for p in req.pages)
    assert any(p.level == "level3" for p in req.pages)
    assert any("12" in f.description for f in req.features)
    assert "framer-motion" in req.stack
    assert "lucide-react" in req.stack


def test_graph_conditional_routes() -> None:
    assert _after_plan({"needs_images": True}) == "images"
    assert _after_plan({"needs_images": False}) == "home_foundation"

    ok = {"compile_report": CompileReport(ok=True), "repair_count": 0, "max_repair": 2}
    assert _after_compile_home(ok) == "cache_home"  # type: ignore[arg-type]
    assert _after_compile_level2(ok) == "level3"  # type: ignore[arg-type]

    bad = {
        "compile_report": CompileReport(ok=False, issue_count=2, issues=["missing"]),
        "repair_count": 0,
        "max_repair": 2,
    }
    assert _after_compile_home(bad) == "repair_home"  # type: ignore[arg-type]
    exhausted = {**bad, "repair_count": 2}
    assert _after_compile_home(exhausted) == "cache_home"  # type: ignore[arg-type]


def test_feature_validation_detects_counts_and_keywords() -> None:
    feature = FeatureSpec(
        id="cars_12",
        description="Include at least 12 vehicles",
        page_level="level2",
        keywords=["lamborghini", "ferrari"],
    )
    corpus = "id: '1'\n" * 6 + "slug: a\n" * 6 + "lamborghini huracan ferrari 296"
    ok, evidence = _feature_satisfied(feature, corpus, ["src/data/cars.ts"])
    assert ok is True
    assert "count" in evidence or "kw" in evidence


def test_coerce_theme_booleans_to_strings() -> None:
    from app.ai.agents.website_builder.nodes.parser import _coerce_requirements

    data = {
        "title": "Premium Car Rental",
        "summary": "luxury rental",
        "stack": ["react", "typescript"],
        "theme": {
            "primary": "#0B1F3A",
            "accent": "#F5B301",
            "glassmorphism": True,
            "soft_shadows": True,
            "premium_gradients": True,
            "smooth_animations": True,
            "responsive": True,
        },
        "navigation": ["Home", "Cars"],
        "pages": [
            {
                "id": "home",
                "title": "Home",
                "route": "/",
                "level": "home",
                "sections": ["hero"],
                "components": [],
                "data_deps": [],
                "notes": "",
            }
        ],
        "features": [
            {
                "id": "cars_12",
                "description": "Include at least 12 vehicles",
                "page_level": "level2",
                "required_paths": [],
                "keywords": ["12", "vehicles"],
            }
        ],
        "data_entities": ["cars"],
        "image_required": True,
        "constraints": [],
    }
    req = _coerce_requirements(data, "Build a Premium Car Rental Website")
    assert req.theme["glassmorphism"] == "true"
    assert req.theme["responsive"] == "true"
    assert any(f.id.startswith("theme_") for f in req.features)


def test_build_website_graph_compiles() -> None:
    graph = build_website_graph()
    assert graph is not None
