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

- **Read-only** commands run immediately.
- **State-changing** commands are shown and require confirmation.
- **Dangerous** commands are refused.

## Status

Basics implemented. Planned next: multi-turn history, user memory,
shell-history awareness, cross-session support, local & tool-calling models.
