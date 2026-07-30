"""Pydantic schemas for the agentic website builder."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


PageLevel = Literal["scaffold", "home", "level2", "level3"]


class FeatureSpec(BaseModel):
    """One user-requested feature that must not be dropped."""

    id: str
    description: str
    page_level: PageLevel = "home"
    required_paths: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    satisfied: bool = False
    evidence: str = ""


class PageSpec(BaseModel):
    """A page the planner decided to generate."""

    id: str
    title: str
    route: str
    level: PageLevel
    sections: List[str] = Field(default_factory=list)
    components: List[str] = Field(default_factory=list)
    data_deps: List[str] = Field(default_factory=list)
    notes: str = ""


class ParsedRequirements(BaseModel):
    """Output of the Parser Agent."""

    title: str = "Website"
    summary: str = ""
    stack: List[str] = Field(default_factory=lambda: ["react", "typescript", "tailwind"])
    theme: Dict[str, str] = Field(default_factory=dict)
    navigation: List[str] = Field(default_factory=list)
    pages: List[PageSpec] = Field(default_factory=list)
    features: List[FeatureSpec] = Field(default_factory=list)
    data_entities: List[str] = Field(default_factory=list)
    image_required: bool = True
    constraints: List[str] = Field(default_factory=list)
    raw_brief: str = ""


class GithubInspiration(BaseModel):
    """Public GitHub repo used only as structural inspiration."""

    full_name: str = ""
    url: str = ""
    description: str = ""
    stars: int = 0
    structure_hints: List[str] = Field(default_factory=list)
    readme_excerpt: str = ""


class SitePlan(BaseModel):
    """Output of the Planner Agent."""

    architecture: str = "react-memory-router"
    folder_tree: List[str] = Field(default_factory=list)
    stages: List[PageLevel] = Field(
        default_factory=lambda: ["scaffold", "home", "level2", "level3"]
    )
    pages: List[PageSpec] = Field(default_factory=list)
    shared_components: List[str] = Field(default_factory=list)
    data_files: List[str] = Field(default_factory=list)
    github: Optional[GithubInspiration] = None
    generation_chunks: Dict[str, List[str]] = Field(default_factory=dict)
    notes: str = ""


class CompileReport(BaseModel):
    """Deterministic compiler / integrity report."""

    ok: bool = True
    stage: str = ""
    issue_count: int = 0
    issues: List[str] = Field(default_factory=list)


class BuilderEvent(BaseModel):
    """Progress event streamed to the chat UI."""

    type: str = "progress"
    stage: str = ""
    message: str = ""
    meta: Dict[str, Any] = Field(default_factory=dict)
