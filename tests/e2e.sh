#!/usr/bin/env bash
# End-to-end smoke test for doit, run inside WSL/Linux where /bin/bash works.
# Uses an isolated temp HOME so the user's real ~/.doit state stays clean.
set -e

REAL_HOME=/home/bentau
REPO=/mnt/c/Users/User/Desktop/Deep-Ex3

TMP=$(mktemp -d)
cp "$REAL_HOME/doit.cfg" "$TMP/doit.cfg"
# Keep the real user-site importable (litellm) even though HOME is isolated.
export PYTHONPATH="$REAL_HOME/.local/lib/python3.12/site-packages:$PYTHONPATH"
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
