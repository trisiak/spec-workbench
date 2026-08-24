"""End-to-end tests driving spec-workbench inside a workspace-style sandboxed iframe.

Each behavior here was first a user-reported bug (or the fix for one) that
did not reproduce outside the sandboxed frame: suppressed confirm dialogs,
fold state resetting on every post, the page reloading out from under the
reader. They are codified against the same embedding the workspace shell
uses, so a regression fails a test instead of waiting for a report.

Requires a chromium (Playwright-managed in CI, Fortress locally); the
e2e_browser fixture skips these cleanly when neither is present. See
conftest.py for the harness.
"""

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.acceptance, pytest.mark.timeout(120)]

# posting/resolving must never navigate; this marker only survives in-place updates
_MARKER_JS = "window.__no_reload_marker = 'alive'"
_MARKER_READ_JS = "window.__no_reload_marker"


def _select_phrase(frame, block_selector: str, phrase: str) -> None:
    """Select a phrase inside a prose block and fire the mouseup the app listens for.

    Headless chromium's dblclick does not produce a text selection here, so
    the selection itself is scripted; the later click on the floating Comment
    button stays a real click (that is where focus semantics matter).
    """
    frame.eval_on_selector(
        block_selector,
        """(block, phrase) => {
            const textNode = Array.from(block.childNodes).find(
                (node) => node.nodeType === Node.TEXT_NODE && node.nodeValue.includes(phrase)
            );
            const start = textNode.nodeValue.indexOf(phrase);
            const range = document.createRange();
            range.setStart(textNode, start);
            range.setEnd(textNode, start + phrase.length);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
            block.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
        }""",
        phrase,
    )


def test_reply_appears_in_place_without_a_page_reload(open_in_workspace_frame) -> None:
    frame = open_in_workspace_frame()
    frame.evaluate(_MARKER_JS)

    frame.fill("#note-t1 textarea", "an in-place reply")
    frame.click("#note-t1 button:has-text('Reply')")

    frame.wait_for_selector("#note-t1 .msg .body:has-text('an in-place reply')")
    assert frame.evaluate(_MARKER_READ_JS) == "alive"


def test_resolving_and_reopening_update_in_place(open_in_workspace_frame) -> None:
    frame = open_in_workspace_frame()
    frame.evaluate(_MARKER_JS)

    frame.click("#note-t1 button:has-text('Resolve')")

    # resolving closes the note in the same click
    frame.wait_for_selector("#note-t1.folded")
    frame.wait_for_selector("#note-t1 .state-terminal")

    frame.click("#note-t1 .head")
    frame.click("#note-t1 button:has-text('Reopen')")
    frame.wait_for_selector("#note-t1 .state-open")
    assert frame.evaluate(_MARKER_READ_JS) == "alive"


def test_fold_state_survives_posting_a_comment(open_in_workspace_frame) -> None:
    frame = open_in_workspace_frame()
    # fold the open thread, then post a fresh comment elsewhere
    frame.click("#note-t1 .fold")
    frame.wait_for_selector("#note-t1.folded")

    frame.click("#why .add-note")
    frame.fill(".note.draft textarea", "a new comment elsewhere")
    frame.click(".note.draft button:has-text('Comment')")

    # the new thread appears via in-place update and t1 stays folded
    frame.wait_for_selector(".note .msg .body:has-text('a new comment elsewhere')")
    assert frame.query_selector("#note-t1.folded") is not None


def test_discard_ask_appears_in_the_sandboxed_frame_and_keep_preserves_the_draft(
    open_in_workspace_frame,
) -> None:
    # the workspace sandbox suppresses window.confirm(); the in-page ask must
    # appear instead, and "keep" must return to the typed draft
    frame = open_in_workspace_frame()
    frame.click("#why .add-note")
    frame.fill(".note.draft textarea", "half-typed thought")

    frame.click("#features .add-note")
    frame.wait_for_selector(".ask-overlay")
    # the ask ignores clicks for 300ms so a double-click's trailing click
    # cannot answer it; wait that guard out before answering
    frame.page.wait_for_timeout(400)
    frame.click(".ask-overlay button:has-text('Keep my draft')")

    frame.wait_for_selector(".ask-overlay", state="detached")
    assert frame.input_value(".note.draft textarea") == "half-typed thought"

    # asking again and discarding starts a clean draft on the new target
    frame.click("#features .add-note")
    frame.wait_for_selector(".ask-overlay")
    frame.page.wait_for_timeout(400)
    frame.click(".ask-overlay button:has-text('Discard and start new')")
    frame.wait_for_selector(".ask-overlay", state="detached")
    assert frame.input_value(".note.draft textarea") == ""
    assert "features" in frame.text_content(".note.draft .head")


def test_selection_comment_opens_a_draft_with_the_caret_in_the_box(
    open_in_workspace_frame,
) -> None:
    frame = open_in_workspace_frame()
    _select_phrase(frame, "#why + p", "documents beat")
    frame.wait_for_selector(".sel-comment", state="visible")

    frame.click(".sel-comment")

    frame.wait_for_selector(".note.draft textarea")
    # the caret must actually land in the box (the historical gap: scripted
    # frames pass this while the real dockview shell has failed it -- this is
    # the regression floor, not proof the shell behaves)
    frame.wait_for_function(
        "document.activeElement && document.activeElement.tagName === 'TEXTAREA'"
    )


def test_posting_a_selection_comment_lands_a_phrase_anchor_in_place(
    open_in_workspace_frame, e2e_workspace: Path
) -> None:
    frame = open_in_workspace_frame()
    frame.evaluate(_MARKER_JS)
    _select_phrase(frame, "#why + p", "documents beat")
    frame.wait_for_selector(".sel-comment", state="visible")
    frame.click(".sel-comment")
    frame.wait_for_selector(".note.draft textarea")

    frame.fill(".note.draft textarea", "about this word")
    frame.click(".note.draft button:has-text('Comment')")

    # the quote highlight and the new card arrive without a reload, and the
    # thread landed in the file with a quoted phrase anchor
    frame.wait_for_selector(".note .msg .body:has-text('about this word')")
    assert frame.evaluate(_MARKER_READ_JS) == "alive"
    spec_text = (e2e_workspace / "spec.md").read_text()
    assert re.search(r'\[!thread\] #t\d+ on \{#[A-Za-z0-9_-]+\} "[^"]+" -- open', spec_text)
    assert "about this word" in spec_text


def test_opening_another_markdown_file_and_commenting_writes_to_that_file(
    open_in_workspace_frame, e2e_workspace: Path
) -> None:
    frame = open_in_workspace_frame("/?doc=notes/other.md")
    assert "Other Notes" in frame.text_content("#article h1")

    frame.click("#article h1 .add-note")
    frame.fill(".note.draft textarea", "a comment on a plain file")
    frame.click(".note.draft button:has-text('Comment')")

    frame.wait_for_selector(".note .msg .body:has-text('a comment on a plain file')")
    other_text = (e2e_workspace / "notes" / "other.md").read_text()
    assert "a comment on a plain file" in other_text
    assert "a comment on a plain file" not in (e2e_workspace / "spec.md").read_text()


def test_notify_button_stamps_the_document_and_marks_fresh_activity_new(
    open_in_workspace_frame, e2e_workspace: Path
) -> None:
    frame = open_in_workspace_frame()
    frame.evaluate(_MARKER_JS)
    # the header stays pinned while scrolling; no notify stamp yet, so no counts
    assert frame.eval_on_selector("header", "h => getComputedStyle(h).position") == "sticky"
    assert frame.text_content("#notify").strip() == "notify agent"

    frame.click("#notify")

    # the version stamp lands in the file and a durable event is written,
    # all without a reload
    frame.wait_for_selector("#notified:has-text('notified v1')")
    assert "notified: v1 (" in (e2e_workspace / "spec.md").read_text()
    assert len(list((e2e_workspace / ".notifications").glob("*.json"))) == 1
    assert frame.evaluate(_MARKER_READ_JS) == "alive"


def _write_counters_document(e2e_workspace: Path) -> None:
    # stamps in minutes past the notify press, so freshness is unambiguous
    (e2e_workspace / "notes" / "counters.md").write_text(
        "---\n"
        "notified: v1 (2026-08-19T10:00:00Z)\n"
        "---\n"
        "\n"
        "## Topic {#topic}\n"
        "\n"
        "Prose.\n"
        "\n"
        "> [!thread] #t1 on {#topic} -- open\n"
        "> **maciek (2026-08-19 10:05):** a pending comment\n"
        "\n"
        "> [!thread] #t2 on {#topic} -- open\n"
        "> **agent (2026-08-19 10:06):** a reply that is new for the reader\n"
    )


def test_counters_show_both_directions_and_pressing_notify_clears_pending(
    open_in_workspace_frame, e2e_workspace: Path
) -> None:
    _write_counters_document(e2e_workspace)
    frame = open_in_workspace_frame("/?doc=notes/counters.md")

    # one pending comment on the button, one agent reply in the blue chip,
    # and the pending comment is soft-highlighted with a NEW mark
    assert "(1)" in frame.text_content("#notify")
    assert "1 new for you" in frame.text_content("#newnav")
    frame.wait_for_selector("#note-t1 .msg.fresh .newmark")
    # header stamps read as relative time, precise stamp in the instant tooltip
    assert "ago" in frame.text_content("#notified")
    assert "2026-08-19T10:00:00Z" in frame.get_attribute("#notified", "data-tip")

    # pressing notify acknowledges everything written up to the press,
    # and the now-empty blue chip disappears entirely (arrows included)
    frame.click("#notify")
    frame.wait_for_selector("#notified:has-text('notified v2')")
    assert frame.text_content("#notify").strip() == "notify agent"
    frame.wait_for_selector("#newnav", state="hidden")


def test_new_for_you_chip_jumps_to_the_next_new_item(
    open_in_workspace_frame, e2e_workspace: Path
) -> None:
    _write_counters_document(e2e_workspace)
    frame = open_in_workspace_frame("/?doc=notes/counters.md")

    frame.click("#newlabel")

    # both notes carry new activity; the jump focuses one of them, and the
    # arrow moves to the other
    frame.wait_for_selector(".note.focused")
    first_focus = frame.eval_on_selector(".note.focused", "n => n.dataset.id")
    frame.click("#newnext")
    frame.wait_for_function(
        "expected => document.querySelector('.note.focused').dataset.id !== expected",
        arg=first_focus,
    )


def test_notify_chevron_sends_a_custom_message_with_the_press(
    open_in_workspace_frame, e2e_workspace: Path
) -> None:
    frame = open_in_workspace_frame()

    frame.click("#notifychev")
    frame.wait_for_selector(".notify-pop:not([hidden]) textarea")
    assert frame.input_value(".notify-pop textarea") == "Please sweep the document."

    frame.fill(".notify-pop textarea", "prioritize the search thread")
    frame.click(".notify-pop button:has-text('notify')")

    frame.wait_for_selector("#notified:has-text('notified v1')")
    frame.wait_for_selector(".notify-pop", state="hidden")
    events = list((e2e_workspace / ".notifications").glob("*.json"))
    assert len(events) == 1
    assert "prioritize the search thread" in events[0].read_text()


def test_search_bar_finds_prose_and_optionally_comments(open_in_workspace_frame) -> None:
    frame = open_in_workspace_frame()
    # the sandboxed frame only receives keys once it holds focus -- a reader
    # has always clicked or scrolled the document before reaching for Cmd+F
    frame.click("#article h1")
    frame.press("body", "Control+f")
    frame.wait_for_selector(".searchbar:not([hidden])")

    # prose matches out of the box
    frame.fill(".search-input", "documents beat")
    frame.wait_for_selector(".search-count:has-text('1/1')")

    # comment text needs the checkbox opt-in
    frame.fill(".search-input", "first line")
    frame.wait_for_selector(".search-count:has-text('0 matches')")
    frame.check(".search-scope input")
    frame.wait_for_selector(".search-count:has-text('1/1')")

    # a match hidden in a folded note unfolds it (s2 starts folded)
    frame.fill(".search-input", "Render nicely")
    frame.wait_for_selector(".search-count:has-text('1/1')")
    frame.wait_for_selector("#note-s2:not(.folded)")

    # Escape closes the bar
    frame.press(".search-input", "Escape")
    frame.wait_for_selector(".searchbar", state="hidden")


def test_file_picker_lists_workspace_markdown_files(open_in_workspace_frame) -> None:
    frame = open_in_workspace_frame()

    frame.click("#openfile")

    frame.wait_for_selector(".file-pick")
    rows = frame.eval_on_selector_all(".file-row", "rows => rows.map(r => r.textContent)")
    assert "spec.md" in rows
    assert "notes/other.md" in rows
