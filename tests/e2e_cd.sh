#!/usr/bin/env bash
# E2E for the cd-wrapper + memory-driven navigation.
set -e

# Resolve the repo from this script's own location; keep using the caller's HOME.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REAL_HOME="${REAL_HOME:-$HOME}"
PYBIN="${PYBIN:-python3}"

TMP=$(mktemp -d)
cp "$REAL_HOME/doit.cfg" "$TMP/doit.cfg"
# Keep installed packages (litellm) importable even though HOME is isolated below.
export PYTHONPATH="$("$PYBIN" -c 'import os,site; print(os.pathsep.join((site.getsitepackages() if hasattr(site,"getsitepackages") else [])+[site.getusersitepackages()]))' 2>/dev/null):$PYTHONPATH"
export HOME="$TMP"
mkdir -p "$TMP/school/llms/ass3"

export DOIT_BIN="$REPO/doit"
export DOIT_SESSION_ID="cd-test"
# shellcheck disable=SC1090
source <(sed 's/\r//' "$REPO/doit.bashrc")

cd "$TMP"
echo "pwd before:        $(pwd)"
doit "move to ~/school/llms/ass3. this is my LLM class project folder."
echo "pwd after 'move':  $(pwd)"
echo "--- memory.jsonl ---"; cat "$TMP/.doit/memory.jsonl"

cd "$TMP"
echo "pwd reset to home: $(pwd)"
doit "go to my llm class project"
echo "pwd after recall:  $(pwd)"
echo "ALL DONE"
