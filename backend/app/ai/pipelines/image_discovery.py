"""Asset Resolution Service for the Website Builder.

Separates image discovery from LLM code generation:

1. Detect whether imagery is required.
2. Search trusted providers (Unsplash / Pexels / Wikimedia / curated CDN).
3. Validate candidates (HTTPS, HTTP 200, image MIME, min size).
4. Use a lightweight vision model to verify subject and named-person identity.
5. Inject only validated, subject-labelled URLs into the generation prompt.

The LLM must integrate these URLs — it must never invent image links.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from app.ai.pipelines.image_verification import (
    ImageCandidate,
    OpenAIImageVerifier,
    VisualAssetRequirement,
)
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_EXPLICIT_IMAGE_PATTERNS = (
    r"\bimages?\b",
    r"\bpictures?\b",
    r"\bphotos?\b",
    r"\bimagery\b",
    r"\bhero\b",
    r"\bbackground\b",
    r"\bposters?\b",
    r"\bgallery\b",
    r"\bproduct images?\b",
    r"\bcategory images?\b",
    r"\bhigh[- ]?quality images?\b",
    r"\brealistic images?\b",
    r"\bvisual redesign\b",
    r"\bricher ui\b",
    r"\bpremium\b",
)

_IMAGE_OPTIONAL_PATTERNS = (
    r"\bwireframe\b",
    r"\bprototype\b",
    r"\btext[- ]only\b",
    r"\bplaceholder layout\b",
    r"\bno images?\b",
    r"\bwithout images?\b",
)

_IMAGE_DOMAIN_KEYWORDS: Dict[str, Sequence[str]] = {
    "sports": (
        "sports", "sport", "football", "soccer", "basketball", "cricket", "tennis",
        "athlete", "athletes", "player", "players", "stadium", "league", "team",
        "messi", "ronaldo", "pele", "maradona", "formula 1", "formula one", "f1",
        "motorsport", "racing", "racer", "driver", "drivers", "grand prix",
    ),
    "movies": ("movie", "movies", "cinema", "cinematic", "film", "films", "netflix", "imdb"),
    "restaurant": ("restaurant", "cafe", "bakery", "food", "dining", "menu", "dish", "cuisine"),
    "travel": ("travel", "tourism", "destination", "destinations", "vacation", "trip", "tour"),
    "hotel": ("hotel", "hotels", "resort", "lodging"),
    "fashion": ("fashion", "clothing", "apparel", "boutique"),
    "real_estate": ("real estate", "property", "apartment", "housing", "realty"),
    "ecommerce": ("ecommerce", "e-commerce", "shop", "store", "storefront"),
    "portfolio": ("portfolio", "photographer", "freelancer"),
    "pets": ("pet", "pets", "dog", "dogs", "cat", "cats", "puppy", "kitten"),
    "dolls": ("doll", "dolls", "toy", "toys"),
    "fitness": ("gym", "fitness", "workout", "yoga"),
    "healthcare": ("hospital", "clinic", "medical", "doctor", "doctors", "healthcare", "dental"),
    "education": ("school", "university", "college", "education", "learning", "courses"),
    "tech": ("saas", "startup", "technology", "gadget", "gadgets", "software"),
    "cars": (
        "car", "cars", "automotive", "dealership", "vehicle", "vehicles",
        "rental", "rent", "lamborghini", "ferrari", "porsche", "bmw",
        "mercedes", "audi", "mclaren", "tesla", "bentley", "rolls-royce",
        "corvette", "supercar", "sports car",
    ),
}

# Words that describe an ASSET SLOT, never the website domain. Excluding these
# stops "movie posters" logic from hijacking e.g. a football site's hero image.
_ASSET_ROLE_WORDS = frozenset(
    {
        "image", "images", "imagery", "photo", "photos", "photography", "picture",
        "pictures", "poster", "posters", "gallery", "galleries", "background",
        "backgrounds", "hero", "banner", "banners", "thumbnail", "thumbnails",
        "card", "cards", "logo", "logos", "icon", "icons", "avatar", "avatars",
    }
)

# Stable Unsplash CDN URLs (public, no API key). Used only after live search fails.
_CURATED_CDN: Dict[str, List[str]] = {
    "movies": [
        "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1478720568477-152d9b164e26?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1440404653325-ab127d49abc1?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1517604931442-7e0c8ed2963c?auto=format&fit=crop&w=1200&q=80",
    ],
    "restaurant": [
        "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1559339352-11d035aa65de?auto=format&fit=crop&w=1200&q=80",
    ],
    "travel": [
        "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1488085061387-422e29b40080?auto=format&fit=crop&w=1200&q=80",
    ],
    "hotel": [
        "https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1582719508461-905c673771fd?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1611892440504-42a792e24d32?auto=format&fit=crop&w=1200&q=80",
    ],
    "fashion": [
        "https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1469334031218-e382a71b716b?auto=format&fit=crop&w=1200&q=80",
    ],
    "real_estate": [
        "https://images.unsplash.com/photo-1564013799919-ab600027ffc6?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1600&q=80",
    ],
    "ecommerce": [
        "https://images.unsplash.com/photo-1441986300917-64674bd600d8?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=1200&q=80",
    ],
    "portfolio": [
        "https://images.unsplash.com/photo-1498050108023-c5249f4df085?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1558655146-d09347e92766?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=1200&q=80",
    ],
    "pets": [
        "https://images.unsplash.com/photo-1548199973-03cce0bbc87b?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1587300003388-59208cc962cb?auto=format&fit=crop&w=1200&q=80",
    ],
    "dolls": [
        "https://images.unsplash.com/photo-1558060370-d644479cb6f7?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1566576912321-d58ddd7a6088?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1596461404969-9ae70f2830c1?auto=format&fit=crop&w=1200&q=80",
    ],
    "fitness": [
        "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?auto=format&fit=crop&w=1200&q=80",
    ],
    "healthcare": [
        "https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1631217868264-e5b90bb7e133?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1584982751601-97dcc096659c?auto=format&fit=crop&w=1200&q=80",
    ],
    "education": [
        "https://images.unsplash.com/photo-1523050854058-8df90110c9f1?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1503676260728-1c00da094a0b?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1523240795612-9a054b0db644?auto=format&fit=crop&w=1200&q=80",
    ],
    "tech": [
        "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1519389950473-47ba0277781c?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?auto=format&fit=crop&w=1200&q=80",
    ],
    "sports": [
        "https://images.unsplash.com/photo-1574629810360-7efbbe195018?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1431324155629-1a6deb1dec8d?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1522778119026-d647f0596c20?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1579952363873-27f3bade9f55?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1543326727-cf6c39e8f84c?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1552667466-07770ae110d0?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1517927033932-b3d18e61fb3a?auto=format&fit=crop&w=1200&q=80",
    ],
    "cars": [
        "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1542362567-b07e54358753?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1614200179396-2bdb77ebf81b?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1555215695-3004980ad54e?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1617814076367-b759c7d7e738?auto=format&fit=crop&w=1600&q=80",
    ],
    "default": [
        "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1486312338219-ce68d2c6f44d?auto=format&fit=crop&w=1200&q=80",
    ],
}

_PLACEHOLDER_MARKERS = (
    "placeholder",
    "dummyimage",
    "via.placeholder",
    "placehold.co",
    "placekitten",
    "fakeimg",
    "example.com",
)

# Formats browsers cannot reliably render inline (Live Preview would show blank).
_UNSUPPORTED_WEB_MIMES = frozenset(
    {"image/tiff", "image/x-xcf", "image/vnd.djvu", "application/pdf", "image/heic"}
)


_ROLE_USAGE = {
    "hero": "full-width hero / banner background",
    "gallery": "gallery grid and wide section backgrounds",
    "players": "player cards and profile portraits",
    "posters": "poster / title cards",
    "products": "product cards and detail images",
    "cards": "feature cards and list thumbnails",
    "vehicles": "vehicle cards, catalogue tiles, and detail galleries",
}

# Named luxury / rental vehicles → curated Unsplash CDN URLs (subject-matched).
# Used when live search fails so car-rental briefs still get real model imagery.
_CURATED_VEHICLE_IMAGES: Dict[str, List[str]] = {
    "lamborghini huracan": [
        "https://images.unsplash.com/photo-1544636331-e26879cd4d9b?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1511919884225-912b5d59ba03?auto=format&fit=crop&w=1200&q=80",
    ],
    "ferrari 296 gtb": [
        "https://images.unsplash.com/photo-1583121274602-3e2820c69888?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1592198084033-aade902d4aa0?auto=format&fit=crop&w=1200&q=80",
    ],
    "porsche 911 turbo s": [
        "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1614162692292-7ac56d7f7f1e?auto=format&fit=crop&w=1200&q=80",
    ],
    "bmw m4 competition": [
        "https://images.unsplash.com/photo-1555215695-3004980ad54e?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1617531653332-bd46c24f2068?auto=format&fit=crop&w=1200&q=80",
    ],
    "mercedes-benz g-class": [
        "https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?auto=format&fit=crop&w=1200&q=80",
    ],
    "audi rs7": [
        "https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1614200179396-2bdb77ebf81b?auto=format&fit=crop&w=1200&q=80",
    ],
    "mclaren 720s": [
        "https://images.unsplash.com/photo-1553440569-bcc63803a83d?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1542362567-b07e54358753?auto=format&fit=crop&w=1200&q=80",
    ],
    "rolls-royce ghost": [
        "https://images.unsplash.com/photo-1631295868223-63265b40d9e4?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1563720360172-67b8f3dce741?auto=format&fit=crop&w=1200&q=80",
    ],
    "bentley continental gt": [
        "https://images.unsplash.com/photo-1563720223185-11003d516935?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1617814076367-b759c7d7e738?auto=format&fit=crop&w=1200&q=80",
    ],
    "tesla model s plaid": [
        "https://images.unsplash.com/photo-1560958089-b8a1929cea89?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1617788138017-80ad40651399?auto=format&fit=crop&w=1200&q=80",
    ],
    "range rover sport": [
        "https://images.unsplash.com/photo-1519641471654-76ce0107ad1b?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?auto=format&fit=crop&w=1200&q=80",
    ],
    "chevrolet corvette c8": [
        "https://images.unsplash.com/photo-1552519507-da3b142c6e3d?auto=format&fit=crop&w=1600&q=80",
        "https://images.unsplash.com/photo-1580273916550-e323be2ae537?auto=format&fit=crop&w=1200&q=80",
    ],
}

# Ordered longest-first so "porsche 911 turbo s" wins over shorter brand-only hits.
_KNOWN_VEHICLE_MODELS: Tuple[str, ...] = tuple(
    sorted(_CURATED_VEHICLE_IMAGES.keys(), key=len, reverse=True)
)


def _relevance_terms(query: str) -> List[str]:
    """Meaningful tokens a candidate should match to be considered on-topic."""
    return [
        token
        for token in re.findall(r"[^\W\d_]{4,}", query.lower(), re.UNICODE)
        if token not in _QUERY_STOPWORDS and token not in _ASSET_ROLE_WORDS
    ]


def _is_relevant(haystack: str, terms: Sequence[str]) -> bool:
    """True when a candidate title/URL matches at least one query term."""
    if not terms:
        return True
    lowered = haystack.lower()
    return any(term in lowered for term in terms)


@dataclass
class ResolvedImage:
    """One validated image asset."""

    url: str
    provider: str
    width: int = 0
    height: int = 0
    mime: str = ""
    title: str = ""
    description: str = ""


@dataclass
class ImageDiscoveryResult:
    """Outcome of the Asset Resolution Service.

    Attributes:
        required: Whether imagery is mandatory for this request.
        reason: Short reason used in prompts/telemetry.
        domain: Detected domain key.
        queries: Search queries used.
        assets: Role → HTTPS URL list (validated).
        asset_subjects: Asset key → exact vision-verified subject label.
        asset_roles: Asset key → intended UI role.
        identity_verified_roles: Asset keys requiring exact identity verification.
        providers_used: Providers that contributed at least one URL.
    """

    required: bool
    reason: str = ""
    domain: str = "default"
    queries: List[str] = field(default_factory=list)
    assets: Dict[str, List[str]] = field(default_factory=dict)
    asset_subjects: Dict[str, str] = field(default_factory=dict)
    asset_roles: Dict[str, str] = field(default_factory=dict)
    identity_verified_roles: List[str] = field(default_factory=list)
    providers_used: List[str] = field(default_factory=list)

    @property
    def url_count(self) -> int:
        return sum(len(urls) for urls in self.assets.values())

    def to_prompt_section(self) -> str:
        """Format validated assets for the LLM — integration only, no searching."""
        if not self.required:
            return (
                "ASSET RESOLUTION SERVICE:\n"
                f"- status: skipped ({self.reason or 'images not required'})\n"
                "- Do not fail generation solely due to absent images.\n"
                "- Do not invent image URLs."
            )
        lines = [
            "ASSET RESOLUTION SERVICE (PRE-VALIDATED — MANDATORY):",
            "The backend already discovered and validated these public HTTPS images.",
            "You MUST embed ONLY these URLs in <img>, CSS backgrounds, and data modules.",
            "Do NOT invent URLs. Do NOT use placeholders. Do NOT leave empty src attributes.",
            "Do NOT tell the user to add images manually.",
            f"- status: REQUIRED ({self.reason})",
            f"- domain: {self.domain}",
            f"- providers: {', '.join(self.providers_used) or 'curated'}",
        ]
        if self.queries:
            lines.append("- search_queries: " + ", ".join(self.queries[:8]))
        if not self.assets or self.url_count == 0:
            lines.append(
                "- ERROR: the vision validator approved no exact subject matches. Do not use an "
                "unverified image or create named cards that imply a false identity."
            )
            return "\n".join(lines)
        lines.append("")
        lines.append("Use each verified subject only for its exact matching content:")
        for role, urls in self.assets.items():
            subject = self.asset_subjects.get(role, role)
            usage_role = self.asset_roles.get(role, role)
            identity_note = (
                "; exact identity verified by vision model"
                if role in self.identity_verified_roles
                else ""
            )
            lines.append(
                f"- {role}: subject={subject!r}; "
                f"usage={_ROLE_USAGE.get(usage_role, 'matching section imagery')}"
                f"{identity_note}"
            )
            for url in urls:
                lines.append(f"  - {url}")
        lines.append("")
        lines.append(
            "Rules: hero/gallery URLs are wide shots (use background-size: cover); "
            f"{'/'.join(r for r in self.assets if r not in {'hero', 'gallery'}) or 'card'} "
            "URLs are subject shots for cards. Give every <img> descriptive alt text and "
            "loading=\"lazy\" below the fold."
        )
        lines.append(
            "Never put a URL on a card whose label/name differs from its verified subject. "
            "If no exact verified subject asset exists, do not invent a named-person card."
        )
        lines.append(
            "Every image URL may appear on only ONE visible Home-page element. Never reuse "
            "the same image for multiple cards, people, products, sections, or backgrounds."
        )
        lines.append(
            "Emit ```file``` blocks that wire these exact subject-to-URL mappings into "
            "the project now."
        )
        return "\n".join(lines)


def images_required(user_request: str) -> Tuple[bool, str, str]:
    """Decide whether asset resolution must run for this request."""
    text = (user_request or "").strip().lower()
    if not text:
        return False, "empty request", "default"
    if any(re.search(p, text) for p in _IMAGE_OPTIONAL_PATTERNS):
        return False, "user requested wireframe/text-only", "default"
    for pattern in _EXPLICIT_IMAGE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True, "explicit image/visual request", _detect_domain(text)
    domain = _detect_domain(text)
    if domain != "default":
        return True, f"imagery-dependent domain ({domain})", domain
    # Premium / landing-page builds usually need visuals even without domain keywords.
    if re.search(r"\b(landing page|saas|marketing site|homepage)\b", text):
        return True, "marketing/landing page needs imagery", "default"
    return False, "images not explicitly required", "default"


def _domain_scores(text: str) -> Dict[str, int]:
    """Score each domain by whole-word keyword hits, ignoring asset-slot words."""
    scores: Dict[str, int] = {}
    for domain, keywords in _IMAGE_DOMAIN_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword in _ASSET_ROLE_WORDS:
                continue
            if re.search(rf"\b{re.escape(keyword)}\b", text):
                score += 1
        if score:
            scores[domain] = score
    return scores


def _detect_domain(text: str) -> str:
    scores = _domain_scores(text)
    if not scores:
        return "default"
    return max(scores.items(), key=lambda item: (item[1], -len(item[0])))[0]


def _roles_for_domain(domain: str) -> List[str]:
    if domain == "movies":
        return ["hero", "posters", "gallery", "cards"]
    if domain == "sports":
        return ["hero", "players", "gallery", "cards"]
    if domain in {"restaurant", "ecommerce", "fashion", "dolls"}:
        return ["hero", "products", "gallery", "cards"]
    if domain == "cars":
        return ["hero", "vehicles", "gallery", "cards"]
    return ["hero", "gallery", "cards"]


# Per-domain query hints: (hero/wide shots, subject/card shots).
_DOMAIN_QUERY_HINTS: Dict[str, Tuple[List[str], List[str]]] = {
    "sports": (
        ["football stadium crowd", "soccer stadium", "football pitch"],
        ["football player action", "soccer player portrait", "footballer match"],
    ),
    "movies": (
        ["cinema hall", "movie theater interior"],
        ["film poster art", "movie set production"],
    ),
    "restaurant": (
        ["restaurant interior dining", "restaurant table setting"],
        ["gourmet dish plating", "food photography plate"],
    ),
    "travel": (
        ["travel destination landscape", "mountain panorama"],
        ["city landmark", "beach resort"],
    ),
    "hotel": (["hotel lobby interior"], ["luxury hotel room"]),
    "fashion": (["fashion runway show"], ["fashion model portrait", "clothing boutique"]),
    "real_estate": (["modern house exterior"], ["living room interior", "apartment interior"]),
    "ecommerce": (["retail store interior"], ["product photography", "product studio shot"]),
    "portfolio": (["creative workspace desk"], ["design portfolio project", "studio work"]),
    "pets": (["pets outdoors"], ["dog portrait", "cat portrait"]),
    "dolls": (["toy store shelves"], ["porcelain doll", "collectible doll"]),
    "fitness": (["gym interior"], ["fitness training workout", "athlete lifting"]),
    "healthcare": (["modern hospital building"], ["doctor portrait", "medical clinic"]),
    "education": (["university campus"], ["students classroom", "student studying"]),
    "tech": (["modern office technology"], ["laptop workspace", "technology device"]),
    "cars": (
        [
            "luxury car rental showroom",
            "premium sports car night city",
            "luxury supercar hero banner",
        ],
        [
            "luxury sports car exterior studio",
            "supercar side profile",
            "premium SUV exterior",
        ],
    ),
    "default": (["cinematic landscape"], ["modern office workspace"]),
}

_QUERY_STOPWORDS = frozenset(
    {
        "build", "website", "site", "page", "pages", "create", "make", "with", "using",
        "react", "premium", "modern", "please", "just", "also", "need", "want", "some",
        "more", "high", "quality", "realistic", "beautiful", "nice", "good", "landing",
        "responsive", "tailwind", "typescript", "javascript", "html", "styles",
        "add", "update", "change", "include", "into", "from", "that", "this", "have",
    }
)

_NON_PERSON_LINE_TERMS = frozenset(
    {
        "about", "button", "career", "competition", "contact", "details", "filter",
        "football", "footer", "gallery", "hero", "home", "icons", "image", "loading",
        "lucide", "menu", "motion", "navbar", "navigation", "page", "personal",
        "player", "players", "profile", "react", "router", "search", "skeleton",
        "stars", "statistics", "timeline", "view",
    }
)


def extract_topic(user_request: str) -> str:
    """Extract the subject of the site (e.g. "football legends") for search queries."""
    text = (user_request or "").strip()
    if not text:
        return ""
    tokens = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text)
    keep: List[str] = []
    for token in tokens:
        lowered = token.lower()
        if lowered in _QUERY_STOPWORDS or lowered in _ASSET_ROLE_WORDS:
            continue
        if lowered in keep:
            continue
        keep.append(lowered)
        if len(keep) >= 4:
            break
    return " ".join(keep)


def _named_people_from_request(user_request: str) -> List[VisualAssetRequirement]:
    """Recover explicit line-item names if model requirement extraction is incomplete."""
    requirements: List[VisualAssetRequirement] = []
    seen: set[str] = set()
    is_motorsport = bool(
        re.search(
            r"\b(f1|formula\s*(?:1|one)|motorsport|racing|grand prix|driver)\b",
            user_request or "",
            re.IGNORECASE,
        )
    )
    for raw_line in (user_request or "").splitlines():
        line = re.sub(r"^[\s#>*+\-\d.)]+", "", raw_line).strip().strip("*_`")
        words = re.findall(r"[^\W\d_][\wÀ-ÖØ-öø-ÿ'-]*\.?", line, re.UNICODE)
        if not 2 <= len(words) <= 4:
            continue
        lowered = {word.lower().rstrip(".") for word in words}
        if lowered.intersection(_NON_PERSON_LINE_TERMS):
            continue
        if not all(
            next((char.isupper() for char in word if char.isalpha()), False)
            or word.lower().rstrip(".") in {"jr", "sr"}
            for word in words
        ):
            continue
        subject = " ".join(words).strip()
        key = re.sub(r"[^a-z0-9]+", "_", subject.lower()).strip("_")
        if not key or key in seen:
            continue
        seen.add(key)
        requirements.append(
            VisualAssetRequirement(
                key=key,
                role="players",
                subject=subject,
                query=(
                    f"{subject} Formula 1 driver portrait"
                    if is_motorsport
                    else f"{subject} athlete portrait"
                ),
                identity_required=True,
            )
        )
    return requirements[:16]


def _normalize_vehicle_label(text: str) -> str:
    """Lowercase and collapse punctuation for vehicle name matching.

    Accented letters (e.g. Huracán) are folded to ASCII so curated keys match.
    """
    import unicodedata

    folded = unicodedata.normalize("NFKD", text or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-z0-9]+", " ", folded.lower())
    return " ".join(cleaned.split())


def _display_vehicle_name(normalized: str) -> str:
    """Title-case a normalized vehicle key for prompt subject labels."""
    specials = {
        "bmw": "BMW",
        "gtb": "GTB",
        "gt": "GT",
        "rs7": "RS7",
        "suv": "SUV",
        "c8": "C8",
        "g": "G",
    }
    parts: List[str] = []
    for token in normalized.split():
        parts.append(specials.get(token, token.capitalize()))
    return " ".join(parts)


def _named_vehicles_from_request(user_request: str) -> List[VisualAssetRequirement]:
    """Extract named car models from a rental / automotive brief.

    Matches known luxury models (longest first) and bullet lines that look like
    vehicle names so catalogue sites get one subject-labelled asset group each.
    """
    text = user_request or ""
    lowered = _normalize_vehicle_label(text)
    requirements: List[VisualAssetRequirement] = []
    seen: set[str] = set()

    for model in _KNOWN_VEHICLE_MODELS:
        if model not in lowered:
            continue
        key = re.sub(r"[^a-z0-9]+", "_", model).strip("_")
        if key in seen:
            continue
        seen.add(key)
        display = _display_vehicle_name(model)
        requirements.append(
            VisualAssetRequirement(
                key=key,
                role="vehicles",
                subject=display,
                query=f"{display} car exterior studio photography",
                identity_required=True,
            )
        )

    # Also pick up bullet-list vehicle lines not in the curated catalogue.
    for raw_line in text.splitlines():
        line = re.sub(r"^[\s#>*+\-\d.)]+", "", raw_line).strip().strip("*_`")
        if not line or len(line) > 60:
            continue
        normalized = _normalize_vehicle_label(line)
        if not normalized or normalized in seen:
            continue
        # Require a known automotive brand token so we don't treat section headers
        # as vehicles.
        brands = (
            "lamborghini", "ferrari", "porsche", "bmw", "mercedes", "audi",
            "mclaren", "rolls", "bentley", "tesla", "range", "rover",
            "chevrolet", "corvette", "aston", "bugatti", "nissan", "toyota",
        )
        if not any(brand in normalized for brand in brands):
            continue
        if normalized in _KNOWN_VEHICLE_MODELS:
            continue
        key = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
        if not key or key in seen:
            continue
        seen.add(key)
        display = _display_vehicle_name(normalized)
        requirements.append(
            VisualAssetRequirement(
                key=key,
                role="vehicles",
                subject=display,
                query=f"{display} car exterior studio photography",
                identity_required=True,
            )
        )

    return requirements[:16]


def _build_role_queries(domain: str, user_request: str, role: str) -> List[str]:
    """Build topic-relevant search queries for one asset role."""
    topic = extract_topic(user_request)
    wide_hints, subject_hints = _DOMAIN_QUERY_HINTS.get(
        domain, _DOMAIN_QUERY_HINTS["default"]
    )
    if domain == "sports" and re.search(
        r"\b(f1|formula\s*(?:1|one)|motorsport|grand prix)\b",
        user_request or "",
        re.IGNORECASE,
    ):
        wide_hints = [
            "Formula 1 race track",
            "Formula 1 starting grid",
            "Grand Prix circuit",
        ]
        subject_hints = [
            "Formula 1 driver portrait",
            "F1 driver paddock portrait",
            "Formula 1 driver",
        ]
    hints = wide_hints if role in {"hero", "gallery"} else subject_hints
    queries: List[str] = []
    if topic:
        # Topic first so results stay on-subject, then domain-anchored variants.
        queries.append(f"{topic} {hints[0]}" if hints else topic)
        queries.append(topic)
    queries.extend(hints)
    seen: set[str] = set()
    ordered: List[str] = []
    for query in queries:
        cleaned = " ".join(query.split())
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            ordered.append(cleaned)
    return ordered[:4]


def _build_queries(domain: str, user_request: str) -> List[str]:
    """Flat query list (kept for telemetry/back-compat)."""
    queries: List[str] = []
    for role in _roles_for_domain(domain):
        for query in _build_role_queries(domain, user_request, role):
            if query not in queries:
                queries.append(query)
    return queries[:8]


def _default_requirements(
    domain: str,
    user_request: str,
) -> List[VisualAssetRequirement]:
    """Build generic role requirements when no named subject extraction is needed."""
    requirements: List[VisualAssetRequirement] = []
    for role in _roles_for_domain(domain):
        queries = _build_role_queries(domain, user_request, role)
        query = queries[0] if queries else f"{domain} {role}"
        requirements.append(
            VisualAssetRequirement(
                key=role,
                role=role,
                subject=query,
                query=query,
                identity_required=False,
            )
        )
    return requirements


class AssetResolutionService:
    """Discover and validate public image URLs before website generation."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 5.0,
        per_role: int = 4,
        validate: bool = True,
        unsplash_access_key: str = "",
        pexels_api_key: str = "",
        budget_seconds: Optional[float] = None,
        semantic_verify: Optional[bool] = None,
        image_verifier: Optional[OpenAIImageVerifier] = None,
    ) -> None:
        settings = get_settings()
        self._timeout = timeout_seconds
        self._budget_seconds = float(
            budget_seconds
            if budget_seconds is not None
            else getattr(settings, "asset_resolution_budget_seconds", 30.0) or 30.0
        )
        self._per_role = max(1, per_role or int(getattr(settings, "asset_resolution_per_role", 4) or 4))
        self._validate = validate if validate is not None else bool(
            getattr(settings, "asset_resolution_validate", True)
        )
        self._semantic_verify = (
            bool(getattr(settings, "asset_semantic_verification_enabled", True))
            if semantic_verify is None
            else semantic_verify
        )
        self._image_verifier = image_verifier or OpenAIImageVerifier(
            timeout_seconds=max(self._timeout, 10.0)
        )
        self._unsplash_key = (
            unsplash_access_key
            or str(getattr(settings, "unsplash_access_key", "") or "")
        ).strip()
        self._pexels_key = (
            pexels_api_key
            or str(getattr(settings, "pexels_api_key", "") or "")
        ).strip()
        self._min_bytes = 8_000
        # Wikimedia rejects generic/library User-Agents with HTTP 403.
        self._user_agent = (
            "Mozilla/5.0 (compatible; ArabyCodeAI/1.0; +https://github.com/araby-codeai)"
        )

    async def resolve(
        self,
        user_request: str,
        *,
        semantic_context: str = "",
    ) -> ImageDiscoveryResult:
        """Run the full asset resolution pipeline for a user request."""
        required, reason, domain = images_required(user_request)
        if not required:
            return ImageDiscoveryResult(required=False, reason=reason, domain=domain)
        discovery_request = "\n".join(
            part.strip()
            for part in (semantic_context, user_request)
            if part and part.strip()
        )
        if domain == "default" and semantic_context:
            domain = _detect_domain(discovery_request.lower())

        enabled = bool(getattr(get_settings(), "asset_resolution_enabled", True))
        if not enabled:
            if self._semantic_verify:
                return ImageDiscoveryResult(
                    required=True,
                    reason=f"{reason}; asset resolution disabled",
                    domain=domain,
                )
            return self._from_curated(domain, reason, queries=[], providers=["curated-cdn"])

        queries = _build_queries(domain, discovery_request)
        default_requirements = _default_requirements(domain, discovery_request)
        verify_with_openai = self._semantic_verify and self._image_verifier.available
        if self._semantic_verify and not verify_with_openai:
            logger.warning(
                "OpenAI image verification unavailable; continuing with exact provider "
                "search metadata instead of returning an image-free website"
            )
        if verify_with_openai:
            extracted = await self._image_verifier.extract_requirements(
                discovery_request,
                domain=domain,
                default_roles=_roles_for_domain(domain),
            )
            requirements = list(extracted)
            known_subjects = {item.subject.lower() for item in requirements}
            requirements.extend(
                item
                for item in _named_people_from_request(discovery_request)
                if item.subject.lower() not in known_subjects
            )
            known_subjects = {item.subject.lower() for item in requirements}
            requirements.extend(
                item
                for item in _named_vehicles_from_request(discovery_request)
                if item.subject.lower() not in known_subjects
            )
            existing_roles = {item.role for item in requirements}
            # Named vehicles already cover the "vehicles" role — don't also add a
            # generic vehicles bucket that would dilute subject-specific assets.
            skip_roles = existing_roles | (
                {"vehicles"} if any(item.role == "vehicles" for item in requirements) else set()
            )
            requirements.extend(
                item for item in default_requirements if item.role not in skip_roles
            )
        else:
            named_subjects = [
                *_named_people_from_request(discovery_request),
                *_named_vehicles_from_request(discovery_request),
            ]
            named_roles = {item.role for item in named_subjects}
            if any(item.role == "vehicles" for item in named_subjects):
                named_roles.add("vehicles")
            requirements = [
                *named_subjects,
                *(
                    item
                    for item in default_requirements
                    if item.role not in named_roles
                ),
            ]

        providers_used: List[str] = []
        assets: Dict[str, List[str]] = {item.key: [] for item in requirements}
        asset_subjects = {item.key: item.subject for item in requirements}
        asset_roles = {item.key: item.role for item in requirements}

        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers={"User-Agent": self._user_agent},
            follow_redirects=True,
        ) as client:
            # Preserve completed roles when another role is slow. A global
            # wait_for(gather(...)) discarded every successful result on timeout.
            tasks = [
                asyncio.create_task(
                    self._resolve_role(
                        client,
                        [
                            requirement.query,
                            requirement.subject,
                            *_build_role_queries(
                                domain,
                                discovery_request,
                                requirement.role,
                            ),
                        ],
                        requirement=requirement,
                        semantic_verify=verify_with_openai,
                        providers_used=providers_used,
                    )
                )
                for requirement in requirements
            ]
            done, pending = await asyncio.wait(tasks, timeout=self._budget_seconds)
            for task in pending:
                task.cancel()
            if pending:
                logger.info(
                    "Asset search budget reached; keeping %s completed roles, "
                    "cancelling %s slow roles",
                    len(done),
                    len(pending),
                )
            role_results: List[List[str]] = []
            for task in tasks:
                if task not in done or task.cancelled():
                    role_results.append([])
                    continue
                try:
                    role_results.append(task.result())
                except Exception as exc:  # noqa: BLE001
                    logger.info("Asset role resolution failed: %s", exc)
                    role_results.append([])

            used_urls: set[str] = set()
            for requirement, candidates in zip(requirements, role_results):
                bucket: List[str] = []
                for url in candidates:
                    if url in used_urls:
                        continue
                    used_urls.add(url)
                    bucket.append(url)
                    if len(bucket) >= self._per_role:
                        break
                assets[requirement.key] = bucket

            for requirement in requirements:
                required_count = 1 if requirement.identity_required else self._per_role
                missing = required_count - len(assets[requirement.key])
                if missing <= 0:
                    continue
                extra = await self._curated_fill(
                    client,
                    domain,
                    requirement=requirement,
                    semantic_verify=verify_with_openai,
                    missing=missing,
                    exclude=used_urls,
                    providers_used=providers_used,
                )
                used_urls.update(extra)
                assets[requirement.key].extend(extra)

        pool = [url for urls in assets.values() for url in urls]
        if not pool and not verify_with_openai:
            return self._from_curated(
                domain,
                reason,
                queries=queries,
                providers=["curated-cdn"],
                requirements=requirements,
            )

        # Stable unique provider list.
        providers = []
        if verify_with_openai and pool:
            providers_used.append("vision-verification")
        for name in providers_used:
            if name not in providers:
                providers.append(name)

        return ImageDiscoveryResult(
            required=True,
            reason=reason,
            domain=domain,
            queries=queries,
            assets=assets,
            asset_subjects=asset_subjects,
            asset_roles=asset_roles,
            identity_verified_roles=[
                item.key
                for item in requirements
                if verify_with_openai
                and item.identity_required
                and assets.get(item.key)
            ],
            providers_used=providers,
        )

    # Back-compat alias used by chat_pipeline / tests.
    async def discover(
        self,
        user_request: str,
        *,
        semantic_context: str = "",
    ) -> ImageDiscoveryResult:
        return await self.resolve(user_request, semantic_context=semantic_context)

    async def _resolve_role(
        self,
        client: httpx.AsyncClient,
        role_queries: List[str],
        *,
        requirement: VisualAssetRequirement,
        semantic_verify: bool,
        providers_used: List[str],
    ) -> List[str]:
        """Search providers for one asset role and return validated URLs.

        Returns more than ``per_role`` when available so cross-role dedupe has spares.
        """
        # Named cards need one correct portrait in the final manifest.
        target = 1 if requirement.identity_required else self._per_role
        # Search deeper for identities: the first Wikimedia results are often the
        # named driver's car, while an actual cropped portrait appears later.
        want = 8 if requirement.identity_required else max(
            target, min(self._per_role + 1, 5)
        )
        collected: List[str] = []
        for query in role_queries:
            candidates: List[ResolvedImage] = []
            if self._unsplash_key:
                found = await self._search_unsplash(client, query, limit=want)
                if found:
                    providers_used.append("unsplash")
                candidates.extend(found)
            if len(candidates) < want and self._pexels_key:
                found = await self._search_pexels(client, query, limit=want)
                if found:
                    providers_used.append("pexels")
                candidates.extend(found)
            if len(candidates) < want:
                found = await self._search_wikimedia(
                    client,
                    query,
                    limit=want,
                    relevance_terms=_relevance_terms(query),
                )
                if found:
                    providers_used.append("wikimedia")
                candidates.extend(found)

            if requirement.identity_required:
                identity_terms = _relevance_terms(requirement.subject)
                candidates = [
                    item
                    for item in candidates
                    if identity_terms
                    and all(
                        term
                        in (
                            f"{item.title} {item.description} {item.url}"
                        ).lower()
                        for term in identity_terms
                    )
                ]
                def _portrait_score(item: ResolvedImage) -> int:
                    metadata = f"{item.title} {item.description}".lower()
                    score = 0
                    if any(term in metadata for term in ("portrait", "cropped", "headshot")):
                        score += 6
                    if metadata.startswith("file:" + requirement.subject.lower()):
                        score += 3
                    if any(
                        term in metadata
                        for term in (" fp1", " fp2", " fp3", "qualifying", "car of")
                    ):
                        score -= 5
                    return score

                candidates.sort(key=_portrait_score, reverse=True)
                candidates = candidates[:4]

            seen_candidates: set[str] = set()
            fresh_candidates: List[ResolvedImage] = []
            for item in candidates:
                if item.url in collected or item.url in seen_candidates:
                    continue
                seen_candidates.add(item.url)
                fresh_candidates.append(item)
            if not fresh_candidates:
                continue
            if self._validate:
                checks = await asyncio.gather(
                    *(
                        self._validate_image(client, item.url)
                        for item in fresh_candidates
                    ),
                    return_exceptions=True,
                )
                fresh_candidates = [
                    item
                    for item, ok in zip(fresh_candidates, checks)
                    if ok is True
                ]
            if semantic_verify:
                image_candidates = [
                    ImageCandidate(
                        url=item.url,
                        provider=item.provider,
                        title=item.title,
                        description=item.description,
                    )
                    for item in fresh_candidates
                ]
                if requirement.identity_required:
                    approved: set[str] = set()
                    for candidate in image_candidates:
                        matches = await self._image_verifier.verify_candidates(
                            requirement,
                            [candidate],
                        )
                        if matches:
                            approved.update(matches)
                            break
                else:
                    approved = set(
                        await self._image_verifier.verify_candidates(
                            requirement,
                            image_candidates,
                        )
                    )
                fresh_candidates = [
                    item for item in fresh_candidates if item.url in approved
                ]
            fresh = [item.url for item in fresh_candidates]
            collected.extend(fresh)
            if len(collected) >= target:
                break
        return collected[:target]

    async def _curated_fill(
        self,
        client: httpx.AsyncClient,
        domain: str,
        *,
        requirement: VisualAssetRequirement,
        semantic_verify: bool,
        missing: int,
        exclude: set[str],
        providers_used: List[str],
    ) -> List[str]:
        """Top up a role with validated curated CDN URLs."""
        if missing <= 0:
            return []
        subject_key = _normalize_vehicle_label(requirement.subject)
        vehicle_pool = list(_CURATED_VEHICLE_IMAGES.get(subject_key, []))
        # Prefer subject-matched vehicle URLs, then domain pool.
        source_urls = vehicle_pool + list(_CURATED_CDN.get(domain, _CURATED_CDN["default"]))
        candidates: List[ResolvedImage] = []
        for url in source_urls:
            if url in exclude or any(item.url == url for item in candidates):
                continue
            if self._validate and not await self._validate_image(client, url):
                logger.info("Curated asset rejected (validation failed) url=%s", url)
                continue
            candidates.append(
                ResolvedImage(
                    url=url,
                    provider="curated-cdn",
                    title=requirement.subject,
                )
            )
        if semantic_verify:
            approved = set(
                await self._image_verifier.verify_candidates(
                    requirement,
                    [
                        ImageCandidate(
                            url=item.url,
                            provider=item.provider,
                            title=item.title,
                        )
                        for item in candidates
                    ],
                )
            )
            candidates = [item for item in candidates if item.url in approved]
        out = [item.url for item in candidates[:missing]]
        for _url in out:
            providers_used.append("curated-cdn")
        return out

    def _from_curated(
        self,
        domain: str,
        reason: str,
        *,
        queries: List[str],
        providers: List[str],
        requirements: Optional[List[VisualAssetRequirement]] = None,
    ) -> ImageDiscoveryResult:
        roles = _roles_for_domain(domain)
        pool = list(_CURATED_CDN.get(domain, _CURATED_CDN["default"]))
        assets: Dict[str, List[str]] = {}
        asset_subjects: Dict[str, str] = {}
        asset_roles: Dict[str, str] = {}
        idx = 0
        used_urls: set[str] = set()

        # When named vehicles are known, give each its own curated subject images.
        for requirement in requirements or []:
            if requirement.role != "vehicles" and not requirement.identity_required:
                continue
            subject_key = _normalize_vehicle_label(requirement.subject)
            vehicle_urls = [
                url
                for url in _CURATED_VEHICLE_IMAGES.get(subject_key, [])
                if url not in used_urls
            ]
            if not vehicle_urls:
                continue
            selected = vehicle_urls[: max(1, self._per_role)]
            assets[requirement.key] = selected
            used_urls.update(selected)
            asset_subjects[requirement.key] = requirement.subject
            asset_roles[requirement.key] = requirement.role

        for role in roles:
            if role in assets or (role == "vehicles" and any(
                asset_roles.get(key) == "vehicles" for key in assets
            )):
                continue
            bucket: List[str] = []
            while len(bucket) < self._per_role and idx < len(pool):
                url = pool[idx]
                idx += 1
                if url in used_urls:
                    continue
                bucket.append(url)
                used_urls.add(url)
            assets[role] = bucket
            asset_subjects[role] = role
            asset_roles[role] = role

        return ImageDiscoveryResult(
            required=True,
            reason=reason,
            domain=domain,
            queries=queries,
            assets=assets,
            asset_subjects=asset_subjects,
            asset_roles=asset_roles,
            providers_used=providers,
        )

    async def _search_unsplash(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        limit: int,
    ) -> List[ResolvedImage]:
        try:
            response = await client.get(
                "https://api.unsplash.com/search/photos",
                params={"query": query, "per_page": max(limit, 4), "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {self._unsplash_key}"},
            )
            if response.status_code != 200:
                return []
            results = (response.json() or {}).get("results") or []
        except Exception as exc:  # noqa: BLE001
            logger.info("Unsplash search failed query=%s err=%s", query, exc)
            return []
        out: List[ResolvedImage] = []
        for item in results:
            urls = item.get("urls") or {}
            url = str(urls.get("regular") or urls.get("full") or "")
            if not url.startswith("https://"):
                continue
            out.append(
                ResolvedImage(
                    url=url,
                    provider="unsplash",
                    width=int(item.get("width") or 0),
                    height=int(item.get("height") or 0),
                    title=str(item.get("alt_description") or ""),
                    description=str(item.get("description") or ""),
                )
            )
            if len(out) >= limit:
                break
        return out

    async def _search_pexels(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        limit: int,
    ) -> List[ResolvedImage]:
        try:
            response = await client.get(
                "https://api.pexels.com/v1/search",
                params={"query": query, "per_page": max(limit, 4), "orientation": "landscape"},
                headers={"Authorization": self._pexels_key},
            )
            if response.status_code != 200:
                return []
            photos = (response.json() or {}).get("photos") or []
        except Exception as exc:  # noqa: BLE001
            logger.info("Pexels search failed query=%s err=%s", query, exc)
            return []
        out: List[ResolvedImage] = []
        for item in photos:
            src = item.get("src") or {}
            url = str(src.get("large2x") or src.get("large") or src.get("original") or "")
            if not url.startswith("https://"):
                continue
            out.append(
                ResolvedImage(
                    url=url,
                    provider="pexels",
                    width=int(item.get("width") or 0),
                    height=int(item.get("height") or 0),
                    title=str(item.get("alt") or ""),
                    description=str(item.get("photographer") or ""),
                )
            )
            if len(out) >= limit:
                break
        return out

    async def _search_wikimedia(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        limit: int,
        relevance_terms: Optional[Sequence[str]] = None,
    ) -> List[ResolvedImage]:
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": "6",
            "gsrlimit": str(max(limit * 3, 8)),
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            # Ask for a scaled render so pages load fast instead of 4000px originals.
            "iiurlwidth": "1600",
            "format": "json",
        }
        try:
            response = await client.get("https://commons.wikimedia.org/w/api.php", params=params)
            response.raise_for_status()
            pages = ((response.json() or {}).get("query") or {}).get("pages") or {}
        except Exception as exc:  # noqa: BLE001
            logger.info("Wikimedia search failed query=%s err=%s", query, exc)
            return []

        out: List[ResolvedImage] = []
        for page in pages.values():
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            info = infos[0]
            # Prefer the scaled thumbnail: same subject, far smaller payload.
            file_url = str(info.get("thumburl") or info.get("url") or "")
            mime = str(info.get("mime") or "")
            width = int(info.get("width") or 0)
            if not file_url.startswith("https://"):
                continue
            if mime and not mime.startswith("image/"):
                continue
            if width and width < 800:
                continue
            if any(marker in file_url.lower() for marker in _PLACEHOLDER_MARKERS):
                continue
            if mime in _UNSUPPORTED_WEB_MIMES:
                continue
            if relevance_terms and not _is_relevant(
                str(page.get("title") or "") + " " + file_url,
                relevance_terms,
            ):
                continue
            out.append(
                ResolvedImage(
                    url=file_url,
                    provider="wikimedia",
                    width=width,
                    height=int(info.get("height") or 0),
                    mime=mime,
                    title=str(page.get("title") or ""),
                )
            )
            if len(out) >= limit:
                break
        return out

    async def _validate_image(self, client: httpx.AsyncClient, url: str) -> bool:
        if not url.startswith("https://"):
            return False
        if any(marker in url.lower() for marker in _PLACEHOLDER_MARKERS):
            return False
        try:
            head = await client.head(url)
            status = head.status_code
            content_type = (head.headers.get("content-type") or "").lower()
            length = int(head.headers.get("content-length") or 0)
            if status == 200 and content_type.startswith("image/"):
                if length and length < self._min_bytes:
                    return False
                return True
            # Some CDNs reject HEAD — fall back to ranged GET.
            get = await client.get(url, headers={"Range": "bytes=0-2047"})
            if get.status_code not in {200, 206}:
                return False
            content_type = (get.headers.get("content-type") or "").lower()
            if not content_type.startswith("image/"):
                # Sniff magic bytes.
                body = get.content[:16]
                if not (
                    body.startswith(b"\xff\xd8\xff")  # jpeg
                    or body.startswith(b"\x89PNG")
                    or body.startswith(b"GIF8")
                    or body.startswith(b"RIFF")
                    or b"ftyp" in body[:12]
                ):
                    return False
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("Image validation failed url=%s err=%s", url, exc)
            return False


# Backward-compatible name used across the pipeline.
ImageAssetResolver = AssetResolutionService
