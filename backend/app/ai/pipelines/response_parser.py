"""Parse LLM responses into text and file change proposals."""

import re
from dataclasses import dataclass, field
from typing import List

from app.schemas.chat import FileChangeProposal

FILE_BLOCK_PATTERN = re.compile(
    r"```file\s+path=(?P<path>[^\s]+)\s+action=(?P<action>create|update|delete)\s*\n(?P<body>[\s\S]*?)```",
    re.IGNORECASE,
)


@dataclass
class ParsedAIResponse:
    """Parsed assistant response.

    Attributes:
        message: Natural-language reply with file blocks removed.
        file_changes: Extracted file change proposals.
        raw: Original raw response.
    """

    message: str
    file_changes: List[FileChangeProposal] = field(default_factory=list)
    raw: str = ""


class ResponseParser:
    """Extract structured file operations from assistant text."""

    def parse(self, content: str) -> ParsedAIResponse:
        """Parse an assistant response.

        Args:
            content: Raw assistant content.

        Returns:
            ParsedAIResponse with message and file changes.
        """
        changes: List[FileChangeProposal] = []
        for match in FILE_BLOCK_PATTERN.finditer(content):
            action = match.group("action").lower()
            path = match.group("path").strip().strip("\"'")
            body = match.group("body")
            if body.endswith("\n"):
                body = body[:-1]
            changes.append(
                FileChangeProposal(
                    path=path,
                    action=action,
                    content=None if action == "delete" else body,
                )
            )
        cleaned = FILE_BLOCK_PATTERN.sub("", content).strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        if not cleaned and changes:
            cleaned = f"Applied {len(changes)} file change(s)."
        return ParsedAIResponse(message=cleaned, file_changes=changes, raw=content)
