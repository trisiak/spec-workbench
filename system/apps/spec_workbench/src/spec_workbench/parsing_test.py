from spec_workbench.data_types import NoteKind
from spec_workbench.data_types import NoteState
from spec_workbench.parsing import parse_spec_document
from spec_workbench.testing import make_sample_document_text


def test_parse_spec_document_reads_frontmatter_values_and_strips_comments() -> None:
    document = parse_spec_document(make_sample_document_text())

    assert document.frontmatter is not None
    assert document.frontmatter.app_name == "sample-app"
    assert document.frontmatter.status == "drafting"
    assert document.frontmatter.agent_seen == "2026-08-14T00:00:00Z"


def test_parse_spec_document_lifts_note_blocks_out_of_the_prose() -> None:
    document = parse_spec_document(make_sample_document_text())

    assert [note.note_id for note in document.notes] == ["t1", "s1", "s2"]
    assert "[!thread]" not in document.prose_markdown
    assert "[!suggest]" not in document.prose_markdown
    assert "Because documents beat chat." in document.prose_markdown
    assert "Closing prose." in document.prose_markdown


def test_parse_spec_document_joins_message_continuation_lines() -> None:
    document = parse_spec_document(make_sample_document_text())

    thread = document.notes[0]
    assert thread.kind == NoteKind.THREAD
    assert len(thread.messages) == 2
    assert thread.messages[0].author == "maciek"
    assert thread.messages[0].text == "first line\nsecond line of the same message"
    assert thread.messages[1].stamp == "2026-08-14, via chat"


def test_parse_spec_document_reads_phrase_form_suggestion_with_quote_anchor() -> None:
    document = parse_spec_document(make_sample_document_text())

    phrase_suggestion = document.notes[1]
    assert phrase_suggestion.kind == NoteKind.SUGGESTION
    assert phrase_suggestion.anchor.block_id == "why"
    assert phrase_suggestion.anchor.quote == "beat chat"
    assert phrase_suggestion.author == "agent"
    assert phrase_suggestion.is_diff_body is False
    assert phrase_suggestion.body_lines == ("beat linear chat",)


def test_parse_spec_document_reads_diff_form_suggestion_with_terminal_state() -> None:
    document = parse_spec_document(make_sample_document_text())

    diff_suggestion = document.notes[2]
    assert diff_suggestion.state == NoteState.REJECTED
    assert diff_suggestion.state_date == "2026-08-15"
    assert diff_suggestion.is_diff_body is True
    assert "-Render" in diff_suggestion.body_lines
    assert "+Render nicely" in diff_suggestion.body_lines


def test_parse_spec_document_without_frontmatter_returns_none_frontmatter() -> None:
    document = parse_spec_document("# Title\n\nJust prose.\n")

    assert document.frontmatter is None
    assert document.notes == ()
    assert "Just prose." in document.prose_markdown


def test_parse_spec_document_on_empty_text_returns_empty_document() -> None:
    document = parse_spec_document("")

    assert document.frontmatter is None
    assert document.notes == ()


def test_header_quote_may_itself_contain_quotation_marks() -> None:
    # selecting text like '"Notify agent" button' embeds quotes in the header
    document_text = (
        "## F4 {#f4}\n"
        "\n"
        '> [!thread] #t9 on {#f4} ""Notify agent" button" -- open\n'
        "> **maciek (2026-08-19):** the header above must still parse\n"
    )

    document = parse_spec_document(document_text)

    assert len(document.notes) == 1
    note = document.notes[0]
    assert note.anchor.block_id == "f4"
    assert note.anchor.quote == '"Notify agent" button'
    assert note.state == NoteState.OPEN
