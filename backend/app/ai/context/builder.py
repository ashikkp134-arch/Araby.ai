"""Project context builder for AI prompts."""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from app.ai.prompts.cleaner import (
    collapse_whitespace,
    dedupe_preserve_order,
    estimate_tokens,
    strip_comments,
    truncate_text,
)
from app.core.redis import RedisCache


@dataclass
class ProjectContext:
    """Structured project context for prompt building.

    Attributes:
        project: Project metadata.
        folder_structure: Textual folder tree.
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
    relevant_files: List[Dict[str, str]] = field(default_factory=list)
    current_file: Optional[Dict[str, str]] = None
    selected_code: Optional[str] = None
    chat_history: List[Dict[str, str]] = field(default_factory=list)
    recent_paths: List[str] = field(default_factory=list)
    open_tabs: List[str] = field(default_factory=list)
    token_estimate: int = 0


class ContextBuilder:
    """Build token-efficient project context for the LLM."""

    MAX_CONTEXT_TOKENS = 12000
    MAX_FILE_CHARS = 4000

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

        Returns:
            ProjectContext ready for prompt building.
        """
        recent = recent_paths or []
        tabs = dedupe_preserve_order([p for p in (open_tabs or []) if p])
        imports = self._extract_imports(files, current_file_path)
        priority_paths = dedupe_preserve_order(
            [p for p in [current_file_path, *imports, *tabs, *recent] if p]
        )
        relevant = self._select_relevant_files(files, priority_paths)
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

    def _select_relevant_files(
        self,
        files: List[Dict[str, Any]],
        priority_paths: List[str],
    ) -> List[Dict[str, str]]:
        """Select and prepare the most relevant files under a token budget.

        Args:
            files: All project files.
            priority_paths: Preferred file paths.

        Returns:
            Prepared relevant file payloads.
        """
        by_path = {f["path"]: f for f in files if f.get("content", "").strip()}
        ordered_paths = dedupe_preserve_order(
            [*priority_paths, *sorted(by_path.keys(), key=lambda p: by_path[p].get("updated_at", ""), reverse=True)]
        )
        selected: List[Dict[str, str]] = []
        used_tokens = 0
        for path in ordered_paths:
            file_doc = by_path.get(path)
            if not file_doc:
                continue
            prepared = self._prepare_content(
                file_doc.get("content", ""),
                file_doc.get("language", "plaintext"),
                prioritize=path in priority_paths[:3],
            )
            if not prepared:
                continue
            tokens = estimate_tokens(prepared)
            if used_tokens + tokens > self.MAX_CONTEXT_TOKENS and selected:
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
        cleaned = collapse_whitespace(strip_comments(content, language))
        if not cleaned:
            return ""
        budget = self.MAX_FILE_CHARS if prioritize else self.MAX_FILE_CHARS // 2
        return truncate_text(cleaned, budget)

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
        current = next((f for f in files if f.get("path") == current_file_path), None)
        if not current:
            return []
        content = current.get("content", "")
        patterns = [
            r"from\s+['\"](\./[^'\"]+|../[^'\"]+)['\"]",
            r"import\s+['\"](\./[^'\"]+|../[^'\"]+)['\"]",
            r"require\(['\"](\./[^'\"]+|../[^'\"]+)['\"]\)",
            r"from\s+([a-zA-Z0-9_\.]+)\s+import",
            r"href=['\"]([^'\"]+\.(?:css|js))['\"]",
            r"src=['\"]([^'\"]+\.(?:js|css))['\"]",
        ]
        found: Set[str] = set()
        for pattern in patterns:
            for match in re.findall(pattern, content):
                found.add(match)
        existing_paths = {f["path"] for f in files}
        resolved: List[str] = []
        for item in found:
            candidate = item.lstrip("./")
            if candidate in existing_paths:
                resolved.append(candidate)
            elif f"{candidate}.py" in existing_paths:
                resolved.append(f"{candidate}.py")
            elif f"{candidate}.js" in existing_paths:
                resolved.append(f"{candidate}.js")
        return resolved

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
