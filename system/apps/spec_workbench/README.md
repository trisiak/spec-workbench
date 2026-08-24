# spec-workbench

Living spec documents: render any markdown file with margin threads,
suggestions, and statuses, Google-Docs style, with everything stored inline
in the file itself (plain markdown, diffable, no database).

- Format and workflow reference: `src/spec_workbench/assets/quickstart.md`
  (also served rendered at the app's `/quickstart` route, linked from the
  document footer).
- Open a specific file: `?doc=<workspace-root-relative path>` or the
  in-app "open file..." picker. Agents can surface a file in the user's
  open tab with `uv run open-spec <path>` (see the quickstart).
- The notify button stamps the document, writes a durable JSON event under
  the app's data dir, and nudges the configured agent
  (`SPEC_WORKBENCH_NOTIFY_AGENT`, default `meta-markdown`) via
  `mngr message`.
