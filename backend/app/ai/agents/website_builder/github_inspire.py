"""Optional public GitHub inspiration for the Planner Agent.

Searches public repositories by title keywords and extracts a shallow file-tree
hint + README excerpt. Used only as structural inspiration — never copied
wholesale into the generated project.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

import httpx

from app.ai.agents.website_builder.schemas import GithubInspiration
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _search_query(title: str, summary: str) -> str:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", f"{title} {summary}")
    stop = {
        "build", "website", "site", "page", "premium", "production", "quality",
        "react", "typescript", "tailwind", "vite", "using", "with", "fully",
        "responsive", "create", "make", "the", "and", "for",
    }
    keep: List[str] = []
    for token in tokens:
        lower = token.lower()
        if lower in stop or lower in keep:
            continue
        keep.append(lower)
        if len(keep) >= 5:
            break
    if not keep:
        keep = ["react", "website"]
    return " ".join(keep[:5]) + " language:TypeScript stars:>20"


async def find_similar_public_repo(
    title: str,
    summary: str = "",
    *,
    timeout: float = 8.0,
) -> Optional[GithubInspiration]:
    """Find one public GitHub repo similar to the website brief.

    Args:
        title: Parsed site title.
        summary: Short brief summary.
        timeout: HTTP timeout seconds.

    Returns:
        GithubInspiration or None when disabled / unavailable.
    """
    settings = get_settings()
    if not getattr(settings, "website_agentic_github_search", True):
        return None

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ArabyCodeAI-WebsiteBuilder/1.0",
    }
    token = (getattr(settings, "github_token", "") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    query = _search_query(title, summary)
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
            search = await client.get(
                "https://api.github.com/search/repositories",
                params={"q": query, "sort": "stars", "order": "desc", "per_page": 5},
            )
            if search.status_code != 200:
                logger.info("GitHub search failed status=%s", search.status_code)
                return None
            items = (search.json() or {}).get("items") or []
            if not items:
                return None
            # Prefer non-archived repos with a clear description.
            repo = next(
                (item for item in items if not item.get("archived") and item.get("description")),
                items[0],
            )
            full_name = str(repo.get("full_name") or "")
            if not full_name:
                return None

            structure_hints: List[str] = []
            contents = await client.get(f"https://api.github.com/repos/{full_name}/contents/")
            if contents.status_code == 200 and isinstance(contents.json(), list):
                for entry in contents.json()[:30]:
                    name = entry.get("name")
                    kind = entry.get("type")
                    if name:
                        structure_hints.append(f"{kind}:{name}")

            readme_excerpt = ""
            readme = await client.get(
                f"https://api.github.com/repos/{full_name}/readme",
                headers={**headers, "Accept": "application/vnd.github.raw"},
            )
            if readme.status_code == 200:
                readme_excerpt = (readme.text or "")[:1200]

            return GithubInspiration(
                full_name=full_name,
                url=str(repo.get("html_url") or ""),
                description=str(repo.get("description") or ""),
                stars=int(repo.get("stargazers_count") or 0),
                structure_hints=structure_hints,
                readme_excerpt=readme_excerpt,
            )
    except Exception as exc:  # noqa: BLE001
        logger.info("GitHub inspiration skipped: %s", exc)
        return None
