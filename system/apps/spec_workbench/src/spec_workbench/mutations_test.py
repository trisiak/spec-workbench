import pytest

from spec_workbench.data_types import NoteState
from spec_workbench.errors import AnchorNotFoundError
from spec_workbench.errors import DocumentChangedError
from spec_workbench.errors import HeadingNotFoundError
from spec_workbench.errors import NoteNotFoundError
from spec_workbench.errors import QuoteResolutionError
from spec_workbench.mutations import append_note_message
from spec_workbench.mutations import create_thread_block
from spec_workbench.mutations import ensure_block_anchor
from spec_workbench.mutations import ensure_heading_anchor
from spec_workbench.mutations import record_notification
from spec_workbench.mutations import resolve_unique_quote
from spec_workbench.mutations import set_note_state
from spec_workbench.parsing import parse_spec_document
from spec_workbench.testing import make_sample_document_text


def test_append_note_message_adds_attributed_dated_line_at_block_end() -> None:
    updated_text = append_note_message(
        document_text=make_sample_document_text(),
        note_id="t1",
        author="maciek",
        date="2026-08-15",
        message_text="sounds good",
    )

    document = parse_spec_document(updated_text)
    thread = document.notes[0]
    assert thread.messages[-1].author == "maciek"
    assert thread.messages[-1].stamp == "2026-08-15"
    assert thread.messages[-1].text == "sounds good"


def test_append_note_message_writes_multi_line_replies_as_continuation_lines() -> None:
    updated_text = append_note_message(
        document_text=make_sample_document_text(),
        note_id="t1",
        author="maciek",
        date="2026-08-15",
        message_text="line one\nline two",
    )

    assert "> **maciek (2026-08-15):** line one\n> line two" in updated_text
    document = parse_spec_document(updated_text)
    assert document.notes[0].messages[-1].text == "line one\nline two"


def test_append_note_message_leaves_the_rest_of_the_document_untouched() -> None:
    original_text = make_sample_document_text()
    updated_text = append_note_message(
        document_text=original_text,
        note_id="s2",
        author="agent",
        date="2026-08-15",
        message_text="noted",
    )

    original_lines = set(original_text.splitlines())
    updated_lines = set(updated_text.splitlines())
    assert original_lines.issubset(updated_lines)
    assert len(updated_lines - original_lines) == 1


def test_append_note_message_raises_for_unknown_note_id() -> None:
    with pytest.raises(NoteNotFoundError):
        append_note_message(
            document_text=make_sample_document_text(),
            note_id="t99",
            author="maciek",
            date="2026-08-15",
            message_text="hello",
        )


def test_set_note_state_resolves_an_open_thread_with_a_date() -> None:
    updated_text = set_note_state(
        document_text=make_sample_document_text(),
        note_id="t1",
        new_state=NoteState.RESOLVED,
        date="2026-08-15",
    )

    document = parse_spec_document(updated_text)
    assert document.notes[0].state == NoteState.RESOLVED
    assert document.notes[0].state_date == "2026-08-15"


def test_set_note_state_reopening_drops_the_state_date() -> None:
    resolved_text = set_note_state(
        document_text=make_sample_document_text(),
        note_id="t1",
        new_state=NoteState.RESOLVED,
        date="2026-08-15",
    )
    reopened_text = set_note_state(
        document_text=resolved_text,
        note_id="t1",
        new_state=NoteState.OPEN,
        date="2026-08-16",
    )

    document = parse_spec_document(reopened_text)
    assert document.notes[0].state == NoteState.OPEN
    assert document.notes[0].state_date is None


def test_set_note_state_preserves_anchor_and_quote_in_the_header() -> None:
    updated_text = set_note_state(
        document_text=make_sample_document_text(),
        note_id="s1",
        new_state=NoteState.ACCEPTED,
        date="2026-08-15",
    )

    assert '> [!suggest] #s1 on {#why} "beat chat" by agent (2026-08-14) -- accepted (2026-08-15)' in updated_text


def test_create_thread_block_inserts_an_open_thread_after_the_anchored_heading() -> None:
    updated_text = create_thread_block(
        document_text=make_sample_document_text(),
        anchor_block_id="features",
        quote=None,
        note_id="t2",
        author="maciek",
        date="2026-08-15",
        message_text="a fresh nit",
    )

    document = parse_spec_document(updated_text)
    new_thread = next(note for note in document.notes if note.note_id == "t2")
    assert new_thread.state == NoteState.OPEN
    assert new_thread.anchor.block_id == "features"
    assert new_thread.messages[0].author == "maciek"
    assert new_thread.messages[0].text == "a fresh nit"
    # the block sits immediately after the heading that carries the anchor
    lines = updated_text.splitlines()
    heading_idx = lines.index("## Features {#features}")
    assert lines[heading_idx + 2] == "> [!thread] #t2 on {#features} -- open"


def test_create_thread_block_writes_multi_line_comments_as_continuation_lines() -> None:
    updated_text = create_thread_block(
        document_text=make_sample_document_text(),
        anchor_block_id="why",
        quote=None,
        note_id="t2",
        author="maciek",
        date="2026-08-15",
        message_text="line one\nline two",
    )

    document = parse_spec_document(updated_text)
    new_thread = next(note for note in document.notes if note.note_id == "t2")
    assert new_thread.messages[0].text == "line one\nline two"


def test_create_thread_block_raises_for_unknown_anchor() -> None:
    with pytest.raises(AnchorNotFoundError):
        create_thread_block(
            document_text=make_sample_document_text(),
            anchor_block_id="no-such-block",
            quote=None,
            note_id="t2",
            author="maciek",
            date="2026-08-15",
            message_text="hello",
        )


def test_ensure_heading_anchor_mints_a_slug_for_an_anchorless_heading() -> None:
    updated_text, block_id = ensure_heading_anchor(
        document_text=make_sample_document_text(),
        heading_text="Sample App",
    )

    assert block_id == "sample-app"
    assert "# Sample App" in updated_text
    assert "{#sample-app}" in updated_text
    document = parse_spec_document(updated_text)
    assert document.frontmatter is not None


def test_ensure_heading_anchor_returns_the_existing_id_without_touching_the_text() -> None:
    original_text = make_sample_document_text()

    updated_text, block_id = ensure_heading_anchor(
        document_text=original_text,
        heading_text="Why",
    )

    assert block_id == "why"
    assert updated_text == original_text


def test_ensure_heading_anchor_finds_headings_with_status_suffixes() -> None:
    updated_text, block_id = ensure_heading_anchor(
        document_text=make_sample_document_text(),
        heading_text="F1. Render",
    )

    assert block_id == "f1"
    assert updated_text == make_sample_document_text()


def test_ensure_heading_anchor_avoids_colliding_with_existing_ids() -> None:
    document_text = "# Other {#sample-app}\n\n## Sample App\n"

    minted_text, minted_id = ensure_heading_anchor(
        document_text=document_text,
        heading_text="Sample App",
    )

    assert minted_id == "sample-app-2"
    assert "{#sample-app-2}" in minted_text


def test_resolve_unique_quote_returns_a_quote_that_is_already_unique() -> None:
    resolved_quote = resolve_unique_quote(
        block_markdown="Chat is linear and ephemeral, a document is spatial.",
        quote="linear and",
        context_before="Chat is",
        context_after="ephemeral, a document",
    )

    assert resolved_quote == "linear and"


def test_resolve_unique_quote_extends_an_ambiguous_quote_with_real_neighbors() -> None:
    resolved_quote = resolve_unique_quote(
        block_markdown="the quick fox and the lazy dog",
        quote="the",
        context_before="",
        context_after="quick fox",
    )

    assert resolved_quote == "the quick"


def test_resolve_unique_quote_matches_across_markdown_inline_marks() -> None:
    resolved_quote = resolve_unique_quote(
        block_markdown="uses `code` and **bold** words",
        quote="code and bold",
        context_before="uses",
        context_after="words",
    )

    assert resolved_quote == "code and bold"


def test_resolve_unique_quote_raises_when_the_text_is_not_in_the_block() -> None:
    with pytest.raises(QuoteResolutionError):
        resolve_unique_quote(
            block_markdown="some block text",
            quote="absent phrase",
            context_before="",
            context_after="",
        )


def test_ensure_block_anchor_mints_an_id_on_a_plain_paragraph() -> None:
    sample_lines = make_sample_document_text().splitlines()
    paragraph_line_idx = sample_lines.index("Because documents beat chat.")

    updated_text, block_id = ensure_block_anchor(
        document_text=make_sample_document_text(),
        start_line_idx=paragraph_line_idx,
        end_line_idx=paragraph_line_idx,
        block_text_prefix="Because documents beat chat.",
    )

    assert block_id == "because-documents-beat-chat"
    assert "Because documents beat chat. {#because-documents-beat-chat}" in updated_text


def test_ensure_block_anchor_returns_an_existing_heading_id_untouched() -> None:
    sample_lines = make_sample_document_text().splitlines()
    heading_line_idx = sample_lines.index("## Why {#why}")

    updated_text, block_id = ensure_block_anchor(
        document_text=make_sample_document_text(),
        start_line_idx=heading_line_idx,
        end_line_idx=heading_line_idx,
        block_text_prefix="Why",
    )

    assert block_id == "why"
    assert updated_text == make_sample_document_text()


def test_ensure_block_anchor_accepts_a_prefix_missing_badge_rendered_marks() -> None:
    # The page shows story marks and heading statuses as badges, so the
    # caller's block text excludes them -- the guard must not misfire
    document_text = "## Why {#why}\n\n- `done` shipped the thing already (#t6)\n"

    updated_text, block_id = ensure_block_anchor(
        document_text=document_text,
        start_line_idx=2,
        end_line_idx=2,
        block_text_prefix="shipped the thing already",
    )

    assert "shipped the thing already (#t6) {#" in updated_text
    assert block_id.startswith("shipped-the-thing")


def test_ensure_block_anchor_accepts_a_heading_prefix_missing_its_status_badge() -> None:
    # the page excludes badge content, so the caller's heading text carries
    # neither the "--" nor the status word
    document_text = "### F9. Future thing -- `planned`\n"

    updated_text, block_id = ensure_block_anchor(
        document_text=document_text,
        start_line_idx=0,
        end_line_idx=0,
        block_text_prefix="F9. Future thing",
    )

    assert block_id.startswith("f9-future-thing")
    assert "{#" + block_id + "}" in updated_text


def test_ensure_block_anchor_rejects_a_shifted_document() -> None:
    sample_lines = make_sample_document_text().splitlines()
    paragraph_line_idx = sample_lines.index("Because documents beat chat.")

    with pytest.raises(DocumentChangedError):
        ensure_block_anchor(
            document_text=make_sample_document_text(),
            start_line_idx=paragraph_line_idx,
            end_line_idx=paragraph_line_idx,
            block_text_prefix="totally different words here",
        )


def test_ensure_heading_anchor_raises_for_unknown_heading() -> None:
    with pytest.raises(HeadingNotFoundError):
        ensure_heading_anchor(
            document_text=make_sample_document_text(),
            heading_text="No Such Section",
        )


def test_set_note_state_raises_for_unknown_note_id() -> None:
    with pytest.raises(NoteNotFoundError):
        set_note_state(
            document_text=make_sample_document_text(),
            note_id="s99",
            new_state=NoteState.RESOLVED,
            date="2026-08-15",
        )


def test_record_notification_increments_an_existing_stamp() -> None:
    document_text = make_sample_document_text().replace(
        "status: drafting\n", "status: drafting\nnotified: v3 (2026-08-14T09:00:00Z)\n"
    )

    updated_text, new_version = record_notification(document_text, "2026-08-19T10:00:00Z")

    assert new_version == 4
    assert "notified: v4 (2026-08-19T10:00:00Z)" in updated_text
    assert "notified: v3" not in updated_text


def test_record_notification_adds_the_stamp_to_existing_frontmatter() -> None:
    updated_text, new_version = record_notification(make_sample_document_text(), "2026-08-19T10:00:00Z")

    assert new_version == 1
    parsed = parse_spec_document(updated_text)
    assert parsed.frontmatter is not None
    assert parsed.frontmatter.notified_version == 1
    assert parsed.frontmatter.notified_at == "2026-08-19T10:00:00Z"
    assert parsed.frontmatter.app_name == "sample-app"


def test_record_notification_creates_frontmatter_on_a_plain_file() -> None:
    updated_text, new_version = record_notification("# Plain\n\nProse.\n", "2026-08-19T10:00:00Z")

    assert new_version == 1
    parsed = parse_spec_document(updated_text)
    assert parsed.frontmatter is not None and parsed.frontmatter.notified_version == 1
    assert "# Plain" in parsed.prose_markdown


def test_ensure_block_anchor_pulls_an_overshot_range_back_onto_the_text() -> None:
    # a stale client range ending on a blank or note line must not plant
    # the anchor there (#t20: a stranded {#id} renders as literal text)
    document_text = (
        "Some paragraph here.\n"
        "\n"
        "> [!thread] #t1 on {#x} -- open\n"
        "> **maciek (2026-08-19):** y\n"
    )

    updated_text, block_id = ensure_block_anchor(
        document_text=document_text,
        start_line_idx=0,
        end_line_idx=2,
        block_text_prefix="Some paragraph here.",
    )

    assert updated_text.splitlines()[0] == f"Some paragraph here. {{#{block_id}}}"
    assert updated_text.splitlines()[1] == ""
