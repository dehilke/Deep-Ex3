"""Offline tests for doit's context layer (no LLM calls).

Loads the extensionless `doit` script as a module, points HOME at a temp dir,
and exercises history / sessions / memory / shell-awareness / project profiles /
context assembly directly.

Run:  python tests/test_doit.py
"""

import importlib.util
import os
import sys
import tempfile
from importlib.machinery import SourceFileLoader
from pathlib import Path


def load_doit():
    root = Path(__file__).resolve().parent.parent
    loader = SourceFileLoader("doit", str(root / "doit"))
    spec = importlib.util.spec_from_loader("doit", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def repoint_home(doit, home):
    """Point all of doit's module-level paths at a fresh temp HOME."""
    home = Path(home)
    doit.CONFIG_PATH = home / "doit.cfg"
    doit.STATE_DIR = home / ".doit"
    doit.HISTORY_PATH = doit.STATE_DIR / "history.jsonl"
    doit.MEMORY_PATH = doit.STATE_DIR / "memory.jsonl"
    doit.SESSIONS_DIR = doit.STATE_DIR / "sessions"


PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")


def main():
    doit = load_doit()
    tmp = tempfile.mkdtemp(prefix="doit-test-")
    repoint_home(doit, tmp)
    os.environ["HOME"] = tmp  # for read_shell_history / Path.home() fallbacks

    # --- history + sessions ---------------------------------------------
    doit.save_interaction({"session": "win1", "cwd": "/a",
                           "instruction": "list files", "kind": "command",
                           "command": "ls", "stdout": "a.txt\n", "returncode": 0})
    doit.save_interaction({"session": "win2", "cwd": "/b",
                           "instruction": "make folders", "kind": "command",
                           "command": "mkdir 2020", "returncode": 0})
    hist = doit.load_history()
    check("history persists two turns", len(hist) == 2)
    check("session tag stored", hist[0]["session"] == "win1")

    msgs = doit.build_context({}, "now sort them by date", "win1")
    joined = "\n".join(m["content"] for m in msgs)
    check("context includes this session's instruction", "list files" in joined)
    check("context includes this session's output", "a.txt" in joined)
    check("current instruction is last message", msgs[-1]["content"] == "now sort them by date")
    check("other-session work NOT in main history flow",
          joined.count("make folders") == 1)  # only via the OTHER-terminals note
    check("cross-session note present", "OTHER terminals" in joined)

    # --- memory ----------------------------------------------------------
    added = doit.store_memories(["LLM project folder is ~/school/llms/ass3",
                                 "always sort newest first"])
    check("two memories stored", len(added) == 2)
    dup = doit.store_memories(["always sort newest first"])
    check("duplicate memory skipped", dup == [])
    block = doit.memory_block()
    check("memory block lists facts", "newest first" in block)
    mems = doit.load_memories()
    first_id = mems[0]["id"]
    removed = doit.forget_memories([first_id])
    check("memory forgotten by id", removed == [first_id])
    check("memory file shrank", len(doit.load_memories()) == 1)

    # --- shell awareness -------------------------------------------------
    histfile = Path(tmp) / ".bash_history"
    histfile.write_text(
        "cd ~/school/llms/ass3\nmkdir data\npython train.py\ndoit summarize what i did\n",
        encoding="utf-8")
    os.environ["HISTFILE"] = str(histfile)
    sblock = doit.shell_activity_block()
    check("shell history read", "python train.py" in sblock)
    check("user command tagged (user)", "(user) python train.py" in sblock)
    check("doit command tagged (doit)", "(doit) doit summarize" in sblock)

    # --- project profiles ------------------------------------------------
    proj = Path(tmp) / "proj"
    sub = proj / "src"
    sub.mkdir(parents=True)
    (proj / ".doit.md").write_text("This is a Python project. Prefer pytest.",
                                   encoding="utf-8")
    found_path, found_text = doit.find_project_profile(sub)
    check("profile found by walking up", found_path is not None)
    check("profile content read", "pytest" in found_text)
    none_path, _ = doit.find_project_profile(tmp)
    check("no profile outside project", none_path is None)

    # --- session identity ------------------------------------------------
    os.environ["DOIT_SESSION_ID"] = "explicit-sid"
    check("session id from env var", doit.session_id() == "explicit-sid")
    del os.environ["DOIT_SESSION_ID"]
    check("session id falls back to ppid", doit.session_id().startswith("ppid-"))

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
