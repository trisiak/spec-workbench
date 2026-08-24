import threading
from pathlib import Path

from imbue.imbue_common.mutable_model import MutableModel
from pydantic import Field
from pydantic import PrivateAttr

from spec_workbench.errors import DocumentNotAllowedError
from spec_workbench.store import FileSpecStore

# Directories never worth walking for the file picker (dot-directories are
# skipped separately)
_SKIPPED_DIRECTORY_NAMES = frozenset({"node_modules", "__pycache__"})


class DocumentRegistry(MutableModel):
    """Maps ``?doc=`` requests to per-file stores, confined to one workspace root.

    Any markdown file under the root can be opened and annotated; each file
    gets exactly one ``FileSpecStore`` so its writes stay serialized no matter
    how many requests target it.
    """

    workspace_root: Path = Field(frozen=True, description="Directory all openable documents must live under")
    default_document: Path = Field(frozen=True, description="Document served when no ?doc= is given")

    _stores_by_path: dict[Path, FileSpecStore] = PrivateAttr(default_factory=dict)
    _stores_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def resolve_document_path(self, doc_param: str | None) -> Path:
        """Resolve a ?doc= value to an absolute path, or raise DocumentNotAllowedError."""
        if doc_param is None or not doc_param.strip():
            return self.default_document.resolve()
        root = self.workspace_root.resolve()
        candidate = (root / doc_param).resolve()
        if not candidate.is_relative_to(root):
            raise DocumentNotAllowedError(doc_param, "it is outside the workspace")
        if candidate.suffix.lower() != ".md":
            raise DocumentNotAllowedError(doc_param, "only markdown files can be opened")
        if not candidate.is_file():
            raise DocumentNotAllowedError(doc_param, "no such file")
        return candidate

    def store_for(self, doc_param: str | None) -> FileSpecStore:
        document_path = self.resolve_document_path(doc_param)
        with self._stores_lock:
            if document_path not in self._stores_by_path:
                self._stores_by_path[document_path] = FileSpecStore(spec_path=document_path)
            return self._stores_by_path[document_path]

    def display_path(self, doc_param: str | None) -> str:
        """The root-relative path shown in the UI and used as the ?doc= value."""
        document_path = self.resolve_document_path(doc_param)
        return str(document_path.relative_to(self.workspace_root.resolve()))

    def list_markdown_files(self) -> list[str]:
        """Every openable markdown file, root-relative and sorted for the picker."""
        root = self.workspace_root.resolve()
        found: list[str] = []
        pending = [root]
        while pending:
            directory = pending.pop()
            for entry in directory.iterdir():
                if entry.name.startswith(".") or entry.name in _SKIPPED_DIRECTORY_NAMES:
                    continue
                if entry.is_dir() and not entry.is_symlink():
                    pending.append(entry)
                elif entry.is_file() and entry.suffix.lower() == ".md":
                    found.append(str(entry.relative_to(root)))
        return sorted(found)
