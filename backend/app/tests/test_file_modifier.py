"""Unit tests for AI file modifier reverse-change tracking."""

import asyncio
from typing import Dict, Optional

from app.ai.pipelines.file_modifier import FileModifier
from app.schemas.chat import FileChangeProposal


class FakeFileService:
    """Minimal in-memory stand-in for FileService used by FileModifier."""

    def __init__(self) -> None:
        self.files: Dict[str, str] = {}

    async def get_raw_content_by_path(self, project_id: str, path: str) -> Optional[str]:
        return self.files.get(path)

    async def apply_path_content(
        self,
        project_id: str,
        path: str,
        content: str,
        create_if_missing: bool = True,
    ) -> None:
        self.files[path] = content

    async def delete_by_path(self, project_id: str, path: str) -> None:
        self.files.pop(path, None)


def test_create_reports_not_existed_before() -> None:
    service = FakeFileService()
    modifier = FileModifier(service)  # type: ignore[arg-type]

    async def run():
        return await modifier.apply(
            "p1",
            [FileChangeProposal(path="new.py", action="create", content="print(1)\n")],
        )

    applied, reverse = asyncio.run(run())

    assert len(applied) == 1
    assert service.files["new.py"] == "print(1)\n"
    assert len(reverse) == 1
    assert reverse[0].existed_before is False
    assert reverse[0].previous_content is None


def test_update_captures_previous_content_for_undo() -> None:
    service = FakeFileService()
    service.files["main.py"] = "print('old')\n"
    modifier = FileModifier(service)  # type: ignore[arg-type]

    async def run():
        return await modifier.apply(
            "p1",
            [FileChangeProposal(path="main.py", action="update", content="print('new')\n")],
        )

    applied, reverse = asyncio.run(run())

    assert service.files["main.py"] == "print('new')\n"
    assert reverse[0].existed_before is True
    assert reverse[0].previous_content == "print('old')\n"

    async def undo():
        for item in reverse:
            if item.existed_before:
                await service.apply_path_content("p1", item.path, item.previous_content or "")
            else:
                await service.delete_by_path("p1", item.path)

    asyncio.run(undo())
    assert service.files["main.py"] == "print('old')\n"


def test_delete_missing_file_is_noop() -> None:
    service = FakeFileService()
    modifier = FileModifier(service)  # type: ignore[arg-type]

    async def run():
        return await modifier.apply(
            "p1",
            [FileChangeProposal(path="ghost.py", action="delete")],
        )

    applied, reverse = asyncio.run(run())

    assert applied == []
    assert reverse == []


def test_delete_existing_file_can_be_undone() -> None:
    service = FakeFileService()
    service.files["gone.py"] = "content-here\n"
    modifier = FileModifier(service)  # type: ignore[arg-type]

    async def run():
        return await modifier.apply(
            "p1",
            [FileChangeProposal(path="gone.py", action="delete")],
        )

    applied, reverse = asyncio.run(run())

    assert len(applied) == 1
    assert "gone.py" not in service.files
    assert reverse[0].existed_before is True
    assert reverse[0].previous_content == "content-here\n"

    asyncio.run(
        service.apply_path_content("p1", reverse[0].path, reverse[0].previous_content or "")
    )
    assert service.files["gone.py"] == "content-here\n"
