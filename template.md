---
title: "Spec Workbench"
description: "Living markdown documents with Google-Docs-style margin comments: annotate any file, notify your agent, and collaborate through threads stored inline in plain markdown in git"
thumbnail: "template.svg"
version: v3
format: v2
---

# Spec Workbench

This file is the manifest for the **Spec Workbench** template (slug:
`spec-workbench`). It is the one document a future agent reads to understand,
present, and adapt this template. If you are an agent in a mind that was
created from this template, this file is your script: read all of it, then
follow "How to adapt it" below.

## What it is

Spec Workbench turns any plain markdown file into a living, collaboratively
annotated document -- the Google-Docs commenting model (comment, thread,
reply, resolve, suggest) applied to files that live in your git repo. You open
a document in a web view, select a phrase or a block, and leave a margin
comment; you and your agent then work the document together through threads
anchored to the exact text they are about. The twist is that every comment,
reply, suggestion, and status is written *back into the markdown file itself*
as ordinary blockquotes -- there is no database, so the file stays readable,
diffable, and versioned in git, and it degrades gracefully in any plain
markdown renderer. When you are ready for your agent to act, one "notify agent"
button stamps the document and pings the agent to sweep it. What you see when
it is running is a two-column reading view: your prose on the left, the live
thread margin on the right, with counters telling you what is new for you and
what you have not yet sent to the agent.

## How it works

The snapshot includes these paths (each is a repo-root-relative path copied
from the original mind onto a clean default-workspace-template base):

- `system/apps/spec_workbench`
- `docs/specs/spec_workbench.md`
- `docs/specs/how_to_use_spec_workbench.md`

`system/apps/spec_workbench` is the whole app: a Flask web service (the app's
`spec-workbench` package) that renders any markdown file under the workspace
root with a margin of anchored threads, suggestions, per-section statuses, and
"new"/"pending" counters, plus the notify-agent button. It bundles its own
format-and-workflow guide (`src/spec_workbench/assets/quickstart.md`, served
rendered at the `/quickstart` route) so any install is self-documenting, and it
ships an `open-spec` CLI (`uv run open-spec <path>`) that an agent uses to
surface a document in the user's open tab.

`docs/specs/spec_workbench.md` is the app's own living spec -- the document that
describes the app and is edited through it. It is included as the deep worked
example of the on-disk format; the bundled intro document
(`docs/specs/how_to_use_spec_workbench.md`) is the default that loads when no
`?doc=` is given. Its remaining threads and its dev history show what a real
Spec Workbench document looks like in practice.

At runtime, the `[program:spec-workbench]` entry in `system/supervisord.conf`
starts the app on boot. It first runs `system/scripts/forward_port.py` to
register the service under the name `spec-workbench` on port 8082, then execs
`uv run spec-workbench`. The system_interface workspace UI proxies it at
`/service/spec-workbench/`, so it appears as a normal tab. Everything the app
writes at runtime -- durable notify events, logs -- lives under
`data/.apps/spec-workbench/` (gitignored); the annotations themselves are
written straight into the markdown files, and the app never touches git.
Pressing notify shells out to `uv run mngr message` to nudge the target agent,
which is the stock template's own agent-messaging command.

## Recipe

This template is version `v3`. It is not a fork of the
workspace it came from -- it is DERIVED from it by a recipe: include these
paths, leave these out, apply these published-version rules. An update re-runs
the recipe against the current workspace and publishes the result as the next
version, so anything excluded stays excluded even though it still exists in the
source workspace.

The recipe is machine-read, so it lives in the sibling
[`template.toml`](template.toml) -- its `[recipe]` table -- along with
the structured requirements and the environment this template needs
installed. That file is authoritative for all of it; this one holds the prose.

## Requirements

Everything the adopting mind must deal with before this template is really
theirs. Two kinds of entry, handled at different times:

- **Activation** -- what must be SET UP before anything runs, in the
  machine-readable `requires_` forms below. The adopting agent acts on these
  ITSELF, first, before asking anything.
- **Adaptation** -- what must be DECIDED or REWIRED, in prose. Worked through
  interactively with the user, after activation.

**Activation -- none.** This app reaches no external service, needs no
secrets, and makes no LLM calls, so there is nothing for the adopting agent to
set up before it runs: no `requires_permission`, no `requires_secret`, no
`requires_llm`. It boots and works as published. (The notify button shells out
to `uv run mngr message`, which is part of the stock template, not an external
integration.)

**Adaptation.** Three things an adopter decides once the app is running, none
of which block boot:

- **Notify fallback target.** When you press "notify agent" the app messages an
  agent to sweep the document. Each document names its own agent through the
  `notify-agent:` key in its frontmatter; documents without that key fall back
  to whatever the `SPEC_WORKBENCH_NOTIFY_AGENT` environment variable names on
  the supervisord program entry. The published entry ships with no such
  variable, so a press on a document with no `notify-agent:` key still stamps
  the document and writes its durable event but nudges no one. To route those
  presses, set `notify-agent:` in the document, or add
  `SPEC_WORKBENCH_NOTIFY_AGENT=<your-agent-name>` to the program's
  `environment=` line in `system/supervisord.conf`.
- **Comment author name.** Comments and replies made through the web UI are
  signed `user` by default. To sign them with a real name, set
  `SPEC_WORKBENCH_AUTHOR=<name>` on the same supervisord program entry.
- **Default document.** With no `?doc=` in the URL the app opens the bundled
  how-to-use intro (`docs/specs/how_to_use_spec_workbench.md`) as the default
  document. Point it at your own document by setting `SPEC_WORKBENCH_DOC`
  to a workspace-root-relative path on the supervisord program entry (any
  markdown file under the workspace root can also be opened ad hoc via the
  in-app "open file..." picker or `?doc=<path>`).

## Environment

What this template needs INSTALLED, beyond what the template already has.
Declared in `template.toml`'s `[environment]` table; an adopting mind
converges it at ITS OWN pinned apt snapshot timestamp, so package versions come
out consistent with the rest of that mind's environment rather than frozen to
whatever this publisher happened to have.

Nothing extra -- runs on the stock workspace environment. The app's only
dependencies are Python packages (flask, flask-sock, markdown-it-py, werkzeug)
declared in its own `system/apps/spec_workbench/pyproject.toml` and resolved by
`uv sync`; it shells out to nothing beyond `uv`/`mngr`, which the stock
template already provides.

## How to adapt it

Instructions for the NEXT agent -- the one adapting this template into a
new mind. This is the `use-template` skill's template path; in short:

1. Read this entire file first, especially "Requirements" below. It holds two
   kinds of entry and they are handled at different times: the machine-readable
   `requires_` lines are ACTIVATION (set them up before anything runs), and
   the prose bullets are ADAPTATION (decide or rewire them afterwards).
2. Present the template to the user in plain, non-technical language: what
   it is, what it does, and what it needs from them (name the activation
   requirements).
3. Ask whether they want to use the same connectors (e.g. their own Slack).
   If YES: ACTIVATE FIRST -- initiate every `requires_permission` line NOW
   via a latchkey permission request (see the `latchkey` skill; the request
   opens the approval/login flow in the minds app), wire up any
   `requires_secret` values, start the services, and get the app showing
   THE USER'S OWN DATA. Done for a data-backed app means the user can open it
   and see their own data -- NOT that a service starts or an endpoint returns
   200. Then tell them it is live and to take a look.
4. Only AFTER that (or immediately, if they chose different connectors -- the
   swap is then the first adaptation) ask: "How do you want to adapt it?"
5. Work through each requirement interactively, one at a time. Translate each
   into plain language, ask for a decision only when you genuinely need one,
   and resolve the obvious ones yourself.
6. When done, append a dated entry to "Adaptation history" below (never
   rewrite earlier entries) and commit.

## Publication history

This template's changelog: what each published version changed. The PUBLISHER
appends one entry per version (newest last); earlier entries are never rewritten.
This is distinct from "Adaptation history" below, which is the ADOPTERS' log.

### v1 (2026-08-24) -- first release: the Spec Workbench app (margin-threaded markdown documents with the notify-agent loop, the bundled quickstart guide, and the open-spec CLI), wired to run on boot, plus its own living spec as the worked-example default document.

### v2 (2026-08-24) -- the default document is now a bundled "how to use this" intro the adopter can annotate immediately (the app's own spec stays included as the worked example); comments preserve line breaks and paragraph gaps; story-list status badges know the full vocabulary; example spec refreshed.

### v3 (2026-08-25) -- comment colors follow role (red reserved for the workspace's human author; any agent name renders blue, with real names in the header legend); the notify dropdown names the agent a press will reach; a quiet "document changed -- refresh" notice appears when the file changes on disk, applying only on click; example spec refreshed.

## Adaptation history

Each mind that adapts this template appends one dated entry below. Earlier
entries are never rewritten.
