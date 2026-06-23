# Rendered context (visual representation)

The textual ACDL lives in [`context.acdl`](./context.acdl). Paste it into the
ACDL site (<https://acdlang26.github.io/acdlsite/>) to generate the official
diagram. Below is a concrete render of the same structure, showing the message
list `build_context()` actually produces for a turn that has prior history.

```
┌──────────────────────────────────────────────────────────────────────┐
│ S: SYSTEM                                                              │
│   ├─ INSTRUCTIONS + RESPONSE_SCHEMA   (static SYSTEM_PROMPT)           │
│   ├─ MEMORY               ◀── sys.memory        (~/.doit/memory.jsonl) │
│   │     [1] User prefers ls -lh                                        │
│   ├─ PROJECT_PROFILE      ◀── sys.project_profile (./.doit.md walk-up) │
│   │     "Node.js project. Use npm. test: npm run test:unit"           │
│   ├─ SHELL_ACTIVITY       ◀── sys.shell_history (~/.bash_history)      │
│   │     (user) cd ~/school/llms/ass3                                   │
│   │     (user) mkdir data                                              │
│   │     (doit) doit "list files"                                       │
│   ├─ OTHER_SESSIONS       ◀── sys.other_sessions (history.jsonl,       │
│   │     [win2 @ ~/documents] "create yearly folders" -> mkdir ...      │
│   │                                          session != current)       │
│   └─ CURRENT_DIR          ◀── env.cwd                                  │
├──────────────────────────────────────────────────────────────────────┤
│ History  (ForEach prior turn WHERE session == current session)        │
│   U: "list the files here"                ◀─┐                          │
│   A: "ls -la  # list with details"          │ sys.turn[@t]            │
│   U: "[output] exit=0 stdout: a.py b.txt"  ◀┘ (history.jsonl)          │
│   U: "now show only the python ones"                                   │
│   A: "ls -1 *.py"                                                      │
│   U: "[output] exit=0 stdout: a.py c.py"                               │
├──────────────────────────────────────────────────────────────────────┤
│ U: env.instruction[@T]   ◀── this turn's request: "sort them by date" │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                       LLM  ──▶  resp[@T]  (JSON)
        { kind, command, risk, explanation, cd,
          memories_to_store[], memories_to_forget[], answer }
                                   │
            ┌──────────────────────┼───────────────────────┐
            ▼                      ▼                       ▼
     run / confirm           request_cd()          store/forget
     (safe vs confirm)    (sessions/<sid>.cd)      memories.jsonl
            │
            ▼
     save_interaction()  ──▶  ~/.doit/history.jsonl   (becomes turn @T+1 context)
```

Key structural points the diagram makes explicit:

* **Disk is the memory.** Every block on the left edge is loaded from a file
  under `~/.doit/`, because each `doit` run is a brand-new process.
* **Two history scopes.** The `History` block is filtered to the *current*
  session, so references like "sort them" stay local to the terminal; the
  `OTHER_SESSIONS` block is a flat, labelled note used only on explicit
  cross-window references.
* **The reply fans out** into four independent effects (run, cd, remember,
  forget), then the whole turn is appended back to `history.jsonl`, closing the
  loop for the next turn.
