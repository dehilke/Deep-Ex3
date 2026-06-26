# doit shell integration — source this from ~/.bashrc (or ~/.zshrc):
#   echo 'source /path/to/doit.bashrc' >> ~/.bashrc
#
# It does three things, all documented in docs/report.md (§15):
#   1. gives each terminal window a stable session id (per-window history),
#   2. flushes shell history after every command (so doit sees recent actions),
#   3. wraps doit so it can change the *parent* shell's directory.

# 1. one stable session id per terminal window
export DOIT_SESSION_ID="${DOIT_SESSION_ID:-$$-$(date +%s)}"

# 2. append each command to the history file immediately
case ":$PROMPT_COMMAND:" in
  *"history -a"*) ;;                                   # already present
  *) export PROMPT_COMMAND="history -a; ${PROMPT_COMMAND:-}" ;;
esac

# 3. wrapper: run the real doit, then apply any requested directory change
#    EDIT this path to point at your checkout of the doit script.
DOIT_BIN="${DOIT_BIN:-$HOME/doit}"
doit() {
  command python3 "$DOIT_BIN" "$@"
  local cdfile="$HOME/.doit/sessions/$DOIT_SESSION_ID.cd"
  if [ -f "$cdfile" ]; then
    cd "$(cat "$cdfile")" && rm -f "$cdfile"
  fi
}
