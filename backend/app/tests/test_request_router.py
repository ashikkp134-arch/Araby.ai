"""Tests for hybrid request routing."""

from app.ai.routing import ModelTier, RequestCategory, RequestRouter
from app.core.config import Settings


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
    assert decision.max_tokens == 16384


def test_website_followup_with_describe_still_builds() -> None:
    """UI enhance follow-ups must not demote to lightweight explain-only."""
    decision = RequestRouter().classify(
        "include pictures of arabian sea, costs, describe in 6-8 cards each place",
        "website",
    )
    assert decision.tier == ModelTier.CODING
    assert decision.category == RequestCategory.WEBSITE_BUILDER


def test_project_model_tier_defaults() -> None:
    assert Settings.model_fields["openai_model_light"].default == "gpt-4o-mini"
    assert Settings.model_fields["openai_model_coding"].default == "gpt-4o"
