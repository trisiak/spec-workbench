import os
import re
import tempfile
import threading
from pathlib import Path

from pydantic import Field
from pydantic import PrivateAttr

from spec_workbench.data_types import NoteState
from spec_workbench.errors import SpecDocumentReadError
from spec_workbench.interfaces import SpecStoreInterface
from spec_workbench.mutations import append_note_message
from spec_workbench.mutations import create_thread_block
from spec_workbench.mutations import ensure_block_anchor
from spec_workbench.mutations import ensure_heading_anchor
from spec_workbench.mutations import record_notification
from spec_workbench.mutations import resolve_unique_quote
from spec_workbench.mutations import set_note_state


class FileSpecStore(SpecStoreInterface):
    """File-backed spec store: reads the document and applies serialized, atomic mutations."""

    spec_path: Path = Field(frozen=True, description="Path to the spec markdown file")

    _write_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def read_document_text(self) -> str:
        try:
            return self.spec_path.read_text()
        except OSError as e:
            raise SpecDocumentReadError(f"Cannot read spec document: {self.spec_path}") from e

    def append_reply(self, note_id: str, author: str, date: str, message_text: str) -> None:
        with self._write_lock:
            updated_text = append_note_message(
                document_text=self.read_document_text(),
                note_id=note_id,
                author=author,
                date=date,
                message_text=message_text,
            )
            self._write_document_text(updated_text)

    def set_note_state(self, note_id: str, new_state: NoteState, date: str) -> None:
        with self._write_lock:
            updated_text = set_note_state(
                document_text=self.read_document_text(),
                note_id=note_id,
                new_state=new_state,
                date=date,
            )
            self._write_document_text(updated_text)

    def record_notification(self, timestamp: str) -> int:
        with self._write_lock:
            updated_text, new_version = record_notification(
                document_text=self.read_document_text(), timestamp=timestamp
            )
            self._write_document_text(updated_text)
            return new_version

    def create_thread(self, anchor_block_id: str, author: str, date: str, message_text: str) -> str:
        # Id assignment happens under the lock so concurrent creates can't collide
        with self._write_lock:
            document_text = self.read_document_text()
            return self._create_thread_while_locked(
                document_text=document_text,
                anchor_block_id=anchor_block_id,
                quote=None,
                author=author,
                date=date,
                message_text=message_text,
            )

    def create_thread_on_heading(self, heading_text: str, author: str, date: str, message_text: str) -> str:
        # Lazy id assignment: minting the heading's anchor and creating the
        # thread happen under one lock so both land in a single write
        with self._write_lock:
            document_text = self.read_document_text()
            anchored_text, anchor_block_id = ensure_heading_anchor(
                document_text=document_text, heading_text=heading_text
            )
            return self._create_thread_while_locked(
                document_text=anchored_text,
                anchor_block_id=anchor_block_id,
                quote=None,
                author=author,
                date=date,
                message_text=message_text,
            )

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
        # Phrase anchoring: mint the block's id if needed, make the quote
        # unique within the block, and file the thread -- one lock, one write
        with self._write_lock:
            document_text = self.read_document_text()
            block_source = "\n".join(document_text.splitlines()[start_line_idx : end_line_idx + 1])
            anchored_text, anchor_block_id = ensure_block_anchor(
                document_text=document_text,
                start_line_idx=start_line_idx,
                end_line_idx=end_line_idx,
                block_text_prefix=block_text_prefix,
            )
            unique_quote = resolve_unique_quote(
                block_markdown=block_source,
                quote=quote,
                context_before=context_before,
                context_after=context_after,
            )
            return self._create_thread_while_locked(
                document_text=anchored_text,
                anchor_block_id=anchor_block_id,
                quote=unique_quote,
                author=author,
                date=date,
                message_text=message_text,
            )

    def _create_thread_while_locked(
        self,
        document_text: str,
        anchor_block_id: str,
        quote: str | None,
        author: str,
        date: str,
        message_text: str,
    ) -> str:
        # Ids are never reused, even after a thread is deleted -- mint past
        # every #tN token anywhere in the text (prose mentions, the log),
        # not just past the threads currently present
        mentioned_thread_numbers = [
            int(number) for number in re.findall(r"#t(\d+)\b", document_text)
        ]
        next_number = max(mentioned_thread_numbers) + 1 if mentioned_thread_numbers else 1
        new_note_id = f"t{next_number}"
        updated_text = create_thread_block(
            document_text=document_text,
            anchor_block_id=anchor_block_id,
            quote=quote,
            note_id=new_note_id,
            author=author,
            date=date,
            message_text=message_text,
        )
        self._write_document_text(updated_text)
        return new_note_id

    def _write_document_text(self, document_text: str) -> None:
        # Atomic replace so a crash mid-write never truncates the document
        try:
            file_descriptor, temp_path = tempfile.mkstemp(
                dir=self.spec_path.parent, prefix=".spec_workbench_", suffix=".tmp"
            )
            with os.fdopen(file_descriptor, "w") as temp_file:
                temp_file.write(document_text)
            os.replace(temp_path, self.spec_path)
        except OSError as e:
            raise SpecDocumentReadError(f"Cannot write spec document: {self.spec_path}") from e
