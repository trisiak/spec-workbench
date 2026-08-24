import re
from pathlib import Path

from spec_workbench.data_types import NoteState
from spec_workbench.parsing import parse_spec_document
from spec_workbench.registry import DocumentRegistry
from spec_workbench.runner import create_app
from spec_workbench.testing import make_sample_document_text

_REPO_ROOT = Path(__file__).parents[5]
_REAL_SPEC_PATH = _REPO_ROOT / "docs" / "specs" / "spec_workbench.md"


def _make_test_app_with_document(tmp_path: Path) -> tuple[object, Path]:
    spec_path = tmp_path / "spec.md"
    spec_path.write_text(make_sample_document_text())
    registry = DocumentRegistry(workspace_root=tmp_path, default_document=spec_path)
    app = create_app(
        document_registry=registry,
        ui_author_name="maciek",
        notifications_dir=tmp_path / ".notifications",
    )
    return app.test_client(), spec_path


def test_index_renders_prose_headings_and_embeds_note_data(tmp_path: Path) -> None:
    client, _ = _make_test_app_with_document(tmp_path)

    response = client.get("/")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'id="why"' in page
    assert '"id": "t1"' in page or "&#34;id&#34;: &#34;t1&#34;" in page
    assert "notes-data" in page


def test_raw_view_shows_the_source_with_a_way_back(tmp_path: Path) -> None:
    client, _ = _make_test_app_with_document(tmp_path)

    response = client.get("/raw")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "back to document" in page
    assert "[!thread] #t1" in page


def test_quickstart_serves_the_rendered_format_guide(tmp_path: Path) -> None:
    client, _ = _make_test_app_with_document(tmp_path)

    response = client.get("/quickstart")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    # rendered (a heading element), not raw markdown source
    assert "Spec Workbench quickstart</h1>" in page
    assert "[!thread]" in page
    assert "back to document" in page


def test_reply_endpoint_appends_the_message_to_the_file(tmp_path: Path) -> None:
    client, spec_path = _make_test_app_with_document(tmp_path)

    response = client.post("/api/notes/t1/reply", json={"text": "reply 73158"})

    assert response.status_code == 200
    document = parse_spec_document(spec_path.read_text())
    last_message = document.notes[0].messages[-1]
    assert last_message.text == "reply 73158"
    assert last_message.author == "maciek"
    # stamps carry time of day so "new" tracking is minute-precise
    assert last_message.stamp is not None
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", last_message.stamp)


def test_reply_endpoint_rejects_empty_text(tmp_path: Path) -> None:
    client, spec_path = _make_test_app_with_document(tmp_path)
    text_before = spec_path.read_text()

    response = client.post("/api/notes/t1/reply", json={"text": "   "})

    assert response.status_code == 400
    assert spec_path.read_text() == text_before


def test_reply_endpoint_returns_404_for_unknown_note(tmp_path: Path) -> None:
    client, _ = _make_test_app_with_document(tmp_path)

    response = client.post("/api/notes/t99/reply", json={"text": "hello"})

    assert response.status_code == 404


def test_state_endpoint_resolves_and_reopens_a_thread(tmp_path: Path) -> None:
    client, spec_path = _make_test_app_with_document(tmp_path)

    resolve_response = client.post("/api/notes/t1/state", json={"state": "resolved"})
    assert resolve_response.status_code == 200
    resolved_document = parse_spec_document(spec_path.read_text())
    assert resolved_document.notes[0].state == NoteState.RESOLVED

    reopen_response = client.post("/api/notes/t1/state", json={"state": "open"})
    assert reopen_response.status_code == 200
    reopened_document = parse_spec_document(spec_path.read_text())
    assert reopened_document.notes[0].state == NoteState.OPEN


def test_state_endpoint_blocks_suggestion_accept_until_suggestion_mode(tmp_path: Path) -> None:
    client, spec_path = _make_test_app_with_document(tmp_path)
    text_before = spec_path.read_text()

    response = client.post("/api/notes/s1/state", json={"state": "accepted"})

    assert response.status_code == 400
    assert spec_path.read_text() == text_before


def test_state_endpoint_rejects_unknown_state_values(tmp_path: Path) -> None:
    client, _ = _make_test_app_with_document(tmp_path)

    response = client.post("/api/notes/t1/state", json={"state": "banana"})

    assert response.status_code == 400


def test_create_note_endpoint_opens_a_new_thread_with_the_next_free_id(tmp_path: Path) -> None:
    client, spec_path = _make_test_app_with_document(tmp_path)

    response = client.post("/api/notes", json={"anchor": "features", "text": "new nit 91437"})

    assert response.status_code == 200
    assert response.get_json()["id"] == "t2"
    document = parse_spec_document(spec_path.read_text())
    new_thread = next(note for note in document.notes if note.note_id == "t2")
    assert new_thread.state == NoteState.OPEN
    assert new_thread.messages[0].text == "new nit 91437"
    assert new_thread.messages[0].author == "maciek"


def test_create_note_never_reuses_a_deleted_thread_id(tmp_path: Path) -> None:
    # a deleted thread leaves #tN mentions behind (prose refs, the log);
    # minting must skip past those, not just past the threads still present
    spec_path = tmp_path / "spec.md"
    spec_path.write_text(make_sample_document_text() + "\n- log: #t15 was deleted on request\n")
    registry = DocumentRegistry(workspace_root=tmp_path, default_document=spec_path)
    client = create_app(
        document_registry=registry, ui_author_name="maciek", notifications_dir=tmp_path / ".notifications"
    ).test_client()

    response = client.post("/api/notes", json={"anchor": "features", "text": "after the deletion"})

    assert response.status_code == 200
    assert response.get_json()["id"] == "t16"


def test_create_note_endpoint_returns_404_for_unknown_anchor(tmp_path: Path) -> None:
    client, spec_path = _make_test_app_with_document(tmp_path)
    text_before = spec_path.read_text()

    response = client.post("/api/notes", json={"anchor": "nope", "text": "hello"})

    assert response.status_code == 404
    assert spec_path.read_text() == text_before


def test_create_note_endpoint_requires_anchor_and_text(tmp_path: Path) -> None:
    client, _ = _make_test_app_with_document(tmp_path)

    assert client.post("/api/notes", json={"anchor": "", "text": "x"}).status_code == 400
    assert client.post("/api/notes", json={"anchor": "why", "text": "  "}).status_code == 400


def test_create_note_on_anchorless_heading_mints_the_id_and_files_the_thread(tmp_path: Path) -> None:
    client, spec_path = _make_test_app_with_document(tmp_path)

    response = client.post("/api/notes", json={"heading": "Sample App", "text": "top-level nit 55023"})

    assert response.status_code == 200
    new_note_id = response.get_json()["id"]
    updated_text = spec_path.read_text()
    assert "# Sample App" in updated_text and "{#sample-app}" in updated_text
    document = parse_spec_document(updated_text)
    new_thread = next(note for note in document.notes if note.note_id == new_note_id)
    assert new_thread.anchor.block_id == "sample-app"
    assert new_thread.messages[0].text == "top-level nit 55023"


def test_create_note_on_unknown_heading_returns_404(tmp_path: Path) -> None:
    client, spec_path = _make_test_app_with_document(tmp_path)
    text_before = spec_path.read_text()

    response = client.post("/api/notes", json={"heading": "No Such Section", "text": "x"})

    assert response.status_code == 404
    assert spec_path.read_text() == text_before


def test_create_note_from_selection_mints_block_id_and_quote_anchor(tmp_path: Path) -> None:
    client, spec_path = _make_test_app_with_document(tmp_path)
    paragraph_line_idx = spec_path.read_text().splitlines().index("Because documents beat chat.")

    response = client.post(
        "/api/notes",
        json={
            "sline": paragraph_line_idx,
            "eline": paragraph_line_idx,
            "prefix": "Because documents beat chat.",
            "quote": "documents beat",
            "before": "Because",
            "after": "chat.",
            "text": "phrase nit 20874",
        },
    )

    assert response.status_code == 200
    new_note_id = response.get_json()["id"]
    updated_text = spec_path.read_text()
    assert "Because documents beat chat. {#because-documents-beat-chat}" in updated_text
    document = parse_spec_document(updated_text)
    new_thread = next(note for note in document.notes if note.note_id == new_note_id)
    assert new_thread.anchor.block_id == "because-documents-beat-chat"
    assert new_thread.anchor.quote == "documents beat"
    assert new_thread.messages[0].text == "phrase nit 20874"


def test_create_note_from_selection_rejects_a_shifted_document(tmp_path: Path) -> None:
    client, spec_path = _make_test_app_with_document(tmp_path)
    text_before = spec_path.read_text()

    response = client.post(
        "/api/notes",
        json={
            "sline": 0,
            "eline": 0,
            "prefix": "words that are not on that line",
            "quote": "anything",
            "before": "",
            "after": "",
            "text": "x",
        },
    )

    assert response.status_code == 409
    assert spec_path.read_text() == text_before


def test_api_doc_returns_the_full_render_payload(tmp_path: Path) -> None:
    client, _ = _make_test_app_with_document(tmp_path)

    response = client.get("/api/doc")

    assert response.status_code == 200
    payload = response.get_json()
    assert 'id="why"' in payload["articleHtml"]
    assert [note["id"] for note in payload["notes"]] == ["t1", "s1", "s2"]
    assert payload["docStatus"] == "drafting"
    assert payload["docPath"] == "spec.md"


def test_doc_param_opens_another_file_and_comments_write_to_it(tmp_path: Path) -> None:
    client, spec_path = _make_test_app_with_document(tmp_path)
    other_path = tmp_path / "notes" / "other.md"
    other_path.parent.mkdir()
    other_path.write_text("# Other Notes\n\nA plain file with no threads yet.\n")

    page_response = client.get("/?doc=notes/other.md")
    assert page_response.status_code == 200
    assert "Other Notes" in page_response.get_data(as_text=True)

    comment_response = client.post(
        "/api/notes?doc=notes/other.md",
        json={"heading": "Other Notes", "text": "annotating a plain file"},
    )

    assert comment_response.status_code == 200
    assert "annotating a plain file" in other_path.read_text()
    assert "annotating a plain file" not in spec_path.read_text()


def test_doc_param_rejects_paths_outside_the_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    spec_path = workspace / "spec.md"
    spec_path.write_text(make_sample_document_text())
    (tmp_path / "outside.md").write_text("# Outside\n")
    registry = DocumentRegistry(workspace_root=workspace, default_document=spec_path)
    client = create_app(
        document_registry=registry, ui_author_name="maciek", notifications_dir=tmp_path / ".notifications"
    ).test_client()

    assert client.get("/?doc=../outside.md").status_code == 404
    assert client.get("/api/doc?doc=../outside.md").status_code == 404
    assert client.post("/api/notes?doc=../outside.md", json={"anchor": "why", "text": "x"}).status_code == 404


def test_api_files_lists_the_workspace_markdown_files(tmp_path: Path) -> None:
    client, _ = _make_test_app_with_document(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "other.md").write_text("# Other\n")

    response = client.get("/api/files")

    assert response.status_code == 200
    assert response.get_json()["files"] == ["notes/other.md", "spec.md"]


def test_plain_markdown_file_without_frontmatter_renders(tmp_path: Path) -> None:
    client, _ = _make_test_app_with_document(tmp_path)
    (tmp_path / "plain.md").write_text("# Just Prose\n\nNothing else.\n")

    response = client.get("/?doc=plain.md")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Just Prose" in page
    assert "notes-data" in page


def test_notify_stamps_the_document_writes_an_event_and_nudges_the_agent(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.md"
    spec_path.write_text(make_sample_document_text())
    registry = DocumentRegistry(workspace_root=tmp_path, default_document=spec_path)
    nudges: list[tuple[str, str]] = []
    notifications_dir = tmp_path / ".notifications"
    client = create_app(
        document_registry=registry,
        ui_author_name="maciek",
        notifications_dir=notifications_dir,
        agent_nudger=lambda agent, message: nudges.append((agent, message)),
        default_notify_agent="fallback-agent",
    ).test_client()

    first = client.post("/api/notify")
    second = client.post("/api/notify")

    assert first.status_code == 200 and first.get_json()["version"] == 1
    assert second.status_code == 200 and second.get_json()["version"] == 2
    assert "notified: v2 (" in spec_path.read_text()
    assert len(list(notifications_dir.glob("*.json"))) == 2
    assert len(nudges) == 2 and "spec.md" in nudges[0][1] and "v1" in nudges[0][1]
    assert nudges[0][0] == "fallback-agent"

    # a message riding on the press reaches the agent and the event record
    third = client.post("/api/notify", json={"message": "focus on the F2 comments first"})
    assert third.status_code == 200
    assert "focus on the F2 comments first" in nudges[2][1]
    newest_event = sorted(notifications_dir.glob("*.json"))[-1]
    assert "focus on the F2 comments first" in newest_event.read_text()


def test_notify_targets_the_agent_named_in_the_document_frontmatter(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.md"
    spec_path.write_text(make_sample_document_text())
    (tmp_path / "owned.md").write_text(
        "---\nnotify-agent: doc-owner\n---\n\n# Owned\n\nProse.\n"
    )
    (tmp_path / "plain.md").write_text("# Plain\n\nProse.\n")
    registry = DocumentRegistry(workspace_root=tmp_path, default_document=spec_path)
    nudges: list[tuple[str, str]] = []
    notifications_dir = tmp_path / ".notifications"
    client = create_app(
        document_registry=registry,
        ui_author_name="maciek",
        notifications_dir=notifications_dir,
        agent_nudger=lambda agent, message: nudges.append((agent, message)),
    ).test_client()

    owned = client.post("/api/notify?doc=owned.md")
    plain = client.post("/api/notify?doc=plain.md")

    # frontmatter names the target; with no frontmatter key and no default,
    # the press stamps and records but nudges no one
    assert owned.status_code == 200 and plain.status_code == 200
    assert [agent for agent, _ in nudges] == ["doc-owner"]
    events = sorted(notifications_dir.glob("*.json"))
    assert len(events) == 2
    assert '"agent": "doc-owner"' in "".join(e.read_text() for e in events)


def test_notify_creates_frontmatter_on_a_plain_markdown_file(tmp_path: Path) -> None:
    client, _ = _make_test_app_with_document(tmp_path)
    plain_path = tmp_path / "plain.md"
    plain_path.write_text("# Just Prose\n\nNothing else.\n")

    response = client.post("/api/notify?doc=plain.md")

    assert response.status_code == 200
    plain_text = plain_path.read_text()
    assert plain_text.startswith("---\nnotified: v1 (")
    assert "# Just Prose" in plain_text


def test_activity_since_the_notify_stamp_is_marked_new_and_counted(tmp_path: Path) -> None:
    # minute-precise stamps: a message is new when stamped after the notify
    # press, until someone else responds or the note closes
    spec_path = tmp_path / "spec.md"
    spec_path.write_text(
        "---\n"
        "notified: v1 (2026-08-19T10:00:00Z)\n"
        "---\n"
        "\n"
        "## Why {#why}\n"
        "\n"
        "Prose.\n"
        "\n"
        "> [!thread] #t1 on {#why} -- open\n"
        "> **maciek (2026-08-19 09:30):** asked before the press\n"
        "> **agent (2026-08-19 11:00):** replied after it\n"
        "\n"
        "> [!thread] #t2 on {#why} -- open\n"
        "> **maciek (2026-08-19 12:00):** pending until the next press\n"
        "\n"
        "> [!thread] #t3 on {#why} -- resolved (2026-08-19)\n"
        "> **maciek (2026-08-19 12:30):** resolved notes are never new\n"
        "\n"
        "> [!thread] #t4 on {#why} -- open\n"
        "> **maciek (2026-08-19 10:00):** same minute as the press -- already sent\n"
    )
    registry = DocumentRegistry(workspace_root=tmp_path, default_document=spec_path)
    client = create_app(
        document_registry=registry, ui_author_name="maciek", notifications_dir=tmp_path / ".n"
    ).test_client()

    payload = client.get("/api/doc").get_json()

    notes = {note["id"]: note for note in payload["notes"]}
    assert [m["isNew"] for m in notes["t1"]["messages"]] == [False, True]
    assert [m["isNew"] for m in notes["t2"]["messages"]] == [True]
    assert [m["isNew"] for m in notes["t3"]["messages"]] == [False]
    # the press acknowledges its whole minute -- a comment written seconds
    # before pressing notify must not stay pending after it
    assert [m["isNew"] for m in notes["t4"]["messages"]] == [False]
    assert (notes["t1"]["isNew"], notes["t2"]["isNew"], notes["t3"]["isNew"]) == (True, True, False)
    # the two header counters: your pending comments, and the agent's replies
    assert payload["pendingCount"] == 1
    assert payload["newForYou"] == 1


def test_real_spec_document_parses_with_all_expected_notes() -> None:
    document = parse_spec_document(_REAL_SPEC_PATH.read_text())

    note_ids = [note.note_id for note in document.notes]
    # survivors of the first bake: the syntax examples and whatever is open
    assert set(note_ids) >= {"t0", "s0", "s2"}
    assert document.frontmatter is not None
    assert document.frontmatter.app_name == "spec-workbench"
