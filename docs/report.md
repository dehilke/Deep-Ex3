# doit — Project Report

`doit` is an interactive LLM agent for the shell: you describe what you want in
natural language, the model turns it into a single shell command, the program
classifies how risky that command is, asks for confirmation when needed, runs
it, and shows the result. On top of that base it can ask a clarifying question
when a request is ambiguous, work with cloud **and** local models (with or
without native tool-calling), and — through a persistent context layer — remember
earlier turns, keep durable memories, stay aware of what the user did by hand,
and separate work across terminal windows.

This is a single, joint report. The two halves were implemented separately:

| Part | Sections | Topic |
|------|----------|-------|
| **A** | 1–6 | The command path: translation, the safety gate, **model flexibility** (cloud / local / tool-calling), the native tool-calling path, and **clarifying questions**. |
| **B** | 7–12 | The **context layer**: multi-turn history, sessions/multi-tasking, persistent memory, shell-history awareness, and the project-profile extension. |

Everything lives in one executable script, `doit`. The two halves meet in
`main()`, which loads `~/doit.cfg` and dispatches on the `tool_calling` flag:

```python
def main(argv):
    instruction = " ".join(argv).strip()
    ...
    settings = load_config()
    if settings["tool_calling"]:
        handle_tool_calling(settings, instruction)   # Part A: native tool path
    else:
        handle(settings, instruction, session_id())  # default: prompt-and-parse + context
```

All transcripts below were produced by running `doit` in WSL against the three
real models described in §3 (configs swapped in `~/doit.cfg`); they are pasted
verbatim, only trimmed for length.

---

# Part A — Command path, safety, model flexibility, clarification

## 1. Translating natural language into a command

**What.** A turn is one process. `handle()` assembles the messages (system
prompt + context, see Part B), calls the model through `call_llm()`, and parses
the reply with `ask_model()`. The model is required to answer with **one JSON
object** — there is no free-form parsing of prose. The contract (full text in
`SYSTEM_PROMPT`) has a discriminating `kind` field:

```json
{
  "kind": "command | answer | clarify | refuse",
  "command": "the shell command (kind=command)",
  "risk": "safe | confirm",
  "explanation": "one sentence (kind=command)",
  "answer": "text reply (kind=answer/refuse)",
  "question": "the clarifying question (kind=clarify)",
  "options": ["optional numbered choices (kind=clarify)"],
  "cd": "dir to navigate to, else \"\"",
  "memories_to_store": ["durable facts about the user"],
  "memories_to_forget": [/* memory ids */]
}
```

**Design decisions.**
- *One call returns everything* — command, risk, optional navigation, memory ops,
  or a clarifying question — instead of a separate LLM call per concern. A single
  turn can both act and remember (Part B §9).
- *`kind` is the router.* `command` runs; `answer`/`refuse` just print text;
  `clarify` asks a question first (§6). This keeps "tell me a joke", "how do I
  …?", "why did that fail?" and an actual command on one uniform code path.
- *Forgiving parse.* `ask_model()` strips accidental ```` ```json ```` fences and,
  on a `JSONDecodeError`, degrades to a `refuse` with the raw text rather than
  crashing — important because weaker local models occasionally wrap their JSON.

**Example (cloud model, a question vs. a command):**
```
> doit "what is the difference between the cp and mv commands?"
Both cp and mv are file-management commands. cp copies a file ... leaving the
original unchanged ...; mv moves (renames) a file ..., removing it from its
original location. Use cp when you need to keep the source, and mv when you
want to relocate or rename the source.

> doit "show me the files here, one per line"
# List files in the current directory, one per line.
$ ls -1
a.py
b.txt
c.py
notes.md
```
The first is `kind=answer` (no command runs); the second is `kind=command`,
`risk=safe`, so it runs immediately.

---

## 2. Safety: risk classification + the confirmation gate

**What.** Every `command` reply carries a `risk`:
- `safe` — read-only, no side effects (`ls`, `cat`, `grep`, `df`, …): run without
  asking.
- `confirm` — changes or destroys state (`rm`, `mv`, `mkdir`, `pip install`,
  `git commit`, …): print the proposed command and require a `y`/`yes` before
  running.

The gate is the `risk == CONFIRM` block in `handle()` (and `maybe_run()` on the
tool path). `confirm()` reads a `y/N` answer; **anything else — including EOF or
Ctrl-C — aborts**, so the safe default is to *not* run.

**Example (cloud model, gate fires and the user declines):**
```
> doit "create an empty file named demo.txt here"
# Creates an empty file named demo.txt in the current directory.
Proposed command:
  touch demo.txt
Run it? [y/N] Aborted.
```

**Design decision & finding — the gate is only as good as the classification.**
The mechanism is correct: it always asks before running a `confirm` command and
defaults to no. But the *risk label comes from the model*, and weaker models get
it wrong. The exact same request above, on the two local models, was labelled
`safe` and therefore **ran with no prompt at all**:

```
# llama3 (local):
> doit "create an empty file named demo.txt here"
$ touch demo.txt && chmod 644 demo.txt
[after run] demo.txt exists? YES        <-- no confirmation was asked

# lfm2.5 (local, tool path):
> doit "create an empty file named demo.txt here"
# Creates an empty file named demo.txt in the current directory.
$ touch demo.txt
The empty file demo.txt has been successfully created.
[after run] demo.txt exists? YES        <-- no confirmation was asked
```
Both local models classified a state-changing `touch` as `safe`; the cloud model
classified it as `confirm`. **Conclusion:** the confirmation feature is sound,
but its safety value depends on model quality — a smaller model both *writes* and
*judges* the command, and a misjudgement silently bypasses the gate. A
conservative hardening (a regexp denylist that forces `confirm` for `rm/mv/dd/…`
regardless of the model's label) is listed under future work in §13.

---

## 3. Model flexibility (cloud, local, tool-calling)

The assignment asks the program to work across model "roles", not just one
provider. `doit` reaches every model through **LiteLLM**, so the model string in
`~/doit.cfg` is the only thing that changes. Three roles were exercised:

| Role | `~/doit.cfg` `model` | `tool_calling` | Path used |
|------|----------------------|----------------|-----------|
| Cloud API | `openrouter/openai/gpt-oss-120b:free` | `false` | prompt-and-parse |
| Local, no tool-calling | `ollama_chat/llama3` | `false` | prompt-and-parse |
| Local, native tool-calling | `ollama_chat/lfm2.5` | `true` | tool-calling |

**Config-driven, zero code change.** `load_config()` reads `model`, `api_key`,
`api_base`, `temperature`, and `tool_calling`. Switching role is just editing
`~/doit.cfg` (the file ships with all three blocks; comment/uncomment one):

```ini
[model]
model = ollama_chat/lfm2.5          # local model served by Ollama
api_base = http://localhost:11434   # local endpoint; no api_key needed
temperature = 0.0
tool_calling = true                 # lfm2.5 is trained for tool use
```

**Design decisions.**
- *LiteLLM as the single abstraction.* OpenAI, OpenRouter, Anthropic and local
  Ollama models all go through `litellm.completion(**kwargs)`; provider routing
  is entirely in the model-string prefix (`openrouter/…`, `ollama_chat/…`).
- *Prefer `ollama_chat/` over `ollama/`* for local models — it uses Ollama's chat
  endpoint, which handles system prompts and tool calls far better.
- *`temperature = 0.0`* everywhere, because command generation should be
  deterministic, not creative.
- *Two extraction paths, one flag.* Capable, tool-trained models can use the
  provider's native tool-calling API; everything else (and every cloud model we
  want maximum compatibility with) stays on prompt-and-parse. §4 covers the tool
  path; the choice is the `tool_calling` boolean.

**Findings across the three roles (same two requests in each):**
- *Translation is robust everywhere.* All three produced correct commands for the
  safe request (`ls -1`).
- *Risk classification degrades on small models.* Only the cloud model flagged
  `touch` as `confirm`; both local models called it `safe` (§2).
- *Small models leak extra fields.* `llama3` emitted a spurious `cd` (it returned
  a `cd` value for a plain "list files" request, printing `cd /tmp/doit_local`),
  and appended a gratuitous `&& chmod 644`. These are tolerated by the schema but
  illustrate why prompt-and-parse needs the forgiving parser in §1.

**Takeaway.** Model flexibility is a config concern, not a code concern — but the
*quality* of the safety gate and of structured-output adherence is a real
function of model capability, which is exactly why the `tool_calling` switch and
the forgiving JSON parse exist.

---

## 4. The native tool-calling path

**What.** When `tool_calling = true`, `handle_tool_calling()` runs instead of
`handle()`. The model is given a real function tool, `run_shell_command`
(`SHELL_TOOL`), whose schema encodes the same contract as the JSON prompt —
`command`, `risk` (enum `safe`/`confirm`), `explanation`:

```python
SHELL_TOOL = {"type": "function", "function": {
    "name": "run_shell_command",
    "parameters": {"type": "object", "properties": {
        "command": {...}, "risk": {"enum": [SAFE, CONFIRM], ...},
        "explanation": {...}}, "required": ["command", "risk", "explanation"]}}}
```

The system prompt (`TOOL_SYSTEM_PROMPT`) is deliberately short: the model either
**calls the tool** (→ run, gated by `maybe_run()`) or **answers in text** (no
tool call → just print it). The real payoff over prompt-and-parse is the second
half: the command's output is fed back as a `role: "tool"` message and the model
**summarises the result**.

**Example (lfm2.5, tool call → run → summary):**
```
> doit "show me the files here, one per line"
# List files in the current directory, one per line
$ ls -1
a.py
b.txt
c.py
notes.md
a.py
b.txt
c.py
notes.md
```
The first `ls -1` block is the command's real stdout (printed by
`run_command()`); the second block is the model's summary of that output fed
back through the tool message.

**Design decisions.**
- *Same risk contract on both paths* (`SAFE`/`CONFIRM` enum), so the safety gate
  behaves identically whether the command arrived as JSON or as a tool call —
  `maybe_run()` is shared gating used by the tool path.
- *One command per turn*: only the first tool call is acted on, keeping the
  "translate one request → one command" contract.
- *The summary is best-effort*: it is wrapped so a failure to summarise never
  fails the run (the command already executed).

**Findings (lfm2.5 on the tool path), kept honestly:**
- *Tool-use decision is inconsistent.* For a "create a file" request lfm2.5 at
  first answered in **prose** (a ```` ```bash ```` block) instead of emitting a tool
  call. Hardening `TOOL_SYSTEM_PROMPT` ("you MUST call the tool; do not describe
  it in prose") fixed it — small tool-trained models need a firmer contract than
  large ones.
- *Risk misclassification reaches this path too* — lfm2.5 labelled `touch` as
  `safe` (§2), so `maybe_run()` ran it without confirming. The gate logic is
  correct; the label was wrong.
- *Output duplication*: because both `run_command()` and the model's summary
  print the result, simple read-only commands echo their output twice. A cleaner
  version would suppress `run_command()`'s print on the tool path and rely on the
  summary, or vice-versa.

**Why keep two paths?** Prompt-and-parse works with *any* model and is where the
whole context layer (Part B) lives; native tool-calling gives nicer
result-summaries but only on models trained for it. The flag lets each model use
its best mode without forking the program.

---

## 5. End-to-end basics, recap

Putting §1–§2 together, the default loop for one request is: **translate →
classify risk → (confirm if needed) → run → show**, with the result also captured
into history (Part B). The cloud model walks the full loop cleanly:

```
> doit "list the files here sorted by date"
# List files in the current directory sorted by modification date (newest first).
$ ls -lt
-rw-r--r-- 1 dehilke dehilke 0 ... a.py
-rw-r--r-- 1 dehilke dehilke 0 ... b.txt
...
```
Note it chose modification time **without** asking — see §6 for why that is the
right behaviour and not a missed clarification.

---

## 6. Asking the user when unsure (clarification)

**What.** A fourth `kind`, `clarify`, lets the agent ask **one** short question
instead of guessing, and **wait for the answer before continuing**. The model
returns `question` and an optional `options` list; `handle()` runs a bounded
clarification loop:

```python
while reply.get("kind") == "clarify" and rounds < MAX_CLARIFY_ROUNDS:
    answer = ask_clarification(reply)      # prints question + numbered menu
    if answer is None:                     # no answer (empty / EOF / Ctrl-C)
        print("Aborted."); return          # never guess on silence
    messages += [assistant(question), user(answer)]
    reply = ask_model(settings, messages)  # re-ask with the answer folded in
```

`ask_clarification()` prints the question and any options as a numbered menu and
lets the user reply with the **option number** (`1`) instead of retyping the
text. The loop is capped by `MAX_CLARIFY_ROUNDS` (2) so an indecisive model can't
loop forever, and the resolved answer is appended to the turn's recorded
instruction (`"… (clarified: creation date)"`) so Part B's history stays
coherent.

**Design decision — useful, not annoying.** The system prompt tells the model to
clarify **only** when the ambiguity would change the command *and* context can't
resolve it; if a sensible default exists, just run. That is exactly why "sorted
by date" in §5 ran with modification-time instead of interrogating the user — the
default is obvious. Clarification fires only on genuine forks:

**Example (cloud model, a real clarification — menu, answer, then command):**
```
> doit "free up some space on my machine"
Which type of files would you like to remove to free up space?
  1. Package caches
  2. Temporary files
  3. Large logs
  4. Docker images
  5. Other
> 1
# Clears the apt package manager cache to free disk space.
Proposed command:
  sudo apt-get clean
Run it? [y/N]
Aborted.
```
Here the request truly forks (caches vs. logs vs. Docker images), so the agent
asks, waits, takes answer `1`, produces the matching command — and because that
command is state-changing it then hits the §2 confirmation gate.

**Limitations.** Clarification currently lives on the prompt-and-parse path only;
the assignment notes it could also be a dedicated `ask_user` tool on the
tool-calling path (future work, §13). The clarifying turn is one extra LLM
round-trip.

---

# Part B — The context layer

This half turns a stateless, per-invocation CLI into an agent that remembers
earlier turns, keeps durable memories, is aware of what the user did by hand in
the shell, separates work across terminal windows, and adapts per project folder.
Example interactions are taken from the test scripts in `tests/` (`e2e.sh`,
`e2e2.sh`).

## 7. Architecture: disk *is* the memory

Every `doit "…"` is its own process and its own turn. Nothing survives in RAM
between turns, so all persistent state lives under `~/.doit/`:

```
~/.doit/
  history.jsonl          one JSON record per turn (all sessions, append-only)
  memory.jsonl           durable facts about the user
  sessions/<sid>.cd      one-shot "change the parent shell to here" request
```

On each turn `build_context()` reloads these files and assembles the message list
described in [`docs/acdl/context.acdl`](./acdl/context.acdl) (visual in
[`rendered-prompt.md`](./acdl/rendered-prompt.md)). The model replies with a
single JSON object; `handle()` fans that reply out into *run / cd / remember /
forget* and appends the turn back to `history.jsonl`. This is the same one-call
schema introduced in Part A §1 — context, action, and memory in a single
round-trip.

---

## 8. Multi-turn history

**What.** `save_interaction()` appends each turn to `history.jsonl` with
`session`, `cwd`, `instruction`, `kind`, `command`, `risk`, `explanation`,
`stdout`, `stderr`, `returncode`. `build_context()` replays the current session's
turns as real chat messages via `turn_to_messages()`: the user instruction
(`U:`), the command the agent ran (`A:`), and the captured output as a `[output]`
note (`U:`). Output is clipped to `OUTPUT_CLIP` (1500 chars).

**Design decisions.**
- *JSONL, not a DB:* append-only, human-readable, trivially tail-able.
- *Output goes back into context* so follow-ups can reason about results ("why
  did that fail?", "which of these is safe to delete?").
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
Turn 2 said only "now show only the python ones" — it resolved "the python ones"
purely from turn 1's history.

**Limitations.** Only the last `MAX_SESSION_TURNS` (8) turns are replayed (no
summarization of older history — the "context compaction" extension). Output is
clipped, so questions about the tail of a huge output can miss it.

---

## 9. Sessions & multi-tasking

**What.** Every record is tagged with a `session` id. `session_id()` uses
`$DOIT_SESSION_ID` (set per-terminal by the install snippet) and falls back to
`ppid-<parent-shell-pid>`, which is already distinct per window. `build_context()`
replays **only the current session's** turns, while `other_sessions_note()` adds
a short, labelled summary (`[sid @ cwd] "instruction" -> command`) of recent turns
from *other* terminals, used only when the user explicitly references another
window.

**Design decisions.**
- *ppid fallback* means multi-tasking works even if the user never edits their
  `.bashrc` — two windows automatically get separate streams.
- *Asymmetric scoping:* current session is replayed in full dialogue form; other
  sessions are a flat note. This keeps "sort *them*" local while still allowing
  "do what I did in the other window".

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

**Limitations.** The cross-session note is recency-capped (`MAX_OTHER_TURNS` = 4);
a reference to something done much earlier in another window may fall out of the
window. `ppid` ids change if the shell restarts.

---

## 10. Persistent memory

**What.** `memory.jsonl` holds `{id, text, ts}` records. The model proposes
`memories_to_store` / `memories_to_forget`; `store_memories()` appends (dedup-ing
exact repeats) and `forget_memories()` drops by id. `memory_block()` injects them
into the system prompt as a numbered list, so the ids the model sees for
forgetting match the ids on disk.

**Design decisions.**
- *Model-curated, not keyword-triggered:* the model decides what is "durable" vs.
  ephemeral, handling standing instructions ("always sort newest first") and
  facts ("my class folder is …") uniformly.
- *Stable integer ids* make "I changed my mind, forget that" a precise delete
  instead of fuzzy text matching.
- *Memory is global* (not session-scoped) so it survives new windows, dirs, and
  sessions — the property that distinguishes it from history.

**Example (from `e2e.sh`):**
```
> remember that I always like ls with details and human-readable sizes
(remembered: User prefers ls with -l and -h options ...)
...
> list files here          # a later, unrelated turn
# List files with detailed info and human-readable sizes as you prefer.
$ ls -lh                    # memory changed the generated command ✔
```

**Combined action + memory** (the assignment's key case) is supported because
`cd` and `memories_to_store` are independent fields on the same reply: one
`doit "move to ~/…/ass3, this is my class folder"` both navigates and remembers.

**Limitations.** No semantic dedup; no automatic expiry; all memories are always
injected, so a very large store would grow the prompt.

---

## 11. User awareness (real shell history)

**What.** `read_shell_history()` reads `$HISTFILE` / `~/.bash_history` /
`~/.zsh_history` (handling zsh's `: ts:0;cmd` format), takes the last
`MAX_SHELL_LINES` (15), and `shell_activity_block()` tags each line `(user)` or
`(doit)` so the model can separate the user's manual actions from the agent's.

**Design decisions.**
- *Read the shell's own history file* (zero extra setup) rather than requiring a
  hook, so it works out of the box.
- *Tagging the two streams* directly answers "distinguish between commands run by
  the user and commands run by doit".
- *cwd comes for free:* because `doit` is launched from the user's shell, a manual
  `cd` is already reflected in `os.getcwd()`, injected as the current directory.

**Example (from `e2e2.sh`):** shell history contained `cd … / mkdir data /
python train.py / git status`, then:
```
> summarize what I just did in the shell
You changed to ~/school/llms/ass3, created a 'data' directory, ran a Python
training script (python train.py), and checked the Git status. ...   ✔
```

**Limitations.** Bash only flushes history to file on exit unless
`PROMPT_COMMAND='history -a'` is set, so very recent commands may be missing
without the install snippet; the history file is global, so attribution to a
specific terminal is best-effort.

---

## 12. Extension: project profiles (`.doit.md`)

**Why this extension.** Of the suggested options it best exercises *context
management* and *per-context behavior* — the agent should behave differently in
different folders, the way real agents read an `AGENTS.md`. It is a genuine
capability (it changes which commands the agent chooses), not a UI tweak.

**What.** `find_project_profile()` walks up from the cwd to `$HOME` looking for a
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

**Limitations.** First match wins (no merging of nested profiles); the whole file
is injected (no size cap).

---

# §13. Future work (described, not implemented)

- *Risk denylist:* force `confirm` for `rm/mv/dd/mkfs/…` regardless of the model's
  label, to harden the gate against small-model misclassification (§2).
- *Clarification as a tool* on the native tool-calling path (a dedicated
  `ask_user` tool), so §6 works in tool-calling mode too.
- *Suppress duplicate output* on the tool path (§4).
- *Context compaction:* summarize the oldest turns once history exceeds N, to
  bound prompt growth (§8).
- *Multi-step plans:* let one request expand into a confirmed sequence of
  commands, re-planning on failure.

---

# §14. How to verify

- **Offline (no API key, no LLM):** `python tests/test_doit.py` — 20 assertions
  over history, sessions, memory, shell-awareness, profiles, and context
  assembly. The clarification loop and the confirm gate are also unit-tested
  offline by stubbing the model and `input()`.
- **End-to-end (needs `~/doit.cfg` + bash):** `bash tests/e2e.sh` and
  `bash tests/e2e2.sh` in WSL/Linux.
- **Model flexibility:** swap the `[model]` block in `~/doit.cfg` between the
  three roles in §3 (cloud / local-no-tools / local-tools) and re-run any
  request; the transcripts in Part A were produced exactly this way.

---

# §15. Install snippet (sessions + real `cd` + fresh history)

Add to `~/.bashrc` (a documented change, per the assignment):

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
