"""Prompt builder for the AI coding assistant."""

from typing import List

from app.ai.context.builder import ProjectContext
from app.ai.providers.base import LLMMessage

SYSTEM_INSTRUCTIONS = """You are an expert coding assistant inside an AI Coding Workspace.
You understand the full project, can reference existing files, suggest improvements,
and modify files when asked.

When you need to create or update files, respond with a clear explanation AND a
fenced block in this exact format for each change:

```file path=relative/path.ext action=update
file contents here
```

Valid actions: create, update, delete.
For delete, the fenced body may be empty.
Only include file blocks for concrete changes.
Prefer minimal, correct edits that match the project's language and style.
For Website Builder projects, use HTML/CSS/JS with Tailwind via CDN when useful.
"""


class PromptBuilder:
    """Construct ordered LLM messages from project context."""

    PROMPT_VERSION = "v1.0.0"

    def build(self, context: ProjectContext, user_request: str) -> List[LLMMessage]:
        """Build the final message list for the LLM.

        Args:
            context: Assembled project context.
            user_request: Latest user request.

        Returns:
            Ordered LLMMessage list.
        """
        sections = [
            "System Instructions:\n" + SYSTEM_INSTRUCTIONS,
            "Workspace Context:\n"
            f"- workspace_type: {context.project.get('workspace_type')}\n"
            f"- prompt_version: {self.PROMPT_VERSION}",
            "Project Metadata:\n"
            f"- id: {context.project.get('id')}\n"
            f"- name: {context.project.get('name')}\n"
            f"- description: {context.project.get('description')}",
            "Folder Structure:\n" + context.folder_structure,
        ]
        if context.relevant_files:
            file_blocks = []
            for item in context.relevant_files:
                file_blocks.append(
                    f"### {item['path']} ({item['language']})\n```{item['language']}\n{item['content']}\n```"
                )
            sections.append("Relevant Files:\n" + "\n\n".join(file_blocks))
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
