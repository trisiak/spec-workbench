# Spec Workbench quickstart

Spec Workbench turns any plain markdown file into a living document with
margin comments, Google-Docs style. Everything -- comments, replies,
suggestions, statuses -- lives *inside the file* as ordinary blockquote
blocks, so the document stays readable and diffable in git and needs no
database. This page is the reference for the on-disk format and the
collaboration loop; it is what an agent (or a person editing by hand)
needs to work with such a file correctly.

## The collaboration loop

1. A person opens a file in the workbench (the default document, the
   "open file..." picker, or `?doc=<root-relative-path>`), selects text
   or a block, and comments. Comments are written straight into the
   markdown file on disk -- the uncommitted working tree is the person's
   contribution.
2. When ready for the agent, they press **notify agent**. The press
   stamps a version into the file's frontmatter, drops a durable JSON
   event, and sends the agent a chat message. The dropdown half of the
   button attaches a custom instruction to the press (prioritization,
   out-of-band asks); the default instruction is "Please sweep the
   document."
3. The agent **sweeps**: reads everything new since its last sweep,
   replies inside the threads, does the work the threads ask for,
   updates the `agent-seen` cursor, and commits. The app itself never
   touches git; committing is the agent's job.
4. The person reads the replies (the "new for you" counter and arrows
   jump through them) and **resolves** threads they are satisfied with.
   A thread is resolved by its owner -- the agent does not resolve
   threads the person opened.
5. Anything reported out-of-band (e.g. in chat) that belongs to the
   document gets transcribed by the agent into a thread, with the
   message stamp marked `via chat`, so the document stays the single
   record.

## The format on disk

### Frontmatter

Optional YAML-style frontmatter carries document metadata and the two
cursors the loop runs on:

```
---
app: spec-workbench
status: in-progress
notify-agent: my-agent              # who this document's notify presses reach
agent-seen: 2026-08-21T06:15:48Z    # agent's sweep cursor (agent updates)
notified: v8 (2026-08-21T06:06:25Z) # notify presses so far (app updates)
---
```

A plain file with no frontmatter is fine -- the app creates it on the
first notify press.

`notify-agent` names the agent responsible for this document, so
different documents can belong to different agents. When the key is
absent, the press falls back to the app's configured default target
(the `SPEC_WORKBENCH_NOTIFY_AGENT` environment variable); with neither
set, the press still stamps the document and writes its durable event,
but nudges no one.

### Threads

A thread is a blockquote block. The header line names the thread,
anchors it, and carries its state; each message is a bold attribution
followed by the text:

```
> [!thread] #t3 on {#some-anchor} "quoted phrase" -- open
> **maciek (2026-08-20 17:26):** Shouldn't this handle the empty case?
> **agent (2026-08-20 18:02):** Good catch -- fixed, see the new guard
> below the loop.
```

Header grammar:

```
> [!thread] #tN [on {#block-id} ["quoted phrase"]] -- open|resolved [(YYYY-MM-DD)]
```

- `#tN` is the thread id, unique within the file. When creating one,
  scan the whole file for the highest `#tN` mentioned and use the next
  number -- ids are never reused.
- `on {#block-id}` ties the thread to the block carrying that anchor;
  the optional `"quoted phrase"` narrows it to a phrase inside the
  block (the phrase may itself contain quotation marks).
- The state date is day-only and records when the state last changed.

Message lines:

```
> **author (YYYY-MM-DD HH:MM):** text
```

- Stamps are UTC, minute-precise -- the "new"/pending counters depend
  on them. Day-only stamps are tolerated and read as the start of that
  day.
- A message transcribed from chat appends `, via chat` inside the
  parenthesis: `**agent (2026-08-20 18:02, via chat):** ...`
- Continuation lines of a message are further `> ` lines without a bold
  attribution.

### Suggestions

A suggestion is a proposed edit, anchored like a thread, with a diff
body and an author on the header:

```
> [!suggest] #s1 on {#some-anchor} "old phrase" by agent (2026-08-14) -- open
> ```diff
> -the old phrase
> +the improved phrase
> ```
```

States are `open`, `accepted`, or `rejected` (with a day-only date).

### Anchors

A block is made addressable by a trailing `{#id}` on its last line:

```
The retry policy backs off exponentially. {#retry-policy}
```

The app writes anchors automatically when a comment targets a block
that has none; when editing by hand, add one wherever a thread needs to
point. Anchor ids are lowercase words joined by hyphens.

## Sweeping (the agent side)

- Find what is new by diffing the file against its last-committed state
  and by the `agent-seen` cursor; the notify press's chat message tells
  you which file and carries any custom instruction.
- Reply *inside* the threads -- substance belongs in the document, chat
  stays terse. Use your author name and a minute-precise UTC stamp.
- Do the work the threads ask for; report what you did as a reply in
  the same thread.
- Leave `open`/`resolved` transitions on a thread to the person who
  opened it. You may resolve threads you yourself opened.
- Transcribe chat-reported issues into threads (marked `via chat`)
  before addressing them.
- Finish by setting `agent-seen` to the current UTC time and
  committing the file.
- Durable notify events (one JSON file per press, with the document
  path, version, timestamp, and instruction) are written under the
  app's data directory in `notifications/` -- a listenable contract if
  chat delivery ever fails.
- To put a document in front of the person -- when you start working on
  a spec, or when they ask you to open one -- run
  `uv run open-spec <root-relative-path>` from the repo root. It opens
  the workbench tab if needed, points it at the file, and focuses it,
  so nobody has to use the in-app file picker.

## Reading the header counters

- **notify agent (N)** -- N of the person's messages are newer than the
  last notify press: work the agent has not yet been told about.
  Pressing the button acknowledges them.
- **N new for you** -- N agent messages arrived since the last press;
  the arrows step through them, newest state first. A message stops
  counting as new once someone else replies after it or its thread is
  resolved.
