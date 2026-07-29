"""Project context builder for AI prompts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional, Set

from app.ai.prompts.cleaner import (
    collapse_whitespace,
    dedupe_preserve_order,
    estimate_tokens,
    strip_comments,
    truncate_text,
)
from app.core.redis import RedisCache

# Always prefer these paths when present (website / React Live Preview).
_WEBSITE_STRUCTURAL_EXACT = (
    "index.html",
    "styles.css",
    "script.js",
    "src/App.tsx",
    "src/App.jsx",
    "src/App.ts",
    "src/App.js",
    "src/main.tsx",
    "src/main.jsx",
    "src/main.ts",
    "src/main.js",
    "src/index.tsx",
    "src/index.jsx",
    "src/index.ts",
    "src/index.js",
    "src/styles.css",
    "src/App.css",
    "src/routes.tsx",
    "src/routes.jsx",
    "src/routes.ts",
    "src/routes.js",
)

_WEBSITE_MUST_PREFIXES = (
    "src/data/",
    "src/pages/",
    "src/routes/",
    "src/types/",
)

_WEBSITE_STRUCTURAL_PREFIXES = (
    *_WEBSITE_MUST_PREFIXES,
    "src/components/",
    "src/hooks/",
    "src/layouts/",
)

_CODE_EXTENSIONS = (".tsx", ".ts", ".jsx", ".js", ".css", ".json")

_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "add",
    "make",
    "build",
    "create",
    "update",
    "please",
    "website",
    "page",
    "pages",
    "site",
    "using",
    "use",
    "my",
    "me",
    "this",
    "that",
    "into",
    "from",
    "have",
    "has",
    "include",
    "some",
    "more",
}


@dataclass
class ProjectContext:
    """Structured project context for prompt building.

    Attributes:
        project: Project metadata.
        folder_structure: Textual folder tree.
        all_paths: Authoritative list of every file path in the project.
        relevant_files: Ordered file snippets.
        current_file: Current file payload.
        selected_code: Selected code snippet.
        chat_history: Recent chat turns.
        recent_paths: Recently opened file paths.
        open_tabs: Currently open editor tab paths.
        token_estimate: Approximate context tokens.
    """

    project: Dict[str, Any]
    folder_structure: str
    all_paths: List[str] = field(default_factory=list)
    relevant_files: List[Dict[str, str]] = field(default_factory=list)
    current_file: Optional[Dict[str, str]] = None
    selected_code: Optional[str] = None
    chat_history: List[Dict[str, str]] = field(default_factory=list)
    recent_paths: List[str] = field(default_factory=list)
    open_tabs: List[str] = field(default_factory=list)
    token_estimate: int = 0


class ContextBuilder:
    """Build token-efficient project context for the LLM."""

    MAX_CONTEXT_TOKENS = 16000
    MAX_FILE_CHARS = 5000
    IMPORT_HOPS = 2

    def __init__(self, cache: RedisCache) -> None:
        """Initialize the context builder.

        Args:
            cache: Redis cache for context snapshots.
        """
        self._cache = cache

    async def build(
        self,
        project: Dict[str, Any],
        files: List[Dict[str, Any]],
        folders: List[Dict[str, Any]],
        chat_history: List[Dict[str, Any]],
        current_file_path: Optional[str] = None,
        selected_code: Optional[str] = None,
        recent_paths: Optional[List[str]] = None,
        open_tabs: Optional[List[str]] = None,
        user_request: Optional[str] = None,
    ) -> ProjectContext:
        """Assemble prioritized project context.

        Args:
            project: Project metadata.
            files: Flat file documents.
            folders: Flat folder documents.
            chat_history: Recent chat messages.
            current_file_path: Currently open file path.
            selected_code: Selected code snippet.
            recent_paths: Recently opened paths.
            open_tabs: Open editor tab paths.
            user_request: Latest user message (drives keyword path matching).

        Returns:
            ProjectContext ready for prompt building.
        """
        recent = [p for p in (recent_paths or []) if p]
        tabs = dedupe_preserve_order([p for p in (open_tabs or []) if p])
        workspace = str(project.get("workspace_type") or "").lower().strip()
        existing_paths = [str(f["path"]) for f in files if f.get("path")]

        structural = self._structural_paths(existing_paths, workspace)
        must_include = self._must_include_paths(existing_paths, workspace)
        query_hits = self._paths_matching_request(user_request or "", existing_paths)
        seed_paths = dedupe_preserve_order(
            [*structural, current_file_path or "", *tabs, *recent, *query_hits]
        )
        seed_paths = [p for p in seed_paths if p]
        imports = self._collect_imports(files, seed_paths, hops=self.IMPORT_HOPS)
        priority_paths = dedupe_preserve_order(
            [
                *query_hits,
                *must_include,
                *structural,
                current_file_path or "",
                *imports,
                *tabs,
                *recent,
            ]
        )
        priority_paths = [p for p in priority_paths if p]

        relevant = self._select_relevant_files(
            files,
            priority_paths,
            must_include=must_include,
        )
        current_file = None
        if current_file_path:
            match = next((f for f in files if f.get("path") == current_file_path), None)
            if match:
                current_file = {
                    "path": match["path"],
                    "language": match.get("language", "plaintext"),
                    "content": self._prepare_content(
                        match.get("content", ""),
                        match.get("language", "plaintext"),
                        prioritize=True,
                    ),
                }
        structure = self._render_structure(folders, files)
        history = [
            {"role": m["role"], "content": truncate_text(m.get("content", ""), 1200)}
            for m in chat_history[-12:]
        ]
        context = ProjectContext(
            project={
                "id": str(project.get("_id") or project.get("id")),
                "name": project.get("name", ""),
                "description": project.get("description", ""),
                "workspace_type": project.get("workspace_type", ""),
            },
            folder_structure=structure,
            all_paths=sorted(existing_paths),
            relevant_files=relevant,
            current_file=current_file,
            selected_code=truncate_text(selected_code, 2000) if selected_code else None,
            chat_history=history,
            recent_paths=recent,
            open_tabs=tabs,
        )
        context.token_estimate = estimate_tokens(json.dumps(context.__dict__, default=str))
        await self._cache.set(
            f"ai:context:{context.project['id']}",
            json.dumps({"token_estimate": context.token_estimate}),
            120,
        )
        return context

    def _must_include_paths(self, existing_paths: List[str], workspace: str) -> List[str]:
        """Paths that should always be packed for coherent edits.

        Args:
            existing_paths: All project file paths.
            workspace: Workspace type key.

        Returns:
            Ordered must-include paths.
        """
        existing = set(existing_paths)
        ordered: List[str] = []
        for path in _WEBSITE_STRUCTURAL_EXACT:
            if path in existing:
                ordered.append(path)
        if workspace == "website":
            ordered.extend(
                sorted(
                    p
                    for p in existing_paths
                    if any(p.startswith(prefix) for prefix in _WEBSITE_MUST_PREFIXES)
                )
            )
        return dedupe_preserve_order(ordered)

    def _structural_paths(self, existing_paths: List[str], workspace: str) -> List[str]:
        """Return high-priority architecture files that already exist.

        Args:
            existing_paths: All project file paths.
            workspace: Workspace type key.

        Returns:
            Ordered structural paths present in the project.
        """
        existing = set(existing_paths)
        ordered: List[str] = []
        for path in _WEBSITE_STRUCTURAL_EXACT:
            if path in existing:
                ordered.append(path)
        # Prefer website prefixes for website; also useful for JS React-ish projects.
        if workspace in {"website", "javascript", ""}:
            prefixed = [
                p
                for p in existing_paths
                if any(p.startswith(prefix) for prefix in _WEBSITE_STRUCTURAL_PREFIXES)
            ]
            ordered.extend(sorted(prefixed))
        # Generic entrypoints for non-website workspaces.
        for path in ("index.js", "index.ts", "main.py", "app.py", "package.json", "requirements.txt"):
            if path in existing:
                ordered.append(path)
        return dedupe_preserve_order(ordered)

    def _paths_matching_request(self, user_request: str, existing_paths: List[str]) -> List[str]:
        """Find existing files whose path/name overlaps the user request.

        Args:
            user_request: Latest user message.
            existing_paths: Project file paths.

        Returns:
            Matching paths, strongest basename hits first.
        """
        tokens = self._request_tokens(user_request)
        if not tokens or not existing_paths:
            return []
        scored: List[tuple[int, str]] = []
        for path in existing_paths:
            lower = path.lower()
            base = PurePosixPath(lower).stem
            score = 0
            for token in tokens:
                if token == base or token in base:
                    score += 5
                elif token in lower:
                    score += 2
            if score:
                scored.append((score, path))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [path for _, path in scored[:24]]

    def _request_tokens(self, user_request: str) -> List[str]:
        """Tokenize a user request for path matching.

        Args:
            user_request: Raw request text.

        Returns:
            Meaningful lowercase tokens.
        """
        raw = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", user_request.lower())
        return dedupe_preserve_order([t for t in raw if t not in _STOPWORDS])

    def _select_relevant_files(
        self,
        files: List[Dict[str, Any]],
        priority_paths: List[str],
        must_include: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """Select and prepare the most relevant files under a token budget.

        Args:
            files: All project files.
            priority_paths: Preferred file paths.
            must_include: Paths that should be packed even if the soft budget is tight.

        Returns:
            Prepared relevant file payloads.
        """
        by_path = {f["path"]: f for f in files if f.get("content", "").strip()}
        must = [p for p in (must_include or []) if p in by_path]
        ordered_paths = dedupe_preserve_order(
            [
                *priority_paths,
                *must,
                *sorted(
                    by_path.keys(),
                    key=lambda p: by_path[p].get("updated_at", ""),
                    reverse=True,
                ),
            ]
        )
        selected: List[Dict[str, str]] = []
        used_tokens = 0
        must_set = set(must)
        soft_limit = self.MAX_CONTEXT_TOKENS
        hard_limit = int(self.MAX_CONTEXT_TOKENS * 1.25)

        for path in ordered_paths:
            file_doc = by_path.get(path)
            if not file_doc:
                continue
            prioritize = path in must_set or path in priority_paths[:12]
            prepared = self._prepare_content(
                file_doc.get("content", ""),
                file_doc.get("language", "plaintext"),
                prioritize=prioritize,
            )
            if not prepared:
                continue
            tokens = estimate_tokens(prepared)
            limit = hard_limit if path in must_set else soft_limit
            if used_tokens + tokens > limit and selected:
                if path in must_set:
                    # Still try a smaller slice for mandatory architecture files.
                    prepared = truncate_text(prepared, self.MAX_FILE_CHARS // 3)
                    tokens = estimate_tokens(prepared)
                    if used_tokens + tokens > hard_limit and selected:
                        continue
                else:
                    break
            selected.append(
                {
                    "path": path,
                    "language": file_doc.get("language", "plaintext"),
                    "content": prepared,
                }
            )
            used_tokens += tokens
        return selected

    def _prepare_content(self, content: str, language: str, prioritize: bool = False) -> str:
        """Clean and truncate file content.

        Args:
            content: Raw content.
            language: Language identifier.
            prioritize: Whether to allow a larger budget.

        Returns:
            Prepared content string.
        """
        lang = (language or "plaintext").lower()
        if lang in {"tsx", "jsx"}:
            lang = "typescript" if lang == "tsx" else "javascript"
        cleaned = collapse_whitespace(strip_comments(content, lang))
        if not cleaned:
            return ""
        budget = self.MAX_FILE_CHARS if prioritize else self.MAX_FILE_CHARS // 2
        return truncate_text(cleaned, budget)

    def _collect_imports(
        self,
        files: List[Dict[str, Any]],
        seed_paths: List[str],
        hops: int = 2,
    ) -> List[str]:
        """Collect local imports transitively from seed files.

        Args:
            files: Project files.
            seed_paths: Starting file paths.
            hops: Max import depth.

        Returns:
            Resolved existing import paths.
        """
        by_path = {f["path"]: f for f in files if f.get("path")}
        existing = set(by_path)
        resolved: List[str] = []
        frontier = [p for p in seed_paths if p in existing]
        seen: Set[str] = set()
        for _ in range(max(1, hops)):
            next_frontier: List[str] = []
            for path in frontier:
                if path in seen:
                    continue
                seen.add(path)
                doc = by_path.get(path)
                if not doc:
                    continue
                for candidate in self._extract_imports_from_content(
                    doc.get("content", ""),
                    path,
                    existing,
                ):
                    if candidate not in seen:
                        resolved.append(candidate)
                        next_frontier.append(candidate)
            frontier = next_frontier
            if not frontier:
                break
        return dedupe_preserve_order(resolved)

    def _extract_imports(
        self,
        files: List[Dict[str, Any]],
        current_file_path: Optional[str],
    ) -> List[str]:
        """Extract imported local file paths from the current file.

        Args:
            files: Project files.
            current_file_path: Current file path.

        Returns:
            Candidate imported paths that exist in the project.
        """
        if not current_file_path:
            return []
        return self._collect_imports(files, [current_file_path], hops=1)

    def _extract_imports_from_content(
        self,
        content: str,
        source_path: str,
        existing_paths: Set[str],
    ) -> List[str]:
        """Parse local import/require/href/src references from file content.

        Args:
            content: Source file body.
            source_path: Path of the file being parsed.
            existing_paths: Set of real project paths.

        Returns:
            Existing resolved paths.
        """
        patterns = [
            r"from\s+['\"]([^'\"]+)['\"]",
            r"import\s+['\"]([^'\"]+)['\"]",
            r"require\(['\"]([^'\"]+)['\"]\)",
            r"import\(\s*['\"]([^'\"]+)['\"]\s*\)",
            r"href=['\"]([^'\"]+\.(?:css|js))['\"]",
            r"src=['\"]([^'\"]+\.(?:js|css))['\"]",
        ]
        found: List[str] = []
        for pattern in patterns:
            for match in re.findall(pattern, content):
                if not match or match.startswith(("http://", "https://", "//", "data:")):
                    continue
                # Skip bare package imports (react, lodash, etc.).
                if not match.startswith((".", "/", "src/", "@/")) and "/" not in match:
                    if not match.endswith(_CODE_EXTENSIONS):
                        continue
                resolved = self._resolve_local_path(match, source_path, existing_paths)
                if resolved:
                    found.append(resolved)
        return dedupe_preserve_order(found)

    def _resolve_local_path(
        self,
        spec: str,
        source_path: str,
        existing_paths: Set[str],
    ) -> Optional[str]:
        """Resolve an import specifier against existing project paths.

        Args:
            spec: Import path string from source.
            source_path: File containing the import.
            existing_paths: Real project paths.

        Returns:
            Matching project path or None.
        """
        cleaned = spec.strip()
        if cleaned.startswith("@/"):
            cleaned = "src/" + cleaned[2:]
        if cleaned.startswith("/"):
            cleaned = cleaned.lstrip("/")

        candidates: List[str] = []
        if cleaned.startswith("."):
            base_dir = str(PurePosixPath(source_path).parent)
            joined = str(PurePosixPath(base_dir) / cleaned)
            # Normalize ./ and ../ segments.
            parts: List[str] = []
            for part in PurePosixPath(joined).parts:
                if part in ("", "."):
                    continue
                if part == "..":
                    if parts:
                        parts.pop()
                    continue
                parts.append(part)
            cleaned = "/".join(parts)

        candidates.append(cleaned)
        if not any(cleaned.endswith(ext) for ext in _CODE_EXTENSIONS):
            for ext in _CODE_EXTENSIONS:
                candidates.append(f"{cleaned}{ext}")
            for ext in _CODE_EXTENSIONS:
                candidates.append(f"{cleaned}/index{ext}")

        for candidate in candidates:
            if candidate in existing_paths:
                return candidate
        return None

    def _render_structure(
        self,
        folders: List[Dict[str, Any]],
        files: List[Dict[str, Any]],
    ) -> str:
        """Render a compact folder structure string.

        Args:
            folders: Folder documents.
            files: File documents.

        Returns:
            Textual tree representation.
        """
        paths = sorted({*[f["path"] + "/" for f in folders], *[f["path"] for f in files]})
        if not paths:
            return "(empty project)"
        return "\n".join(paths)
