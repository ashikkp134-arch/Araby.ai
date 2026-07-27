"""Prompt cleaning and context optimization helpers."""

import re
from typing import List


def strip_comments(content: str, language: str) -> str:
    """Remove common comment patterns to reduce tokens.

    Args:
        content: Source content.
        language: Language identifier.

    Returns:
        Content with comments removed where safe.
    """
    if language in {"python"}:
        content = re.sub(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', "", content)
        content = re.sub(r"#.*$", "", content, flags=re.MULTILINE)
    elif language in {"javascript", "typescript", "css", "java"}:
        content = re.sub(r"/\*[\s\S]*?\*/", "", content)
        content = re.sub(r"//.*$", "", content, flags=re.MULTILINE)
    elif language == "html":
        content = re.sub(r"<!--([\s\S]*?)-->", "", content)
    return content


def collapse_whitespace(content: str) -> str:
    """Collapse excessive blank lines and trailing spaces.

    Args:
        content: Source content.

    Returns:
        Compacted content.
    """
    content = re.sub(r"[ \t]+$", "", content, flags=re.MULTILINE)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


def truncate_text(content: str, max_chars: int) -> str:
    """Safely truncate text to a character budget.

    Args:
        content: Source content.
        max_chars: Maximum characters to keep.

    Returns:
        Truncated content with marker when needed.
    """
    if len(content) <= max_chars:
        return content
    return content[: max_chars - 20] + "\n/* ...truncated... */"


def estimate_tokens(text: str) -> int:
    """Estimate token count using a simple heuristic.

    Args:
        text: Input text.

    Returns:
        Approximate token count.
    """
    return max(1, len(text) // 4)


def dedupe_preserve_order(items: List[str]) -> List[str]:
    """Deduplicate strings while preserving order.

    Args:
        items: Input strings.

    Returns:
        Deduplicated list.
    """
    seen = set()
    result: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
