#!/usr/bin/env bash
# E2E for sessions / cross-session refs / user-awareness / project profiles.
set -e

REAL_HOME=/home/bentau
REPO=/mnt/c/Users/User/Desktop/Deep-Ex3

TMP=$(mktemp -d)
cp "$REAL_HOME/doit.cfg" "$TMP/doit.cfg"
export PYTHONPATH="$REAL_HOME/.local/lib/python3.12/site-packages:$PYTHONPATH"
export HOME="$TMP"

CLASS="$TMP/school/llms/ass3"; mkdir -p "$CLASS"; touch "$CLASS/z.txt" "$CLASS/a.txt"
DOCS="$TMP/documents"; mkdir -p "$DOCS"

# auto-confirm 'y' for any confirm-gated command (safe cmds ignore stdin)
doit() { printf 'y\n' | python3 "$REPO/doit" "$@"; }

echo "################ MULTI-TASKING / SESSIONS ################"
cd "$CLASS"
echo "--- window1: list files ---"
DOIT_SESSION_ID=win1 doit "list the files here"
cd "$DOCS"
echo "--- window2: create yearly folders ---"
DOIT_SESSION_ID=win2 doit "create a folder for each year from 2020 to 2026"
echo "--- window2 result ---"; ls "$DOCS"
cd "$CLASS"
echo "--- window1: 'sort them by date' (must mean the FILES, not win2 folders) ---"
DOIT_SESSION_ID=win1 doit "sort them by date"
echo "--- window1: explicit cross-session ref ---"
DOIT_SESSION_ID=win1 doit "what did I do in the other terminal window?"

echo
echo "################ USER AWARENESS (shell history) ################"
HF="$TMP/.bash_history"
printf 'cd ~/school/llms/ass3\nmkdir data\npython train.py\ngit status\n' > "$HF"
export HISTFILE="$HF"
echo "--- summarize what I just did (should reflect cd/mkdir/python/git) ---"
DOIT_SESSION_ID=win3 doit "summarize what I just did in the shell"
unset HISTFILE

echo
echo "################ PROJECT PROFILE EXTENSION ################"
PROJ="$TMP/coolproj"; mkdir -p "$PROJ"
cat > "$PROJ/.doit.md" <<'EOF'
This is a Node.js project.
- Use `npm` (never yarn).
- The test command for this project is: npm run test:unit
EOF
cd "$PROJ"
echo "--- ask to run tests; profile should pick npm run test:unit ---"
DOIT_SESSION_ID=win4 doit "run the tests"

echo
echo "ALL DONE"
