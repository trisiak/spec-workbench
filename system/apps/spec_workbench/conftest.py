"""Fixtures for spec-workbench's end-to-end browser tests.

The interactive bugs this app has shipped (suppressed confirm dialogs, fold
state resetting, the caret never landing in the draft box) only reproduce
inside the workspace shell, which embeds the app in a *sandboxed* iframe.
These fixtures boot a real threaded server on a real port and drive it with
a real browser inside an iframe carrying the workspace's exact sandbox
attributes, so those behaviors are codified as tests instead of re-reported.

Browser resolution: CI installs Playwright's managed chromium
(`playwright install`); local workspaces ship the Fortress build instead.
Tests skip cleanly when neither is present.
"""

import os
import socket
import threading
from collections.abc import Callable
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Frame
from playwright.sync_api import Page
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

from spec_workbench.registry import DocumentRegistry
from spec_workbench.runner import create_app
from spec_workbench.testing import make_sample_document_text

_FORTRESS_EXECUTABLE = Path("/opt/fortress/tilion-fortress/tilion")

# The exact sandbox the workspace shell puts on app iframes (IframePanel.js).
# Note the absence of allow-modals: window.confirm() is silently suppressed.
WORKSPACE_IFRAME_SANDBOX = "allow-scripts allow-same-origin allow-forms allow-popups"


def _browser_launch_candidates() -> list[dict[str, Any]]:
    """Launch-kwarg candidates, most-preferred first; each may fail on a
    given host (e.g. a managed cache holding the full chromium but not the
    headless shell), so the fixture tries them in order."""
    # --no-sandbox variants: chromium's sandbox needs unprivileged user
    # namespaces, absent under some container runtimes here; these tests
    # only ever render our own local pages.
    # Fortress leads when installed: the managed full-chromium build has
    # proven flaky under this container runtime (launches, then hangs
    # mid-suite), while CI hosts have no Fortress and use the managed pair.
    candidates: list[dict[str, Any]] = []
    if _FORTRESS_EXECUTABLE.is_file() and os.access(_FORTRESS_EXECUTABLE, os.X_OK):
        candidates.append({"executable_path": str(_FORTRESS_EXECUTABLE), "args": ["--no-sandbox"]})
    candidates.append({})                     # managed headless shell (CI's install)
    candidates.append({"channel": "chromium", "args": ["--no-sandbox"]})
    return candidates


@pytest.fixture(scope="session")
def e2e_browser() -> Generator[Browser, None, None]:
    with sync_playwright() as playwright:
        browser: Browser | None = None
        for launch_kwargs in _browser_launch_candidates():
            try:
                browser = playwright.chromium.launch(timeout=15000, **launch_kwargs)
                # a launch can "succeed" and still be unusable (e.g. the
                # sandbox dies on first use); prove it with a real page
                probe_context = browser.new_context()
                probe_context.new_page()
                probe_context.close()
                break
            except PlaywrightError:
                # do NOT close() a crashed browser -- that call can hang;
                # abandon it and let sync_playwright's exit reap it
                browser = None
                continue
        if browser is None:
            pytest.skip("No launchable chromium (neither Playwright-managed nor Fortress)")
        yield browser
        browser.close()


@pytest.fixture
def e2e_page(e2e_browser: Browser) -> Generator[Page, None, None]:
    # Wide viewport so the two-column layout (prose + margin rail) is active
    context = e2e_browser.new_context(viewport={"width": 1400, "height": 1000})
    yield context.new_page()
    context.close()


@pytest.fixture
def e2e_workspace(tmp_path: Path) -> Path:
    """A throwaway document root: the sample spec plus a second plain markdown file."""
    (tmp_path / "spec.md").write_text(make_sample_document_text())
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "other.md").write_text("# Other Notes\n\nA plain file with no threads yet.\n")
    return tmp_path


@pytest.fixture
def e2e_server(e2e_workspace: Path) -> Generator[str, None, None]:
    """The real app on a real port, serving the throwaway workspace. Yields the base URL."""
    registry = DocumentRegistry(
        workspace_root=e2e_workspace, default_document=e2e_workspace / "spec.md"
    )
    app = create_app(
        document_registry=registry,
        ui_author_name="maciek",
        notifications_dir=e2e_workspace / ".notifications",
    )
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = make_server("127.0.0.1", port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture
def open_in_workspace_frame(e2e_page: Page, e2e_server: str) -> Callable[..., Frame]:
    """Load an app URL inside a same-origin iframe with the workspace's sandbox attrs.

    The parent page must be a real http origin (not about:blank) or the
    browser downgrades the frame's context; /health serves that role.
    """

    def _open(path: str = "/") -> Frame:
        e2e_page.goto(e2e_server + "/health")
        e2e_page.evaluate(
            """([src, sandbox]) => {
                document.body.innerHTML = "";
                document.body.style.margin = "0";
                const frame = document.createElement("iframe");
                frame.id = "app-frame";
                frame.setAttribute("sandbox", sandbox);
                frame.style.width = "1380px";
                frame.style.height = "980px";
                frame.style.border = "0";
                frame.src = src;
                document.body.appendChild(frame);
            }""",
            [e2e_server + path, WORKSPACE_IFRAME_SANDBOX],
        )
        frame_element = e2e_page.wait_for_selector("#app-frame")
        frame = frame_element.content_frame()
        assert frame is not None
        frame.wait_for_selector("#article")
        return frame

    return _open
