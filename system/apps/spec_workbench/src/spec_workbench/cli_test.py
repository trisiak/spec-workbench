from pathlib import Path

import pytest

from spec_workbench.cli import surface_document
from spec_workbench.errors import DocumentNotAllowedError
from spec_workbench.registry import DocumentRegistry


def _registry(tmp_path: Path) -> DocumentRegistry:
    (tmp_path / "spec.md").write_text("# Spec\n")
    return DocumentRegistry(workspace_root=tmp_path, default_document=tmp_path / "spec.md")


def test_surface_document_drives_open_retarget_focus_in_order(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def recording_runner(layout_args: list[str]) -> int:
        calls.append(layout_args)
        return 0

    exit_code = surface_document(_registry(tmp_path), "spec.md", recording_runner)
    assert exit_code == 0
    assert calls == [
        ["open", "spec-workbench"],
        ["replace-url", "spec-workbench", "service:spec-workbench/?doc=spec.md"],
        ["focus", "spec-workbench"],
    ]


def test_surface_document_quotes_the_doc_path(tmp_path: Path) -> None:
    nested = tmp_path / "docs and notes"
    nested.mkdir()
    (nested / "plan.md").write_text("# Plan\n")
    calls: list[list[str]] = []
    exit_code = surface_document(
        _registry(tmp_path), "docs and notes/plan.md", lambda a: calls.append(a) or 0
    )
    assert exit_code == 0
    assert calls[1] == [
        "replace-url",
        "spec-workbench",
        "service:spec-workbench/?doc=docs%20and%20notes/plan.md",
    ]


def test_surface_document_rejects_bad_paths_without_touching_the_layout(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    with pytest.raises(DocumentNotAllowedError):
        surface_document(_registry(tmp_path), "missing.md", lambda a: calls.append(a) or 0)
    assert calls == []


def test_surface_document_stops_on_the_first_layout_failure(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def failing_runner(layout_args: list[str]) -> int:
        calls.append(layout_args)
        return 3

    exit_code = surface_document(_registry(tmp_path), "spec.md", failing_runner)
    assert exit_code == 3
    assert calls == [["open", "spec-workbench"]]
