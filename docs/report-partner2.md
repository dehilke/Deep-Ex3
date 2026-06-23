# doit — Report (Partner 2: History, Memory, Context, Sessions, Extension)

This part of the report covers the **context layer** of `doit`: how a stateless,
per-invocation CLI is turned into an agent that remembers earlier turns, keeps
durable memories, is aware of what the user did by hand in the shell, separates
work across terminal windows, and adapts per project folder.

All example interactions below are copied verbatim from the test scripts in
`tests/` (`e2e.sh`, `e2e2.sh`), run in WSL against the configured model
(`openrouter/openai/gpt-oss-120b:free`).

## 0. Architecture: disk *is* the memory

Every `doit "…"` is its own process and its own turn (`@T`). Nothing survives in
RAM between turns, so all persistent state lives under `~/.doit/`:

```
~/.doit/
  history.jsonl          one JSON record per turn (all sessions, append-only)
  memory.jsonl           durable facts about the user
  sessions/<sid>.cd      one-shot "change the parent shell to here" request
```

On each turn `build_context()` reloads these files and assembles the message
list described in [`docs/acdl/context.acdl`](./acdl/context.acdl) (visual in
[`rendered-prompt.md`](./acdl/rendered-prompt.md)). The model replies with a
single JSON object; `handle()` fans that reply out into *run / cd / remember /
forget* and then appends the turn back to `history.jsonl`.

### The response schema (structured output)

The whole system is driven by one JSON contract (full text in `SYSTEM_PROMPT`
inside `doit`):

```json
{
  "kind": "command | answer | refuse",
  "command": "the shell command (kind=command)",
  "risk": "safe | confirm",
  "explanation": "one sentence (kind=command)",
  "answer": "text reply (kind=answer/refuse)",
  "cd": "dir to navigate to, else \"\"",
  "memories_to_store": ["durable facts about the user"],
  "memories_to_forget": [/* memory ids */]
}
```

Design decision: a **single call returns everything** — command, risk, optional
navigation, and memory operations — instead of a separate LLM call per concern.
The same turn can both *act* and *remember* (the assignment's "move to … this is
my class folder" case) without extra round-trips.

---

## 1. Multi-turn history

**What:** `save_interaction()` appends each turn to `history.jsonl` with
`session`, `cwd`, `instruction`, `kind`, `command`, `risk`, `explanation`,
`stdout`, `stderr`, `returncode`. `build_context()` replays the current
session's turns as real chat messages via `turn_to_messages()`: the user
instruction (`U:`), the command the agent ran (`A:`), and the captured output as
a `[output]` note (`U:`). Output is clipped to `OUTPUT_CLIP` (1500 chars).

**Design decisions:**
- *JSONL, not a DB:* append-only, human-readable, trivially tail-able for logs.
- *Output goes back into context* so follow-ups can reason about results
  ("why did that fail?", "which of these is safe to delete?").
- *Replay as chat roles* rather than one blob, so the model treats it as genuine
  dialogue and resolves anaphora ("them", "those") naturally.

**Example (from `e2e.sh`):**
```
=== turn 1: list files ===
$ ls -la
... a.py  b.txt  c.py  notes.md
=== turn 2: multi-turn reference (the python ones) ===
# List only files with .py extension in the current directory.
$ ls -1 *.py
a.py
c.py
```
Turn 2 said only "now show only the python ones" — it resolved "the python
ones" purely from turn 1's history.

**Limitations:** only the last `MAX_SESSION_TURNS` (8) turns are replayed (no
summarization of older history — that would be the "context compaction"
extension). Output is clipped, so questions about the tail of a huge output can
miss it.

---

## 2. Sessions & multi-tasking

**What:** every record is tagged with a `session` id. `session_id()` uses
`$DOIT_SESSION_ID` (set per-terminal by the install snippet) and falls back to
`ppid-<parent-shell-pid>`, which is already distinct per window. `build_context()`
replays **only the current session's** turns, while `other_sessions_note()` adds
a short, labelled summary (`[sid @ cwd] "instruction" -> command`) of recent
turns from *other* terminals, used only when the user explicitly references
another window.

**Design decisions:**
- *ppid fallback* means multi-tasking works even if the user never edits their
  `.bashrc` — two windows automatically get separate streams.
- *Asymmetric scoping:* current session is replayed in full dialogue form;
  other sessions are a flat note. This is what makes "sort *them*" stay local
  while still allowing "do what I did in the other window".

**Example (from `e2e2.sh`):** window1 lists files, window2 makes folders, then:
```
--- window1: 'sort them by date' (must mean the FILES, not win2 folders) ---
$ ls -lt
... a.txt  z.txt                # the files, NOT the 2020-2026 folders ✔
--- window1: explicit cross-session ref ---
> what did I do in the other terminal window?
In the other terminal you created a set of directories named 2020 through 2026
with the command: mkdir -p 2020 2021 2022 2023 2024 2025 2026   ✔
```

**Limitations:** the cross-session note is recency-capped
(`MAX_OTHER_TURNS` = 4); a reference to something done much earlier in another
window may fall out of the window. `ppid` ids change if the shell restarts.

---

## 3. Persistent memory

**What:** `memory.jsonl` holds `{id, text, ts}` records. The model proposes
`memories_to_store` / `memories_to_forget`; `store_memories()` appends
(dedup-ing exact repeats) and `forget_memories()` drops by id.
`memory_block()` injects them into the system prompt as a numbered list, so the
ids the model sees for forgetting match the ids on disk.

**Design decisions:**
- *Model-curated, not keyword-triggered:* the model decides what is "durable"
  vs. ephemeral, which handles standing instructions ("always sort newest
  first") and facts ("my class folder is …") uniformly.
- *Stable integer ids* make "I changed my mind, forget that" implementable as a
  precise delete instead of fuzzy text matching.
- *Memory is global* (not session-scoped) so it survives new windows, new dirs,
  and new sessions — the property that distinguishes it from history.

**Example (from `e2e.sh`):**
```
> remember that I always like ls with details and human-readable sizes
(remembered: User prefers ls with -l and -h options ...)
...
> list files here          # a later, unrelated turn
# List files with detailed info and human-readable sizes as you prefer.
$ ls -lh                    # memory changed the generated command ✔
```

**Combined action + memory** (assignment's key case) is supported because `cd`
and `memories_to_store` are independent fields on the same reply: one
`doit "move to ~/…/ass3, this is my class folder"` both navigates and remembers.

**Limitations:** no semantic dedup (two differently-worded but equivalent
memories can coexist); no automatic expiry; all memories are always injected, so
a very large memory store would grow the prompt.

---

## 4. User awareness (real shell history)

**What:** `read_shell_history()` reads `$HISTFILE` / `~/.bash_history` /
`~/.zsh_history` (handling zsh's `: ts:0;cmd` format), takes the last
`MAX_SHELL_LINES` (15), and `shell_activity_block()` tags each line `(user)` or
`(doit)` so the model can separate the user's manual actions from the agent's.

**Design decisions:**
- *Read the shell's own history file* (zero extra setup) rather than requiring a
  hook, so it works out of the box; a hook is offered for richer cases.
- *Tagging the two streams* directly answers the assignment's "distinguish
  between commands run by the user and commands run by doit".
- *cwd comes for free:* because `doit` is launched from the user's shell, a
  manual `cd` is already reflected in `os.getcwd()`, which is injected as
  `CURRENT_DIR`.

**Example (from `e2e2.sh`):** shell history contained `cd … / mkdir data /
python train.py / git status`, then:
```
> summarize what I just did in the shell
You changed to ~/school/llms/ass3, created a 'data' directory, ran a Python
training script (python train.py), and checked the Git status. ...   ✔
```

**Limitations:** bash only flushes history to file on exit unless
`PROMPT_COMMAND='history -a'` is set, so very recent commands may be missing
without the install snippet; the history file is global, so attribution to a
specific terminal is best-effort.

---

## 5. Extension: project profiles (`.doit.md`)

**Why this extension:** of the suggested options it best exercises *context
management* and *per-context behavior* — the agent should behave differently in
different folders, the way real agents read an `AGENTS.md`/`agent.md`. It is a
genuine capability (it changes what commands the agent chooses), not a UI tweak.

**What:** `find_project_profile()` walks up from the cwd to `$HOME` looking for a
`.doit.md` file; `project_profile_block()` injects its contents into the system
prompt as folder-specific instructions. Because it walks **up**, the profile
applies in subdirectories too.

**Example (from `e2e2.sh`):** a folder with `.doit.md` saying *"Node.js project.
Use npm. test: npm run test:unit"*:
```
> run the tests
# Runs the project's unit test suite as defined in the project profile.
$ npm run test:unit          # picked the project-specific command ✔
```
Without the profile, "run the tests" is ambiguous; the profile makes the agent
choose the project's real test command.

**Limitations:** first match wins (no merging of nested profiles); the whole
file is injected (no size cap), so a large profile inflates the prompt.

**Two further extensions (described, not implemented):**
1. *Context compaction:* when session history exceeds N turns, summarize the
   oldest turns into a single rolling summary message to bound prompt growth.
2. *Multi-step plans:* let one request expand into a confirmed sequence of
   commands (a plan the agent executes step-by-step, re-planning on failure).

---

## 6. How to verify

- Offline (no API key, no LLM): `python tests/test_doit.py` — 20 assertions over
  history, sessions, memory, shell-awareness, profiles, context assembly.
- End-to-end (needs `~/doit.cfg` + bash): `bash tests/e2e.sh` and
  `bash tests/e2e2.sh` in WSL/Linux.

## 7. Install snippet (sessions + real `cd` + fresh history)

Add to `~/.bashrc` (documented change, per the assignment):

```bash
# doit: one stable session id per terminal window
export DOIT_SESSION_ID="${DOIT_SESSION_ID:-$$-$(date +%s)}"
# flush each command to history immediately, so doit sees recent user actions
export PROMPT_COMMAND="history -a; ${PROMPT_COMMAND:-}"
# wrapper so doit can change the *parent* shell's directory
doit() {
  command python3 /path/to/doit "$@"
  local f="$HOME/.doit/sessions/$DOIT_SESSION_ID.cd"
  if [ -f "$f" ]; then cd "$(cat "$f")" && rm -f "$f"; fi
}
```

Why each line: the session id gives per-window history streams; `history -a`
makes user-awareness see the latest commands; the wrapper applies `request_cd()`
since a child process cannot change its parent shell's directory on its own.
