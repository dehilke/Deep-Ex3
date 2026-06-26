# Deep-Ex3 — `doit`

An interactive LLM agent that turns natural-language requests into shell
commands, classifies their risk, asks for confirmation when needed, runs them,
and shows the result. (Assignment 3: Agentic Shell.)

## Requirements

- Linux / WSL with `bash`
- Python 3
- `pip install -r requirements.txt` (LiteLLM)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp doit.cfg.example ~/doit.cfg     # then edit the model / set your API key
chmod +x doit
```

Set your API key in the environment, e.g.:

```bash
export OPENAI_API_KEY=sk-...
```

## Usage

```bash
./doit list the python files in this folder
./doit how do I see disk usage
./doit delete all the .tmp files
```

- **Read-only** (`safe`) commands run immediately.
- **State-changing** (`confirm`) commands are shown with an explanation and run
  only after you confirm.
- Requests that aren't shell commands are answered directly; ones that can't be
  done at all are refused.

## Status

All assignment sections implemented: the command path (translate → classify →
confirm → run), clarifying questions, model flexibility (cloud / local /
native tool-calling via LiteLLM), and the full context layer — multi-turn
history, persistent memory, shell-history awareness, multi-session separation,
and the project-profile extension. See `docs/report.md` for the full write-up.
