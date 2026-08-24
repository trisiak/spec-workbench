import re
from collections.abc import Sequence
from typing import Final

from imbue.imbue_common.pure import pure
from markdown_it import MarkdownIt

from spec_workbench.data_types import MarginNote
from spec_workbench.data_types import NoteKind
from spec_workbench.data_types import NoteState
from spec_workbench.data_types import SpecDocument
from spec_workbench.parsing import TRAILING_ID_RE

# A stamp's leading date and optional minutes: '2026-08-19' or '2026-08-19 23:58'
_STAMP_DATETIME_RE: Final[re.Pattern[str]] = re.compile(
    r"^(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}))?"
)

_STATUS_CODE_RE: Final[re.Pattern[str]] = re.compile(
    r"\s*--\s*<code>(idea|planned|building|done|verified)</code>"
)

# A story mark opening a list item, e.g. "- `done` drafted comments survive...";
# the full status vocabulary badges here, same as headings (#t28)
_STORY_MARK_RE: Final[re.Pattern[str]] = re.compile(
    r"(<li[^>]*>\s*(?:<p[^>]*>)?)<code>(idea|planned|building|done|verified|open)</code>"
)

_AGENT_AUTHOR_NAME: Final[str] = "agent"

_DIFF_FENCE_RE: Final[re.Pattern[str]] = re.compile(r"^\s*```")

# Block tokens that carry an anchor id and a source-line range in the
# rendered HTML (the selection API climbs to the nearest of these)
_ANCHORABLE_TOKEN_TYPES: Final[tuple[str, ...]] = (
    "heading_open",
    "paragraph_open",
    "list_item_open",
)


@pure
def _ink_for_author(author: str | None) -> str:
    return "pencil" if author == _AGENT_AUTHOR_NAME else "pen"


@pure
def render_prose_html(prose_markdown: str, prose_file_line_numbers: Sequence[int]) -> str:
    """Render prose to HTML; blocks carry their {#id} anchors and source file-line ranges."""
    # Strip trailing {#id} markers (outside code fences), remembering the line that owned each
    lines = prose_markdown.splitlines()
    block_id_by_line_idx: dict[int, str] = {}
    cleaned_lines: list[str] = []
    is_in_fence = False
    for idx, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            is_in_fence = not is_in_fence
            cleaned_lines.append(line)
            continue
        id_match = TRAILING_ID_RE.match(line) if not is_in_fence else None
        if id_match is not None:
            block_id_by_line_idx[idx] = id_match.group("block_id")
            cleaned_lines.append(id_match.group("rest"))
        else:
            cleaned_lines.append(line)

    # Parse (tables enabled), then stamp block tokens with ids and file-line ranges
    markdown_renderer = MarkdownIt().enable("table")
    tokens = markdown_renderer.parse("\n".join(cleaned_lines))
    consumed_id_line_idxs: set[int] = set()
    for token in tokens:
        if token.type not in _ANCHORABLE_TOKEN_TYPES or token.map is None or token.hidden:
            continue
        start_line_idx, end_line_idx = token.map[0], token.map[1] - 1
        # markdown-it maps loose list items through their trailing blank
        # lines; trim them, or the block's data-eline points past its own
        # text -- and across a lifted note block once mapped to file lines
        while end_line_idx > start_line_idx and not cleaned_lines[end_line_idx].strip():
            end_line_idx -= 1
        if start_line_idx < len(prose_file_line_numbers) and end_line_idx < len(prose_file_line_numbers):
            token.attrSet("data-sline", str(prose_file_line_numbers[start_line_idx]))
            token.attrSet("data-eline", str(prose_file_line_numbers[end_line_idx]))
        for line_idx in range(start_line_idx, end_line_idx + 1):
            if line_idx in block_id_by_line_idx and line_idx not in consumed_id_line_idxs:
                token.attrSet("id", block_id_by_line_idx[line_idx])
                consumed_id_line_idxs.add(line_idx)
                break

    rendered_html = markdown_renderer.renderer.render(tokens, markdown_renderer.options, {})

    # Badges: trailing status codes in headings, and story marks opening list items
    html_with_badges = _STATUS_CODE_RE.sub(r' <span class="badge \1">\1</span>', rendered_html)
    return _STORY_MARK_RE.sub(r'\1<span class="badge \2">\2</span>', html_with_badges)


@pure
def _build_diff_line_views(body_lines: tuple[str, ...]) -> list[dict[str, str]]:
    diff_line_views: list[dict[str, str]] = []
    for line in body_lines:
        if _DIFF_FENCE_RE.match(line) is not None:
            continue
        if line.startswith("+"):
            diff_line_views.append({"op": "add", "text": line})
        elif line.startswith("-"):
            diff_line_views.append({"op": "del", "text": line})
        else:
            diff_line_views.append({"op": "ctx", "text": line})
    return diff_line_views


@pure
def _normalize_stamp_end(stamp: str | None) -> str | None:
    """A message stamp as a sortable timestamp, read as late as it could be.

    Stamps carry a date and optionally minutes ('2026-08-19 23:58'); the
    unknown seconds are read as :59 so same-minute activity over-marks as
    new rather than hiding. Legacy day-only stamps read as start of day.
    """
    if stamp is None:
        return None
    stamp_match = _STAMP_DATETIME_RE.match(stamp.strip())
    if stamp_match is None:
        return None
    time_part = stamp_match.group(2)
    return f"{stamp_match.group(1)}T{time_part + ':59' if time_part else '00:00:00'}"


@pure
def _normalize_cursor(cursor: str | None) -> str | None:
    # Frontmatter cursors are full ISO timestamps ('2026-08-19T23:54:54Z'),
    # but stamps are minute-granular, so the press acknowledges its whole
    # minute -- otherwise a comment written seconds before the press stays
    # "pending" after it (the reported counter-not-clearing bug)
    return f"{cursor[:16]}:59" if cursor else None


@pure
def _new_message_flags(note: MarginNote, notified_cursor: str | None) -> list[bool]:
    # A message is "new" while it awaits a reaction: stamped after the last
    # notify press, in an open note, with no later message from someone else
    if notified_cursor is None or note.state != NoteState.OPEN:
        return [False] * len(note.messages)
    flags: list[bool] = []
    for idx, message in enumerate(note.messages):
        stamp_end = _normalize_stamp_end(message.stamp)
        is_after_notify = stamp_end is not None and stamp_end > notified_cursor
        is_responded = any(later.author != message.author for later in note.messages[idx + 1 :])
        flags.append(is_after_notify and not is_responded)
    return flags


@pure
def count_message_activity(document: SpecDocument) -> tuple[int, int]:
    """(pending_from_user, new_from_agent): new messages awaiting the other side."""
    notified_cursor = _normalize_cursor(
        document.frontmatter.notified_at if document.frontmatter is not None else None
    )
    pending_from_user = 0
    new_from_agent = 0
    for note in document.notes:
        for message, is_new in zip(note.messages, _new_message_flags(note, notified_cursor)):
            if not is_new:
                continue
            if message.author == _AGENT_AUTHOR_NAME:
                new_from_agent += 1
            else:
                pending_from_user += 1
    return pending_from_user, new_from_agent


@pure
def build_note_views(document: SpecDocument) -> list[dict[str, object]]:
    """Serialize margin notes into the JSON shape the frontend renders."""
    # breaks=True: a message renders inline-only (no structural markdown),
    # but its line breaks become <br> so multi-line comments keep their
    # shape -- a blank line reads as a paragraph gap (#t29)
    markdown_renderer = MarkdownIt("commonmark", {"breaks": True})
    notified_cursor = _normalize_cursor(
        document.frontmatter.notified_at if document.frontmatter is not None else None
    )
    note_views: list[dict[str, object]] = []
    for note in document.notes:
        opener_author = note.author if note.author is not None else (
            note.messages[0].author if note.messages else None
        )
        new_flags = _new_message_flags(note, notified_cursor)
        message_views = [
            {
                "author": message.author,
                "stamp": message.stamp,
                "ink": _ink_for_author(message.author),
                "html": markdown_renderer.renderInline(message.text),
                "isNew": is_new,
            }
            for message, is_new in zip(note.messages, new_flags)
        ]
        # an open suggestion with no discussion yet is new on its own stamp
        opener_is_new = (
            not note.messages
            and note.state == NoteState.OPEN
            and notified_cursor is not None
            and (_normalize_stamp_end(note.author_date) or "") > notified_cursor
        )
        body_html = (
            markdown_renderer.renderInline("\n".join(note.body_lines))
            if note.body_lines and not note.is_diff_body
            else None
        )
        note_views.append(
            {
                "id": note.note_id,
                "kind": note.kind.value.lower(),
                "ink": _ink_for_author(opener_author),
                "anchor": note.anchor.block_id,
                "quote": note.anchor.quote,
                "state": note.state.value.lower(),
                "stateDate": note.state_date,
                "author": note.author,
                "authorDate": note.author_date,
                "isDiff": note.is_diff_body,
                "diffLines": _build_diff_line_views(note.body_lines) if note.is_diff_body else [],
                "bodyHtml": body_html,
                "messages": message_views,
                "isThread": note.kind == NoteKind.THREAD,
                "isNew": any(new_flags) or opener_is_new,
            }
        )
    return note_views
