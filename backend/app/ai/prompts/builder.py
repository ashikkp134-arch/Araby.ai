"""Prompt builder for the AI coding assistant."""

from typing import List, Optional

from app.ai.context.builder import ProjectContext
from app.ai.pipelines.image_discovery import ImageDiscoveryResult
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
        image_discovery: Optional[ImageDiscoveryResult] = None,
    ) -> List[LLMMessage]:
        """Build the final message list for the LLM.

        Message shape (system then user):
        1. System instructions
        2. Workspace / project metadata
        3. Authoritative project tree + path inventory
        4. Open tabs / recent paths
        5. Relevant file contents (routes, components, data, imports)
        6. Current file / selection / chat history
        7. Optional resolved image assets (when discovery required)
        8. User request (user role)

        Args:
            context: Assembled project context.
            user_request: Latest user request.
            category: Routed request category for system prompt selection.
            image_discovery: Conditional image discovery result for websites.

        Returns:
            Ordered LLMMessage list.
        """
        category_key = category.value if isinstance(category, RequestCategory) else str(category)
        workspace_type = str(context.project.get("workspace_type") or "javascript")
        system_instructions = self._registry.resolve(workspace_type, category_key)

        path_inventory = context.all_paths or []
        if not path_inventory and context.relevant_files:
            path_inventory = [item["path"] for item in context.relevant_files]

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
            "PROJECT GROUNDING (MANDATORY):\n"
            "- The project tree and path inventory below are AUTHORITATIVE.\n"
            "- Prefer updating existing paths that already implement the feature "
            "(App/routes, pages, components, data modules, styles).\n"
            "- Do NOT invent parallel files (e.g. src/data/dolls.ts) when an equivalent "
            "existing path already covers the domain—update the real file instead.\n"
            "- Only create a NEW path when no suitable existing file exists.\n"
            "- Never reply with only \"update X.ts\" instructions; emit ```file path=...``` "
            "blocks that modify the real project files listed here.\n"
            "- If Live Preview must change, file blocks are required.",
            "Current Project Tree:\n" + (context.folder_structure or "(empty project)"),
        ]

        if path_inventory:
            sections.append(
                "Existing Project Paths (do not invent alternatives):\n"
                + "\n".join(f"- {path}" for path in path_inventory)
            )
        else:
            sections.append(
                "Existing Project Paths:\n- (none yet — greenfield; create a coherent tree)"
            )

        if context.open_tabs:
            sections.append(
                "Open Files / Tabs:\n" + "\n".join(f"- {path}" for path in context.open_tabs)
            )
        if context.recent_paths:
            sections.append(
                "Recently Modified / Opened Files:\n"
                + "\n".join(f"- {path}" for path in context.recent_paths)
            )
        if context.relevant_files:
            file_blocks = []
            for item in context.relevant_files:
                file_blocks.append(
                    f"### {item['path']} ({item['language']})\n"
                    f"```{item['language']}\n{item['content']}\n```"
                )
            sections.append(
                "Relevant Files (routes, components, imports, data, styles — "
                "edit these when they already match the request):\n"
                + "\n\n".join(file_blocks)
            )
        elif path_inventory:
            sections.append(
                "Relevant Files:\n"
                "(Path inventory is present but file bodies were not packed. "
                "Still update existing paths from the inventory—do not invent new ones.)"
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
        if image_discovery is not None and (
            workspace_type == "website"
            or category_key == RequestCategory.WEBSITE_BUILDER.value
        ):
            sections.append(image_discovery.to_prompt_section())
        sections.append("Current User Prompt:\n" + user_request.strip())
        system_content = "\n\n".join(sections[:-1])
        return [
            LLMMessage(role="system", content=system_content),
            LLMMessage(role="user", content=sections[-1]),
        ]
