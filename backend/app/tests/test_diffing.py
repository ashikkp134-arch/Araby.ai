"""Unit tests for applied-change line diffs."""

from app.utils.diffing import build_file_diff, split_lines


def test_split_lines_drops_single_trailing_newline() -> None:
    assert split_lines("a\nb\n") == ["a", "b"]
    assert split_lines("a\nb") == ["a", "b"]
    assert split_lines("") == []
    assert split_lines(None) == []


def test_update_reports_added_line_with_context() -> None:
    diff = build_file_diff(
        action="update",
        previous_content="def f(v):\n    return v\n",
        current_content='def f(v):\n    print("hi")\n    return v\n',
        existed_before=True,
    )

    assert diff.additions == 1
    assert diff.deletions == 0
    assert diff.is_new_file is False
    assert diff.truncated is False

    added = [line for hunk in diff.hunks for line in hunk.lines if line.type == "add"]
    assert [line.content for line in added] == ['    print("hi")']
    assert added[0].new_line == 2
    assert added[0].old_line is None


def test_replaced_line_reports_add_and_remove() -> None:
    diff = build_file_diff(
        action="update",
        previous_content="print('old')\n",
        current_content="print('new')\n",
        existed_before=True,
    )

    assert diff.additions == 1
    assert diff.deletions == 1
    kinds = [line.type for hunk in diff.hunks for line in hunk.lines]
    assert kinds == ["remove", "add"]


def test_created_file_is_all_additions() -> None:
    diff = build_file_diff(
        action="create",
        previous_content=None,
        current_content="a\nb\n",
        existed_before=False,
    )

    assert diff.is_new_file is True
    assert diff.additions == 2
    assert diff.deletions == 0


def test_deleted_file_is_all_deletions() -> None:
    diff = build_file_diff(
        action="delete",
        previous_content="a\nb\n",
        current_content=None,
        existed_before=True,
    )

    assert diff.is_deleted is True
    assert diff.deletions == 2
    assert diff.additions == 0


def test_identical_content_has_no_hunks() -> None:
    diff = build_file_diff(
        action="update",
        previous_content="same\n",
        current_content="same\n",
        existed_before=True,
    )

    assert diff.additions == 0
    assert diff.deletions == 0
    assert diff.hunks == []


def test_huge_diff_reports_counts_without_hunks() -> None:
    diff = build_file_diff(
        action="update",
        previous_content="",
        current_content="\n".join(str(i) for i in range(25_000)) + "\n",
        existed_before=True,
    )

    assert diff.additions == 25_000
    assert diff.truncated is True
    assert diff.hunks == []
