---
# This is the spec of the Spec Workbench app itself, kept as a live worked example -- its threads are the app's own dev history, not adopter documentation.
app: spec-workbench          # name settled in #t1
status: building             # drafting -> building -> maintaining
notify-agent:               # set to your agent's name to route this document's notify presses
agent-seen: 2026-08-24T18:13:59Z
notified: v10 (2026-08-24T18:11:59Z)
---

# Spec Workbench

An editable markdown document is the single artifact for planning, describing,
and tracking an app. Humans and agents collaborate on it through anchored
threads, diff-suggestions, and per-section status -- the Google-Docs
collaboration model (comment, thread, resolve, suggest, accept) applied to a
plain markdown file that lives in git.

This file is the first such document: it describes the app that renders it,
and is edited through that very app. The human comments, replies, and
resolves in the rendered view (or in any editor, or via chat -- both stay
valid); the agent sweeps the file, replies in threads, applies accepted
suggestions, updates statuses, and commits. Every gap felt while using it
becomes a feature below.

## Why                                                       {#why}

Chat is linear and ephemeral. A document is spatial and persistent: multiple
conversations proceed in parallel as threads anchored to the text they are
about, decisions harden into prose, and the same artifact that plans the work
tracks its implementation. The document is the workspace; chat becomes the
notification channel.

## Document model                                            {#doc-model}

- One markdown file per app, all gathered under `docs/specs/` in the
  workspace's single git repo (settled in #t2). Git supplies history,
  authorship, and dates for the prose; entries that need finer lineage
  (thread messages, suggestions) carry their own author and timestamp.
- The file must degrade gracefully: in any plain markdown renderer (GitHub,
  an editor preview) threads and suggestions appear as readable blockquotes,
  never garbage.

### Anchors                                                  {#anchors}

Everything attachable (threads, suggestions) points at an anchor:

- `{#id}` -- a stable id suffix on a heading or block (Pandoc attribute
  syntax). Ids are assigned lazily, when something first needs to point at
  that block, and are never reused after deletion.
- `{#id} "quoted text"` -- a phrase within the block, for word- or
  phrase-level precision. The quote must be unique within the block; extend
  it until it is, or pin an instance with an inline anchor (next bullet).
- `[some text]{#id}` -- an inline anchor on one specific instance, wrapped
  in place (Pandoc's span form of the same attribute syntax). The escape
  hatch for repeated content where no amount of quote-extending
  disambiguates: mark the instance you mean and anchor `on {#id}` directly.
  Sturdier than an occurrence index ("2nd of 3"), which silently rots when
  instances are added or removed above it. Plain renderers show the wrapper
  literally, so it is reserved for when it is actually needed.
- Suggestions and threads have ids too (`#s1`, `#t1`) and are themselves
  valid anchor targets. A thread anchored on a suggestion is a comment
  thread on that proposed change; with a quote it targets individual words
  inside the proposal. Nesting falls out of the anchor grammar rather than
  from physically nesting blocks.
- If an anchored block is deleted, its threads float up to the nearest
  surviving ancestor section rather than disappearing.

### Threads                                                  {#threads}

- Placement: a thread block sits immediately after the block it anchors to
  (for `{#id} "quote"` anchors, after the block containing the quote). The
  rendered view (F1) shows threads in a margin regardless of file position,
  so in-file placement exists purely for the raw reading experience -- and
  there, locality wins: reading or editing a section surfaces its open
  questions. An overview of everything open is a view concern (the F3
  rollup), not a storage concern. Threads with no textual anchor (F5 app
  annotations) collect in the Feedback appendix instead.
- States: `open` or `resolved (date)`. Resolving collapses the thread in the
  rendered view; the block stays where it is so the thread can be continued
  (reopened) later. Resolved threads are kept indefinitely; an occasional
  "bake" commit may prune long-resolved ones to keep the file lean, with git
  as the full archive. No prescribed cadence or process -- baking happens
  when the clutter bothers someone.
- New messages are appended, always attributed and stamped -- date plus
  time of day in UTC (e.g. `2026-08-19 23:59`) since 2026-08-19;
  day-only stamps remain valid and compare as start of day. A position taken
  in chat rather than in-file is transcribed into the thread by the agent,
  paraphrased and marked `via chat`.

### Suggestions                                              {#suggestions}

A suggestion proposes an edit instead of making it. Two forms, sized to the
edit:

- *Phrase form* -- the anchor's `"quote"` selects the text to change and the
  body is simply its replacement. Right-sized for typos, single words, and
  short rewordings; to insert next to existing text, include the quoted text
  in the replacement. No diff ceremony:

> [!suggest] #s2 on {#suggestions} "(example phrase)" by agent (2026-08-14) -- open
> (example phrase, replaced wholesale)

- *Diff form* -- the body is a fenced diff against the anchor block, for
  multi-line or structural edits (a whole new paragraph is an all-additions
  diff):

> [!suggest] #s0 on {#suggestions} by agent (2026-08-14) -- open
> ```diff
> -(Example target sentence.)
> +(Example target sentence, amended by this very suggestion.)
> ```

- States: `open`, then `accepted (date)` or `rejected (date)`. Accepting
  applies the change and removes the suggestion block (the applied text is
  now simply the document; git records the transition). Rejecting removes
  the block too. Threads anchored on the suggestion resolve with it -- their
  content survives in git history.
- Threads and suggestions share one anchor grammar: the anchor selects the
  target (block, phrase, or another thread/suggestion); the block type says
  whether you are discussing it or proposing a change to it.

### Statuses                                                 {#statuses}

- Feature sections carry an inline status in their heading:
  `idea -> planned -> building -> done -> verified`.
- The document's overall status lives in the frontmatter.
- Status changes are made by whoever does the work (usually the agent) and
  land as ordinary edits, so git dates them.

### Lineage (what has the agent seen?)                       {#lineage}

- Every thread message and suggestion is stamped with author and date.
- The frontmatter `agent-seen` timestamp is the agent's cursor: on each
  sweep, anything stamped after it is new; the agent handles it and bumps
  the cursor. `git diff` since the agent's last commit is the fallback for
  unstamped prose edits.
- This makes the pull model sufficient: no event system needed. The
  "notify agent" button (F4) stamps the document and nudges the right chat.
- Hand-written entries owe no ceremony: they may arrive unstamped, unanchored,
  or with an id from the wrong namespace (all three happened on day one). The
  sweep normalizes -- assigns the id, anchor, and stamp -- and never alters
  the words. The app's editor (F1/F2) does this at write time instead.

## Features

### F0. The format, used by hand -- `done`                   {#f0}

This file, maintained manually: human comments and suggests in-file or via
chat; agent sweeps, replies, applies, updates statuses. The exercise that
validated the format before any code existed -- completed once the rendered
view became the primary surface; hand-editing remains a supported door.

### F1. Rendered document with margin threads -- `building`  {#f1}

Web view renders the markdown with threads in a right margin, Google-Docs
style. Open threads are prominent; resolved ones collapse. Reply and resolve
from the UI; the UI writes the same file the agent reads.

Once this exists it is the user's *primary* surface (stated via chat,
2026-08-14): the editor does the right things automatically -- ids, stamps,
anchors, placement -- so format ceremony is machine work, never the user's.
Hand-editing the raw file stays valid forever; the sweep normalizes it.

Interaction model (via chat, 2026-08-14): notes fold and unfold
independently of resolution; one note at a time holds *focus* -- it aligns
exactly to the line it refers to while the others yield around it; clicking
annotated text on the left focuses its note and puts the cursor in the
reply field. Folded notes render quiet and gray; a resolved note takes no
replies until reopened. New threads open from the page itself (the "+" on
any anchored section); the view assigns the id, stamp, and placement. The
raw view stays one click away (syntax coloring is a noted nicety, not yet
built). {#interaction-model-via-chat}

The app never touches git (via chat, 2026-08-14): everything it writes
stays uncommitted, so the working tree cleanly separates the user's
contributions -- which matters more once inline editing lands -- and the
agent's sweep is what commits.

User stories -- the running list of smaller UX units this feature
accretes (#t6). Deliberately plain bullets: no table or story grammar
(#t8, settled 2026-08-17). {#user-stories-the}

- `done` drafted comments survive losing focus; only Cancel discards
  (frontend-only draft state for now; a first-class DRAFT state is a
  listed candidate) (#t6) {#done-drafted-comments}
- `done` comment and reply boxes grow with their content (#t6)
- `done` every heading takes comments; anchor ids are minted lazily on
  first use (#t7)
- `done` folded notes render gray; replies require an open note; the
  whole note header folds on click
- `done` phrase-level comments: select text, comment on exactly those
  words; ids minted lazily for paragraphs and list items; ambiguous
  quotes extended with their real neighbors until unique; quoted
  phrases render highlighted in the opener's ink and pin their notes.
  Known gap, parked at maciek's call (#t10, 2026-08-17): in the real
  workspace shell the caret still does not land in the box, though
  scripted-frame checks pass {#done-phrase-level-comments}
- `done` end-to-end browser tests drive the app inside a frame carrying
  the workspace shell's exact sandbox, codifying every reported behavior
  (suppressed dialogs, fold resets, reload jumps, caret focus) as
  repeatable checks (#t10, 2026-08-18); driving the full dockview shell
  itself is the remaining fidelity gap
- `done` no-reload updates after replying, resolving, or commenting --
  the page re-renders in place, so scroll and fold state simply never
  move (#t13, 2026-08-18) {#open-no-reload-updates}

- `done` any markdown file in the workspace opens in the app -- the
  header's "open file" picker or `?doc=path` -- and comments, threads,
  and replies write to that file (via chat, 2026-08-18)
- `done` the header stays pinned to the top of the page and the notify
  button carries a live count (#t18, 2026-08-19; the count's meaning
  settled under F4's stories)
- `done` quoted phrases that themselves contain quotation marks parse
  and render as threads (#t17, 2026-08-19)
- `done` minted anchors land on the text they name: rendered blocks trim
  trailing blank lines and the server never plants an id on a blank or
  note line (#t20, 2026-08-20)

- `done` posting a comment or reply keeps every thread folded or
  unfolded exactly as the reader left it -- the reset was the real
  cause of the residual scroll shift (2026-08-17)
- `done` thread numbers are never reused: ids are minted past every
  number the document has ever mentioned, so a deleted thread's id
  stays retired (2026-08-17)
- `done` word-level notes carry no count marker -- the underline is the
  affordance (via chat, 2026-08-15)
- `done` story marks render as badges (#t9); the renderer supports tables
  (#t8)
- `done` starting a comment while a draft is active discards it silently
  if empty and asks first if not -- via the app's own dialog, since the
  workspace's sandboxed frame suppresses native browser asks (#t11)
- `done` focusing never scrolls the document: the note comes to the
  anchor, and the discussed words stay on screen (#t14)
- `done` the selected text is highlighted while its comment is being
  drafted, not only after sending (2026-08-15)
- `done` sending a reply or comment keeps the reader's exact place --
  no scroll jump (2026-08-15)
- `done` comments keep their line breaks and paragraph gaps when
  rendered -- inline markdown only, no structural elements (#t29,
  2026-08-24)
- `planned` structural selections (double-click on a bullet, etc.)
  shrink to the commentable range where that is unambiguous (#t30)
- `planned` a selection beyond what can be anchored shows a disabled
  comment button whose tooltip says why, instead of no affordance at
  all -- the base for later expanding what is commentable (#t30)

### F2. Suggestion mode -- `planned`                         {#f2}

Propose, view as inline diff, accept or reject from the UI. Accept applies
the diff to the file. Prose-only in v1: accepting changes the document, never
triggers implementation work by itself (that is F6 territory, deliberately
deferred).

### F3. Status tracking and progress rollup -- `planned`     {#f3}

Statuses render as badges; a small overview (per-feature state, open thread
count) rolls up at the top. The document doubles as the project dashboard. {#statuses-render-as-badges}

### F4. "Notify agent" button -- `done`                      {#f4}

A button in the rendered view that stamps the document (`notified: vN
(timestamp)` in the frontmatter), drops a durable event file an agent can
listen for, and messages the workspace agent to sweep -- the document loop
with no chat interaction (#t16). Notes with activity since the stamp render
as `new` in the margin until resolved. {#a-button-in-the}

Iterations on this feature, tracked like F1's stories (#t16):

- `done` the notify loop: version stamp in the frontmatter, durable
  event file, direct nudge to the workspace agent (#t16, 2026-08-19)
- `done` the header pins to the top of the page (#t18, 2026-08-19)
- `done` message stamps carry time of day (UTC), making "new" tracking
  minute-precise; day-only stamps stay valid (#t16, 2026-08-19)
- `done` very new comments carry a NEW mark and a soft highlight until
  responded to or resolved (#t16, 2026-08-19)
- `done` the top bar tracks both directions: "new for you" (agent
  replies since your last notify) and the button's pending count (your
  comments not yet notified) (#t18, 2026-08-19) {#the-top-bar-tracks}
- `done` "new for you" is clickable: the label jumps to the next new
  item and attached arrows step both ways (#t19, 2026-08-20)
- `done` pressing notify clears the pending count even for comments
  written the same minute (#t21, 2026-08-20)
- `done` the nudge wakes a stopped agent -- a press with no chat session
  running still lands (found via v6, 2026-08-20)
- `done` a message can ride on a notify press: variant A picked -- a
  split button whose adjacent chevron opens a prefilled editor; the text
  lands in the nudge and the notification record (#t27, 2026-08-21)

### F5. Annotations on the running app -- `idea`             {#f5}

Later: the user annotates the *running application* (click an element, leave
a note) and it lands in this document as a thread in the Feedback appendix,
its anchor carrying an app reference (route, element selector, screenshot)
instead of a block id. Bridges "comment on the app" and "comment on the
spec" without a second artifact.

### F6. Suggestions that trigger work -- `idea`              {#f6}

Accepting certain suggestions kicks off implementation (spec change ->
agent builds it). Explicitly out of scope until F1-F3 are lived-in.

### F7. Raw source niceties -- `idea`                        {#f7}

Everything about the raw markdown view beyond "it exists with a way back":
syntax coloring and whatever else. Moved out of F1's scope (#t12) -- the
raw text is not currently relevant.

### F8. Usability in Minds -- `building`                     {#minds-usability}

Everything that makes the workbench work *as a Minds citizen* -- usable by
agents, portable across workspaces, self-explanatory to a Mind that has
never seen it. Partially delivered; also the parking lot for
adoption-related work (skills, `use-template` follow-ups, cross-workspace
feedback).

- `done` per-document agent routing: `notify-agent:` in frontmatter names
  the document's agent; documents without it fall back to the
  workspace-configured target (`SPEC_WORKBENCH_NOTIFY_AGENT`); with
  neither, a press stamps and records but nudges no one (2026-08-24)
- `done` a notify press wakes a stopped agent (`--start`), and every
  press leaves a durable JSON event regardless of delivery (#t27)
- `done` self-documenting: the bundled quickstart covers the format and
  the sweep conventions, serves rendered at `/quickstart`, and every
  nudge carries a pointer to it for agents that have never seen the
  format (2026-08-24)
- `done` agents can surface a document in the user's tab --
  `uv run open-spec <path>` opens, retargets, and focuses the workbench
  (2026-08-24)
- `done` published as a template: `github.com/trisiak/spec-workbench`
  (private, v1, 2026-08-24) -- a bootable snapshot other Minds adopt via
  `use-template`; personal names stay in workspace config, and the
  published copy of this spec ships as the worked example
- `planned` a crystallized skill for the sweep workflow, so an adopting
  Mind's agent gets the conventions as a skill rather than only a guide
  to read
- `idea` capture `use-template` adoption results: what the adopting
  workspace had to adapt, fed back into this spec and the next template
  version {#idea-capture-use-template-adoption}

> [!thread] #t31 on {#idea-capture-use-template-adoption} "adoption results" -- open
> **maciek (2026-08-24 17:52):** After `use-template` and opening the app, it opens spec_workbench.md. I think it should instead of open a different "new" document that serves as an intro on how to use it (vs the current what it is).
> **agent (2026-08-24 17:56):** Agreed -- the first adoption result, right
> on cue. The worked example answers "what is this app" when a fresh
> adopter needs "how do I start". Tracked as a `planned` F8 story: the
> template's next version ships a short intro document (try commenting
> on this line, notify your agent, open your own file) as the default
> document, with this spec still included one picker-click away.
> **maciek (2026-08-24 18:11):** Great, work on the "how to use this" and republishing. Which I'll test afterwards.
> **agent (2026-08-24 18:13):** The intro exists --
> `docs/specs/how_to_use_spec_workbench.md`, a short annotate-me page
> (try a comment, bring your agent in, open your own files, learn the
> format) that the next template version opens by default; this spec
> stays a picker-click away as the lived-in example. You can preview it
> via "open file...". Republishing as v2 is underway -- it has two
> confirmation stops in chat, so it lands after your go-aheads there.
- `planned` the template's default document is a fresh "how to use
  this" intro the adopter annotates on first open; this spec stays
  included as the deep worked example (#t31, 2026-08-24)
- `idea` template update flow: republish as v2+ when this workspace's
  copy meaningfully advances, and a way for adopters to pull the update
- `idea` notify events as an automation surface: cron or skills in the
  adopting Mind reacting to the durable event files, not just chat
  nudges

## UX & Polish                                               {#ux-polish}

Cross-feature interface niceties, tracked as stories like F1's; started
at maciek's ask in #t22 (2026-08-20).

- `done` Cmd/Ctrl+F opens an in-document search bar with an "in
  comments" checkbox; matches highlight, Enter and the arrows step
  through them, and a match hidden in a folded note unfolds it
  (#t22, 2026-08-20)
- `done` resolving a note folds it in the same click (#t23, 2026-08-20)
- `done` the "new for you" control disappears entirely at zero, arrows
  included (#t25, 2026-08-20)
- `done` top-bar stamps read as relative time with the precise stamp in
  the tooltip (#t26, 2026-08-20)
- `done` tooltips are the app's own and appear instantly; native ones
  were unreliable in the nested frame (#t26, 2026-08-21)

## Feedback

(Empty. F5 annotations on the running app land here.)

## Implementation log

(Each entry names the threads it settled; pruned threads live in git
history under these dates. Retired ids -- #t15 was used twice before
minting learned to skip mentioned numbers -- stay retired.)

- 2026-08-24 (fourteenth in-app sweep; first bake): all fourteen
  resolved threads pruned per the notify rider -- git holds them under
  this date. Story badges learned the full status vocabulary (#t28);
  comment display keeps line breaks and paragraph gaps, inline-only
  (#t29); selection-shrinking and the disabled comment button tracked
  as F1 stories (#t30); the template's intro-as-default-document
  tracked as an F8 story (#t31). Between sweeps: F8 added, the app
  published as a private template (v1) and adopted in another
  workspace.
- 2026-08-21 (thirteenth in-app sweep): the split button's chevron was
  mirrored by a CSS-specificity slip -- fixed and visually verified
  (#t27). Browser suite still deferred; the host remains busy.
- 2026-08-21 (twelfth in-app sweep): notify-with-message shipped as the
  picked variant A split button (#t27); tooltips became instant in-app
  ones (#t26). Browser tests deferred once: the host was shedding
  browsers under memory pressure from concurrent agents.
- 2026-08-20 (eleventh in-app sweep): the v6 press surfaced the gap
  that a nudge could not reach a stopped agent -- it now wakes one. The
  zero-state "new for you" shell hidden (#t25); top-bar stamps turned
  relative with precise tooltips (#t26); notify-with-context variants
  mocked for #t27.
- 2026-08-20 (tenth in-app sweep): in-document search landed (Cmd/Ctrl+F,
  "in comments" scope, highlight and step-through) and resolving now
  folds the note in the same click (#t22, #t23); F4 marked `done` at
  maciek's call (#t24); the UX & Polish section opened for
  cross-feature niceties.
- 2026-08-20 (ninth in-app sweep): a minted anchor landed past its
  block (loose-list line ranges overshoot across lifted note blocks) and
  rendered as literal text (#t20) -- trimmed at render time and guarded
  server-side, stray id repaired in place. "New for you" became a
  jump control (#t19); same-minute comments now clear on notify (#t21).
- 2026-08-19 (eighth in-app sweep): message stamps gained time of day
  and per-message NEW marks with soft highlights, cleared on response
  or resolution; the top bar split into "new for you" and the pending
  count; F4 got its own story list (#t16, #t18).
- 2026-08-19 (seventh in-app sweep): quotes inside quoted phrases broke
  the thread-header grammar and #t16 rendered as bare markdown (#t17) --
  the parser now delimits on the state suffix. Header pinned to the top
  and the notify button counts unswept open notes (#t18).
- 2026-08-19 (sixth in-app sweep): F4 prioritized ahead of F2 and its
  minimal loop built (#t16): the notify button stamps `notified: vN`,
  writes a listenable event, and messages the agent directly; open
  notes with activity since the stamp carry a `new` badge.
- 2026-08-18 (no-reload, e2e, multi-file): actions re-render the page
  in place from a fresh render payload (#t13) -- the reload-era
  scroll-restore machinery dissolved. The e2e story delivered: browser
  tests drive the app inside a sandboxed frame matching the workspace
  shell's embedding, one check per previously reported behavior. Any
  workspace markdown file now opens via the header picker, each file
  keeping its own thread namespace.
- 2026-08-17 (first bake): all resolved threads pruned (#t1-#t12, #t14;
  decisions captured in prose first); document status moved to
  `building`. #t10's caret-in-the-box bug parked unfixed at maciek's
  call after scripted-frame checks kept passing while the real shell
  kept failing; its lesson -- end-to-end tests inside the real
  workspace shell -- is now an open story.
- 2026-08-17 (fifth in-app sweep): posting reset every thread to
  unfolded (the real cause of the residual scroll shift) -- fold
  choices now persist. That report arrived as a second #t15, exposing
  id reuse after deletion; minting now skips every number the text has
  ever mentioned. Discard ask hardened against double-click; #t10
  caret focus handoff attempted.
- 2026-08-17 (fourth in-app sweep): the missing discard ask root-caused
  (#t11): the workspace's sandboxed frame suppresses native dialogs, so
  declining was assumed -- maciek's iframe hunch, confirmed. The ask is
  now an in-page dialog. Story tables dropped per #t8.
- 2026-08-15 (third in-app sweep): focusing never scrolls the document
  (#t14); drafting highlights the selection and sending keeps the
  reader's place (#t15); raw-view niceties moved to F7 (#t12);
  no-reload updates confirmed next (#t13); asset URLs version-stamped.
- 2026-08-15 (guard fix): a false "document has changed" -- badge
  styling made page text disagree with the file; the change-guard now
  strips badge-rendered decorations (surfaced via chat as #t11).
- 2026-08-15 (second in-app sweep): first phrase-anchored threads
  (#t8-#t10): selection drafts focus their box (#t10), story marks
  render as badges (#t9), tables render (#t8), word-level notes drop
  the count marker.
- 2026-08-15 (phrase anchors + deployment): the {#id} "quote" grammar
  fully live -- lazy id minting on any block, quote extension on
  ambiguity. The app became a supervised workspace service.
- 2026-08-15 (first in-app sweep): #t5-#t7 arrived through the app.
  F1 set to `building` (#t5); drafts survive losing focus and boxes
  grow (#t6); every heading takes comments via lazy id minting (#t7);
  the user-story list begins.
- 2026-08-14 (F1 round 2): comments open from the page; folded notes
  gray; replies require an open note. Decided: the app never touches
  git -- the sweep commits.
- 2026-08-14 (F1 built): the app renders this file -- margin notes
  pinned to anchors, fold/focus, Reply/Resolve/Reopen writing back.
  Mock confirmed and retired.
- 2026-08-14 (second sweep): metadata optional at write time, required
  at rest; inline anchors adopted via Pandoc spans (#t4).
- 2026-08-14 (first hand-edit sweep): name settled (#t1); specs' home
  settled as `docs/specs/` (#t2); the phrase form for suggestions born
  (#t4). Hand-written entries normalized by the sweep -- now a Lineage
  rule.
- 2026-08-14 (later): threads moved inline next to their anchors;
  retention decided (#t3): resolved threads stay, git is the archive,
  occasional "bake" commits prune.
- 2026-08-14: format designed in chat; this spec written by hand.
  Single inline file in git; block-id + quoted-phrase anchors; threads
  and suggestions themselves anchorable; pull-based agent loop with an
  `agent-seen` cursor.
