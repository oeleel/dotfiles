// Run: node --test ~/dotfiles/herdr/tests/*.test.mjs
//
// Runs herdr-remod in a sandbox: fake shipped mods, patches and layout, and fake `herdr-app`
// and `osascript` on the script's PATH ($HOME/.local/bin), so a test posts no notification.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { chmodSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT = fileURLToPath(new URL("../herdr-remod", import.meta.url));
const SIDEBAR_ACCOUNTS_BLOCK = { id: "accounts", type: "block", size: { weight: 0.6 }, min: 110, content: { mod: "accounts" } };
const PANEL_ACCOUNTS_BLOCK = { id: "accounts", type: "block", content: { mod: "accounts" } };
const PATCH = "--- a/main.js\n+++ b/main.js\n@@ -1,3 +1,3 @@\n one\n-two\n+two patched\n three\n";
const STALE_PATCH = "--- a/main.js\n+++ b/main.js\n@@ -1,3 +1,3 @@\n one\n-zwei\n+zwei patched\n three\n";
// The shipped tabs mod names its own folder and mod id, so the clone rename shows.
const SHIPPED_TABS_MAIN = 'alpha\nbeta\ngamma\nsvg("mods/tabs/win-min.svg");\nopenOverlay({ mod: "tabs" });\n';
const TABS_PATCH = "--- a/main.js\n+++ b/main.js\n@@ -1,3 +1,3 @@\n alpha\n-beta\n+beta patched\n gamma\n";
const STALE_TABS_PATCH = "--- a/main.js\n+++ b/main.js\n@@ -1,3 +1,3 @@\n alpha\n-bravo\n+bravo patched\n gamma\n";
const ACCOUNTS_MODULES = ["accounts.js", "core.js", "resume.js", "tab.js"];

const block = (id, mod) => ({ id, type: "block", size: { weight: 1 }, min: 90, content: { mod } });
const panelBlock = (mod) => ({ id: mod, type: "block", content: { mod } });
const TABS_BLOCK = { id: "tabs", type: "block", size: { px: 42 }, window_drag: true, content: { mod: "tabs" } };
const panelBody = (children) => ({ id: "panel-body", type: "stack", active: "files", children });
const workBody = (panelChildren) => ({
  id: "work-body",
  type: "row",
  children: [
    { id: "main", type: "block", content: { tab: "active" } },
    { id: "panel", type: "column", hidden: true, children: panelChildren },
  ],
});
const WORK = [TABS_BLOCK, workBody([panelBody([panelBlock("files"), panelBlock("changes")])])];
const layout = (sidebarLists, workChildren = WORK) => ({
  id: "root",
  type: "row",
  traffic_lights: [12, 16],
  children: [
    {
      id: "sidebar",
      type: "column",
      children: [
        { id: "brand", type: "block", size: { px: 46 }, content: { mod: "workspace-chrome" } },
        { id: "sidebar-lists", type: "column", children: sidebarLists },
      ],
    },
    { id: "work", type: "column", children: workChildren },
  ],
});
const SHIPPED_LAYOUT = layout([block("spaces", "spaces"), block("agents", "agents")]);

function write(path, text, mode = 0o644) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text);
  chmodSync(path, mode);
}

/** A source folder, an app home and a home with fake tools, as herdr-remod sees them. */
function sandbox(shippedLayout) {
  const root = mkdtempSync(join(tmpdir(), "remod-test-"));
  const box = { root, src: join(root, "herdr"), app: join(root, "app"), home: join(root, "home") };
  mkdirSync(box.src);
  copyFileSync(SCRIPT, join(box.src, "herdr-remod"));
  chmodSync(join(box.src, "herdr-remod"), 0o755);
  write(join(box.src, "agents-menu.patch"), PATCH);
  write(join(box.src, "agents-menu", "sessions.js"), "export {};\n");
  write(join(box.src, "tabs-leo.patch"), TABS_PATCH);
  write(join(box.src, "tabs-leo", "button.js"), "export {};\n");
  write(join(box.src, "accounts", "mod.json"), '{ "place": "none", "title": "Accounts" }\n');
  write(join(box.src, "accounts", "main.js"), "export default class Accounts {}\n");
  write(join(box.src, "accounts", "config.json"), '{ "pollSeconds": 60 }\n');
  for (const name of ACCOUNTS_MODULES) write(join(box.src, "accounts", name), `// ${name}\n`);
  write(join(box.src, "accounts", "fixtures", "cswap-list.json"), "{}\n");
  write(join(box.src, "accounts", "panel.test.mjs"), "\n");
  write(join(box.app, "mods", "agents", "main.js"), "one\ntwo\nthree\n");
  write(join(box.app, "mods", "agents", "mod.json"), '{ "place": "none", "title": "Agents" }\n');
  write(join(box.app, "mods", "tabs", "main.js"), SHIPPED_TABS_MAIN);
  write(join(box.app, "mods", "tabs", "mod.json"), '{ "place": "none", "title": "Tabs" }\n');
  write(join(box.app, "mods", "tabs", "win-min.svg"), "<svg/>\n");
  write(join(box.app, "mods", "tabs", "gpui-kit.d.ts"), "// app-written\n");
  write(join(box.app, "layouts", "main.json"), JSON.stringify(shippedLayout, null, 2) + "\n");
  // FAKE_CHECK_FAILS names the one mod folder the fake check rejects.
  write(join(box.home, ".local", "bin", "herdr-app"),
    '#!/bin/sh\n[ "$(basename "$2")" = "$FAKE_CHECK_FAILS" ] && { echo "bad mod: $2" >&2; exit 1; }\nexit 0\n', 0o755);
  write(join(box.home, ".local", "bin", "osascript"), '#!/bin/sh\necho "$@" >> "$HOME/notifications.log"\n', 0o755);
  return box;
}

function remod(box, env = {}) {
  return spawnSync(join(box.src, "herdr-remod"), {
    encoding: "utf8",
    env: { HOME: box.home, HERDR_APP_HOME: box.app, TMPDIR: box.root, ...env },
  });
}

/** Every file under dir with its inode and mtime, so a rewrite of any file shows. */
function fileStamps(dir) {
  return readdirSync(dir, { recursive: true })
    .map((name) => join(dir, name))
    .filter((path) => statSync(path).isFile())
    .sort()
    .map((path) => [path, statSync(path).ino, statSync(path).mtimeMs]);
}

/** The node with this id in the built main-leo layout. */
function builtNode(box, id) {
  const find = (node) => (node.id === id ? node : (node.children ?? []).map(find).find(Boolean));
  return find(JSON.parse(readFileSync(join(box.app, "layouts", "main-leo.json"), "utf8")));
}

const sidebarLists = (box) => builtNode(box, "sidebar-lists").children;
const panelStack = (box) => builtNode(box, "panel-body").children;
const tabsMod = (box) => builtNode(box, "tabs").content.mod;

test("test_remod_installs_the_accounts_mod_without_test_files", () => {
  const box = sandbox(SHIPPED_LAYOUT);

  const run = remod(box);

  assert.equal(run.status, 0, run.stderr);
  assert.deepEqual(readdirSync(join(box.app, "mods", "accounts")).sort(), [...ACCOUNTS_MODULES, "config.json", "main.js", "mod.json"].sort());
});

test("test_remod_installs_both_clones", () => {
  const box = sandbox(SHIPPED_LAYOUT);

  const run = remod(box);

  assert.equal(run.status, 0, run.stderr);
  assert.equal(readFileSync(join(box.app, "mods", "agents-menu", "main.js"), "utf8"), "one\ntwo patched\nthree\n");
  assert.equal(readFileSync(join(box.app, "mods", "tabs-leo", "main.js"), "utf8"),
    'alpha\nbeta patched\ngamma\nsvg("mods/tabs-leo/win-min.svg");\nopenOverlay({ mod: "tabs-leo" });\n');
  assert.deepEqual(readdirSync(join(box.app, "mods", "tabs-leo")).sort(),
    [...ACCOUNTS_MODULES, "button.js", "main.js", "mod.json", "win-min.svg"].sort());
});

test("test_remod_puts_accounts_last_in_the_panel_stack_and_tabs_on_tabs_leo", () => {
  const box = sandbox(SHIPPED_LAYOUT);

  const run = remod(box);

  assert.equal(run.status, 0, run.stderr);
  assert.equal(tabsMod(box), "tabs-leo");
  assert.deepEqual(panelStack(box), [panelBlock("files"), panelBlock("changes"), PANEL_ACCOUNTS_BLOCK]);
  assert.deepEqual(sidebarLists(box), [block("spaces", "spaces"), block("agents", "agents-menu")]);
});

test("test_remod_keeps_accounts_in_the_sidebar_when_the_tabs_leo_patch_fails", () => {
  const box = sandbox(SHIPPED_LAYOUT);
  write(join(box.src, "tabs-leo.patch"), STALE_TABS_PATCH);

  const run = remod(box);

  assert.equal(run.status, 1);
  assert.match(run.stderr, /tabs-leo.patch does not apply to the shipped tabs mod/);
  assert.equal(existsSync(join(box.app, "mods", "tabs-leo")), false);
  assert.equal(tabsMod(box), "tabs");
  assert.deepEqual(sidebarLists(box), [block("spaces", "spaces"), block("agents", "agents-menu"), SIDEBAR_ACCOUNTS_BLOCK]);
  assert.deepEqual(panelStack(box), [panelBlock("files"), panelBlock("changes")]);
});

test("test_remod_fails_only_the_layout_when_panel_body_is_missing", () => {
  const box = sandbox(layout([block("spaces", "spaces"), block("agents", "agents")], [TABS_BLOCK, workBody([])]));

  const run = remod(box);

  assert.equal(run.status, 1);
  assert.match(run.stderr, /expected 1 panel-body stack in the shipped main layout, found 0 \(stacks: none\)/);
  assert.equal(existsSync(join(box.app, "layouts", "main-leo.json")), false);
  assert.equal(existsSync(join(box.app, "mods", "agents-menu", "main.js")), true);
  assert.equal(existsSync(join(box.app, "mods", "tabs-leo", "main.js")), true);
  assert.equal(existsSync(join(box.app, "mods", "accounts", "main.js")), true);
});

test("test_remod_fails_only_the_layout_when_the_tabs_block_is_missing", () => {
  const box = sandbox(layout([block("spaces", "spaces"), block("agents", "agents")], WORK.slice(1)));

  const run = remod(box);

  assert.equal(run.status, 1);
  assert.match(run.stderr, /expected 1 tabs block in the shipped main layout, found 0 \(blocks: agents, changes, files, spaces, workspace-chrome\)/);
  assert.equal(existsSync(join(box.app, "layouts", "main-leo.json")), false);
  assert.equal(existsSync(join(box.app, "mods", "tabs-leo", "main.js")), true);
});

test("test_remod_second_run_prints_and_writes_nothing", () => {
  const box = sandbox(SHIPPED_LAYOUT);
  remod(box);
  const before = fileStamps(box.app);

  const run = remod(box);

  assert.equal(run.status, 0, run.stderr);
  assert.equal(run.stdout + run.stderr, "");
  assert.deepEqual(fileStamps(box.app), before);
});

test("test_remod_fails_when_the_layout_has_no_agents_block", () => {
  const box = sandbox(layout([block("spaces", "spaces")]));

  const run = remod(box);

  assert.equal(run.status, 1);
  assert.match(run.stderr, /expected 1 agents block in the shipped main layout, found 0/);
  assert.equal(existsSync(join(box.app, "layouts", "main-leo.json")), false);
  assert.equal(existsSync(join(box.app, "mods", "accounts", "main.js")), true);
});

test("test_remod_fails_when_the_agents_block_is_outside_the_sidebar_lists", () => {
  const box = sandbox(layout([block("spaces", "spaces")], [...WORK, block("agents", "agents")]));

  const run = remod(box, { FAKE_CHECK_FAILS: "tabs-leo" });

  assert.equal(run.status, 1);
  assert.match(run.stderr, /expected 1 accounts block after the agents-menu block in sidebar-lists of the main-leo layout, found 0 \(sidebar-lists holds: spaces\)/);
  assert.equal(existsSync(join(box.app, "layouts", "main-leo.json")), false);
  assert.equal(existsSync(join(box.app, "mods", "accounts", "main.js")), true);
});

test("test_remod_installs_agents_menu_when_the_accounts_check_fails", () => {
  const box = sandbox(SHIPPED_LAYOUT);

  const run = remod(box, { FAKE_CHECK_FAILS: "accounts" });

  assert.equal(run.status, 1);
  assert.match(run.stderr, /the rebuilt accounts mod does not pass herdr-app check: bad mod: /);
  assert.match(readFileSync(join(box.home, "notifications.log"), "utf8"), /Herdr panel rebuild failed/);
  assert.equal(existsSync(join(box.app, "mods", "accounts")), false);
  assert.equal(readFileSync(join(box.app, "mods", "agents-menu", "main.js"), "utf8"), "one\ntwo patched\nthree\n");
  assert.deepEqual(sidebarLists(box), [block("spaces", "spaces"), block("agents", "agents-menu")]);
  assert.deepEqual(panelStack(box), [panelBlock("files"), panelBlock("changes")]);
});

test("test_remod_installs_agents_menu_when_the_accounts_folder_is_missing", () => {
  const box = sandbox(SHIPPED_LAYOUT);
  rmSync(join(box.src, "accounts"), { recursive: true });

  const run = remod(box);

  assert.equal(run.status, 1);
  assert.match(run.stderr, /accounts mod not found: .*\/accounts\/main\.js/);
  assert.equal(existsSync(join(box.app, "mods", "agents-menu", "main.js")), true);
  assert.deepEqual(sidebarLists(box), [block("spaces", "spaces"), block("agents", "agents-menu")]);
});

test("test_remod_keeps_the_installed_accounts_mod_when_its_check_fails", () => {
  const box = sandbox(SHIPPED_LAYOUT);
  remod(box);
  const before = fileStamps(join(box.app, "mods", "accounts"));
  write(join(box.src, "accounts", "main.js"), "export default class Broken {}\n");

  const run = remod(box, { FAKE_CHECK_FAILS: "accounts" });

  assert.equal(run.status, 1);
  assert.deepEqual(fileStamps(join(box.app, "mods", "accounts")), before);
  assert.deepEqual(panelStack(box), [panelBlock("files"), panelBlock("changes"), PANEL_ACCOUNTS_BLOCK]);
});

test("test_remod_installs_the_accounts_mod_when_the_patch_fails", () => {
  const box = sandbox(SHIPPED_LAYOUT);
  write(join(box.src, "agents-menu.patch"), STALE_PATCH);

  const run = remod(box);

  assert.equal(run.status, 1);
  assert.match(run.stderr, /agents-menu.patch does not apply to the shipped agents mod/);
  assert.equal(existsSync(join(box.app, "mods", "agents-menu")), false);
  assert.equal(existsSync(join(box.app, "mods", "accounts", "main.js")), true);
  assert.deepEqual(sidebarLists(box), [block("spaces", "spaces"), block("agents", "agents")]);
  assert.deepEqual(panelStack(box), [panelBlock("files"), panelBlock("changes"), PANEL_ACCOUNTS_BLOCK]);
});
