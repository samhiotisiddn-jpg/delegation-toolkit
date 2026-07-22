#!/usr/bin/env bash
set -euo pipefail

FILE="CLAUDE.md"
if [ ! -f "$FILE" ]; then
  echo "CLAUDE.md not found; skipping."
  exit 0
fi

echo "Scanning CLAUDE.md for risky patterns..."
grep -Ein "(api[_ -]?key|secret|private[_ -]?key|seed phrase|mnemonic|password|dark web|credential harvesting|exploit)" "$FILE" || true
echo "Manual review still required."
