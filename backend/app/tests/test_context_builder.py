"""Tests for project context assembly and prompt packaging."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from app.ai.context.builder import ContextBuilder, ProjectContext
from app.ai.prompts.builder import PromptBuilder
from app.ai.routing import RequestCategory


class _FakeCache:
    async def set(self, *args: Any, **kwargs: Any) -> None:
        return None


def _file(path: str, content: str, language: str = "typescript") -> Dict[str, Any]:
    return {
        "path": path,
        "content": content,
        "language": language,
        "updated_at": "2026-01-01T00:00:00Z",
    }


def test_website_context_includes_tree_data_routes_and_imports() -> None:
    """Website context should pack App, data, pages, and imported components."""
    files = [
        _file(
            "src/App.tsx",
            "import { MemoryRouter, Routes, Route } from 'react-router-dom';\n"
            "import Home from './pages/Home';\n"
            "import Dolls from './pages/Dolls';\n"
            "export default function App(){ return <MemoryRouter><Routes>"
            "<Route path='/' element={<Home/>}/>"
            "<Route path='/dolls' element={<Dolls/>}/>"
            "</Routes></MemoryRouter>; }",
            "tsx",
        ),
        _file(
            "src/pages/Dolls.tsx",
            "import { dolls } from '../data/dolls';\n"
            "import DollCard from '../components/DollCard';\n"
            "export default function Dolls(){ return dolls.map(d => <DollCard key={d.id} doll={d}/>); }",
            "tsx",
        ),
        _file(
            "src/pages/Home.tsx",
            "export default function Home(){ return <h1>Home</h1>; }",
            "tsx",
        ),
        _file(
            "src/data/dolls.ts",
            "export const dolls = [{ id: '1', name: 'Lila', image: 'https://example.org/a.jpg' }];",
            "typescript",
        ),
        _file(
            "src/components/DollCard.tsx",
            "export default function DollCard({ doll }: any){ return <article>{doll.name}</article>; }",
            "tsx",
        ),
        _file(
            "src/styles.css",
            "body { margin: 0; }",
            "css",
        ),
        _file(
            "README.md",
            "ignore me",
            "markdown",
        ),
    ]
    folders = [
        {"path": "src"},
        {"path": "src/pages"},
        {"path": "src/data"},
        {"path": "src/components"},
    ]
    builder = ContextBuilder(_FakeCache())  # type: ignore[arg-type]
    context = asyncio.run(
        builder.build(
            project={"_id": "p1", "name": "Dolls", "workspace_type": "website"},
            files=files,
            folders=folders,
            chat_history=[],
            current_file_path=None,
            open_tabs=[],
            user_request="Add 6 more dolls with images and costs",
        )
    )

    assert "src/App.tsx" in context.folder_structure
    assert "src/data/dolls.ts" in context.all_paths
    relevant_paths = [item["path"] for item in context.relevant_files]
    assert "src/App.tsx" in relevant_paths
    assert "src/data/dolls.ts" in relevant_paths
    assert "src/pages/Dolls.tsx" in relevant_paths
    assert "src/components/DollCard.tsx" in relevant_paths


def test_query_keywords_prioritize_matching_existing_files() -> None:
    """User keywords should surface matching existing data/component files."""
    files = [
        _file("src/App.tsx", "export default function App(){ return null; }", "tsx"),
        _file("src/data/regions.ts", "export const regions = [];", "typescript"),
        _file("src/data/menus.ts", "export const menus = [];", "typescript"),
        _file("src/pages/Regions.tsx", "export default function Regions(){ return null; }", "tsx"),
    ]
    builder = ContextBuilder(_FakeCache())  # type: ignore[arg-type]
    context = asyncio.run(
        builder.build(
            project={"id": "p2", "workspace_type": "website"},
            files=files,
            folders=[],
            chat_history=[],
            user_request="Update regions with coastline cards and images",
        )
    )
    relevant_paths = [item["path"] for item in context.relevant_files]
    assert relevant_paths.index("src/data/regions.ts") < relevant_paths.index("src/data/menus.ts")
    assert "src/pages/Regions.tsx" in relevant_paths


def test_prompt_builder_packages_tree_open_files_and_relevant_contents() -> None:
    """Prompt shape must include tree, path inventory, open files, relevant files, user prompt."""
    context = ProjectContext(
        project={
            "id": "p3",
            "name": "Demo",
            "description": "",
            "workspace_type": "website",
        },
        folder_structure="src/\nsrc/App.tsx\nsrc/data/dolls.ts",
        all_paths=["src/App.tsx", "src/data/dolls.ts"],
        open_tabs=["src/App.tsx"],
        relevant_files=[
            {
                "path": "src/data/dolls.ts",
                "language": "typescript",
                "content": "export const dolls = [];",
            }
        ],
    )
    messages = PromptBuilder().build(
        context,
        "Add more dolls",
        category=RequestCategory.WEBSITE_BUILDER,
    )
    assert len(messages) == 2
    system = messages[0].content
    user = messages[1].content
    assert "Current Project Tree:" in system
    assert "Existing Project Paths" in system
    assert "- src/data/dolls.ts" in system
    assert "Open Files / Tabs:" in system
    assert "Relevant Files" in system
    assert "export const dolls = [];" in system
    assert "PROJECT GROUNDING" in system
    assert "Do NOT invent parallel files" in system
    assert user.startswith("Current User Prompt:")
    assert "Add more dolls" in user
