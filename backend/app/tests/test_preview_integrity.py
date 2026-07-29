"""Tests for Live Preview import integrity detection."""

from app.ai.pipelines.preview_integrity import (
    build_exhausted_user_message,
    extract_project_imports,
    find_asset_usage_issues,
    find_integrity_issues,
)


def test_extract_relative_and_alias_imports() -> None:
    source = """
import Home from './pages/Home';
import { x } from '@/components/Foo';
export { default } from '../Bar';
const lazy = () => import('./Lazy');
const req = require('./legacy');
import React from 'react';
"""
    imports = extract_project_imports(source)
    assert './pages/Home' in imports
    assert '@/components/Foo' in imports
    assert '../Bar' in imports
    assert './Lazy' in imports
    assert './legacy' in imports
    assert 'react' not in imports


def test_find_missing_page_import() -> None:
    files = {
        'src/App.tsx': "import Home from './pages/Home';\nexport default function App(){return <Home/>}",
        'src/main.tsx': "import App from './App';",
    }
    issues = find_integrity_issues(files)
    assert any(issue.specifier == './pages/Home' for issue in issues)


def test_resolves_tsx_extension_and_index() -> None:
    files = {
        'src/App.tsx': "import Home from './pages/Home';\nimport Ui from './components/Ui';",
        'src/pages/Home.tsx': 'export default function Home(){return null}',
        'src/components/Ui/index.tsx': 'export default function Ui(){return null}',
    }
    assert find_integrity_issues(files) == []


def test_reports_react_root_without_mounting_entry() -> None:
    files = {
        "index.html": '<html><body><div id="root"></div></body></html>',
        "src/App.tsx": "export default function App(){return <main>Ready</main>}",
    }
    issues = find_integrity_issues(files)
    assert any(issue.kind == "entry" for issue in issues)
    assert any("Live Preview will be blank" in issue.summary for issue in issues)


def test_accepts_react_root_with_mounting_entry() -> None:
    files = {
        "index.html": '<html><body><div id="root"></div></body></html>',
        "src/App.tsx": "export default function App(){return <main>Ready</main>}",
        "src/main.tsx": (
            "import { createRoot } from 'react-dom/client';"
            "import App from './App';"
            "createRoot(document.getElementById('root')!).render(<App />);"
        ),
    }
    assert find_integrity_issues(files) == []


def test_exhausted_message_mentions_specificity() -> None:
    files = {'src/App.tsx': "import X from './missing';"}
    issues = find_integrity_issues(files)
    text = build_exhausted_user_message(issues)
    assert 'more specific prompt' in text
    assert 'src/App.tsx' in text


def test_reports_resolved_image_group_missing_from_generated_ui() -> None:
    files = {
        "src/App.tsx": "export default function App(){return <main>Football</main>}",
    }
    issues = find_asset_usage_issues(
        files,
        {
            "hero": ["https://images.example/stadium.jpg"],
            "cristiano_ronaldo": ["https://images.example/ronaldo.jpg"],
        },
        asset_subjects={
            "hero": "football stadium",
            "cristiano_ronaldo": "Cristiano Ronaldo",
        },
    )
    assert len(issues) == 2
    assert all(issue.kind == "asset_usage" for issue in issues)
    assert any("Cristiano Ronaldo" in issue.summary for issue in issues)


def test_accepts_image_group_when_any_approved_url_is_used() -> None:
    files = {
        "src/data/players.ts": (
            'export const image = "https://images.example/ronaldo.jpg";'
        ),
    }
    issues = find_asset_usage_issues(
        files,
        {
            "cristiano_ronaldo": [
                "https://images.example/ronaldo-alt.jpg",
                "https://images.example/ronaldo.jpg",
            ],
        },
    )
    assert issues == []


def test_rejects_placeholder_image_urls_even_when_real_assets_exist() -> None:
    files = {
        "src/Hero.tsx": (
            "export const hero = 'https://example.com/football-stadium.jpg';"
        ),
    }
    issues = find_asset_usage_issues(
        files,
        {"hero": ["https://images.example/stadium.jpg"]},
    )
    assert any("forbidden placeholder/example" in issue.summary for issue in issues)
