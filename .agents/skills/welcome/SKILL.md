---
name: welcome
description: "Greet the user when a new project starts. This mind was created from the Spec Workbench template, so the welcome introduces that template and immediately starts the adaptation conversation."
---

# Welcome the user (template: Spec Workbench)

This mind was created from a template -- a published snapshot of apps
another mind built:

- Title: Spec Workbench
- Slug: `spec-workbench`
- Description: Living markdown documents with Google-Docs-style margin comments: annotate any file, notify your agent, and collaborate through threads stored inline in plain markdown in git
- Manifest: `template.md` (at the repo root, with `template.toml` beside it)

Do ALL of the following in your FIRST response, in the same turn, without
waiting to be asked:

1. Open with a short CUSTOM welcome that names **Spec Workbench** and gives the
   one-line description above. Do NOT use a generic "Welcome to Minds"
   greeting and do NOT offer a generic suggestions list.
2. Immediately read `template.md` at the repo root (reading the
   manifest in the first turn is required).
3. In plain, non-technical language, present what the template is and
   what it needs from the user -- name the manifest's activation requirements
   (the connectors/permissions it runs on). Then ask whether they want to hook it
   up to their own accounts now (e.g. "Want me to connect this to your own
   Slack?"). End your first response on THAT question. This is the
   `use-template` skill's template path; the manifest's "How to adapt
   it" section is the full script: if they say yes, ACTIVATE FIRST -- initiate
   each `requires_permission` via a latchkey permission request, get the
   app showing THEIR OWN DATA (that is the definition of working; a running
   service is not), invite them to take a look -- and only then ask how they
   want to adapt it.

This repo holds exactly one template. If `template.toml` lists
`[[lineage]]` entries, those are the templates this one was built on --
each with the repo URL and commit it was taken at, so you can go read any of
them at the exact state that was used. They are provenance, not something to
adapt here.
