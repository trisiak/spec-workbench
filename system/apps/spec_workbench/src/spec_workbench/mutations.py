import re
from typing import Final
from typing import assert_never

from imbue.imbue_common.pure import pure

from spec_workbench.data_types import NoteState
from spec_workbench.errors import AnchorNotFoundError
from spec_workbench.errors import DocumentChangedError
from spec_workbench.errors import HeadingNotFoundError
from spec_workbench.errors import NoteNotFoundError
from spec_workbench.errors import QuoteResolutionError
from spec_workbench.parsing import NOTIFIED_VALUE_RE
from spec_workbench.parsing import TRAILING_ID_RE

_STATE_SUFFIX_RE: Final[re.Pattern[str]] = re.compile(
    r" -- (open|resolved|accepted|rejected)( \([^)]*\))?\s*$"
)

_HEADING_PARTS_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<hashes>#{1,6}) (?P<title>.+?)"
    r"(?P<status> -- `(?:idea|planned|building|done|verified)`)?"
    r"(?:\s*\{#(?P<block_id>[A-Za-z0-9_-]+)\})?\s*$"
)

_BLOCK_ID_RE: Final[re.Pattern[str]] = re.compile(r"\{#([A-Za-z0-9_-]+)\}")

# Column where existing headings park their {#id} suffix
_ANCHOR_ALIGN_COLUMN: Final[int] = 61


@pure
def _slugify_heading_title(heading_title: str) -> str:
    lowered = heading_title.lower()
    dashed = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return dashed if dashed else "section"


@pure
def ensure_heading_anchor(document_text: str, heading_text: str) -> tuple[str, str]:
    """Return (document_text, block_id) for the titled heading, minting and writing the id if absent."""
    lines = document_text.splitlines()
    existing_block_ids = set(_BLOCK_ID_RE.findall(document_text))
    for idx, line in enumerate(lines):
        if line.startswith(">"):
            continue
        heading_match = _HEADING_PARTS_RE.match(line)
        if heading_match is None or heading_match.group("title") != heading_text:
            continue
        existing_id = heading_match.group("block_id")
        if existing_id is not None:
            return document_text, existing_id

        # Mint a unique slug and append it, aligned like the other headings
        base_slug = _slugify_heading_title(heading_text)
        slug = base_slug
        suffix_number = 2
        while slug in existing_block_ids:
            slug = f"{base_slug}-{suffix_number}"
            suffix_number += 1
        padding = max(1, _ANCHOR_ALIGN_COLUMN - len(line))
        updated_lines = lines[:idx] + [f"{line}{' ' * padding}{{#{slug}}}"] + lines[idx + 1 :]
        trailing_newline = "\n" if document_text.endswith("\n") else ""
        return "\n".join(updated_lines) + trailing_newline, slug
    raise HeadingNotFoundError(heading_text)


@pure
def _find_note_block_line_range(lines: list[str], note_id: str) -> tuple[int, int]:
    """Return (header_idx, end_idx) where end_idx is one past the block's last line."""
    header_prefix_re = re.compile(rf"^> \[!(thread|suggest)\] #{re.escape(note_id)}\b")
    for idx, line in enumerate(lines):
        if header_prefix_re.match(line) is None:
            continue
        end_idx = idx + 1
        while end_idx < len(lines) and lines[end_idx].startswith(">"):
            end_idx += 1
        return idx, end_idx
    raise NoteNotFoundError(note_id)


@pure
def append_note_message(
    document_text: str,
    note_id: str,
    author: str,
    date: str,
    message_text: str,
) -> str:
    """Append an attributed, dated message to a note block, preserving the rest of the file byte-for-byte."""
    lines = document_text.splitlines()
    _, block_end_idx = _find_note_block_line_range(lines, note_id)

    # First message line carries the attribution; further lines continue the quote block
    message_lines = message_text.strip().splitlines() or [""]
    new_lines = [f"> **{author} ({date}):** {message_lines[0]}"]
    for continuation_line in message_lines[1:]:
        new_lines.append(f"> {continuation_line}")

    updated_lines = lines[:block_end_idx] + new_lines + lines[block_end_idx:]
    trailing_newline = "\n" if document_text.endswith("\n") else ""
    return "\n".join(updated_lines) + trailing_newline


@pure
def create_thread_block(
    document_text: str,
    anchor_block_id: str,
    quote: str | None,
    note_id: str,
    author: str,
    date: str,
    message_text: str,
) -> str:
    """Insert a new open thread block immediately after the block carrying the anchor id."""
    anchor_line_re = re.compile(rf"^(?!>).*\{{#{re.escape(anchor_block_id)}\}}\s*$")
    lines = document_text.splitlines()
    anchor_idx = next(
        (idx for idx, line in enumerate(lines) if anchor_line_re.match(line) is not None),
        None,
    )
    if anchor_idx is None:
        raise AnchorNotFoundError(anchor_block_id)

    quote_part = f' "{quote}"' if quote is not None else ""
    message_lines = message_text.strip().splitlines() or [""]
    block_lines = [
        "",
        f"> [!thread] #{note_id} on {{#{anchor_block_id}}}{quote_part} -- open",
        f"> **{author} ({date}):** {message_lines[0]}",
    ]
    for continuation_line in message_lines[1:]:
        block_lines.append(f"> {continuation_line}")

    updated_lines = lines[: anchor_idx + 1] + block_lines + lines[anchor_idx + 1 :]
    trailing_newline = "\n" if document_text.endswith("\n") else ""
    return "\n".join(updated_lines) + trailing_newline


@pure
def normalize_to_plain_text(markdown_text: str) -> str:
    """Approximate a markdown fragment's rendered text: links to their labels, marks dropped, whitespace collapsed."""
    without_links = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", markdown_text)
    without_marks = re.sub(r"[`*_]", "", without_links)
    return re.sub(r"\s+", " ", without_marks).strip()


@pure
def _build_flexible_quote_pattern(quote_text: str) -> re.Pattern[str]:
    escaped_words = [re.escape(word) for word in quote_text.split()]
    return re.compile(r"\s+".join(escaped_words))


@pure
def _count_quote_occurrences(block_plain_text: str, quote_text: str) -> int:
    if not quote_text:
        return 0
    return len(_build_flexible_quote_pattern(quote_text).findall(block_plain_text))


@pure
def resolve_unique_quote(
    block_markdown: str,
    quote: str,
    # words immediately before/after the selection, used to extend an ambiguous quote
    context_before: str,
    context_after: str,
) -> str:
    """Return a quote unique within the block, extending with real neighboring words when ambiguous."""
    block_plain_text = normalize_to_plain_text(block_markdown)
    normalized_quote = re.sub(r"\s+", " ", quote).strip()
    occurrence_count = _count_quote_occurrences(block_plain_text, normalized_quote)
    if occurrence_count == 1:
        return normalized_quote
    if occurrence_count == 0:
        raise QuoteResolutionError(f"Selected text not found in its block: '{normalized_quote}'")

    # Extend outward word by word -- after first, then before -- until unique
    before_words = normalize_to_plain_text(context_before).split()
    after_words = normalize_to_plain_text(context_after).split()
    extended_quote = normalized_quote
    for step_idx in range(len(before_words) + len(after_words)):
        if step_idx < len(after_words):
            extended_quote = f"{extended_quote} {after_words[step_idx]}"
        else:
            before_idx = len(before_words) - 1 - (step_idx - len(after_words))
            extended_quote = f"{before_words[before_idx]} {extended_quote}"
        if _count_quote_occurrences(block_plain_text, extended_quote) == 1:
            return extended_quote
    raise QuoteResolutionError(f"Selected text is ambiguous within its block: '{normalized_quote}'")


@pure
def _mint_unique_slug(base_text: str, existing_block_ids: set[str]) -> str:
    base_slug = _slugify_heading_title(" ".join(normalize_to_plain_text(base_text).split()[:4]))
    slug = base_slug
    suffix_number = 2
    while slug in existing_block_ids:
        slug = f"{base_slug}-{suffix_number}"
        suffix_number += 1
    return slug


@pure
def ensure_block_anchor(
    document_text: str,
    start_line_idx: int,
    end_line_idx: int,
    # the block's leading rendered text, used to detect a shifted document
    block_text_prefix: str,
) -> tuple[str, str]:
    """Return (document_text, block_id) for the block at the given lines, minting the id if absent."""
    lines = document_text.splitlines()
    is_range_valid = 0 <= start_line_idx <= end_line_idx < len(lines)
    if not is_range_valid:
        raise DocumentChangedError(f"Block lines {start_line_idx}-{end_line_idx} are out of range")

    # Belt-and-braces against a client whose range overshoots: the anchor
    # must land on the block's own text, never a blank or a note line
    while end_line_idx > start_line_idx and (
        not lines[end_line_idx].strip() or lines[end_line_idx].lstrip().startswith(">")
    ):
        end_line_idx -= 1

    # Guard against a document that shifted since the caller rendered it
    block_source = "\n".join(lines[start_line_idx : end_line_idx + 1])
    id_stripped_match = TRAILING_ID_RE.match(block_source)
    comparable_source = id_stripped_match.group("rest") if id_stripped_match is not None else block_source
    # Rendered text carries no heading hashes or list markers -- drop them
    # before comparing, along with everything the renderer turns into badges
    # (story marks opening a list item, status suffixes on headings), since
    # the caller's text excludes badge content
    comparable_source_without_markers = re.sub(r"^(#{1,6} |[-*] )", "", comparable_source)
    without_story_mark = re.sub(r"^`(done|open)`\s+", "", comparable_source_without_markers)
    without_status_suffix = re.sub(
        r"\s*--\s*`(idea|planned|building|done|verified)`\s*$", "", without_story_mark
    )
    source_words = normalize_to_plain_text(without_status_suffix).split()
    prefix_words = normalize_to_plain_text(block_text_prefix).split()[:4]
    if not prefix_words or source_words[: len(prefix_words)] != prefix_words:
        raise DocumentChangedError("The document changed since the page was rendered; reload and retry")

    last_line_match = TRAILING_ID_RE.match(lines[end_line_idx])
    if last_line_match is not None:
        return document_text, last_line_match.group("block_id")

    # Mint a new id: headings reuse their aligned style, other blocks get a plain suffix
    existing_block_ids = set(_BLOCK_ID_RE.findall(document_text))
    heading_match = _HEADING_PARTS_RE.match(lines[start_line_idx])
    is_heading_block = heading_match is not None and start_line_idx == end_line_idx
    if is_heading_block and heading_match is not None:
        slug = _mint_unique_slug(heading_match.group("title"), existing_block_ids)
        padding = max(1, _ANCHOR_ALIGN_COLUMN - len(lines[end_line_idx]))
        updated_line = f"{lines[end_line_idx]}{' ' * padding}{{#{slug}}}"
    else:
        # slug from the decoration-stripped text so marks don't leak into ids
        slug = _mint_unique_slug(without_status_suffix, existing_block_ids)
        updated_line = f"{lines[end_line_idx]} {{#{slug}}}"
    updated_lines = lines[:end_line_idx] + [updated_line] + lines[end_line_idx + 1 :]
    trailing_newline = "\n" if document_text.endswith("\n") else ""
    return "\n".join(updated_lines) + trailing_newline, slug


@pure
def record_notification(document_text: str, timestamp: str) -> tuple[str, int]:
    """Bump the frontmatter's 'notified: vN (timestamp)' stamp; returns (text, new version).

    Creates the frontmatter block when a plain markdown file has none, so
    the notify button works on any document the app can open.
    """
    lines = document_text.splitlines()
    has_frontmatter = bool(lines) and lines[0].strip() == "---"
    if not has_frontmatter:
        new_lines = ["---", f"notified: v1 ({timestamp})", "---", ""] + lines
        trailing_newline = "\n" if document_text.endswith("\n") or not document_text else ""
        return "\n".join(new_lines) + trailing_newline, 1

    closing_idx = next(
        (idx for idx in range(1, len(lines)) if lines[idx].strip() == "---"), None
    )
    if closing_idx is None:
        # an opening fence with no close is not frontmatter; treat as plain
        new_lines = ["---", f"notified: v1 ({timestamp})", "---", ""] + lines
        trailing_newline = "\n" if document_text.endswith("\n") else ""
        return "\n".join(new_lines) + trailing_newline, 1

    next_version = 1
    notified_line_idx = None
    for idx in range(1, closing_idx):
        key, _, raw_value = lines[idx].partition(":")
        if key.strip() != "notified":
            continue
        notified_line_idx = idx
        value_match = NOTIFIED_VALUE_RE.match(raw_value.split("#", 1)[0].strip())
        if value_match is not None:
            next_version = int(value_match.group("version")) + 1
        break

    notified_line = f"notified: v{next_version} ({timestamp})"
    if notified_line_idx is not None:
        updated_lines = lines[:notified_line_idx] + [notified_line] + lines[notified_line_idx + 1 :]
    else:
        updated_lines = lines[:closing_idx] + [notified_line] + lines[closing_idx:]
    trailing_newline = "\n" if document_text.endswith("\n") else ""
    return "\n".join(updated_lines) + trailing_newline, next_version


@pure
def set_note_state(
    document_text: str,
    note_id: str,
    new_state: NoteState,
    date: str,
) -> str:
    """Rewrite a note's state suffix; terminal states carry the date, reopening drops it."""
    match new_state:
        case NoteState.OPEN:
            new_suffix = " -- open"
        case NoteState.RESOLVED:
            new_suffix = f" -- resolved ({date})"
        case NoteState.ACCEPTED:
            new_suffix = f" -- accepted ({date})"
        case NoteState.REJECTED:
            new_suffix = f" -- rejected ({date})"
        case _ as unreachable:
            assert_never(unreachable)

    lines = document_text.splitlines()
    header_idx, _ = _find_note_block_line_range(lines, note_id)
    updated_header = _STATE_SUFFIX_RE.sub(new_suffix, lines[header_idx])
    updated_lines = lines[:header_idx] + [updated_header] + lines[header_idx + 1 :]
    trailing_newline = "\n" if document_text.endswith("\n") else ""
    return "\n".join(updated_lines) + trailing_newline
