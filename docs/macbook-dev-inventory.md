# MacBook development setup, for the Arch desktop to match

Taken on the MacBook (macOS 27.2.1, arm64) on 2026-11-23. Brief for the Claude Code agent on the
Arch Linux desktop: bring the desktop to the same development setup. Check each item first and
install only what is missing. The Mac home is `/Users/leolee`; the desktop home is `/home/leo`.
Every path below written as `~/...` means the same place on both machines.

## 1. The dotfiles repo already carries most of the Claude setup

`github.com/oeleel/dotfiles` is cloned to `~/dotfiles` on both machines. These are symlinks into
it, so a `git pull` brings them over:

| `~/.claude/...` | Links to |
|---|---|
| `CLAUDE.md` | `~/dotfiles/claude/CLAUDE.md` |
| `settings.json` | `~/dotfiles/claude/settings.json` |
| `rules/` | `~/dotfiles/claude/rules/` |
| `hooks/` | `~/dotfiles/claude/hooks/` |
| `statusline-command.sh` | `~/dotfiles/claude/statusline-command.sh` |

`~/dotfiles/claude/SETUP.md` has the link commands for a new device. Run it first, then check
each link with `ls -la ~/.claude`.

The hooks need `git`, `jq`, `uv` and `herdr` on PATH. `format-python.sh` runs `ruff` through `uv`.

## 2. Claude Code runs the native install with all plugins off

| Item | State on the Mac | Desktop action |
|---|---|---|
| Claude Code | 2.1.331, native install at `~/.local/bin/claude` | Install the native build if missing |
| Model and effort | `settings.json`: model `opus`, effort `xhigh` for Opus 5.5, auto mode on, fast mode off | Comes from dotfiles |
| Official plugins | `context7`, `figma`, `frontend-design`, `github`, `superpowers`, `swift-lsp` are installed and all **disabled** | Do not install them |
| MCP: treg | HTTP server `https://treg.to/mcp/`, user scope, bearer token header | See section 6 |
| MCP: claude.ai Claude Docs | A claude.ai connector | Comes with the account sign-in |
| Claude in Chrome | Browser extension | Install the extension in the desktop browser if wanted |
| Anthropic skills (`docx`, `pdf`, `pptx`, `xlsx`, `skill-creator`, `deep-research` and others) | Synced into `~/.claude/skills/synced/` from the claude.ai account | No action; they sync on sign-in |
| claude-swap (`cswap`) 1.2.0 | `uv tool install claude-swap` | Install. Add each account with `claude auth login && cswap add`. Auto-switch stays off (Leo, 2026-11-23) |

## 3. Skills come from five sources, each with its own install step

| Skills | Source | How they are installed on the Mac |
|---|---|---|
| `coverage-audit`, `handoff`, `herdr`, `land-branch`, `meeting-pack`, `meeting-to-actions`, `recap`, `run-status` | `~/dotfiles/claude/skills/` | Symlinks, commands in `SETUP.md` |
| `diagram`, `framework-page`, `how-it-works`, `overnight`, `overnight-queue`, `parallelize` | `~/N2O/n2o-kit/skills/` | Symlinks, made by steps 1 and 2 of `~/N2O/n2o-kit/install.sh` |
| `humanize` | `~/N2O/n2o-kit/plugins/humanize/skills/humanize` | One manual symlink. `unslop` from the same plugin is left out on purpose: it forces a casual voice that conflicts with Leo's STE rule |
| `nah-enhance`, `nah-file-backlog`, `nah-harden`, `nah-help`, `nah-implement`, `nah-project-overview`, `nah-review`, `nah-scope`, `nah-sprint-overview` | `~/N2O/nah/skills/` | Symlinks |
| `nah-impl`, `nah-po`, `nah-so` | NAH alias payloads | Plain folders written by NAH (assumed `nah host install`; run `nah host diagnose` first to confirm) |
| `agent-lint`, `nak-bootstrap`, `nak-draft`, `nak-help`, `nak-organize`, `nak-register`, `nak-review` | NAK package | Plain folders, from `nak skills` |
| `design-taste-frontend` | `github.com/Leonxlnx/taste-skill`, cloned to `~/repos/taste-skill` | Symlink to `skills/taste-skill`, commands in `SETUP.md`. Needs ffmpeg with libwebp (`ffmpeg -encoders \| grep libwebp`). The `guard-n2o-skills.sh` hook blocks it under `~/N2O` |
| `frontend-design` | Anthropic's frontend-design skill | A plain folder copy in `~/.claude/skills/` (the plugin copy is disabled) |
| `treg` | treg installer | Written by `curl -fsSL https://treg.to/install.sh \| sh` |

Do not install these:

- Prism's own skills (`~/N2O/prism/skills/`). Three of them share names with older copies of the
  n2o-kit skills and would collide.
- The n2o-kit plugin marketplace (`arch`, `n2o-engineering`, `playbook`, `gather-prep`,
  `cmux-agents`). None of them is installed on the Mac.
- `~/N2O/.claude/skills/trace` and `skill-builder`. They date from 2026-03 and do not load.

## 4. The n2o-kit rules load only under ~/N2O

Do **not** run step 3 of `install.sh`. Step 3 appends the rules line to the global
`~/.claude/CLAUDE.md`, which is the dotfiles file shared with school and personal work. On the Mac
the rules load from `~/N2O/CLAUDE.md`, which is not in git. Create it on the desktop with this
exact text:

```markdown
# n2o work

Repos for n2o and its clients live under this folder; each has its own instructions.
Private context (role, company, build records, handle-with-care rules): `notes/`. Read it on demand.

# N2O rules, from n2o-kit (Wiley's house rules; scoped to ~/N2O, not loaded globally)
@~/.n2o-kit/rules/CLAUDE.md
```

`~/.n2o-kit` must be a symlink to `~/N2O/n2o-kit` (step 1 of `install.sh` makes it).

## 5. Repositories

Clone with `gh repo clone` over HTTPS. `gh` is the git credential helper (`gh auth login`, account
`oeleel`, scopes `repo`, `workflow`, `read:org`, `gist`).

### 5.1 N2O work lives in ~/N2O

| Folder | Remote | Last commit | Role |
|---|---|---|---|
| `firehose` | `N2O-com/firehose` | 2026-11-23 | Main project. Section 7 has its setup |
| `nah` | `N2O-com/nah` | 2026-11-16 | NAH workflow CLI and skills. Mac branch: `feature/herdr-core-provider` |
| `nak` | `N2O-com/nak` | 2026-09-12 | NAK knowledge CLI and skills |
| `n2o-kit` | `N2O-com/n2o-kit` | 2026-11-20 | Wiley's rules, page skills, page frame |
| `prism` | `N2O-com/prism` | 2026-11-18 | Prism components and pages, used as a reference for page work |
| `notes` | `oeleel/n2o-notes` (private) | 2026-10-21 | Private n2o notes |
| `totalcents` | `lukesteinbicker/totalcents` | 2026-10-31 | Client project |
| `SONAR` | `N2O-com/SONAR` | 2026-04-13 | Older |
| `platform` | `N2O-com/platform` (SSH remote) | 2026-03-28 | Older |
| `entune` | `oeleel/entune` | 2026-03-22 | Older |
| `hormozi-wiki` | `N2O-com/hormozi-wiki` | 2026-05-08 | Older |
| `ai-agent-example` | `linq-team/ai-agent-example` (SSH remote) | 2026-02-15 | Older |

Clone the top six first. Clone the older ones only when a task needs them.

Skip these folders. They are not separate repos:

- Every `firehose-<topic>` folder is a git worktree of `firehose`. Make worktrees on the desktop
  only when a task needs them.
- `nah-tabfix` is a worktree of `nah`. `nah-herdr` is an experiment clone of `nah`.
- `totalcents copy` and `totalcents-handoff` are local copies.
- `firehose-private` and `firehose-private-harden` are local folders with no remote.

### 5.2 Personal repos live in ~/repos and ~

| Folder | Remote | Last commit |
|---|---|---|
| `~/repos/golf-coach` | `oeleel/golf-coach` | 2026-11-05 |
| `~/repos/kalshekki` | `oeleel/kalshekki` | 2026-10-21 |
| `~/repos/parlee` | `oeleel/parlee` | 2026-10-21 |
| `~/repos/dial` | `oeleel/dial` | 2026-04-27 |
| `~/repos/taste-skill` | `Leonxlnx/taste-skill` (third party) | 2026-11-22 |
| `~/jobapp` | `oeleel/jobapp` | 2026-10-21 |
| `~/dotfiles` | `oeleel/dotfiles` | 2026-11-23 |

`~/repos/agent-workflow-research` and `~/leo-vault` (the Obsidian vault) have no remote, so git
cannot carry them. The class exercise repos from 2023 and 2024 are not needed.

## 6. Secrets travel by hand and never go into git

Only the names are listed here. Copy the values over a channel Leo picks, with file mode `600`.

| File | Variables or content | Used by |
|---|---|---|
| `~/.config/firehose/claude.env` | `CLAUDE_CODE_OAUTH_TOKEN` | Firehose daily judge run |
| `~/.config/firehose/r2.env` | `TWITTERAPI_IO_KEY` | Firehose collector |
| `~/.config/firehose/run.env` | `FIREHOSE_MODEL_STAGES` (a setting, not a secret) | Firehose run |
| `~/.config/firehose/treg.env` | `TREG_TOKEN`, `TREG_ORG` | Firehose treg sources |
| `~/.treg/config.json` | treg sign-in | Written by `treg login` |
| treg MCP server | Bearer token | `claude mcp add --transport http treg https://treg.to/mcp/ --header "Authorization: Bearer <token>"`, or the treg installer |
| GitHub | `gh` keyring token | `gh auth login` |
| Claude accounts | Keychain logins on the Mac | `claude auth login`, then `cswap add`, once per account |

## 7. Firehose needs uv, Node and Playwright

```bash
cd ~/N2O/firehose
uv sync --project pipeline                     # Python >= 3.12
uv run --project pipeline pytest               # pipeline tests
cd dashboard && npm install
npx playwright install chromium                # page tests
npm run page                                   # builds firehose.html
npm run test:page                              # page tests
```

**Do not install the judge schedule on the desktop.** The Mac runs the daily judge from the
worktree `~/N2O/firehose-judge` through the launchd job `com.n2o.firehose.judge` at 07:00. A second
machine that runs it would push to `main` at the same time. `--install-schedule` writes a launchd
agent, so it does not work on Linux anyway.

## 8. CLI toolchain

Arch names are the usual `pacman` or AUR packages. Confirm each name with `pacman -Ss` or
`yay -Ss` before installing.

### 8.1 Current work needs these

| Tool | Mac version | Needed by |
|---|---|---|
| `git` | 2.48.1 | Everything |
| `gh` | 2.102.0 | Clones, PRs, credential helper, `land-branch` skill |
| `node` + `npm` | 25.8.2 + 11.11.1 | Firehose dashboard; NAH needs Node >= 24 |
| `pnpm` | 10.26.2 globally; NAH pins `pnpm@11.1.2` through `packageManager` | NAH build |
| `uv` | 0.10.8 | Firehose pipeline, hooks, claude-swap |
| `python` 3.12 | Homebrew `python@3.12` | Firehose (`requires-python >= 3.12`) |
| `jq` | 1.8.1 | Hooks |
| `ffmpeg` with libwebp | 9.0.2, Homebrew `ffmpeg-full` | Taste skill photos |
| `herdr` | 0.9.5 | Agent multiplexer, hooks, `herdr` skill |
| `treg` | 1.0.0-beta.5, `~/.local/bin/treg` | Firehose collection, treg skill (`curl -fsSL https://treg.to/install.sh \| sh`) |
| `nah` | 0.1.10, `npm link` of `~/N2O/nah` | NAH workflow |
| `nak` | 0.1.0, `npm link` of `~/N2O/nak` | NAK knowledge |
| `shellcheck` | 0.11.0 | Shell scripts in dotfiles and Firehose |

Install NAH and NAK from their clones:

```bash
cd ~/N2O/nah && pnpm install && pnpm build && npm link && nah help
cd ~/N2O/nak && pnpm install && pnpm build && npm link && nak help
nah host diagnose                               # then: nah host install
nak skills
```

### 8.2 Deploy and data CLIs, installed on demand

| Tool | Mac version |
|---|---|
| `vercel` (npm global) | 54.7.1 |
| `neonctl` | 2.22.0 |
| `supabase` | 2.12.1 |
| `heroku` | 10.13.2 |
| `cloudflared` | 2026.3.0 |
| `pm2` (npm global) | 5.4.2 |
| `postgresql` 14 client | 14.19 |
| `ollama` | 0.19.0 |

### 8.3 Terminal tools, by preference

`neovim`, `tmux`, `lazygit`, `yazi`, `glow`, `pandoc`. The tmux and Ghostty configs are in
dotfiles.

### 8.4 Older school and project toolchains

`R` 4.5.2, `php` 8.5, `openjdk` 21, `rust` 1.95, `cmake`, `gdal`, `udunits`, `exiftool`, `drogon`,
`hiredis`, `xcodegen`, miniconda and anaconda. No current N2O repo needs them. Install one only
when a task asks for it.

## 9. Mac-only items have a Linux replacement or are skipped

| Mac item | Desktop action |
|---|---|
| Herdr desktop app (`Herdr.app`, `herdr-core`, `hc` 0.1.22) | Already on the desktop; the Hyprland config refers to it |
| `dev.leolee.herdr-remod` launchd job, which rebuilds the patched agents panel when Herdr updates | Needs a systemd user path unit on Linux. `~/dotfiles/herdr/herdr-remod` is the script; its tests run with `node --test ~/dotfiles/herdr/tests/*.test.mjs` |
| Herdr Accounts panel | In progress on dotfiles branch `feature/herdr-accounts`; not on `main` |
| cmux (Ghostty-based terminal for agents) | macOS only. The `overnight-queue` skill depends on cmux, so it does not run on the desktop |
| `apple-mcp`, `mcp-server-apple-reminders` (npm globals) | macOS only, and not configured in Claude. Skip |
| `chrome-devtools-mcp` (npm global) | Not configured in Claude. Skip |
| `cursor-agent` (2025-09 build) | Stale. Skip |
| Dia browser | Mac default for opening pages. Use the desktop browser |
| Raycast, AltTab, Ice, Itsycal, Logi Options+, Reminders menu bar | Mac utilities. Skip |
| Claude.app, Cursor, Zed, VS Code, Positron, Obsidian, Linear, Slack, Loom, Tailscale, Wispr Flow, ChatGPT | Install the Linux build of any that Leo uses on the desktop |

## 10. Machine-local state does not transfer

- Claude project memories in `~/.claude/projects/<path>/memory/` are keyed by the absolute path, so
  `/Users/leolee/...` folders do not match `/home/leo/...`. Many of the Firehose memories describe
  Mac-only facts, such as the launchd judge and the Mac worktrees. Copy one only when Leo asks.
- Never copy or delete `~/.claude/projects` transcripts (n2o-kit rule 10).

## 11. Order of work, with a check for each step

| Step | Work | Check |
|---|---|---|
| 1 | Pull dotfiles, run `SETUP.md` links | `ls -la ~/.claude` shows the five links |
| 2 | Install the 8.1 toolchain | Each tool prints a version |
| 3 | `gh auth login`, clone the 5.1 top six and the 5.2 repos | `git -C <repo> status` is clean |
| 4 | n2o-kit `install.sh` steps 1 and 2 only, the `humanize` link, `~/N2O/CLAUDE.md` | A new session under `~/N2O` lists the kit skills and loads the rules |
| 5 | NAH and NAK build and link, then their skills | `nah help`, `nak help`, `nah host diagnose` report no drift |
| 6 | Taste skill clone and link | `/design-taste-frontend` appears outside `~/N2O` |
| 7 | treg install and login, treg MCP, `cswap` and accounts | `treg balance` works; `claude mcp list` shows treg connected; `cswap list` shows the accounts |
| 8 | Secrets from section 6 | `ls -la ~/.config/firehose` shows four files with mode `600` |
| 9 | Firehose setup from section 7 | `uv run --project pipeline pytest` and `npm run test:page` pass |

Report each step's check output, and list anything that failed or was skipped.
