"""Semantic verification for discovered website images using a vision LLM."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence

from openai import AsyncOpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_GENERIC_PERSON_TERMS = frozenset(
    {
        "athlete",
        "athletes",
        "football",
        "footballer",
        "footballers",
        "legend",
        "legends",
        "people",
        "person",
        "player",
        "players",
        "portrait",
        "portraits",
        "soccer",
        "sports",
        "team",
        "teams",
    }
)


def _is_usable_api_key(api_key: str) -> bool:
    key = (api_key or "").strip()
    return bool(key) and not key.startswith("sk-your-")


def _json_object(content: str) -> Dict[str, Any]:
    """Parse a JSON object, tolerating an accidental fenced response."""
    text = (content or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _safe_key(value: str, fallback: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    return key[:64] or fallback


def _looks_like_person_name(subject: str, role: str) -> bool:
    """Conservatively recognize a specific person requirement."""
    if role not in {"person", "people", "player", "players", "portrait"}:
        return False
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'-]+", subject or "")
    if not 2 <= len(words) <= 5:
        return False
    lowered = {word.lower() for word in words}
    return not lowered.intersection(_GENERIC_PERSON_TERMS)


@dataclass(frozen=True)
class VisualAssetRequirement:
    """One visual subject whose images must be independently verified."""

    key: str
    role: str
    subject: str
    query: str
    identity_required: bool = False


@dataclass(frozen=True)
class ImageCandidate:
    """Candidate metadata sent alongside an image to OpenAI."""

    url: str
    provider: str
    title: str = ""
    description: str = ""


class OpenAIImageVerifier:
    """Extract visual requirements and verify candidates with a vision model."""

    def __init__(
        self,
        *,
        api_key: str = "",
        model: str = "",
        timeout_seconds: float = 20.0,
        client: Any = None,
    ) -> None:
        settings = get_settings()
        base_url = str(
            getattr(settings, "image_verification_base_url", "")
            or "https://api.openai.com/v1"
        ).strip()
        provider_key = (
            settings.xai_api_key
            if "api.x.ai" in base_url
            else settings.openai_api_key
        )
        self._api_key = (
            api_key
            or getattr(settings, "image_verification_api_key", "")
            or provider_key
            or ""
        ).strip()
        self._model = (
            model
            or str(getattr(settings, "image_verification_model", "") or "")
            or str(getattr(settings, "openai_image_verification_model", "") or "")
            or "gpt-4o-mini"
        ).strip()
        self._timeout = timeout_seconds
        self._client = client or (
            AsyncOpenAI(
                api_key=self._api_key,
                base_url=base_url,
                timeout=self._timeout,
            )
            if _is_usable_api_key(self._api_key)
            else None
        )

    @property
    def available(self) -> bool:
        return self._client is not None

    async def extract_requirements(
        self,
        user_request: str,
        *,
        domain: str,
        default_roles: Sequence[str],
    ) -> List[VisualAssetRequirement]:
        """Identify exact visual subjects, especially named people and entities."""
        if not self.available:
            return []
        role_list = ", ".join(default_roles)
        prompt = (
            "Extract the visual assets needed for this website request. Return JSON only "
            'as {"requirements":[{"key":"...", "role":"...", "subject":"...", '
            '"query":"...", "identity_required":true|false}]}. '
            f"Allowed generic roles: {role_list}. Include every explicitly named person, "
            "product, place, team, or other entity as a separate requirement. For a named "
            "person, set identity_required=true, use role=players when appropriate, and "
            "make the search query the exact full name plus useful context. Do not invent "
            "people or entities absent from the request. Also include useful generic hero, "
            "gallery, or card requirements when the brief needs them. Use at most 12 items.\n\n"
            f"Website domain: {domain}\nUser request:\n{user_request}"
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You extract precise website image requirements. "
                            "Return valid JSON and no commentary."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=1200,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAI image requirement extraction failed: %s", exc)
            return []

        payload = _json_object(response.choices[0].message.content or "")
        raw_items = payload.get("requirements")
        if not isinstance(raw_items, list):
            return []

        requirements: List[VisualAssetRequirement] = []
        used_keys: set[str] = set()
        for index, item in enumerate(raw_items[:12]):
            if not isinstance(item, Mapping):
                continue
            subject = str(item.get("subject") or "").strip()
            query = str(item.get("query") or subject).strip()
            role = _safe_key(str(item.get("role") or "cards"), "cards")
            if not subject or not query:
                continue
            base_key = _safe_key(str(item.get("key") or subject), f"asset_{index + 1}")
            key = base_key
            suffix = 2
            while key in used_keys:
                key = f"{base_key}_{suffix}"
                suffix += 1
            used_keys.add(key)
            requirements.append(
                VisualAssetRequirement(
                    key=key,
                    role=role,
                    subject=subject,
                    query=query,
                    identity_required=(
                        bool(item.get("identity_required"))
                        or _looks_like_person_name(subject, role)
                    ),
                )
            )
        return requirements

    async def verify_candidates(
        self,
        requirement: VisualAssetRequirement,
        candidates: Sequence[ImageCandidate],
    ) -> List[str]:
        """Return only URLs OpenAI confirms match the exact required subject."""
        if not self.available or not candidates:
            return []

        content: List[Dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "Verify each numbered candidate against this required website image.\n"
                    f"Subject: {requirement.subject}\n"
                    f"Search intent: {requirement.query}\n"
                    f"Usage role: {requirement.role}\n"
                    f"Exact identity required: {requirement.identity_required}\n\n"
                    "Return JSON only as "
                    '{"results":[{"index":1,"matches":true|false,'
                    '"identity_verified":true|false,"confidence":0.0,"reason":"..."}]}. '
                    "Reject generic topical similarity when the exact subject is required. "
                    "For a named person, matches=true only when the image and its supplied "
                    "source metadata support that it is the exact named person; if the face "
                    "is unclear, absent, contradicted, or uncertain, reject it. For other "
                    "subjects, reject images that do not directly depict the subject. "
                    "Use confidence from 0 to 1 and be conservative."
                ),
            }
        ]
        for index, candidate in enumerate(candidates, start=1):
            content.append(
                {
                    "type": "text",
                    "text": (
                        f"Candidate {index} metadata: provider={candidate.provider}; "
                        f"title={candidate.title or 'unknown'}; "
                        f"description={candidate.description or 'unknown'}"
                    ),
                }
            )
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": candidate.url, "detail": "low"},
                }
            )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict image relevance validator. Approve only "
                            "direct subject matches. Return valid JSON without commentary."
                        ),
                    },
                    {"role": "user", "content": content},
                ],
                temperature=0,
                max_tokens=1400,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Image verification failed subject=%s: %s",
                requirement.subject,
                exc,
            )
            if len(candidates) > 1:
                error_text = str(exc)
                remaining = [
                    candidate
                    for candidate in candidates
                    if candidate.url not in error_text
                ]
                if 0 < len(remaining) < len(candidates):
                    return await self.verify_candidates(requirement, remaining)
                approved: List[str] = []
                for candidate in candidates:
                    approved.extend(
                        await self.verify_candidates(requirement, [candidate])
                    )
                return list(dict.fromkeys(approved))
            return []

        payload = _json_object(response.choices[0].message.content or "")
        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            return []

        approved: List[str] = []
        for item in raw_results:
            if not isinstance(item, Mapping):
                continue
            try:
                index = int(item.get("index") or 0)
                confidence = float(item.get("confidence") or 0)
            except (TypeError, ValueError):
                continue
            if index < 1 or index > len(candidates):
                continue
            identity_ok = bool(item.get("identity_verified"))
            if not bool(item.get("matches")) or confidence < 0.8:
                continue
            if requirement.identity_required and not identity_ok:
                continue
            approved.append(candidates[index - 1].url)
        return approved
