# Leo's agent instructions

Global instructions for every Claude Code session on every device: the Arch Linux desktop
(primary), the MacBook, and the phone (remote control). Project instructions add to these.

## Context

- Leo Lee is a full-stack software engineer at n2o, building AI products for enterprise and
  government clients, and a CS (AI) and Applied Statistics student at UVA, graduating May 2027.
- Leo runs personal projects solo. Leo designs and reviews; agents carry the execution.

## How to work

@~/dotfiles/claude/preferences.md

Git rules (`git.md`, always loaded) and language style (path-scoped, such as `python.md`)
load from `~/.claude/rules/`, which links to `~/dotfiles/claude/rules/`.

## Where context lives

Information lives with the thing it is about. Look it up when a task needs it; none of it
is loaded up front.
- A project's state, decisions, and research: that repo's `AGENTS.md` and `docs/`
  (`documentation/` in epiForecasting). Personal repos are under `~/repos/` on the MacBook
  and `~/dev/` on the desktop.
- Private notes about a shared repo: a `<repo>-private` sibling folder.
- n2o work: `~/N2O/` (private notes in `~/N2O/notes/`).
- Career (resume, applications, recruiting, profile): `~/jobapp`.
