import re
from typing import Final

from imbue.imbue_common.model_update import to_update
from imbue.imbue_common.pure import pure

from spec_workbench.data_types import MarginNote
from spec_workbench.data_types import NoteAnchor
from spec_workbench.data_types import NoteKind
from spec_workbench.data_types import NoteMessage
from spec_workbench.data_types import NoteState
from spec_workbench.data_types import SpecDocument
from spec_workbench.data_types import SpecFrontmatter

# The quote group is greedy (.*) rather than [^"]*: a quoted phrase may
# itself contain quotation marks (e.g. selecting '"Notify agent" button'),
# and the tail-anchored ' -- state' plus backtracking find its real end
NOTE_HEADER_RE: Final[re.Pattern[str]] = re.compile(
    r"^> \[!(?P<kind>thread|suggest)\] #(?P<note_id>[a-z]\d+)"
    r"(?: on \{#(?P<block_id>[A-Za-z0-9_-]+)\}(?: \"(?P<quote>.*)\")?)?"
    r"(?: by (?P<author>\S+) \((?P<author_date>[^)]*)\))?"
    r" -- (?P<state>open|resolved|accepted|rejected)(?: \((?P<state_date>[^)]*)\))?\s*$"
)

MESSAGE_START_RE: Final[re.Pattern[str]] = re.compile(
    r"^\*\*(?P<author>[^*(]+?) \((?P<stamp>[^)]*)\):\*\* (?P<text>.*)$"
)

# A line whose block carries a trailing {#id} anchor
TRAILING_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<rest>.*\S)\s*\{#(?P<block_id>[A-Za-z0-9_-]+)\}\s*$"
)

_FRONTMATTER_DELIMITER: Final[str] = "---"

# The notify button's frontmatter stamp: "notified: v3 (2026-08-19T01:02:03Z)"
NOTIFIED_VALUE_RE: Final[re.Pattern[str]] = re.compile(
    r"^v(?P<version>\d+) \((?P<timestamp>[^)]+)\)$"
)

_KIND_BY_MARKER: Final[dict[str, NoteKind]] = {
    "thread": NoteKind.THREAD,
    "suggest": NoteKind.SUGGESTION,
}

_DIFF_FENCE: Final[str] = "```diff"


@pure
def _strip_frontmatter_comment(raw_value: str) -> str:
    return raw_value.split("#", 1)[0].strip()


@pure
def _parse_frontmatter_lines(frontmatter_lines: list[str]) -> SpecFrontmatter:
    value_by_key: dict[str, str] = {}
    for line in frontmatter_lines:
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        value_by_key[key.strip()] = _strip_frontmatter_comment(raw_value)
    notified_match = NOTIFIED_VALUE_RE.match(value_by_key.get("notified", ""))
    return SpecFrontmatter(
        app_name=value_by_key.get("app"),
        status=value_by_key.get("status"),
        agent_seen=value_by_key.get("agent-seen"),
        notified_version=int(notified_match.group("version")) if notified_match else None,
        notified_at=notified_match.group("timestamp") if notified_match else None,
        notify_agent=value_by_key.get("notify-agent") or None,
    )


@pure
def _parse_note_block(header_match: re.Match[str], block_lines: list[str]) -> MarginNote:
    # Body lines (before any message) and messages both live in the quoted
    # block; a message starts with a bold attribution and owns every
    # following line until the next attribution.
    body_lines: list[str] = []
    messages: list[NoteMessage] = []
    current_message: NoteMessage | None = None
    for line in block_lines:
        content = line[2:] if line.startswith("> ") else line[1:]
        message_match = MESSAGE_START_RE.match(content)
        if message_match is not None:
            if current_message is not None:
                messages.append(current_message)
            current_message = NoteMessage(
                author=message_match.group("author").strip(),
                stamp=message_match.group("stamp") or None,
                text=message_match.group("text"),
            )
        elif current_message is not None:
            current_message = current_message.model_copy_update(
                to_update(current_message.field_ref().text, current_message.text + "\n" + content),
            )
        else:
            body_lines.append(content)
    if current_message is not None:
        messages.append(current_message)

    # Trim leading/trailing blank body lines so an empty body stays empty
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()

    is_diff_body = any(line.strip().startswith(_DIFF_FENCE) for line in body_lines)
    return MarginNote(
        note_id=header_match.group("note_id"),
        kind=_KIND_BY_MARKER[header_match.group("kind")],
        anchor=NoteAnchor(
            block_id=header_match.group("block_id"),
            quote=header_match.group("quote"),
        ),
        state=NoteState(header_match.group("state").upper()),
        state_date=header_match.group("state_date"),
        author=header_match.group("author"),
        author_date=header_match.group("author_date"),
        body_lines=tuple(body_lines),
        is_diff_body=is_diff_body,
        messages=tuple(messages),
    )


@pure
def parse_spec_document(document_text: str) -> SpecDocument:
    """Parse a spec file into frontmatter, prose markdown, and margin notes."""
    lines = document_text.splitlines()

    # Split off frontmatter when the document opens with a --- fence
    frontmatter: SpecFrontmatter | None = None
    body_start_idx = 0
    if lines and lines[0].strip() == _FRONTMATTER_DELIMITER:
        for idx in range(1, len(lines)):
            if lines[idx].strip() == _FRONTMATTER_DELIMITER:
                frontmatter = _parse_frontmatter_lines(lines[1:idx])
                body_start_idx = idx + 1
                break

    # Lift note blocks out of the prose flow, remembering where each prose
    # line lives in the source file (the selection API works in file lines)
    prose_lines: list[str] = []
    prose_file_line_numbers: list[int] = []
    notes: list[MarginNote] = []
    idx = body_start_idx
    while idx < len(lines):
        header_match = NOTE_HEADER_RE.match(lines[idx])
        if header_match is None:
            prose_lines.append(lines[idx])
            prose_file_line_numbers.append(idx)
            idx += 1
            continue
        block_end_idx = idx + 1
        while block_end_idx < len(lines) and lines[block_end_idx].startswith(">"):
            block_end_idx += 1
        notes.append(_parse_note_block(header_match, lines[idx + 1 : block_end_idx]))
        idx = block_end_idx

    return SpecDocument(
        frontmatter=frontmatter,
        prose_markdown="\n".join(prose_lines) + "\n",
        prose_file_line_numbers=tuple(prose_file_line_numbers),
        notes=tuple(notes),
    )
