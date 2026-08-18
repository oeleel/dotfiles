# Omarchy 3.8.4 -> 4.0 "Quattro" migration

Prepared 2026-08-18, before upgrading. Everything here is inert on 3.8.4:
nothing on the running system reads `shell.json` yet.

## Why the rice survives updates on v4

Per upstream `docs/file-layout.md` at v4.0.0, the package/user split is explicit:

- Package files live in `/usr/share/omarchy/**` and `/usr/bin/omarchy-*`. Updates
  only ever touch those.
- `/etc/skel` seeds `$HOME` **only at user creation**. An update never re-copies
  into an existing home.
- `~/.config/omarchy/` is designated upstream as the place for files "a user may
  intentionally version in a dotfile manager" - user themes, hooks, shell layout,
  plugins, themed template overrides.
- Only `omarchy-reinstall-configs` clobbers user config, and it is explicit and
  destructive by design.
- Derived/generated state moves to `~/.local/state/omarchy/current/`, away from
  authored config.

So: authored config in `~/.config/omarchy/` (symlinked here), logic in
`~/.local/bin` (symlinked from `dotfiles/bin`). Both are outside what updates touch.

## Upgrade steps

1. `omarchy-update` first, and confirm it reports **v4.0.0 stable**. On 2026-08-18
   this box's `omarchy-update-available` reported `v4.0.0-beta3`, which is stale
   metadata from a checkout last synced 2026-07-20. Do not upgrade onto a beta.
2. `Update > Omarchy to Quattro` (or `omarchy-upgrade-to-quattro`). Converts the
   git checkout at `~/.local/share/omarchy` into the package-backed layout
   (`omarchy` + `omarchy-settings`), preserves boot-critical kernel params, and
   handles the NetworkManager -> iwd transition.
3. Reboot.
4. Link the bar config, matching the existing per-subdir convention already used
   for `hooks` and `themes`:

       ln -s ~/dotfiles/omarchy/shell.json ~/.config/omarchy/shell.json

5. Verify both custom modules render and click through:
   - `audio-swap` shows 󰋋 or 󰓃 and swaps the port on click
   - `goodnight` shows 󰤄 and toggles on click

## What this replaces

The bar was Noctalia (`~/.config/noctalia/config.toml`), not Waybar - Waybar's
autostart has been off via the omarchy `waybar-off` toggle. Both customs were
`custom_button` entries with static glyphs:

| Noctalia widget | Quattro equivalent | Change |
|---|---|---|
| `widget.audio-swap` | `audio-swap` command module | now **stateful** - shows the live port instead of a fixed icon |
| `widget.goodnight` | `goodnight` command module | now **stateful** - `goodnight status` already emitted Waybar JSON |

Quattro's `omarchy.audio` / `.network` / `.bluetooth` widgets ship real popups
(output picker, per-app mixer, Wi-Fi scan), which is what `bar-dropdown`,
`audio-dropdown`, `bar-bt-json`, and `bar-net-json` were hand-rolling.

## After the upgrade is verified

- Decide Noctalia's fate: running it alongside `omarchy-shell` means two
  Quickshell instances and two bars. Drop `exec-once = noctalia` from
  `hypr/autostart.conf` once the Quattro bar is confirmed good.
- Then retire the now-dead scripts: `bar-dropdown`, `audio-dropdown`,
  `bar-bt-json`, `bar-net-json`, and the whole `dotfiles/waybar/` tree.
- Do **not** delete them before the Quattro bar is confirmed working.

## Known cost

`shell.json` has no deep merge. Once the file exists it is canonical, so new
default widgets from future Omarchy releases will not appear automatically.
After major releases, diff against `/usr/share/omarchy/config/omarchy/shell.json`.
