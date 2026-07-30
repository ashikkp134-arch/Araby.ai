"""Tests for the Asset Resolution Service (pre-LLM image discovery)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai.context.builder import ProjectContext
from app.ai.pipelines.image_discovery import (
    AssetResolutionService,
    ImageDiscoveryResult,
    ImageAssetResolver,
    ResolvedImage,
    _build_role_queries,
    _named_people_from_request,
    _named_vehicles_from_request,
    _relevance_terms,
    images_required,
)
from app.ai.pipelines.image_verification import (
    ImageCandidate,
    OpenAIImageVerifier,
    VisualAssetRequirement,
)
from app.ai.prompts.builder import PromptBuilder
from app.ai.prompts.registry import WEBSITE_AGENT_PROMPT
from app.ai.routing import RequestCategory


def test_website_prompt_requires_visible_resolved_images() -> None:
    assert "IMAGES AND ASSETS" in WEBSITE_AGENT_PROMPT
    assert "must be visibly rendered" in WEBSITE_AGENT_PROMPT
    assert "PRE-VALIDATED" in WEBSITE_AGENT_PROMPT
    assert "Never assign one person's image to another" in WEBSITE_AGENT_PROMPT
    assert "User-provided assets are authoritative" in WEBSITE_AGENT_PROMPT
    assert "VISUAL COMPLETENESS (NON-NEGOTIABLE)" in WEBSITE_AGENT_PROMPT
    assert "Factual and identity accuracy always outrank visual completeness" in (
        WEBSITE_AGENT_PROMPT
    )
    assert 'loading="lazy"' in WEBSITE_AGENT_PROMPT
    assert "srcset and sizes" in WEBSITE_AGENT_PROMPT
    assert "Never use bitmap images for interface icons" in WEBSITE_AGENT_PROMPT
    assert "create a clean, accessible SVG brand mark" in WEBSITE_AGENT_PROMPT


def test_images_required_for_explicit_and_domain_requests() -> None:
    required, reason, domain = images_required("Add movie posters and a hero background")
    assert required is True
    assert domain == "movies"

    required, reason, domain = images_required("Build a restaurant website")
    assert required is True
    assert domain == "restaurant"

    required, reason, domain = images_required(
        "Build a Premium Car Rental Website with real car images"
    )
    assert required is True
    assert domain == "cars"

    required, reason, domain = images_required("Make a wireframe text-only layout")
    assert required is False


def test_named_vehicles_extracted_from_car_rental_brief() -> None:
    prompt = """
    Include at least 12 vehicles:
    * Lamborghini Huracán
    * Ferrari 296 GTB
    * Porsche 911 Turbo S
    * BMW M4 Competition
    * Mercedes-Benz G-Class
    * Audi RS7
    * McLaren 720S
    * Rolls-Royce Ghost
    * Bentley Continental GT
    * Tesla Model S Plaid
    * Range Rover Sport
    * Chevrolet Corvette C8
    """
    vehicles = _named_vehicles_from_request(prompt)
    subjects = {item.subject.lower() for item in vehicles}
    assert len(vehicles) >= 10
    assert any("lamborghini" in s for s in subjects)
    assert any("ferrari" in s for s in subjects)
    assert any("porsche" in s for s in subjects)
    assert all(item.role == "vehicles" for item in vehicles)
    assert all(item.identity_required for item in vehicles)


def test_asset_role_words_do_not_hijack_domain() -> None:
    """Regression: "posters"/"gallery" must not turn a football site into movies."""
    for prompt in (
        "Build a Football Legends website with player posters and hero background",
        "football legends site with player images and a gallery",
        "Add posters and gallery images to my football team page",
    ):
        required, _, domain = images_required(prompt)
        assert required is True
        assert domain == "sports", f"{prompt!r} resolved to {domain!r}"


def test_f1_people_use_driver_search_context() -> None:
    prompt = """Build an F1 driver website with images:
    Max Verstappen
    Lewis Hamilton
    George Russell
    """
    required, _, domain = images_required(prompt)
    people = _named_people_from_request(prompt)
    assert required is True
    assert domain == "sports"
    assert {item.subject for item in people} == {
        "Max Verstappen",
        "Lewis Hamilton",
        "George Russell",
    }
    assert all("Formula 1 driver portrait" in item.query for item in people)


def test_domain_keywords_match_whole_words_only() -> None:
    """Regression: "cat" must not match "catalog", "car" must not match "carpet"."""
    _, _, domain = images_required("Build a product catalog page with images")
    assert domain != "pets"
    _, _, domain = images_required("Build a carpet shop website with images")
    assert domain != "cars"


def test_role_queries_stay_on_topic() -> None:
    hero = _build_role_queries("sports", "Build a Football Legends site with posters", "hero")
    players = _build_role_queries("sports", "Build a Football Legends site with posters", "players")
    assert any("football" in q for q in hero)
    assert any("stadium" in q or "pitch" in q for q in hero)
    assert any("player" in q or "footballer" in q for q in players)
    # Asset-slot words must never leak into search text.
    assert all("poster" not in q for q in hero + players)


def test_images_optional_for_generic_non_visual_brief() -> None:
    required, reason, domain = images_required("Explain how routing works in this project")
    assert required is False


def test_resolver_returns_https_assets_when_required() -> None:
    result = asyncio.run(
        AssetResolutionService(
            timeout_seconds=3.0,
            per_role=2,
            validate=False,
            semantic_verify=False,
        ).resolve("Build a travel website with gallery images")
    )
    assert result.required is True
    assert result.domain == "travel"
    assert result.assets
    assert result.url_count >= 2
    for urls in result.assets.values():
        assert urls
        assert all(url.startswith("https://") for url in urls)
        assert all("placeholder" not in url.lower() for url in urls)


def test_prompt_builder_injects_asset_resolution_section() -> None:
    result = asyncio.run(
        ImageAssetResolver(
            timeout_seconds=3.0,
            per_role=1,
            validate=False,
            semantic_verify=False,
        ).discover(
            "Build a doll store with product images"
        )
    )
    context = ProjectContext(
        project={"id": "p", "name": "Dolls", "description": "", "workspace_type": "website"},
        folder_structure="src/App.tsx",
        all_paths=["src/App.tsx"],
    )
    messages = PromptBuilder().build(
        context,
        "Build a doll store with product images",
        category=RequestCategory.WEBSITE_BUILDER,
        image_discovery=result,
    )
    system = messages[0].content
    assert "ASSET RESOLUTION SERVICE" in system
    assert "PRE-VALIDATED" in system
    assert "Do NOT invent URLs" in system
    assert any(url.startswith("https://") for url in system.split())


def test_validate_image_rejects_placeholders() -> None:
    service = AssetResolutionService(
        validate=True,
        timeout_seconds=2.0,
        semantic_verify=False,
    )

    async def _run() -> bool:
        client = AsyncMock()
        return await service._validate_image(client, "https://via.placeholder.com/300")

    assert asyncio.run(_run()) is False


def test_curated_fallback_used_when_search_empty() -> None:
    service = AssetResolutionService(
        validate=False,
        per_role=2,
        timeout_seconds=1.0,
        semantic_verify=False,
    )

    async def _empty(*_args, **_kwargs):
        return []

    with patch.object(service, "_search_unsplash", new=_empty), patch.object(
        service, "_search_pexels", new=_empty
    ), patch.object(service, "_search_wikimedia", new=_empty):
        result = asyncio.run(service.resolve("Build a sports website with images"))
    assert result.required is True
    assert result.url_count > 0
    assert "curated-cdn" in result.providers_used


def test_curated_assets_are_unique_across_all_roles() -> None:
    """A Home page must never receive the same fallback image twice."""
    service = AssetResolutionService(
        validate=False,
        per_role=3,
        timeout_seconds=1.0,
        semantic_verify=False,
    )

    async def _empty(*_args, **_kwargs):
        return []

    with patch.object(service, "_search_unsplash", new=_empty), patch.object(
        service, "_search_pexels", new=_empty
    ), patch.object(service, "_search_wikimedia", new=_empty):
        result = asyncio.run(service.resolve("Build a football website with images"))
    assert result.assets
    urls = [url for role_urls in result.assets.values() for url in role_urls]
    assert urls
    assert len(urls) == len(set(urls))


def test_search_budget_timeout_falls_back_to_curated() -> None:
    """A slow provider must never stall the chat turn."""
    service = AssetResolutionService(
        validate=False,
        per_role=2,
        budget_seconds=0.05,
        semantic_verify=False,
    )

    async def _slow(*_args, **_kwargs):
        await asyncio.sleep(5)
        return []

    with patch.object(service, "_search_wikimedia", new=_slow):
        result = asyncio.run(service.resolve("Build a travel website with images"))
    assert result.required is True
    assert result.url_count > 0
    assert "curated-cdn" in result.providers_used


def test_prompt_section_maps_roles_to_sections() -> None:
    service = AssetResolutionService(
        validate=False,
        per_role=1,
        timeout_seconds=1.0,
        semantic_verify=False,
    )

    async def _empty(*_args, **_kwargs):
        return []

    with patch.object(service, "_search_unsplash", new=_empty), patch.object(
        service, "_search_pexels", new=_empty
    ), patch.object(service, "_search_wikimedia", new=_empty):
        result = asyncio.run(service.resolve("Build a football website with images"))
    section = result.to_prompt_section()
    assert "usage=full-width hero / banner background" in section
    assert "usage=player cards and profile portraits" in section
    assert "only ONE visible Home-page element" in section


def test_openai_semantic_verifier_rejects_wrong_named_person() -> None:
    """A topical football image must not pass for a different named player."""

    class FakeOpenAIVerifier:
        available = True

        async def verify_candidates(self, requirement, candidates):
            assert requirement.subject == "Cristiano Ronaldo"
            return [
                item.url
                for item in candidates
                if "ronaldo" in item.title.lower()
            ]

    service = AssetResolutionService(
        validate=False,
        per_role=1,
        semantic_verify=True,
        image_verifier=FakeOpenAIVerifier(),
    )
    candidates = [
        ResolvedImage(
            url="https://images.example/wrong.jpg",
            provider="wikimedia",
            title="Unknown golfer on a course",
        ),
        ResolvedImage(
            url="https://images.example/ronaldo.jpg",
            provider="wikimedia",
            title="Cristiano Ronaldo playing for Portugal",
        ),
    ]

    async def _search(*_args, **_kwargs):
        return candidates

    with patch.object(service, "_search_wikimedia", new=_search):
        urls = asyncio.run(
            service._resolve_role(
                AsyncMock(),
                ["Cristiano Ronaldo football"],
                requirement=VisualAssetRequirement(
                    key="cristiano_ronaldo",
                    role="players",
                    subject="Cristiano Ronaldo",
                    query="Cristiano Ronaldo football",
                    identity_required=True,
                ),
                semantic_verify=True,
                providers_used=[],
            )
        )
    assert urls == ["https://images.example/ronaldo.jpg"]


def test_prompt_preserves_verified_subject_to_url_mapping() -> None:
    result = ImageDiscoveryResult(
        required=True,
        reason="explicit image request",
        domain="sports",
        assets={
            "cristiano_ronaldo": ["https://images.example/ronaldo.jpg"],
        },
        asset_subjects={"cristiano_ronaldo": "Cristiano Ronaldo"},
        asset_roles={"cristiano_ronaldo": "players"},
        identity_verified_roles=["cristiano_ronaldo"],
        providers_used=["wikimedia", "openai"],
    )
    section = result.to_prompt_section()
    assert "subject='Cristiano Ronaldo'" in section
    assert "usage=player cards and profile portraits" in section
    assert "exact identity verified by OpenAI" in section
    assert "label/name differs from its verified subject" in section


def test_openai_identity_verification_fails_closed_on_uncertain_match() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=(
                        '{"results":['
                        '{"index":1,"matches":true,"identity_verified":false,'
                        '"confidence":0.95,"reason":"generic footballer"},'
                        '{"index":2,"matches":true,"identity_verified":true,'
                        '"confidence":0.92,"reason":"exact named person"}]}'
                    )
                )
            )
        ]
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    verifier = OpenAIImageVerifier(api_key="sk-test", client=client)
    requirement = VisualAssetRequirement(
        key="cristiano_ronaldo",
        role="players",
        subject="Cristiano Ronaldo",
        query="Cristiano Ronaldo football",
        identity_required=True,
    )
    approved = asyncio.run(
        verifier.verify_candidates(
            requirement,
            [
                ImageCandidate(
                    url="https://images.example/generic.jpg",
                    provider="wikimedia",
                ),
                ImageCandidate(
                    url="https://images.example/ronaldo.jpg",
                    provider="wikimedia",
                    title="Cristiano Ronaldo",
                ),
            ],
        )
    )
    assert approved == ["https://images.example/ronaldo.jpg"]


def test_named_player_requirement_forces_identity_verification() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=(
                        '{"requirements":[{"key":"ronaldo","role":"players",'
                        '"subject":"Cristiano Ronaldo",'
                        '"query":"Cristiano Ronaldo football",'
                        '"identity_required":false}]}'
                    )
                )
            )
        ]
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    verifier = OpenAIImageVerifier(api_key="sk-test", client=client)
    requirements = asyncio.run(
        verifier.extract_requirements(
            "Add a Cristiano Ronaldo player card",
            domain="sports",
            default_roles=["hero", "players"],
        )
    )
    assert len(requirements) == 1
    assert requirements[0].subject == "Cristiano Ronaldo"
    assert requirements[0].identity_required is True


def test_followup_image_request_uses_prior_chat_subject() -> None:
    service = AssetResolutionService(
        validate=False,
        per_role=1,
        semantic_verify=False,
    )

    async def _empty(*_args, **_kwargs):
        return []

    with patch.object(service, "_search_unsplash", new=_empty), patch.object(
        service, "_search_pexels", new=_empty
    ), patch.object(service, "_search_wikimedia", new=_empty):
        result = asyncio.run(
            service.resolve(
                "Add images to every player card",
                semantic_context=(
                    "Build a football legends site with Cristiano Ronaldo and Lionel Messi"
                ),
            )
        )
    assert result.domain == "sports"
    assert any("football" in query for query in result.queries)


def test_explicit_player_lines_become_identity_requirements() -> None:
    requirements = _named_people_from_request(
        """
        Include these players:
        Lionel Messi
        Cristiano Ronaldo
        Neymar Jr.
        Kylian Mbappé
        Loading Skeleton
        Player Details
        """
    )
    subjects = {item.subject for item in requirements}
    assert subjects == {
        "Lionel Messi",
        "Cristiano Ronaldo",
        "Neymar Jr.",
        "Kylian Mbappé",
    }
    assert all(item.identity_required for item in requirements)
    assert "vinícius" in _relevance_terms("Vinícius Jr. football portrait")


def test_role_timeout_keeps_completed_image_results() -> None:
    service = AssetResolutionService(
        validate=False,
        per_role=1,
        budget_seconds=0.05,
        semantic_verify=False,
    )

    async def _resolve(_client, _queries, *, requirement, **_kwargs):
        if requirement.role == "hero":
            return ["https://images.example/stadium.jpg"]
        await asyncio.sleep(1)
        return []

    async def _no_fill(*_args, **_kwargs):
        return []

    with patch.object(service, "_resolve_role", new=_resolve), patch.object(
        service, "_curated_fill", new=_no_fill
    ):
        result = asyncio.run(service.resolve("Build a football website with images"))
    assert result.url_count > 0
    assert "https://images.example/stadium.jpg" in {
        url for urls in result.assets.values() for url in urls
    }
