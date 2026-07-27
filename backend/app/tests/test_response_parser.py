"""Unit tests for prompt response parsing."""

from app.ai.pipelines.response_parser import ResponseParser


def test_parse_file_update_block() -> None:
    """Ensure file action blocks are extracted correctly."""
    parser = ResponseParser()
    raw = """Here is an update.

```file path=index.js action=update
console.log('hi');
```
"""
    parsed = parser.parse(raw)
    assert len(parsed.file_changes) == 1
    assert parsed.file_changes[0].path == "index.js"
    assert parsed.file_changes[0].action == "update"
    assert "console.log" in (parsed.file_changes[0].content or "")
    assert "Here is an update" in parsed.message
