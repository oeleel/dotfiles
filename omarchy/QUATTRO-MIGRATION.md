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
4. Link the bar config and the machine-level shell tokens, matching the
   existing per-subdir convention already used for `hooks` and `themes`:

       ln -s ~/dotfiles/omarchy/shell.json ~/.config/omarchy/shell.json
       ln -s ~/dotfiles/omarchy/shell.toml ~/.config/omarchy/shell.toml

5. Re-seed the dynamic theme so `colors.toml` is regenerated in the v4 semantic
   schema, and the shell picks up the new tokens:

       wall-theme ~/Pictures/wallpapers/1-wano-night.png

6. Verify both custom modules render and click through:
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

## Wallpaper theming across the schema change

Omarchy 4 replaced the ANSI `colorN` palette in `colors.toml` with semantic
keys (`lighter_background`, `dark_foreground`, `muted`, `selection`, `mode`,
named hues). `omarchy-theme-color` still accepts the legacy block via an alias
cascade, so the old template does not error - it degrades silently, which is
worse. Resolved against v4's own parser, the pre-migration template collapsed
three of the four ramps:

| key | old template under v4 | fixed |
|---|---|---|
| `lighter_background` | `#1a110e`, identical to `background` | `#322824` |
| `light_foreground` / `bright_foreground` | both `#f1dfd9`, identical to `foreground` | `#f7ece9` / `#fbf6f4` |
| `muted` | `#a08d86`, identical to `dark_foreground` | `#53433e` |
| `selection` | `#ffb599`, full-strength primary slab | `#71361d`, tinted |

Every elevated surface in the new shell - bar capsules, hovered rows, menu and
launcher selection, cards - is drawn from `lighter_background`. Left alone it
would have rendered dead flat against the window behind it.

`matugen/templates/omarchy-colors.toml` now emits **both** schemas. v4 prefers
the canonical semantic names; 3.8.x reads the legacy block and ignores the rest.
That makes the template correct on either side of the upgrade, so a wallpaper
change never has to be sequenced against the reboot. Drop the legacy block once
3.8.x is gone.

Verify the resolved palette at any time without switching themes:

    omarchy-theme-color --file ~/.config/omarchy/themes/dynamic/colors.toml --all

### Where the glass lives now

- **Color** stays wallpaper-driven: matugen -> `themes/dynamic/colors.toml` ->
  v4 generates `shell.toml` from `default/themed/shell.toml.tpl`.
- **Alpha** is pinned machine-level in `omarchy/shell.toml`, which v4 merges
  over the theme's generated file, so it survives theme switches and retints.
  Values are ported from the Noctalia bar (0.78 bar / 0.82 cards / 0.88 auth).
- **Frost** is compositor-side: the `layerrule = blur` block in
  `hypr/hyprland.conf` targeting `^omarchy-(bar|menu|...)$`. Both halves are
  required - alpha without blur is flat translucency.

## Still open after the reboot

- **`claude.json` / `pi.json` are new themed templates.** They will auto-generate
  from the wallpaper, which widens past the agreed core-shell scope (terminals
  and editors stay curated). Freeze them into `themes/dynamic/` to opt out, or
  accept them. Cosmetic, decide on screen.
- **Dead files in `themes/dynamic/`**: `hyprlock.conf` and `swayosd.css` are
  inert once the upgrade removes hyprlock and swayosd. Harmless, delete when tidying.
- **`hypr/*.conf` -> `*.lua`.** The upgrade installs a compat shim so the legacy
  `.conf` tree keeps working, but it is a transition crutch, not the destination.
  The blur rules above are in `.conf` and will need porting.
- **Retire Noctalia** once the v4 bar is confirmed: drop `exec-once = noctalia`
  from `hypr/autostart.conf`, remove the `[templates.noctalia]` block from
  `matugen/config.toml`, then delete the dead `bar-*`/`audio-dropdown` scripts
  and the `dotfiles/waybar/` tree. `wall-theme`'s Noctalia step is already
  guarded by `pgrep -x noctalia`, so it self-disables the moment Noctalia stops.
