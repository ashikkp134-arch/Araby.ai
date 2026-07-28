"""Tests for hybrid request routing."""

from app.ai.routing import ModelTier, RequestCategory, RequestRouter


def test_explain_routes_to_light_model() -> None:
    """Explanations should use the lightweight tier."""
    decision = RequestRouter().classify("Explain this file", "python")
    assert decision.tier == ModelTier.LIGHT
    assert decision.category == RequestCategory.CODE_EXPLANATION


def test_edit_routes_to_coding_python_agent() -> None:
    """Code edits should use the Python coding agent."""
    decision = RequestRouter().classify("add a print statement in main.py", "python")
    assert decision.tier == ModelTier.CODING
    assert decision.category == RequestCategory.PYTHON_WORKSPACE


def test_website_build_routes_to_website_agent() -> None:
    """Website builds should use the website builder category."""
    decision = RequestRouter().classify("Build a SaaS landing page", "website")
    assert decision.tier == ModelTier.CODING
    assert decision.category == RequestCategory.WEBSITE_BUILDER
