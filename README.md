# 🧱 יערים (YAARIM) — יוני

A Hebrew private tutor for a student aged 10–16, running **entirely on local hardware**.
No cloud. No student data leaving the machine.

---

## 🪟 Start here — Windows, no Docker

Open **PowerShell** in the project folder and run one line:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

That does everything: checks Python, creates `.venv`, installs the pinned dependencies, installs
Ollama through `winget` if missing, starts the Ollama server, downloads the model (~3.3 GB, once),
runs the health check, and opens the app on **http://localhost:8501**.

Afterwards, to start it again:

```powershell
.\scripts\run.ps1            # the web app
.\scripts\run.ps1 -Cli       # the self-building CLI (/build)
```

**If PowerShell refuses to run scripts** — that is a Windows security setting, not a bug:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**Useful flags:** `-SkipModel` (skip the 3.3 GB download) · `-NoLaunch` (install only).

### Extra models, only if you need them

The installer pulls `gemma3:4b`, which covers the tutor and the quiz — everything a student touches.
Two more are optional and heavy:

```powershell
ollama pull qwen2.5-coder:7b   # only for /build (writing code)
ollama pull qwen3:8b           # only for /reason (deep reasoning)
```

They never load at the same time: the VRAM budget is enforced in code before every call.

---

## 🍎 macOS / Linux

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ollama serve &            # in another terminal
ollama pull gemma3:4b
PYTHONPATH=src streamlit run src/yoni/interfaces/web/app.py
```

Or, with Docker:

```bash
DOCKER_UID=$(id -u) DOCKER_GID=$(id -g) docker compose up app
```

---

## 🛑 Before you change anything

**Read [`Documentation/AI-Agent-Instructions/project-directives.md`](Documentation/AI-Agent-Instructions/project-directives.md).**
Four minutes. It lists what this project guarantees, why, and how each guarantee is enforced — so you
do not remove a mechanism that looks redundant and is not.

The three-line version:

1. **Children use this.** When elegance and a child's safety conflict, safety wins.
2. **Run the gate before calling anything done** — it is green or red, no interpretation:
   ```powershell
   .\scripts\check.ps1          # Windows
   ./scripts/check.sh           # macOS / Linux
   python scripts/check.py      # anywhere
   ```
3. **Do not clear `"verified": false`** on the hotline numbers in `data/safety.json`. That is
   Jhonny's call.

---

## What is in the box

```
src/yoni/
├── domain/          entities + 7 ports    ← imports nothing external
├── application/     conversation · assessment · authoring
├── agents/          tutor · quiz · reasoning · builder + factory
├── infrastructure/  Ollama · SQLite · files · crypto · guards
├── interfaces/      cli/ · web/
└── container.py     the only place that instantiates concrete classes
tests/               117 cases — they run without `requests` installed
data/                runtime: safety config, database, backups
students/            demo/ (in git) · real/ (never in git)
```

| Doc | What for |
|-----|----------|
| [project-directives.md](Documentation/AI-Agent-Instructions/project-directives.md) | **the standard — read first** |
| [status.md](Documentation/Roadmap_Status/status.md) | current state, metrics, open items |
| [roadmap.md](Documentation/Roadmap_Status/roadmap.md) | what is planned and why |
| [status-diagrams.md](Documentation/Roadmap_Status/status-diagrams.md) | how the parts fit |

## What it promises a child

Five rules, in `src/yoni/agents/base.py`. Two of them are enforced by code rather than by asking the
model nicely:

- **"I do not modify myself"** — every write path goes through a policy that refuses anything outside
  the project, checked again at write time so approval cannot bypass it.
- **"Distress goes to a responsible adult"** — checked *before* routing and *before* any model call.
  On a hit, no agent is invoked at all.

A quiz question with a single correct answer is graded **in code**, never by the model.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) running locally
- A GPU with ≥ 8 GB VRAM is comfortable; less works but heavy models spill to RAM (you get a warning
  at startup)
- No internet needed at runtime — including the Hebrew fonts, which are served locally
