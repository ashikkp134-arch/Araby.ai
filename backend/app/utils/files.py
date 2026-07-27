"""File path sanitization and language detection utilities."""

import os
import re
from typing import Optional

from app.utils.exceptions import ValidationAppError

SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._\-@+ ]+$")

LANGUAGE_BY_EXTENSION = {
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".py": "python",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".json": "json",
    ".md": "markdown",
    ".txt": "plaintext",
    ".svg": "xml",
}


def sanitize_name(name: str) -> str:
    """Sanitize a file or folder name.

    Args:
        name: Raw name supplied by the client.

    Returns:
        Sanitized name.

    Raises:
        ValidationAppError: If the name is unsafe.
    """
    cleaned = name.strip()
    if not cleaned or cleaned in {".", ".."}:
        raise ValidationAppError("Invalid name")
    if "/" in cleaned or "\\" in cleaned:
        raise ValidationAppError("Name cannot contain path separators")
    if not SAFE_NAME_PATTERN.match(cleaned):
        raise ValidationAppError("Name contains invalid characters")
    return cleaned


def normalize_path(path: str) -> str:
    """Normalize a project-relative path.

    Args:
        path: Raw path string.

    Returns:
        Normalized path without leading slash.

    Raises:
        ValidationAppError: If the path escapes the project root.
    """
    raw = (path or "").replace("\\", "/").strip()
    if raw.startswith("/"):
        raw = raw[1:]
    parts = [part for part in raw.split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        raise ValidationAppError("Path traversal is not allowed")
    return "/".join(parts)


def join_path(parent: str, name: str) -> str:
    """Join a parent path and child name safely.

    Args:
        parent: Parent folder path.
        name: Child name.

    Returns:
        Combined normalized path.
    """
    parent_norm = normalize_path(parent)
    child = sanitize_name(name)
    return f"{parent_norm}/{child}" if parent_norm else child


def detect_language(filename: str) -> str:
    """Detect editor language from a filename.

    Args:
        filename: File name including extension.

    Returns:
        Language identifier string.
    """
    _, ext = os.path.splitext(filename.lower())
    return LANGUAGE_BY_EXTENSION.get(ext, "plaintext")


def parent_path_of(path: str) -> str:
    """Return the parent directory path.

    Args:
        path: Full path.

    Returns:
        Parent path or empty string for root items.
    """
    normalized = normalize_path(path)
    if "/" not in normalized:
        return ""
    return normalized.rsplit("/", 1)[0]


def basename_of(path: str) -> str:
    """Return the final path segment.

    Args:
        path: Full path.

    Returns:
        Base name.
    """
    normalized = normalize_path(path)
    return normalized.rsplit("/", 1)[-1] if normalized else ""


def default_files_for_workspace(workspace_type: str) -> list[dict[str, str]]:
    """Return starter files for a workspace type.

    Args:
        workspace_type: Workspace type key.

    Returns:
        List of dicts with name and content keys.
    """
    if workspace_type == "javascript":
        return [
            {
                "name": "index.js",
                "content": (
                    "// Welcome to your JavaScript workspace\n"
                    "export function main() {\n"
                    "  console.log('Hello from AI Coding Workspace');\n"
                    "}\n\n"
                    "main();\n"
                ),
            },
            {
                "name": "README.md",
                "content": "# JavaScript Project\n\nAsk the AI chat to help build features.\n",
            },
        ]
    if workspace_type == "python":
        return [
            {
                "name": "main.py",
                "content": (
                    '"""Entry point for your Python project."""\n\n'
                    "def main() -> None:\n"
                    '    """Run the application."""\n'
                    '    print("Hello from AI Coding Workspace")\n\n\n'
                    'if __name__ == "__main__":\n'
                    "    main()\n"
                ),
            },
            {
                "name": "README.md",
                "content": "# Python Project\n\nAsk the AI chat to help build features.\n",
            },
        ]
    return [
        {
            "name": "index.html",
            "content": (
                "<!DOCTYPE html>\n"
                '<html lang="en">\n'
                "<head>\n"
                '  <meta charset="UTF-8" />\n'
                '  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
                "  <title>Website Builder</title>\n"
                '  <script src="https://cdn.tailwindcss.com"></script>\n'
                '  <link rel="stylesheet" href="styles.css" />\n'
                "</head>\n"
                "<body class=\"min-h-screen bg-slate-950 text-slate-100\">\n"
                '  <main class="mx-auto flex min-h-screen max-w-3xl flex-col '
                'items-center justify-center gap-4 px-6 text-center">\n'
                '    <h1 class="text-4xl font-semibold tracking-tight">Website Builder</h1>\n'
                '    <p class="text-slate-400">Describe your site in chat to generate it with AI.</p>\n'
                '    <button id="cta" class="rounded-lg bg-cyan-500 px-4 py-2 '
                'font-medium text-slate-950 hover:bg-cyan-400">Get Started</button>\n'
                "  </main>\n"
                '  <script src="script.js"></script>\n'
                "</body>\n"
                "</html>\n"
            ),
        },
        {
            "name": "styles.css",
            "content": "/* Custom styles beyond Tailwind */\nbody {\n  font-family: ui-sans-serif, system-ui, sans-serif;\n}\n",
        },
        {
            "name": "script.js",
            "content": (
                "const button = document.getElementById('cta');\n"
                "if (button) {\n"
                "  button.addEventListener('click', () => {\n"
                "    alert('Ready to build with AI!');\n"
                "  });\n"
                "}\n"
            ),
        },
    ]
