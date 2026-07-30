---
last_update: 2026-07-30
active: true
owner: jhonny
scope: global-roadmap
tags: roadmap, yaarim, yoni, tutor, ollama, hebrew, security, architecture, rag
---

# Project Roadmap — YAARIM (יערים)

> **Last updated:** 2026-07-30
> **Version:** 0.2.0

---

## 🛑 Before you write a line

> **Read [`Documentation/AI-Agent-Instructions/project-directives.md`](../AI-Agent-Instructions/project-directives.md) first.**
> Four minutes. It is the difference between contributing and causing a rewrite.
>
> It holds the five things this project guarantees, why each exists, and how each is enforced —
> so you do not remove a mechanism that looks redundant and is not.
>
> **Getting it running (Windows, no Docker):**
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File scripts\install.ps1
> ```
>
> One line. Python, `.venv`, pinned deps, Ollama via `winget`, the model, the gate, then the app.
> Afterwards: `.\scripts\run.ps1`. macOS/Linux: `docker compose up app` — see the
> [README](../../README.md).
>
> **The short version, if you read nothing else:**
>
> 1. **Children use this.** When elegance and a child's safety conflict, safety wins.
> 2. **Run the gate.** `.\scripts\check.ps1` (Windows) · `./scripts/check.sh` (Unix) ·
>    `python scripts/check.py` (anywhere). green or red, no interpretation. If it is red,
>    the project is not in a working state — including after *your* change.
> 3. **The core imports no infrastructure.** `domain/`, `application/` and `agents/` know nothing of
>    `requests`, `sqlite3` or `streamlit`. The whole suite runs without `requests` installed, and the
>    gate verifies it.
> 4. **`container.py` is the only place that instantiates concrete classes.** If you reach for
>    `patch()` in a test, the dependency is not injected — that is the bug, not the test.
> 5. **Do not clear `"verified": false`** on the hotline numbers in `data/safety.json`. That is
>    Jhonny's call, and it is the last thing between a child and someone who answers.
>
> Some mechanisms here look like duplication and are not: the write policy runs **twice**, the
> distress check runs **before** routing, and `ExactGrader` has **no model attribute** on purpose.
> The directives explain each. Removing one because it "looks redundant" reopens a hole that was
> closed deliberately.

---

## Vision

A patient private tutor, in Hebrew, running **entirely on local hardware** — no cloud, no student
data leaving the machine. Two stacks in one package: agents facing the student (teach · test ·
reason) under a constitution enforced by code, and a self-building path where the system writes its
own code only through an explicit human gate.

Success is not model size. It is that **a student is remembered** — their open bricks, their last
session — and that **nothing about them ever leaves the box**.

## Phases

### Phase 1: Self-building CLI — ✅ Complete
- [x] `Planner` — request → structured `BuildPlan` (summary, target, exists), with a retry
- [x] `Coder` — approved plan → code, markdown fences stripped (incl. unterminated)
- [x] Two-stage human approval (plan, then write)
- [x] Backup before overwrite (`data/backups/<name>.<ts>.bak`)
- [x] Change log to SQLite
- [x] `ContextReader` — beyond 6 000 chars, send only the AST chunks matching the request

### Phase 2: Student-facing agents — ✅ Complete
- [x] `Router` — rules only, zero model call; `/build` and `/reason` are explicit modes
- [x] `Tutor` — teach directly for "explain X", socratic for "solve X"; history + summary
- [x] `Quiz` — three question types generated as validated JSON
- [x] `Quiz` — **iron rule**: closed answers graded in code, model only sees open + rubric
- [x] `Reasoning` — Qwen3 8B, `<think>` stripped before the student sees it
- [x] Constitution injected at the one choke point every student agent passes through
- [x] VRAM budget enforced before every call
- [x] Web UI in RTL Hebrew · student profiles · greeting built in code

### Phase 3: Identity & safety — ✅ Complete (2026-07-30)
> The rule was: nothing real enters this system before this closes.

- [x] **Write perimeter confined** — `ProjectWritePolicy`: normalise, then resolve symlinks against
      the nearest existing ancestor, then one containment check on the resolved path. Neither
      traversal nor symlink has its own bypass. Re-checked at commit, so approval cannot skip it
- [x] **Distress safety net** — `SafetyPolicy` before routing and before any model call; escalation
      to an adult; alert written to the student's folder. Proven with the model *available*
- [x] **Authentication wired** — pbkdf2 200k, login/registration separated, uniform error message
- [x] **Dependencies pinned** — `requests==2.34.2`, `streamlit==1.60.0`
- [x] **Deterministic gate** — `scripts/check.py`, one implementation, three entry points
- [x] **Containerised** — only the project is mounted, so the perimeter holds twice: refused by the
      policy, absent from the namespace. Ollama stays on the host with the GPU
- [ ] **Verify the three hotline numbers** in `data/safety.json` — each carries `"verified": false`
      on purpose. Mechanism proven; the numbers are yours to confirm before a real student sees them

### Phase 3.5: Architecture — ✅ Complete (2026-07-30)
> Requested: system design, separation of concerns, OOP, polymorphism, dependency injection.

- [x] **Hexagonal layout** under `src/` — `domain · application · agents · infrastructure · interfaces`
- [x] **7 ports** in `domain/ports.py`, 12 implementations (each port has a real second case)
- [x] **Composition root** — `container.py` is the only place that instantiates concrete classes
- [x] **Polymorphism that earns its keep** — graders (`ExactGrader` holds no model) · logs
      (file · sqlite · composite) · write policies (project · read-only) · agents (`AgentFactory`)
- [x] **Settings as an object**, not module globals — injectable, overridable per test
- [x] **Two memory stores reconciled** into an explicit `CompositeConversationLog`
- [x] **Brick loop closed** — a wrong answer opens a brick, which reaches the next lesson's prompt
- [x] **`Critic` removed** — unreachable stub, nowhere left to hide
- [x] **Layer guard** — the core cannot import infrastructure; verified by grep *and* by loading it
      with `requests` neutralised
- [x] **Tests moved to `tests/`** — no `patch` of modules anywhere; fakes are injected
- [x] **Single entry point** — `python -m yoni`; zero `.py` at the project root
- [x] Fixed while refactoring: SQLite connection leak (10 sites) · Streamlit entry-point imports ·
      stale `yoni/data/` directory

### Phase 3.6: Windows without Docker — ✅ Complete (2026-07-30)
> The next developer works on Windows and has no Docker. The gate had to stop being Bash-only,
> otherwise the directives would be telling them to run something they cannot run.

- [x] **Gate ported to Python** — `scripts/check.py` holds the logic; `check.sh` and `check.ps1` are
      three-line wrappers. One implementation, no drift between platforms
- [x] **`scripts/install.ps1`** — Python check (incl. the Microsoft Store stub trap), `.venv`, pinned
      deps, Ollama via `winget`, server start, model pull, gate, launch. Re-runnable
- [x] **`scripts/run.ps1`** — web by default, `-Cli` for the self-building CLI
- [x] **`README.md`** — Windows first, one command, above everything else
- [ ] **Run the PowerShell scripts on a real Windows machine.** They were written against the API
      surface but never executed there (the author's box is a Mac without `pwsh`). First contact will
      tell — fix and record, do not work around

### Phase 3.7: Types that are checked — ✅ Complete (2026-07-30)
> The import graph exposed two things: a capability lost in the refactor, and services that never
> named what they manipulate.

- [x] **`benchmark` restored** — the capability was lost in the refactor while `data/benchmarks.jsonl`
      kept its real measurements. An orphan data file is the signature of a silent deletion.
      Now `infrastructure/llm/benchmark.py` + `/bench` in the CLI. Measured live: 116.8 tok/s
- [x] **Public methods annotated — 56% → 80%**, starting with `domain/ports.py` where the absence
      cost most: a contract that does not say what passes through it forces the implementer to read
      an existing implementation
- [x] **`StudentRepository.open_brick()` added to the contract** — it was used but never declared.
      A second implementation would have silently broken the pedagogical loop
- [x] **`mypy==2.3.0`** in `requirements-dev.txt`, configured in `pyproject.toml`, wired into the
      gate. Core checked strictly, edges softly, third-party imports not followed
- [x] Two real errors found and fixed: an untyped `_history`, and a heterogeneous record typed as
      `str | None`
- [ ] Remaining 20% of annotations — mostly trivial constructors and container properties. Annotating
      them would be coverage for its own sake

### Phase 4: Memory that recalls — ⏳ Next
- [ ] RAG over past sessions — `LanguageModel.embed()` exists on the port; nothing consumes it
- [ ] Retrieve past struggles into the tutor prompt (today only the current brick is injected)
- [ ] Progress view for the student, a parent or a teacher: mastered vs open over time
- [ ] Persist the conversation as it happens (a tab close before "end session" still loses it)

### Phase 5: Multi-student operation — ⏳ Planned
- [ ] Roles — student vs teacher/parent, distinct views
- [ ] Concurrent sessions (Streamlit session state is single-user by construction)
- [ ] Retention policy — what is kept, how long, who can erase it

## Current Sprint

**Sprint 3 (proposed): recall + the last rough edges**

| Priority | Item | Status |
|----------|------|--------|
| **P0** | **Verify the hotline numbers** | ⏳ **yours** |
| P1 | RAG over past sessions (Phase 4 first brick) | ⏳ |
| P2 | demo/real namespace collision | ⏳ |
| P2 | Measure real test coverage | ⏳ |
| P3 | Root README · deduplicate the PDF | ⏳ |
| P3 | Regenerate `Documentation/CodeReference` (pre-refactor) | ⏳ |

## Improvements / Refactorization

| Item | Source | Priority | Notes |
|------|--------|----------|-------|
| Hotlines unverified | audit 2026-07-30 | P0 | The only thing between a child and someone who answers |
| demo-before-real lookup | audit 2026-07-30 | P2 | Namespace collision masks real students |
| Coverage never measured | audit 2026-07-30 | P2 | a test/source line ratio is not coverage |
| `CodeReference` stale | refactor 2026-07-30 | P3 | Generated against the old module tree |
| No root README | audit 2026-07-30 | P3 | Onboarding is oral knowledge |

## Dependencies

| Dependency | Status | Impact |
|------------|--------|--------|
| Ollama on `localhost:11434` | 🟡 External | Everything — no fallback by design |
| `gemma3:4b` pulled | 🟢 Present | Tutor · Quiz · Planner |
| `qwen2.5-coder:7b` | 🟡 External | `/build` only |
| `qwen3:8b` | 🟡 External | `/reason` only |
| `nomic-embed-text` | 🟡 External | Phase 4 only |
| GPU ≥ 8 GB VRAM | 🟢 Target hw | Below this, heavy models spill to RAM (a warning fires at startup) |
| `requests`, `streamlit` | 🟢 Pinned | — |

## Milestones

| Milestone | Target | Status |
|-----------|--------|--------|
| Working prototype (both stacks) | 2026-07 | 🟢 Reached |
| Safe for a first real student | — | 🟡 Code ready · blocked on the hotline verification |
| Architecture that survives growth | 2026-07-30 | 🟢 Reached |
| Remembers across sessions (Phase 4) | TBD | ⏳ |
| Multi-student (Phase 5) | TBD | ⏳ |

## Links

- [Global Status](status.md)
- [Status Diagrams](status-diagrams.md)
