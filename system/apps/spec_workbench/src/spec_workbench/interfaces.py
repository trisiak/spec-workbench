from abc import ABC
from abc import abstractmethod

from imbue.imbue_common.mutable_model import MutableModel

from spec_workbench.data_types import NoteState


class SpecStoreInterface(MutableModel, ABC):
    """Contract for reading and mutating the spec document file."""

    @abstractmethod
    def read_document_text(self) -> str:
        """Return the current full text of the spec document."""

    @abstractmethod
    def append_reply(self, note_id: str, author: str, date: str, message_text: str) -> None:
        """Append an attributed message to the given note and persist the document."""

    @abstractmethod
    def set_note_state(self, note_id: str, new_state: NoteState, date: str) -> None:
        """Change the given note's lifecycle state and persist the document."""

    @abstractmethod
    def record_notification(self, timestamp: str) -> int:
        """Bump the document's 'notified' version stamp and return the new version number."""

    @abstractmethod
    def create_thread(self, anchor_block_id: str, author: str, date: str, message_text: str) -> str:
        """Open a new thread on the given anchor, persist it, and return the assigned note id."""

    @abstractmethod
    def create_thread_on_heading(self, heading_text: str, author: str, date: str, message_text: str) -> str:
        """Open a new thread on the titled heading, minting its anchor id if absent; return the note id."""

    @abstractmethod
    def create_thread_on_block(
        self,
        start_line_idx: int,
        end_line_idx: int,
        block_text_prefix: str,
        quote: str,
        context_before: str,
        context_after: str,
        author: str,
        date: str,
        message_text: str,
    ) -> str:
        """Open a phrase-anchored thread on the block at the given source lines, minting ids as needed."""
