"""Surface a document in the user's spec-workbench tab from the command line.

``uv run open-spec <path>`` is the agent-facing entry point: when an agent
starts working on a spec, or the user asks for one in chat, this opens the
workbench tab (if it isn't open already), points it at the document, and
brings it to the front -- no trip through the in-app file picker. Run it
from the repo root: the layout script it drives resolves its service
registry relative to the cwd, and narrates each action on stderr.
"""

import argparse
import subprocess
import sys
from collections.abc import Callable
from urllib.parse import quote

from spec_workbench.errors import DocumentNotAllowedError
from spec_workbench.registry import DocumentRegistry
from spec_workbench.runner import SPEC_PATH
from spec_workbench.runner import WORKSPACE_ROOT

_LAYOUT_SCRIPT = "system/scripts/layout.py"
_SERVICE_NAME = "spec-workbench"


def surface_document(
    document_registry: DocumentRegistry,
    requested_path: str,
    layout_runner: Callable[[list[str]], int],
) -> int:
    """Open + retarget + focus the workbench tab onto the document; returns an exit code.

    Raises DocumentNotAllowedError before touching the layout when the path
    is outside the workspace root, not markdown, or missing.
    """
    display_path = document_registry.display_path(requested_path)
    target_url = f"service:{_SERVICE_NAME}/?doc={quote(display_path)}"
    # ``open`` is a no-op when the tab already exists; ``replace-url``
    # points the iframe at the document (reloading it); ``focus`` brings
    # the tab to the front either way (open's no-op path does not).
    for layout_args in (
        ["open", _SERVICE_NAME],
        ["replace-url", _SERVICE_NAME, target_url],
        ["focus", _SERVICE_NAME],
    ):
        exit_code = layout_runner(layout_args)
        if exit_code != 0:
            return exit_code
    return 0


def _run_layout_script(layout_args: list[str]) -> int:
    return subprocess.run([sys.executable, _LAYOUT_SCRIPT, *layout_args]).returncode


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Open a markdown file in the user's spec-workbench tab"
    )
    parser.add_argument("path", help="Path to the markdown file, relative to the workspace root")
    args = parser.parse_args()
    document_registry = DocumentRegistry(
        workspace_root=WORKSPACE_ROOT, default_document=SPEC_PATH
    )
    try:
        sys.exit(surface_document(document_registry, args.path, _run_layout_script))
    except DocumentNotAllowedError as e:
        parser.error(str(e))
