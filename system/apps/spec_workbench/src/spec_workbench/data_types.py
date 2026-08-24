from enum import auto

from imbue.imbue_common.enums import UpperCaseStrEnum
from imbue.imbue_common.frozen_model import FrozenModel
from pydantic import Field


class NoteKind(UpperCaseStrEnum):
    """Whether a margin note discusses its target or proposes a change to it."""

    THREAD = auto()
    SUGGESTION = auto()


class NoteState(UpperCaseStrEnum):
    """Lifecycle state of a margin note."""

    OPEN = auto()
    RESOLVED = auto()
    ACCEPTED = auto()
    REJECTED = auto()


class NoteAnchor(FrozenModel):
    """Where a margin note points: a block id, optionally narrowed to a quoted phrase."""

    block_id: str | None = Field(description="Id of the anchored block, without the '#'")
    quote: str | None = Field(description="Quoted phrase within the block, if the anchor is phrase-level")


class NoteMessage(FrozenModel):
    """One attributed message inside a thread or suggestion block."""

    author: str = Field(description="Author name as written in the document")
    stamp: str | None = Field(description="Raw parenthesized stamp, e.g. '2026-08-14' or '2026-08-14, via chat'")
    text: str = Field(description="Message text in markdown, continuation lines joined with newlines")


class MarginNote(FrozenModel):
    """A thread or suggestion block lifted out of the document's prose flow."""

    note_id: str = Field(description="Note id without the '#', e.g. 't4' or 's2'")
    kind: NoteKind = Field(description="Thread or suggestion")
    anchor: NoteAnchor = Field(description="What the note points at")
    state: NoteState = Field(description="Current lifecycle state")
    state_date: str | None = Field(description="Date attached to a terminal state, e.g. resolved (2026-08-14)")
    author: str | None = Field(description="Author from a 'by <name> (<date>)' header, used by suggestions")
    author_date: str | None = Field(description="Date from a 'by <name> (<date>)' header")
    body_lines: tuple[str, ...] = Field(description="Suggestion body lines (diff or replacement); empty for threads")
    is_diff_body: bool = Field(description="Whether the body is a fenced diff rather than a plain replacement")
    messages: tuple[NoteMessage, ...] = Field(description="Attributed messages, in document order")


class SpecFrontmatter(FrozenModel):
    """Key-value frontmatter of a spec document."""

    app_name: str | None = Field(description="Value of the 'app' key, comments stripped")
    status: str | None = Field(description="Value of the 'status' key, comments stripped")
    agent_seen: str | None = Field(description="Value of the 'agent-seen' key, comments stripped")
    notified_version: int | None = Field(
        default=None, description="N from the 'notified' key's 'vN (timestamp)' value, if present"
    )
    notified_at: str | None = Field(
        default=None, description="Timestamp from the 'notified' key's 'vN (timestamp)' value, if present"
    )
    notify_agent: str | None = Field(
        default=None,
        description="Value of the 'notify-agent' key: the agent this document's notify presses nudge",
    )


class SpecDocument(FrozenModel):
    """A parsed spec: frontmatter, prose markdown, and the margin notes lifted out of it."""

    frontmatter: SpecFrontmatter | None = Field(description="Parsed frontmatter, if the document has one")
    prose_markdown: str = Field(description="The document's markdown with frontmatter and note blocks removed")
    prose_file_line_numbers: tuple[int, ...] = Field(
        description="For each prose_markdown line, the 0-based line number it came from in the source file"
    )
    notes: tuple[MarginNote, ...] = Field(description="All thread and suggestion blocks, in document order")
