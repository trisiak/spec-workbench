class SpecWorkbenchError(Exception):
    """Base exception for all spec-workbench errors."""

    ...


class NoteNotFoundError(SpecWorkbenchError, KeyError):
    """Raised when a thread or suggestion id cannot be found in the document."""

    def __init__(self, note_id: str) -> None:
        self.note_id = note_id
        super().__init__(f"Note '#{note_id}' not found in the document")


class AnchorNotFoundError(SpecWorkbenchError, KeyError):
    """Raised when a block id has no matching anchored block in the document."""

    def __init__(self, anchor_block_id: str) -> None:
        self.anchor_block_id = anchor_block_id
        super().__init__(f"Anchor '{{#{anchor_block_id}}}' not found in the document")


class HeadingNotFoundError(SpecWorkbenchError, KeyError):
    """Raised when no heading in the document matches the given text."""

    def __init__(self, heading_text: str) -> None:
        self.heading_text = heading_text
        super().__init__(f"No heading titled '{heading_text}' in the document")


class DocumentChangedError(SpecWorkbenchError, ValueError):
    """Raised when the document no longer matches what the caller was looking at."""

    ...


class QuoteResolutionError(SpecWorkbenchError, ValueError):
    """Raised when a quoted phrase cannot be located uniquely within its block."""

    ...


class SpecDocumentReadError(SpecWorkbenchError, OSError):
    """Raised when the spec document file cannot be read or written."""

    ...


class DocumentNotAllowedError(SpecWorkbenchError, ValueError):
    """Raised when a requested document path is outside the workspace, not markdown, or missing."""

    def __init__(self, requested_path: str, reason: str) -> None:
        self.requested_path = requested_path
        super().__init__(f"Cannot open '{requested_path}': {reason}")
