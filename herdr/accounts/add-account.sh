#!/bin/bash
# Adds one more Claude account to claude-swap (cswap) without touching the live login.
#
# The Accounts panel's "Add" button runs this in a new Herdr tab. The usual way
# (`claude auth login && cswap add`) replaces the live login, so every running session moves
# to the new account until a switch back. Here the sign-in goes to a throwaway config folder
# instead: cswap reads the login to add from CLAUDE_CONFIG_DIR, but keeps its own account store
# in ~/.claude-swap-backup whatever CLAUDE_CONFIG_DIR says.
#
# Never `claude auth logout` in the throwaway folder: a logout revokes the token, and cswap now
# holds a copy of it. Its Keychain item ("Claude Code-credentials-<hash>") stays behind unused.
set -euo pipefail

readonly CSWAP="$HOME/.local/bin/cswap"

[ -x "$CSWAP" ] || { echo "cswap is not installed: run uv tool install claude-swap" >&2; exit 1; }

tmp="$(mktemp -d "${TMPDIR:-/tmp}/claude-add-account.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

echo "Add a Claude account. Your current login and running sessions stay as they are."
echo "In the browser, sign in with the account to add (not the one in use now)."
read -r -p "Email of the account to add (Enter to pick it in the browser): " email || email=""

CLAUDE_CONFIG_DIR="$tmp" claude auth login --claudeai ${email:+--email "$email"}
CLAUDE_CONFIG_DIR="$tmp" "$CSWAP" add
# cswap add marks the added account as its active one, but the live login did not change.
# Adding the live login again puts that right and refreshes its stored copy.
env -u CLAUDE_CONFIG_DIR -u CLAUDE_SECURESTORAGE_CONFIG_DIR "$CSWAP" add
env -u CLAUDE_CONFIG_DIR -u CLAUDE_SECURESTORAGE_CONFIG_DIR "$CSWAP" list
echo "Done. The Accounts panel shows the new account within a minute."
