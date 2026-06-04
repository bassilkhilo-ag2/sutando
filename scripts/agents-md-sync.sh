#!/usr/bin/env bash
# Generate AGENTS.md from CLAUDE.md via systematic substitutions.
# Re-runnable and idempotent; AGENTS.md is fully reproducible from CLAUDE.md.
#
# Usage:
#   bash scripts/agents-md-sync.sh           # regenerate AGENTS.md
#   bash scripts/agents-md-sync.sh --check   # exit 1 if AGENTS.md would change (CI)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src="$REPO_ROOT/CLAUDE.md"
dst="$REPO_ROOT/AGENTS.md"

[ -f "$src" ] || { echo "agents-md-sync: CLAUDE.md missing at $src" >&2; exit 1; }

# Order matters: longer 'Claude Code default' before shorter 'Claude Code'
# so the shorter rule doesn't half-substitute the longer phrase first.
sed \
  -e 's/Claude Code default/Codex default/g' \
  -e 's/Claude Code/Codex/g' \
  -e 's/pgrep -f claude/pgrep -f Codex/g' \
  -e 's/CLAUDE\.md/AGENTS.md/g' \
  "$src" > "$dst.tmp"

# Verify expected markers are present (regression catch).
for marker in 'Codex' 'AGENTS.md'; do
  grep -qF "$marker" "$dst.tmp" || {
    echo "agents-md-sync: expected marker '$marker' missing from output" >&2
    rm -f "$dst.tmp"
    exit 1
  }
done

if [ "${1:-}" = "--check" ]; then
  if diff -q "$dst" "$dst.tmp" > /dev/null 2>&1; then
    echo "agents-md-sync: AGENTS.md is up to date"
    rm -f "$dst.tmp"
    exit 0
  else
    echo "agents-md-sync: AGENTS.md is out of sync with CLAUDE.md — run: bash scripts/agents-md-sync.sh" >&2
    rm -f "$dst.tmp"
    exit 1
  fi
fi

mv "$dst.tmp" "$dst"
echo "agents-md-sync: AGENTS.md regenerated from CLAUDE.md ($(wc -l < "$dst") lines)"
