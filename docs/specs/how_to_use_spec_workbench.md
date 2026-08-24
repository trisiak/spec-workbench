---
notify-agent:                # set to your agent's name to route this document's notify presses
---

# How to use Spec Workbench

You are looking at a living document. Everything you do on this page --
comments, replies, resolutions -- is written straight into this markdown
file on disk, as readable blockquotes. There is no database; the file in
git is the whole record.

## Try it right now

Select a few words in this sentence and a comment button will appear next
to your selection. Write something and send it -- your comment shows up in
the right margin, anchored to the exact words you picked, and lands in the
file at the same moment.

Then hover your comment in the margin: you can reply to it, and resolve it
once it has served its purpose. Resolved comments fold away but stay in
the file until an occasional cleanup pass prunes them (git keeps them
forever).

## Bring your agent in

The **notify agent** button in the header stamps the document and messages
an agent to come read it -- reply in your threads, do what they ask, and
commit. The counter on the button shows how many of your comments the
agent has not been told about yet; "new for you" counts the agent's
replies waiting for you. The small arrow next to the button lets a note
ride along with the press ("prioritize the first section").

Presses on this document reach the agent named in the `notify-agent:` line
at the top of this file -- it ships blank, so ask your agent to put its
own name there (or set a workspace-wide default; the full manifest covers
this).

## Open your own files

Any markdown file in your workspace can be a living document -- this app
is not just for specs. Use **open file...** in the header, add
`?doc=<path>` to the URL, or ask your agent to run
`uv run open-spec <path>`, which opens the file right in your tab. Files
need no special setup: the first comment or notify press adds whatever the
format needs.

## Learn the format

The footer's **how this works** link opens the full reference for the
on-disk format and the collaboration loop -- worth pointing your agent at
before its first sweep (agents get the same pointer in every notify
message).

For a real, lived-in example, open the spec of this very app -- a document
with months of threads, statuses, and an implementation log, edited
through the app it describes:
[docs/specs/spec_workbench.md](?doc=docs/specs/spec_workbench.md)
