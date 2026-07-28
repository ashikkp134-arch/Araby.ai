"""Prompt builder for the AI coding assistant."""

from typing import List, Optional

from app.ai.context.builder import ProjectContext
from app.ai.prompts.registry import SystemPromptRegistry
from app.ai.providers.base import LLMMessage
from app.ai.routing import RequestCategory


class PromptBuilder:
    """Construct ordered LLM messages from project context and routed prompts."""

    PROMPT_VERSION = SystemPromptRegistry.PROMPT_VERSION

    def __init__(self, registry: Optional[SystemPromptRegistry] = None) -> None:
        """Initialize the prompt builder.

        Args:
            registry: Optional system prompt registry.
        """
        self._registry = registry or SystemPromptRegistry()

    def build(
        self,
        context: ProjectContext,
        user_request: str,
        *,
        category: str | RequestCategory = RequestCategory.CODE_GENERATION,
    ) -> List[LLMMessage]:
        """Build the final message list for the LLM.

        Args:
            context: Assembled project context.
            user_request: Latest user request.
            category: Routed request category for system prompt selection.

        Returns:
            Ordered LLMMessage list.
        """
        category_key = category.value if isinstance(category, RequestCategory) else str(category)
        workspace_type = str(context.project.get("workspace_type") or "javascript")
        system_instructions = self._registry.resolve(workspace_type, category_key)

        sections = [
            "System Instructions:\n" + system_instructions,
            "Workspace Context:\n"
            f"- workspace_type: {workspace_type}\n"
            f"- project_type: {workspace_type}\n"
            f"- prompt_version: {self.PROMPT_VERSION}\n"
            f"- request_category: {category_key}",
            "Project Metadata:\n"
            f"- id: {context.project.get('id')}\n"
            f"- name: {context.project.get('name')}\n"
            f"- description: {context.project.get('description')}",
            "Folder Structure (file tree):\n" + context.folder_structure,
        ]
        if context.open_tabs:
            sections.append("Open Tabs:\n" + "\n".join(f"- {path}" for path in context.open_tabs))
        if context.recent_paths:
            sections.append(
                "Recently Modified / Opened Files:\n"
                + "\n".join(f"- {path}" for path in context.recent_paths)
            )
        if context.relevant_files:
            file_blocks = []
            for item in context.relevant_files:
                file_blocks.append(
                    f"### {item['path']} ({item['language']})\n```{item['language']}\n{item['content']}\n```"
                )
            sections.append(
                "Relevant Files (imports, current, recent, and related):\n"
                + "\n\n".join(file_blocks)
            )
        if context.current_file:
            sections.append(
                "Current File:\n"
                f"path: {context.current_file['path']}\n"
                f"```{context.current_file['language']}\n{context.current_file['content']}\n```"
            )
        if context.selected_code:
            sections.append("Selected Code:\n```\n" + context.selected_code + "\n```")
        if context.chat_history:
            history_lines = [
                f"{item['role']}: {item['content']}" for item in context.chat_history
            ]
            sections.append("Chat History:\n" + "\n".join(history_lines))
        sections.append("User Request:\n" + user_request.strip())
        system_content = "\n\n".join(sections[:-1])
        return [
            LLMMessage(role="system", content=system_content),
            LLMMessage(role="user", content=sections[-1]),
        ]
