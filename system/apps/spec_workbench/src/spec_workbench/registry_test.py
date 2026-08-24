from pathlib import Path

import pytest

from spec_workbench.errors import DocumentNotAllowedError
from spec_workbench.registry import DocumentRegistry


def _make_registry(tmp_path: Path) -> DocumentRegistry:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "spec.md").write_text("# Spec\n")
    notes_dir = workspace / "notes"
    notes_dir.mkdir()
    (notes_dir / "other.md").write_text("# Other\n")
    return DocumentRegistry(workspace_root=workspace, default_document=workspace / "spec.md")


def test_resolves_the_default_document_when_no_param_given(tmp_path: Path) -> None:
    registry = _make_registry(tmp_path)

    assert registry.resolve_document_path(None).name == "spec.md"
    assert registry.resolve_document_path("  ").name == "spec.md"
    assert registry.display_path(None) == "spec.md"


def test_resolves_a_relative_markdown_path_inside_the_workspace(tmp_path: Path) -> None:
    registry = _make_registry(tmp_path)

    resolved = registry.resolve_document_path("notes/other.md")

    assert resolved == (tmp_path / "workspace" / "notes" / "other.md").resolve()
    assert registry.display_path("notes/other.md") == "notes/other.md"


def test_rejects_paths_that_escape_the_workspace(tmp_path: Path) -> None:
    registry = _make_registry(tmp_path)
    (tmp_path / "outside.md").write_text("# Outside\n")

    with pytest.raises(DocumentNotAllowedError):
        registry.resolve_document_path("../outside.md")


def test_rejects_non_markdown_and_missing_files(tmp_path: Path) -> None:
    registry = _make_registry(tmp_path)
    (tmp_path / "workspace" / "script.py").write_text("print\n")

    with pytest.raises(DocumentNotAllowedError):
        registry.resolve_document_path("script.py")
    with pytest.raises(DocumentNotAllowedError):
        registry.resolve_document_path("notes/missing.md")


def test_store_for_returns_the_same_store_per_file(tmp_path: Path) -> None:
    # one store per file keeps its writes serialized across requests
    registry = _make_registry(tmp_path)

    assert registry.store_for("notes/other.md") is registry.store_for("notes/other.md")
    assert registry.store_for(None) is not registry.store_for("notes/other.md")


def test_list_markdown_files_skips_dot_directories_and_symlinks(tmp_path: Path) -> None:
    registry = _make_registry(tmp_path)
    workspace = tmp_path / "workspace"
    hidden_dir = workspace / ".hidden"
    hidden_dir.mkdir()
    (hidden_dir / "secret.md").write_text("hidden\n")
    (workspace / "loop").symlink_to(workspace)

    assert registry.list_markdown_files() == ["notes/other.md", "spec.md"]
