#!/usr/bin/env bash
# E2E for the cd-wrapper + memory-driven navigation.
set -e

REAL_HOME=/home/bentau
REPO=/mnt/c/Users/User/Desktop/Deep-Ex3

TMP=$(mktemp -d)
cp "$REAL_HOME/doit.cfg" "$TMP/doit.cfg"
export PYTHONPATH="$REAL_HOME/.local/lib/python3.12/site-packages:$PYTHONPATH"
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
