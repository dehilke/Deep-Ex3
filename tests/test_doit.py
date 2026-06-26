"""Offline tests for doit's context layer (no LLM calls).

Loads the extensionless `doit` script as a module, points HOME at a temp dir,
and exercises history / sessions / memory / shell-awareness / project profiles /
context assembly directly.

Run:  python tests/test_doit.py
"""

import builtins
import contextlib
import importlib.util
import io
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

    # --- forgiving JSON extraction (extract_json_object) -----------------
    check("extract clean json", doit.extract_json_object('{"kind": "answer"}')
          == '{"kind": "answer"}')
    fenced = "Sure!\n```json\n{\"kind\": \"command\"}\n```"
    check("extract json from prose + fence",
          doit.extract_json_object(fenced) == '{"kind": "command"}')
    braces_in_str = '{"command": "echo {hi} ${x}", "risk": "safe"}'
    check("balanced parse ignores braces inside strings",
          doit.extract_json_object("noise " + braces_in_str + " trailing")
          == braces_in_str)
    check("no json -> empty string", doit.extract_json_object("just prose") == "")

    # --- confirm gate + execution (stub the model, drive handle()) -------
    # These exercise handle() end-to-end with a canned model reply and a
    # scripted stdin, so the safety gate and execution path run for real
    # without any LLM. Output is captured to keep the test log clean.
    real_input = builtins.input
    real_ask = doit.ask_model
    work = Path(tmp) / "work"
    work.mkdir(exist_ok=True)
    os.chdir(work)

    def drive(reply, inputs):
        """Run handle() with ask_model stubbed to `reply` (dict or list of
        dicts) and input() scripted by `inputs` (EOFError sentinel allowed)."""
        replies = iter(reply if isinstance(reply, list) else [reply])
        doit.ask_model = lambda settings, messages: next(replies)
        seq = iter(inputs)

        def fake_input(prompt=""):
            try:
                val = next(seq)
            except StopIteration:
                raise EOFError
            if val is EOFError:
                raise EOFError
            return val

        builtins.input = fake_input
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            doit.handle({}, "", "gate-test")
        return buf.getvalue()

    # safe command runs with no prompt
    drive({"kind": "command", "command": "echo hi", "risk": "safe",
           "explanation": "print hi"}, [])
    last = doit.load_history()[-1]
    check("confirm gate: safe runs (no prompt)",
          last["kind"] == "command" and last.get("returncode") == 0)

    # confirm command, user declines -> not run, recorded as aborted
    target = work / "made_by_yes.txt"
    drive({"kind": "command", "command": f"touch {target.name}",
           "risk": "confirm", "explanation": "create a file"}, ["n"])
    check("confirm gate: confirm + n aborts (file NOT created)",
          not target.exists() and doit.load_history()[-1].get("aborted") is True)

    # confirm command, user accepts -> runs
    drive({"kind": "command", "command": f"touch {target.name}",
           "risk": "confirm", "explanation": "create a file"}, ["y"])
    check("confirm gate: confirm + y runs (file created)", target.exists())

    # EOF at the confirm prompt -> fail-safe abort
    target2 = work / "made_by_eof.txt"
    drive({"kind": "command", "command": f"touch {target2.name}",
           "risk": "confirm", "explanation": "create a file"}, [EOFError])
    check("confirm gate: EOF aborts (fail-safe)", not target2.exists())

    # failing command stores its non-zero return code and stderr
    drive({"kind": "command", "command": "ls /nonexistent_dir_xyz",
           "risk": "safe", "explanation": "list a missing dir"}, [])
    failed = doit.load_history()[-1]
    check("failing command records non-zero exit + stderr",
          failed.get("returncode") not in (0, None) and bool(failed.get("stderr")))

    # --- clarification loop ----------------------------------------------
    clarify_reply = {"kind": "clarify", "question": "By which date?",
                     "options": ["creation date", "access date"]}
    cmd_reply = {"kind": "command", "command": "ls -lt", "risk": "safe",
                 "explanation": "sort by date"}
    out = drive([clarify_reply, cmd_reply], ["1"])  # answer with option number
    check("clarify question shown", "By which date?" in out)
    check("clarify options shown", "creation date" in out)
    resolved = doit.load_history()[-1]
    check("clarify resolved into final command",
          resolved["kind"] == "command" and "clarified" in resolved["instruction"])

    # no answer (EOF) at the clarification prompt -> abort, nothing recorded
    before = len(doit.load_history())
    drive(clarify_reply, [EOFError])
    check("clarify aborts gracefully on no answer",
          len(doit.load_history()) == before)

    builtins.input = real_input
    doit.ask_model = real_ask

    # --- command timeout (exit 124) --------------------------------------
    saved_timeout = doit.COMMAND_TIMEOUT
    doit.COMMAND_TIMEOUT = 1
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        timed = doit.run_command("sleep 5")
    doit.COMMAND_TIMEOUT = saved_timeout
    check("hung command is killed and recorded as exit 124",
          timed.returncode == 124 and "timed out" in buf.getvalue())

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
