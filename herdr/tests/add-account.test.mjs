// Run: node --test ~/dotfiles/herdr/tests/*.test.mjs
// Runs herdr/accounts/add-account.sh with stand-in `claude` and `cswap` programs that log their
// arguments and their CLAUDE_CONFIG_DIR, in a temp HOME and TMPDIR.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT = join(dirname(fileURLToPath(import.meta.url)), "../accounts/add-account.sh");
const THROWAWAY = /^config=\/.+\/claude-add-account\.[A-Za-z0-9]+ /;

// A stand-in that appends "config=<CLAUDE_CONFIG_DIR or -> <name> <args>" to $LOG and exits $2.
const fake = (name, exitCode) => `#!/bin/bash\necho "config=\${CLAUDE_CONFIG_DIR:--} ${name} $*" >> "$LOG"\nexit ${exitCode}\n`;

function setup({ loginExit = 0, withCswap = true } = {}) {
  const root = mkdtempSync(join(tmpdir(), "add-account-test-"));
  const home = join(root, "home");
  const bin = join(root, "bin");
  const tmp = join(root, "tmp");
  for (const dir of [join(home, ".local/bin"), bin, tmp]) mkdirSync(dir, { recursive: true });
  writeFileSync(join(bin, "claude"), fake("claude", loginExit));
  chmodSync(join(bin, "claude"), 0o755);
  if (withCswap) {
    writeFileSync(join(home, ".local/bin/cswap"), fake("cswap", 0));
    chmodSync(join(home, ".local/bin/cswap"), 0o755);
  }
  return { home, bin, tmp, log: join(root, "log") };
}

function run(box, stdin) {
  const env = { HOME: box.home, TMPDIR: box.tmp, LOG: box.log, PATH: `${box.bin}:/usr/bin:/bin` };
  const r = spawnSync("bash", [SCRIPT], { input: stdin, encoding: "utf8", env });
  let lines = [];
  try { lines = readFileSync(box.log, "utf8").trim().split("\n"); } catch { lines = []; }
  return { status: r.status, stderr: r.stderr, lines, leftovers: readdirSync(box.tmp) };
}

test("test_add_account_signs_in_to_a_throwaway_folder_then_adds_twice_and_lists", () => {
  const box = setup();

  const r = run(box, "\n");

  assert.equal(r.status, 0);
  assert.equal(r.lines.length, 4);
  assert.match(r.lines[0], THROWAWAY);
  assert.match(r.lines[0], / claude auth login --claudeai$/);
  assert.match(r.lines[1], THROWAWAY);
  assert.match(r.lines[1], / cswap add$/);
  assert.equal(r.lines[2], "config=- cswap add");
  assert.equal(r.lines[3], "config=- cswap list");
});

test("test_add_account_passes_the_typed_email_to_the_login", () => {
  const box = setup();

  const r = run(box, "alt@example.com\n");

  assert.match(r.lines[0], / claude auth login --claudeai --email alt@example\.com$/);
});

test("test_add_account_removes_the_throwaway_folder", () => {
  const box = setup();

  const r = run(box, "\n");

  assert.deepEqual(r.leftovers, []);
});

test("test_add_account_failed_login_adds_nothing", () => {
  const box = setup({ loginExit: 1 });

  const r = run(box, "\n");

  assert.notEqual(r.status, 0);
  assert.equal(r.lines.length, 1);
  assert.deepEqual(r.leftovers, []);
});

test("test_add_account_without_cswap_stops_before_the_login", () => {
  const box = setup({ withCswap: false });

  const r = run(box, "\n");

  assert.equal(r.status, 1);
  assert.match(r.stderr, /cswap is not installed/);
  assert.deepEqual(r.lines, []);
});

test("test_add_account_closed_input_still_signs_in", () => {
  const box = setup();

  const r = run(box, "");

  assert.equal(r.status, 0);
  assert.match(r.lines[0], / claude auth login --claudeai$/);
});
