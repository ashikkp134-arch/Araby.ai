"""Detect Live Preview blockers in generated website/React projects.

Scans TypeScript/JavaScript sources for relative and ``@/`` imports and reports
targets that do not resolve to any project file. Used after AI file applies so
the chat pipeline can auto-repair (retry) before the user opens Live Preview.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence

SOURCE_EXTENSIONS = (".tsx", ".ts", ".jsx", ".js")
RESOLVE_EXTENSIONS = ("", ".tsx", ".ts", ".jsx", ".js", ".css", ".json")
REACT_ENTRY_PATHS = (
    "src/main.tsx",
    "src/index.tsx",
    "index.tsx",
    "src/main.jsx",
    "src/index.jsx",
    "index.jsx",
    "src/main.ts",
    "src/index.ts",
)
REACT_APP_PATHS = ("src/App.tsx", "src/App.jsx", "App.tsx", "App.jsx")

# Matches: import … from '…' | export … from '…' | require('…') | dynamic import('…')
_IMPORT_RE = re.compile(
    r"""(?<![\w.])(?:import|export)\s+(?:type\s+)?(?:[\s\S]*?\sfrom\s*)?['"]([^'"]+)['"]"""
    r"""|(?<![\w.])(?:import|require)\s*\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE,
)


@dataclass(frozen=True)
class IntegrityIssue:
    """One unresolved import that would break Live Preview.

    Attributes:
        importer: File that contains the bad import.
        specifier: Raw import specifier from source.
        tried: Candidate paths that were checked and missing.
    """

    importer: str
    specifier: str
    tried: tuple[str, ...]
    kind: str = "import"
    detail: str = ""

    @property
    def summary(self) -> str:
        """Human-readable one-liner for prompts and UI."""
        if self.detail:
            return self.detail
        hint = self.tried[0] if self.tried else self.specifier
        return f'{self.importer} imports "{self.specifier}" (missing {hint})'


def normalize_path(path: str) -> str:
    """Normalize a project-relative path to POSIX form without leading ``./``."""
    parts: List[str] = []
    for part in str(path).replace("\\", "/").split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _directory_of(path: str) -> str:
    index = path.rfind("/")
    return "" if index == -1 else path[:index]


def _is_project_import(specifier: str) -> bool:
    return (
        specifier.startswith(".")
        or specifier.startswith("/")
        or specifier.startswith("@/")
    )


def _resolve_candidates(importer: str, specifier: str) -> List[str]:
    if specifier.startswith("@/"):
        base = f"src/{specifier[2:]}"
    elif specifier.startswith("/"):
        base = specifier.lstrip("/")
    else:
        base = f"{_directory_of(importer)}/{specifier}"
    normalized = normalize_path(base)
    candidates = [f"{normalized}{ext}" for ext in RESOLVE_EXTENSIONS]
    candidates.extend(
        f"{normalized}/index{ext}" for ext in RESOLVE_EXTENSIONS if ext
    )
    # De-dupe while preserving order.
    seen: set[str] = set()
    ordered: List[str] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def extract_project_imports(source: str) -> List[str]:
    """Return project-local import specifiers from a source file."""
    found: List[str] = []
    for match in _IMPORT_RE.finditer(source or ""):
        specifier = match.group(1) or match.group(2) or ""
        if _is_project_import(specifier):
            found.append(specifier)
    return found


def find_integrity_issues(
    files: Mapping[str, str] | Sequence[Mapping[str, str]],
) -> List[IntegrityIssue]:
    """Find unresolved relative/``@/`` imports across project files.

    Args:
        files: Either a ``path -> content`` map, or a sequence of file dicts
            with ``path`` / ``content`` keys (as returned by repositories).

    Returns:
        List of IntegrityIssue (empty when the graph looks resolvable).
    """
    by_path: Dict[str, str] = {}
    if isinstance(files, Mapping):
        by_path = {normalize_path(path): content or "" for path, content in files.items()}
    else:
        for item in files:
            path = normalize_path(str(item.get("path") or ""))
            if path:
                by_path[path] = str(item.get("content") or "")

    path_set = set(by_path)
    issues: List[IntegrityIssue] = []
    for path, content in by_path.items():
        if not path.endswith(SOURCE_EXTENSIONS):
            continue
        for specifier in extract_project_imports(content):
            candidates = _resolve_candidates(path, specifier)
            if any(candidate in path_set for candidate in candidates):
                continue
            issues.append(
                IntegrityIssue(
                    importer=path,
                    specifier=specifier,
                    tried=tuple(candidates[:6]),
                )
            )

    html = by_path.get("index.html", "")
    has_react_app = any(path in path_set for path in REACT_APP_PATHS)
    has_react_entry = any(path in path_set for path in REACT_ENTRY_PATHS)
    if has_react_app and not has_react_entry and re.search(
        r"""id\s*=\s*["']root["']""",
        html,
        re.IGNORECASE,
    ):
        issues.append(
            IntegrityIssue(
                importer="index.html",
                specifier="React entry",
                tried=REACT_ENTRY_PATHS[:6],
                kind="entry",
                detail=(
                    "React App component exists and index.html contains #root, but no "
                    "main/index entry mounts App with createRoot; Live Preview will be blank"
                ),
            )
        )
    return issues


def find_asset_usage_issues(
    files: Mapping[str, str] | Sequence[Mapping[str, str]],
    assets: Mapping[str, Sequence[str]],
    *,
    asset_subjects: Mapping[str, str] | None = None,
) -> List[IntegrityIssue]:
    """Report resolved asset groups that generation failed to use."""
    if isinstance(files, Mapping):
        contents = [str(content or "") for content in files.values()]
    else:
        contents = [str(item.get("content") or "") for item in files]
    generated_source = "\n".join(contents)
    subjects = asset_subjects or {}
    issues: List[IntegrityIssue] = []
    placeholder_patterns = (
        "example.com/",
        "via.placeholder.com",
        "placeholder.com",
        "placehold.co",
        "dummyimage.com",
    )
    used_placeholders = [
        marker for marker in placeholder_patterns if marker in generated_source.lower()
    ]
    if used_placeholders:
        issues.append(
            IntegrityIssue(
                importer="generated website",
                specifier="placeholder image URL",
                tried=tuple(used_placeholders),
                kind="asset_usage",
                detail=(
                    "Generated website still contains forbidden placeholder/example "
                    f"image URLs: {', '.join(used_placeholders)}"
                ),
            )
        )
    for key, urls in assets.items():
        valid_urls = [str(url) for url in urls if str(url).startswith("https://")]
        if not valid_urls or any(url in generated_source for url in valid_urls):
            continue
        subject = subjects.get(key, key)
        issues.append(
            IntegrityIssue(
                importer="generated website",
                specifier=key,
                tried=tuple(valid_urls[:3]),
                kind="asset_usage",
                detail=(
                    f"Resolved image group {key!r} for subject {subject!r} is not used "
                    "in any generated HTML, CSS, component, or data file"
                ),
            )
        )
    return issues


def build_repair_prompt(
    issues: Iterable[IntegrityIssue],
    *,
    attempt: int,
    max_attempts: int,
    file_paths: Sequence[str],
) -> str:
    """Build a background user prompt that asks the model to fix preview blockers.

    Args:
        issues: Detected integrity problems.
        attempt: 1-based repair attempt index.
        max_attempts: Configured maximum retries.
        file_paths: Current project file paths for context.

    Returns:
        Prompt text for a silent repair regeneration turn.
    """
    issue_list = list(issues)
    lines = [
        "LIVE PREVIEW AUTO-REPAIR (background, do not ask the user questions):",
        f"Attempt {attempt}/{max_attempts}.",
        "The previous generation has unresolved preview or content-integrity issues.",
        "Fix EVERY issue below. Resolve broken imports and visibly wire supplied",
        "pre-validated image groups into their matching sections when listed.",
        "Do not leave placeholder imports. Do not claim success until imports resolve.",
        "",
        "Integrity issues:",
    ]
    for issue in issue_list[:40]:
        lines.append(f"- {issue.summary}")
    lines.extend(
        [
            "",
            "Current project files:",
            *[f"- {path}" for path in sorted(file_paths)[:200]],
            "",
            "Return ```file path=... action=create|update``` blocks for every fix.",
            "Keep MemoryRouter for React Router. Keep one coherent React entry.",
        ]
    )
    return "\n".join(lines)


def build_exhausted_user_message(issues: Sequence[IntegrityIssue]) -> str:
    """Message shown when auto-repair retries are exhausted."""
    samples = "\n".join(f"- {issue.summary}" for issue in list(issues)[:8])
    more = "" if len(issues) <= 8 else f"\n- …and {len(issues) - 8} more"
    return (
        "Live Preview still has unresolved integrity issues after automatic repair attempts "
        f"({len(issues)} remaining).\n\n"
        f"{samples}{more}\n\n"
        "Please send a more specific prompt, for example:\n"
        '- "Create src/pages/Home.tsx and wire it in App.tsx"\n'
        '- "Fix all missing page imports and make Live Preview run"\n'
        "Name the missing files/routes you expect so the next generation can complete the graph."
    )
