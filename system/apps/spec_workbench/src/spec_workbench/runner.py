"""Living spec documents: render app specs with margin threads, suggestions, and statuses.

Services run from /home/user/workspace (the repo root). Conventions:

- Persistent state (anything written and read across runs -- cursors,
  caches, snapshots, user records): read and write it under ``DATA_DIR``
  (defined below), never a hardcoded ``data/.apps/spec-workbench/`` at the
  call site. ``DATA_DIR`` defaults to ``data/.apps/spec-workbench/`` but
  honors the ``SPEC_WORKBENCH_DATA_DIR`` env var, so an editing agent can point a
  throwaway instance at a *copy* of the data instead of the live store
  (see the update-app skill). Do NOT use ``Path(__file__)``-based
  paths for state -- the bug to avoid is one process writing to
  ``/home/user/workspace/data/.apps/...`` while another reads from
  ``/home/user/workspace/system/apps/<pkg>/data/...``.
- Static assets shipped alongside this file (templates, default
  configs, bundled JSON): ``Path(__file__).parent / "assets/..."`` is
  fine and is the right pattern.
- Listen port: bind ``PORT`` (defined below), which defaults to this
  app's assigned port but honors the ``SPEC_WORKBENCH_PORT`` env var, so
  an editing agent can boot a throwaway instance on a *spare* port
  alongside the live one (see the update-app skill). Never hardcode
  the port at the ``run_simple`` call.

This is a synchronous Flask app served by the threaded Werkzeug server.
The system_interface proxy at ``/service/spec-workbench/`` rewrites absolute
paths in served HTML and installs a scoped service worker that prepends
the prefix to the page's own fetches, so the app can serve at ``/`` and
still work behind the proxy. Use ``flask_sock`` if you need WebSockets.

Any markdown file under the workspace root can be opened via ``?doc=<path>``
(root-relative); without it the app serves its own living spec. Every
route resolves the parameter through one ``DocumentRegistry`` so path
confinement and per-file write serialization live in a single place.
"""

import json
import os
import subprocess
from collections.abc import Callable
from datetime import datetime
from datetime import timezone
from html import escape
from pathlib import Path
from urllib.parse import quote

from flask import Flask
from flask import Response
from flask import jsonify
from flask import render_template
from flask import request
from flask import send_from_directory
from werkzeug.serving import run_simple

from spec_workbench.data_types import NoteState
from spec_workbench.errors import AnchorNotFoundError
from spec_workbench.errors import DocumentChangedError
from spec_workbench.errors import DocumentNotAllowedError
from spec_workbench.errors import HeadingNotFoundError
from spec_workbench.errors import NoteNotFoundError
from spec_workbench.errors import QuoteResolutionError
from spec_workbench.parsing import parse_spec_document
from spec_workbench.registry import DocumentRegistry
from spec_workbench.rendering import build_note_views
from spec_workbench.rendering import collect_agent_author_names
from spec_workbench.rendering import count_message_activity
from spec_workbench.rendering import render_prose_html
from spec_workbench.store import FileSpecStore

# Persistent state for this app lives under DATA_DIR. It defaults to
# ``data/.apps/spec-workbench/`` but is overridable via the ``SPEC_WORKBENCH_DATA_DIR`` env var
# so a throwaway instance can run against a *copy* of the data while editing --
# see the update-app skill. Always read/write state through DATA_DIR;
# never hardcode ``data/.apps/spec-workbench/`` at a call site, or the override is
# bypassed. A writing call site should ``DATA_DIR.mkdir(parents=True,
# exist_ok=True)`` before writing.
DATA_DIR = Path(os.environ.get("SPEC_WORKBENCH_DATA_DIR", "data/.apps/spec-workbench"))

# Listen port. Defaults to this app's assigned port but is overridable via
# the ``SPEC_WORKBENCH_PORT`` env var so an editing agent can boot a throwaway
# instance on a spare port next to the live one (see the update-app skill).
# Never hardcode the port at the ``run_simple`` call, or the override is bypassed.
PORT = int(os.environ.get("SPEC_WORKBENCH_PORT", "8082"))

# The document served when no ?doc= is given (this app's own living spec),
# the root all openable documents must live under, and the author name
# attributed to edits made through the UI. All honor env overrides so a
# throwaway instance can run against copies.
SPEC_PATH = Path(os.environ.get("SPEC_WORKBENCH_DOC", "docs/specs/spec_workbench.md"))
WORKSPACE_ROOT = Path(os.environ.get("SPEC_WORKBENCH_ROOT", "."))
UI_AUTHOR_NAME = os.environ.get("SPEC_WORKBENCH_AUTHOR", "user")

# The agent a notify press nudges (via `mngr message`) when the document's
# own frontmatter has no `notify-agent:` key. Empty disables the nudge for
# such documents; the durable notification event under DATA_DIR is written
# either way. This workspace sets it in the supervisord program entry --
# the code ships with no agent name baked in.
NOTIFY_AGENT = os.environ.get("SPEC_WORKBENCH_NOTIFY_AGENT", "")

_ASSETS_DIR = Path(__file__).parent / "assets"

# The bundled format-and-workflow guide; served rendered at /quickstart and
# referenced by path in agent nudges so a fresh agent can read the conventions
QUICKSTART_PATH = _ASSETS_DIR / "quickstart.md"


def _asset_version() -> int:
    # Newest asset mtime; versioned URLs defeat stale cached scripts
    return max(int(asset_path.stat().st_mtime) for asset_path in _ASSETS_DIR.iterdir())

# UI state changes are limited to the thread lifecycle; suggestion
# accept/reject arrives with suggestion mode (F2).
_UI_ALLOWED_STATES = (NoteState.OPEN, NoteState.RESOLVED)


def _current_utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _current_utc_stamp() -> str:
    # message stamps carry time of day so "new" tracking is minute-precise;
    # lifecycle dates (resolved/accepted) stay day-only for readability
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def create_app(
    document_registry: DocumentRegistry,
    ui_author_name: str,
    notifications_dir: Path,
    agent_nudger: Callable[[str, str], None] | None = None,
    default_notify_agent: str = "",
) -> Flask:
    """Build the Flask app around a document registry; separated for tests.

    ``notifications_dir`` receives one durable JSON event per notify-button
    press (the listenable contract); ``agent_nudger``, when given, is also
    called per press with the target agent and a one-line message (the live
    nudge). The target is the document's own ``notify-agent:`` frontmatter
    key when present, else ``default_notify_agent``; documents with neither
    get the durable event but no nudge.
    """
    app = Flask("spec_workbench", static_folder=None)

    def _requested_doc_param() -> str | None:
        return request.args.get("doc")

    def _resolved_store() -> FileSpecStore:
        # Raises DocumentNotAllowedError; each route maps that to a 404
        return document_registry.store_for(_requested_doc_param())

    def _document_payload(spec_store: FileSpecStore) -> dict[str, object]:
        """Everything the frontend needs to (re)render: prose HTML, notes, header fields."""
        document = parse_spec_document(spec_store.read_document_text())
        frontmatter = document.frontmatter
        pending_from_user, new_from_agent = count_message_activity(document, ui_author_name)
        notified = (
            f"v{frontmatter.notified_version} {frontmatter.notified_at}"
            if frontmatter is not None and frontmatter.notified_version is not None
            else None
        )
        # the same resolution the notify press uses, surfaced so the UI can
        # say who a press will reach before it happens (#t32)
        notify_target = (
            frontmatter.notify_agent if frontmatter is not None and frontmatter.notify_agent else None
        ) or (default_notify_agent or None)
        file_stat = spec_store.spec_path.stat()
        return {
            "docStamp": f"{file_stat.st_mtime_ns}-{file_stat.st_size}",
            "notifyAgent": notify_target,
            "articleHtml": render_prose_html(document.prose_markdown, document.prose_file_line_numbers),
            "notes": build_note_views(document, ui_author_name),
            # display string for the header legend: the actual agent names
            # seen in this document, not a generic "agent" (#t33)
            "agentNames": ", ".join(collect_agent_author_names(document, ui_author_name)) or None,
            "appName": frontmatter.app_name if frontmatter is not None else None,
            "docStatus": frontmatter.status if frontmatter is not None else None,
            "agentSeen": frontmatter.agent_seen if frontmatter is not None else None,
            "notified": notified,
            "pendingCount": pending_from_user,
            "newForYou": new_from_agent,
            "docPath": document_registry.display_path(_requested_doc_param()),
        }

    @app.route("/")
    def index() -> str | tuple[str, int]:
        try:
            spec_store = _resolved_store()
        except DocumentNotAllowedError as e:
            return f"<!doctype html><pre>{escape(str(e))}</pre>", 404
        payload = _document_payload(spec_store)
        doc_param = _requested_doc_param()
        return render_template(
            "doc.html",
            notify_agent=payload["notifyAgent"],
            agent_names=payload["agentNames"],
            app_name=payload["appName"],
            doc_status=payload["docStatus"],
            agent_seen=payload["agentSeen"],
            spec_path=payload["docPath"],
            notified=payload["notified"],
            pending_count=payload["pendingCount"],
            new_for_you=payload["newForYou"],
            doc_query=f"?doc={quote(str(doc_param))}" if doc_param else "",
            ui_author_name=ui_author_name,
            article_html=payload["articleHtml"],
            note_views=payload["notes"],
            asset_version=_asset_version(),
        )

    @app.route("/raw")
    def raw() -> Response | tuple[str, int]:
        # The raw source this view derives from, always one click away.
        # Plain <pre> for now; syntax coloring is a noted nice-to-have.
        try:
            spec_store = _resolved_store()
        except DocumentNotAllowedError as e:
            return f"<!doctype html><pre>{escape(str(e))}</pre>", 404
        doc_param = _requested_doc_param()
        back_href = f"./?doc={quote(str(doc_param))}" if doc_param else "./"
        display_path = document_registry.display_path(doc_param)
        page = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{escape(display_path)} (raw)</title><style>"
            "body{margin:0;background:#FBFBF9;color:#1F2328;font-family:ui-monospace,"
            "'SF Mono',Menlo,Consolas,monospace}"
            ".bar{position:sticky;top:0;background:#FFF;border-bottom:1px solid #E7E5DF;"
            "padding:10px 24px;font-size:12.5px}"
            ".bar a{color:#2F6B8F;text-decoration:none}"
            "pre{margin:0;padding:24px;font-size:12.5px;line-height:1.55;"
            "white-space:pre-wrap;overflow-wrap:anywhere}"
            "</style></head><body>"
            f"<div class='bar'><a href='{escape(back_href)}'>&larr; back to document</a>"
            f"&nbsp;&nbsp;{escape(display_path)}</div>"
            f"<pre>{escape(spec_store.read_document_text())}</pre></body></html>"
        )
        return Response(page, mimetype="text/html")

    @app.route("/quickstart")
    def quickstart() -> Response:
        # The bundled format-and-workflow guide, rendered through the same
        # markdown pipeline the documents use. Ships with the app so any
        # install (and any agent pointed at it) is self-documenting.
        guide = parse_spec_document((_ASSETS_DIR / "quickstart.md").read_text())
        article_html = render_prose_html(guide.prose_markdown, guide.prose_file_line_numbers)
        page = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Spec Workbench quickstart</title>"
            f"<link rel='stylesheet' href='assets/style.css?v={_asset_version()}'>"
            "<style>body{display:block;background:#FBFBF9}"
            "article.prose{max-width:780px;margin:0 auto;padding:28px 28px 48px}"
            ".bar{position:sticky;top:0;background:#FFF;border-bottom:1px solid #E7E5DF;"
            "padding:10px 24px;font-size:12.5px;font-family:ui-monospace,'SF Mono',Menlo,monospace}"
            ".bar a{color:#2F6B8F;text-decoration:none}</style>"
            "</head><body>"
            "<div class='bar'><a href='./'>&larr; back to document</a></div>"
            f"<article class='prose'>{article_html}</article>"
            "</body></html>"
        )
        return Response(page, mimetype="text/html")

    @app.route("/assets/<path:asset_name>")
    def assets(asset_name: str) -> Response:
        return send_from_directory(_ASSETS_DIR, asset_name)

    @app.route("/api/doc")
    def api_doc() -> Response | tuple[Response, int]:
        # The in-place refresh payload: after a mutation the page re-renders
        # from this instead of reloading, so scroll and fold state survive
        try:
            spec_store = _resolved_store()
        except DocumentNotAllowedError as e:
            return jsonify({"error": str(e)}), 404
        return jsonify(_document_payload(spec_store))

    @app.route("/api/files")
    def api_files() -> Response:
        return jsonify({"files": document_registry.list_markdown_files()})

    @app.route("/api/stamp")
    def api_stamp() -> Response | tuple[Response, int]:
        # The cheap poll target behind live refresh (#t34): the document's
        # on-disk identity, no parsing or rendering. The page re-fetches
        # the full document only when this changes.
        try:
            spec_store = _resolved_store()
        except DocumentNotAllowedError as e:
            return jsonify({"error": str(e)}), 404
        file_stat = spec_store.spec_path.stat()
        return jsonify({"stamp": f"{file_stat.st_mtime_ns}-{file_stat.st_size}"})

    @app.route("/api/notify", methods=["POST"])
    def notify() -> Response | tuple[Response, int]:
        # The notify button: stamp the document's version, drop a durable
        # event an agent can listen for, and nudge the configured agent
        try:
            spec_store = _resolved_store()
        except DocumentNotAllowedError as e:
            return jsonify({"error": str(e)}), 404
        payload = request.get_json(silent=True) or {}
        # an optional rider on the press: prioritization, out-of-band asks
        custom_message = str(payload.get("message", "")).strip()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        version = spec_store.record_notification(timestamp=timestamp)
        display_path = document_registry.display_path(_requested_doc_param())
        notifications_dir.mkdir(parents=True, exist_ok=True)
        instruction = custom_message or "Please sweep the document."
        # the document's own frontmatter names its agent; the configured
        # default only covers documents that don't
        frontmatter = parse_spec_document(spec_store.read_document_text()).frontmatter
        target_agent = (
            frontmatter.notify_agent if frontmatter is not None and frontmatter.notify_agent else None
        ) or default_notify_agent
        event = {
            "kind": "notify",
            "doc": display_path,
            "version": version,
            "timestamp": timestamp,
            "message": instruction,
            "agent": target_agent or None,
        }
        event_name = f"{timestamp.replace(':', '').replace('-', '')}-{display_path.replace('/', '__')}-v{version}.json"
        (notifications_dir / event_name).write_text(json.dumps(event, indent=2) + "\n")
        if agent_nudger is not None and target_agent:
            # the guide pointer makes the nudge self-documenting for agents
            # that have never seen the thread format
            agent_nudger(
                target_agent,
                f"spec-workbench: '{display_path}' was marked notified (v{version}). {instruction}"
                f" (Format and sweep conventions: {QUICKSTART_PATH})",
            )
        return jsonify({"ok": True, "version": version, "timestamp": timestamp})

    @app.route("/api/notes", methods=["POST"])
    def create_note() -> Response | tuple[Response, int]:
        try:
            spec_store = _resolved_store()
        except DocumentNotAllowedError as e:
            return jsonify({"error": str(e)}), 404
        payload = request.get_json(silent=True) or {}
        anchor_block_id = str(payload.get("anchor", "")).strip()
        heading_text = str(payload.get("heading", "")).strip()
        quote_text = str(payload.get("quote", "")).strip()
        has_block_lines = "sline" in payload and "eline" in payload
        message_text = str(payload.get("text", "")).strip()
        if not message_text or not (anchor_block_id or heading_text or (has_block_lines and quote_text)):
            return jsonify({"error": "Comment text and a target (anchor, heading, or selection) are required"}), 400
        try:
            if anchor_block_id:
                new_note_id = spec_store.create_thread(
                    anchor_block_id=anchor_block_id,
                    author=ui_author_name,
                    date=_current_utc_stamp(),
                    message_text=message_text,
                )
            elif heading_text:
                new_note_id = spec_store.create_thread_on_heading(
                    heading_text=heading_text,
                    author=ui_author_name,
                    date=_current_utc_stamp(),
                    message_text=message_text,
                )
            else:
                new_note_id = spec_store.create_thread_on_block(
                    start_line_idx=int(payload["sline"]),
                    end_line_idx=int(payload["eline"]),
                    block_text_prefix=str(payload.get("prefix", "")),
                    quote=quote_text,
                    context_before=str(payload.get("before", "")),
                    context_after=str(payload.get("after", "")),
                    author=ui_author_name,
                    date=_current_utc_stamp(),
                    message_text=message_text,
                )
        except AnchorNotFoundError:
            return jsonify({"error": f"No block {{#{anchor_block_id}}} in the document"}), 404
        except HeadingNotFoundError:
            return jsonify({"error": f"No heading titled '{heading_text}' in the document"}), 404
        except DocumentChangedError:
            return jsonify({"error": "The document changed since this page loaded -- reload and retry"}), 409
        except QuoteResolutionError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True, "id": new_note_id})

    @app.route("/api/notes/<note_id>/reply", methods=["POST"])
    def reply(note_id: str) -> Response | tuple[Response, int]:
        try:
            spec_store = _resolved_store()
        except DocumentNotAllowedError as e:
            return jsonify({"error": str(e)}), 404
        payload = request.get_json(silent=True) or {}
        message_text = str(payload.get("text", "")).strip()
        if not message_text:
            return jsonify({"error": "Reply text is empty"}), 400
        try:
            spec_store.append_reply(
                note_id=note_id,
                author=ui_author_name,
                date=_current_utc_stamp(),
                message_text=message_text,
            )
        except NoteNotFoundError:
            return jsonify({"error": f"No note #{note_id} in the document"}), 404
        return jsonify({"ok": True})

    @app.route("/api/notes/<note_id>/state", methods=["POST"])
    def state(note_id: str) -> Response | tuple[Response, int]:
        try:
            spec_store = _resolved_store()
        except DocumentNotAllowedError as e:
            return jsonify({"error": str(e)}), 404
        payload = request.get_json(silent=True) or {}
        raw_state = str(payload.get("state", ""))
        try:
            new_state = NoteState(raw_state.upper())
        except ValueError:
            return jsonify({"error": f"Unknown state '{raw_state}'"}), 400
        if new_state not in _UI_ALLOWED_STATES:
            return jsonify({"error": "Suggestion accept/reject arrives with suggestion mode (F2)"}), 400
        try:
            spec_store.set_note_state(note_id=note_id, new_state=new_state, date=_current_utc_date())
        except NoteNotFoundError:
            return jsonify({"error": f"No note #{note_id} in the document"}), 404
        return jsonify({"ok": True})

    @app.route("/health")
    def health() -> Response:
        return Response('{"status": "ok"}', mimetype="application/json")

    return app


def _nudge_agent_via_mngr(agent_name: str, message: str) -> None:
    # Fire-and-forget: mngr's delivery confirmation can take seconds and must
    # not block the request; output lands in DATA_DIR/notify.log.
    # --start wakes a stopped agent -- a notify press must reach an agent
    # even when no chat session is currently running
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / "notify.log", "a") as log_file:
        subprocess.Popen(
            ["uv", "run", "mngr", "message", agent_name, "--start", "-m", message],
            stdout=log_file,
            stderr=log_file,
        )


def main() -> None:
    document_registry = DocumentRegistry(workspace_root=WORKSPACE_ROOT, default_document=SPEC_PATH)
    app = create_app(
        document_registry=document_registry,
        ui_author_name=UI_AUTHOR_NAME,
        notifications_dir=DATA_DIR / "notifications",
        agent_nudger=_nudge_agent_via_mngr,
        default_notify_agent=NOTIFY_AGENT,
    )
    run_simple(
        "127.0.0.1", PORT, app, threaded=True, use_reloader=False, use_debugger=False
    )


if __name__ == "__main__":
    main()
