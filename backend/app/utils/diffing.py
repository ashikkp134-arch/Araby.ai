"""Line-level diffs for AI-applied file changes.

Produces the hunk data the editor renders next to "Applied changes" so a user
can review exactly which lines the AI added or removed.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import List, Optional

from app.schemas.chat import DiffHunk, DiffLine, FileChangeDiff

# Context lines kept around each changed region.
_CONTEXT_LINES = 3
# Rendered-line budget per file; counts stay exact when hunks are dropped.
_MAX_DIFF_LINES = 600
# Above this size a line-by-line match is too slow to run inline with a request.
_MAX_SOURCE_LINES = 20_000


def split_lines(text: Optional[str]) -> List[str]:
    """Split file text into lines, ignoring a single trailing newline.

    Args:
        text: File content, or None when the file did not exist.

    Returns:
        Lines without their newline terminators.
    """
    if not text:
        return []
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def build_file_diff(
    *,
    action: str,
    previous_content: Optional[str],
    current_content: Optional[str],
    existed_before: bool,
) -> FileChangeDiff:
    """Build the line-level diff for one applied file change.

    Args:
        action: create, update, or delete.
        previous_content: File content before the change (None if absent).
        current_content: File content after the change (None for deletes).
        existed_before: Whether the file existed before the change.

    Returns:
        FileChangeDiff with add/remove counts and renderable hunks.
    """
    old_lines = split_lines(previous_content)
    new_lines = split_lines(current_content)
    diff = FileChangeDiff(
        is_new_file=not existed_before,
        is_deleted=action == "delete",
    )

    matcher = SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in {"replace", "delete"}:
            diff.deletions += i2 - i1
        if tag in {"replace", "insert"}:
            diff.additions += j2 - j1

    if not diff.additions and not diff.deletions:
        return diff

    if max(len(old_lines), len(new_lines)) > _MAX_SOURCE_LINES:
        diff.truncated = True
        return diff

    rendered = 0
    for group in matcher.get_grouped_opcodes(_CONTEXT_LINES):
        hunk = _build_hunk(group, old_lines, new_lines)
        if rendered + len(hunk.lines) > _MAX_DIFF_LINES:
            diff.truncated = True
            break
        diff.hunks.append(hunk)
        rendered += len(hunk.lines)

    return diff


def _build_hunk(
    group: List[tuple],
    old_lines: List[str],
    new_lines: List[str],
) -> DiffHunk:
    """Render one grouped opcode run into a diff hunk.

    Args:
        group: Opcodes from ``SequenceMatcher.get_grouped_opcodes``.
        old_lines: Lines of the old file.
        new_lines: Lines of the new file.

    Returns:
        DiffHunk with positioned context/add/remove lines.
    """
    lines: List[DiffLine] = []
    for tag, i1, i2, j1, j2 in group:
        if tag == "equal":
            for offset in range(i2 - i1):
                lines.append(
                    DiffLine(
                        type="context",
                        old_line=i1 + offset + 1,
                        new_line=j1 + offset + 1,
                        content=old_lines[i1 + offset],
                    )
                )
            continue
        for index in range(i1, i2):
            lines.append(
                DiffLine(type="remove", old_line=index + 1, content=old_lines[index])
            )
        for index in range(j1, j2):
            lines.append(
                DiffLine(type="add", new_line=index + 1, content=new_lines[index])
            )

    first, last = group[0], group[-1]
    return DiffHunk(
        old_start=first[1] + 1,
        old_lines=last[2] - first[1],
        new_start=first[3] + 1,
        new_lines=last[4] - first[3],
        lines=lines,
    )
