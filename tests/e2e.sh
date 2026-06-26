#!/usr/bin/env bash
# End-to-end smoke test for doit, run inside WSL/Linux where /bin/bash works.
# Uses an isolated temp HOME so the user's real ~/.doit state stays clean.
set -e

# Resolve the repo from this script's own location; keep using the caller's HOME.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REAL_HOME="${REAL_HOME:-$HOME}"
PYBIN="${PYBIN:-python3}"

TMP=$(mktemp -d)
cp "$REAL_HOME/doit.cfg" "$TMP/doit.cfg"
# Keep installed packages (litellm) importable even though HOME is isolated below
# -- works whether they live in a venv or in the user site-packages.
export PYTHONPATH="$("$PYBIN" -c 'import os,site; print(os.pathsep.join((site.getsitepackages() if hasattr(site,"getsitepackages") else [])+[site.getusersitepackages()]))' 2>/dev/null):$PYTHONPATH"
export HOME="$TMP"

WORK=$(mktemp -d)
cd "$WORK"
touch a.py b.txt c.py notes.md

echo "=== turn 1: list files ==="
DOIT_SESSION_ID=e2e-A python3 "$REPO/doit" "list the files here"

echo
echo "=== turn 2: multi-turn reference (the python ones) ==="
DOIT_SESSION_ID=e2e-A python3 "$REPO/doit" "now show only the python ones"

echo
echo "=== history.jsonl ==="
cat "$TMP/.doit/history.jsonl"

echo
echo "=== memory: combined action + memory store ==="
DOIT_SESSION_ID=e2e-A python3 "$REPO/doit" "remember that I always like ls with details and human-readable sizes"
echo "--- memory.jsonl ---"
cat "$TMP/.doit/memory.jsonl" 2>/dev/null || echo "(none)"

echo
echo "=== turn 4: does memory influence a fresh request? ==="
DOIT_SESSION_ID=e2e-A python3 "$REPO/doit" "list files here"

echo
echo "ALL DONE"
