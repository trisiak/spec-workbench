from spec_workbench.parsing import parse_spec_document
from spec_workbench.rendering import build_note_views
from spec_workbench.rendering import collect_agent_author_names
from spec_workbench.rendering import render_prose_html
from spec_workbench.testing import make_sample_document_text


def test_render_prose_html_carries_heading_ids_onto_elements() -> None:
    document = parse_spec_document(make_sample_document_text())

    rendered_html = render_prose_html(document.prose_markdown, document.prose_file_line_numbers)

    assert 'id="why"' in rendered_html
    assert 'id="f1"' in rendered_html
    assert "{#why}" not in rendered_html


def test_render_prose_html_leaves_headings_without_ids_unchanged() -> None:
    rendered_html = render_prose_html("# Plain Title\n\n## Also Plain\n", (0, 1, 2))

    assert "Plain Title</h1>" in rendered_html
    assert 'id="' not in rendered_html


def test_render_prose_html_stamps_blocks_with_their_source_file_lines() -> None:
    document = parse_spec_document(make_sample_document_text())
    file_lines = make_sample_document_text().splitlines()
    paragraph_file_line = file_lines.index("Because documents beat chat.")

    rendered_html = render_prose_html(document.prose_markdown, document.prose_file_line_numbers)

    assert f'data-sline="{paragraph_file_line}" data-eline="{paragraph_file_line}"' in rendered_html


def test_render_prose_html_renders_tables() -> None:
    rendered_html = render_prose_html("| a | b |\n|---|---|\n| 1 | 2 |\n", (0, 1, 2))

    assert "<table>" in rendered_html
    assert "<td>1</td>" in rendered_html


def test_render_prose_html_turns_story_marks_into_badges() -> None:
    rendered_html = render_prose_html(
        "- `done` shipped thing\n- `open` pending thing\n- `planned` next thing\n- `idea` parked thing\n",
        (0, 1, 2, 3),
    )

    assert '<span class="badge done">done</span>' in rendered_html
    assert '<span class="badge open">open</span>' in rendered_html
    assert '<span class="badge planned">planned</span>' in rendered_html
    assert '<span class="badge idea">idea</span>' in rendered_html
    assert "<code>done</code>" not in rendered_html


def test_render_prose_html_leaves_mid_sentence_code_words_alone() -> None:
    rendered_html = render_prose_html("States are `open` or `resolved` in the format.\n", (0,))

    assert "<code>open</code>" in rendered_html
    assert 'badge open' not in rendered_html


def test_render_prose_html_turns_heading_status_codes_into_badges() -> None:
    document = parse_spec_document(make_sample_document_text())

    rendered_html = render_prose_html(document.prose_markdown, document.prose_file_line_numbers)

    assert '<span class="badge building">building</span>' in rendered_html
    assert "<code>building</code>" not in rendered_html


def test_build_note_views_keeps_message_line_breaks() -> None:
    document = parse_spec_document(
        "# Doc\n"
        "\n"
        "A block. {#b}\n"
        "\n"
        "> [!thread] #t1 on {#b} -- open\n"
        "> **maciek (2026-08-24 17:00):** first line\n"
        "> second line\n"
        ">\n"
        "> a paragraph after a blank line\n"
    )

    note_views = build_note_views(document, "maciek")

    message_html = note_views[0]["messages"][0]["html"]
    # line breaks survive as <br> (a blank line reads as a paragraph gap);
    # no structural markdown is introduced
    assert "first line<br" in message_html
    assert "second line<br" in message_html
    assert "<p" not in message_html and "<ul" not in message_html


def test_build_note_views_assigns_inks_by_opening_author() -> None:
    document = parse_spec_document(make_sample_document_text())

    note_views = build_note_views(document, "maciek")

    ink_by_id = {view["id"]: view["ink"] for view in note_views}
    # t1 opened by maciek (pen), s1 authored by agent (pencil), s2 by maciek (pen)
    assert ink_by_id == {"t1": "pen", "s1": "pencil", "s2": "pen"}


def test_ink_is_role_not_name_so_named_agents_render_pencil() -> None:
    # an agent signing with its Mind's logical name must not borrow the
    # human's ink -- pen is reserved for the configured author (#t33)
    document = parse_spec_document(
        "A block. {#b}\n"
        "\n"
        "> [!thread] #t1 on {#b} -- open\n"
        "> **maciek (2026-08-24 17:00):** question\n"
        "> **meta-markdown (2026-08-24 17:05):** answer under a logical name\n"
        "> **user (2026-08-24 17:06):** unconfigured-workspace human\n"
    )

    note_views = build_note_views(document, "maciek")

    inks = [m["ink"] for m in note_views[0]["messages"]]
    assert inks == ["pen", "pencil", "pen"]
    assert collect_agent_author_names(document, "maciek") == ["meta-markdown"]


def test_build_note_views_renders_diff_bodies_as_typed_lines() -> None:
    document = parse_spec_document(make_sample_document_text())

    note_views = build_note_views(document, "maciek")
    diff_view = next(view for view in note_views if view["id"] == "s2")

    assert diff_view["isDiff"] is True
    diff_ops = [line["op"] for line in diff_view["diffLines"]]
    assert diff_ops == ["del", "add"]


def test_build_note_views_renders_message_markdown_inline() -> None:
    document = parse_spec_document("> [!thread] #t1 on {#x} -- open\n> **agent (2026-08-14):** uses `code` here\n")

    note_views = build_note_views(document, "maciek")

    assert "<code>code</code>" in str(note_views[0]["messages"][0]["html"])


def test_list_item_line_ranges_stop_at_their_own_text() -> None:
    # markdown-it maps loose list items through trailing blank lines; once
    # notes are lifted out, an untrimmed end line would point past the list
    # -- across the note block -- and anchors would land on the wrong line
    document = parse_spec_document(
        "## L {#l}\n"
        "\n"
        "- first bullet\n"
        "- second bullet spans\n"
        "  two lines\n"
        "\n"
        "> [!thread] #t1 on {#l} -- open\n"
        "> **maciek (2026-08-19):** x\n"
        "\n"
        "### Next\n"
    )

    html = render_prose_html(document.prose_markdown, document.prose_file_line_numbers)

    assert 'data-sline="3" data-eline="4"' in html  # the bullet's own two lines
