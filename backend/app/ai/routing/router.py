"""Request classification and hybrid model routing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.core.config import get_settings


class RequestCategory(str, Enum):
    """High-level request categories for routing."""

    SIMPLE_CHAT = "simple_chat"
    DOCUMENTATION = "documentation"
    CODE_EXPLANATION = "code_explanation"
    CODE_GENERATION = "code_generation"
    MULTI_FILE_EDIT = "multi_file_edit"
    WEBSITE_BUILDER = "website_builder"
    JAVASCRIPT_WORKSPACE = "javascript_workspace"
    PYTHON_WORKSPACE = "python_workspace"


class ModelTier(str, Enum):
    """Model capability tiers."""

    LIGHT = "light"
    CODING = "coding"


@dataclass(frozen=True)
class RoutingDecision:
    """Outcome of classifying a user request.

    Attributes:
        category: Semantic category.
        tier: light or coding model tier.
        model: Concrete model id to call.
        temperature: Suggested sampling temperature.
        max_tokens: Suggested max output tokens.
        reason: Short routing rationale for telemetry.
    """

    category: RequestCategory
    tier: ModelTier
    model: str
    temperature: float
    max_tokens: int
    reason: str


_LIGHT_PATTERNS = [
    r"\b(explain|what does|how does|summar(y|ise|ize)|overview)\b",
    r"\b(readme|documentation|docs|comment|comments|docstring)\b",
    r"\b(faq|what is|why is|describe|clarify)\b",
    r"\b(rename|naming|name suggestion|grammar)\b",
    r"\b(translate to plain english|walk me through)\b",
]

_CODING_PATTERNS = [
    r"\b(create|add|implement|generate|build|scaffold|write|include|enhance|improve)\b",
    r"\b(refactor|fix|bug|debug|optimise|optimize)\b",
    r"\b(update|modify|change|edit|delete|remove|rename file)\b",
    r"\b(fastapi|flask|react|mongodb|tailwind|endpoint|api)\b",
    r"\b(multi[- ]?file|across files|project|architecture|dependency)\b",
    r"\b(landing page|website|portfolio|saas|restaurant|page|pages|cards?|section)\b",
    r"\b(picture|pictures|image|images|photo|photos|gallery|hero|navbar|footer)\b",
]

# Website follow-ups that change UI/content (even if they also say "describe").
_WEBSITE_EDIT_PATTERNS = [
    r"\b(build|create|generate|make|design|include|add|update|enhance|improve|fix)\b",
    r"\b(picture|pictures|image|images|photo|photos|cost|costs|price|card|cards)\b",
    r"\b(page|pages|region|regions|section|layout|style|css|react|tsx|html|tailwind)\b",
    r"\b(reference|like this|hungerstation|landing|hero|navbar|gallery)\b",
]


class RequestRouter:
    """Classify requests and map them to model tier + workspace category."""

    def classify(
        self,
        user_request: str,
        workspace_type: str,
        *,
        has_selection: bool = False,
        open_tab_count: int = 0,
    ) -> RoutingDecision:
        """Classify a request and select model settings.

        Args:
            user_request: Latest user message.
            workspace_type: javascript | python | website.
            has_selection: Whether selected code is present.
            open_tab_count: Number of open editor tabs (context hint).

        Returns:
            RoutingDecision with model and prompt category.
        """
        text = (user_request or "").strip().lower()
        workspace = (workspace_type or "javascript").lower().strip()
        settings = get_settings()
        if settings.llm_provider.lower().strip() == "xai":
            light_model = settings.xai_model_light.strip()
            coding_model = settings.xai_model_coding.strip()
        else:
            light_model = (settings.openai_model_light or settings.openai_model).strip()
            coding_model = (settings.openai_model_coding or settings.openai_model).strip()

        light_hit = any(re.search(p, text) for p in _LIGHT_PATTERNS)
        coding_hit = any(re.search(p, text) for p in _CODING_PATTERNS)
        website_edit_hit = any(re.search(p, text) for p in _WEBSITE_EDIT_PATTERNS)
        long_request = len(text) > 280
        implies_edit = bool(
            re.search(r"\b(in|into|to)\s+[\w./-]+\.(js|ts|jsx|tsx|py|html|css)\b", text)
        ) or has_selection

        # Website workspace: content/UI changes must use the Website Builder agent
        # (file blocks). Do NOT demote to lightweight "explain" just because the
        # user said "describe" while also asking to add cards/images/pages.
        if workspace == "website" and (
            coding_hit
            or website_edit_hit
            or long_request
            or re.search(r"\b(build|create|generate|make|design)\b", text)
        ):
            return RoutingDecision(
                category=RequestCategory.WEBSITE_BUILDER,
                tier=ModelTier.CODING,
                model=coding_model,
                temperature=0.3,
                max_tokens=settings.openai_coding_max_tokens,
                reason="website generation / edit",
            )

        if coding_hit or implies_edit:
            if re.search(r"\b(across|multiple|several|all)\s+files?\b", text) or open_tab_count > 2:
                category = RequestCategory.MULTI_FILE_EDIT
            elif workspace == "python":
                category = RequestCategory.PYTHON_WORKSPACE
            elif workspace == "javascript":
                category = RequestCategory.JAVASCRIPT_WORKSPACE
            elif workspace == "website":
                category = RequestCategory.WEBSITE_BUILDER
            else:
                category = RequestCategory.CODE_GENERATION
            return RoutingDecision(
                category=category,
                tier=ModelTier.CODING,
                model=coding_model,
                temperature=0.2,
                max_tokens=7000,
                reason="code generation / multi-file edit",
            )

        if light_hit and not coding_hit:
            if re.search(r"\b(readme|documentation|docs|comment|docstring)\b", text):
                category = RequestCategory.DOCUMENTATION
            elif re.search(r"\b(explain|what does|how does|describe)\b", text):
                category = RequestCategory.CODE_EXPLANATION
            else:
                category = RequestCategory.SIMPLE_CHAT
            return RoutingDecision(
                category=category,
                tier=ModelTier.LIGHT,
                model=light_model,
                temperature=0.4,
                max_tokens=2048,
                reason="lightweight explanation / docs",
            )

        if workspace == "python":
            category = RequestCategory.PYTHON_WORKSPACE
        elif workspace == "website":
            category = RequestCategory.WEBSITE_BUILDER
        else:
            category = RequestCategory.JAVASCRIPT_WORKSPACE
        return RoutingDecision(
            category=category,
            tier=ModelTier.CODING,
            model=coding_model,
            temperature=0.2,
            max_tokens=8000,
            reason="default workspace coding agent",
        )


class ModelRouter:
    """Resolve concrete model ids for a tier (config-driven)."""

    def resolve(self, tier: ModelTier) -> str:
        """Return the configured model for a tier.

        Args:
            tier: light or coding.

        Returns:
            Model identifier string.
        """
        settings = get_settings()
        if settings.llm_provider.lower().strip() == "xai":
            if tier == ModelTier.LIGHT:
                return settings.xai_model_light.strip()
            return settings.xai_model_coding.strip()
        if tier == ModelTier.LIGHT:
            return (settings.openai_model_light or settings.openai_model).strip()
        return (settings.openai_model_coding or settings.openai_model).strip()
