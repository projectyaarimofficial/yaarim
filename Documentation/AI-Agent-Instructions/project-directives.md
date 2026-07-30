---
last_update: 2026-07-30
active: true
owner: jhonny
scope: project-directives
tags: standards, contributing, architecture, invariants, yaarim
---

# YAARIM — Project Directives

**Read this before writing a line. It takes four minutes and it will save you a rewrite.**

This file is for whoever comes next — human or AI. It is not a style guide. It is the list of things
this project guarantees, why each one exists, and how not to break them by accident.

---

## 0. Getting it running

**Windows, no Docker** — one line in PowerShell, from the project folder:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

It checks Python, creates `.venv`, installs the pinned dependencies, installs Ollama via `winget` if
missing, starts the server, pulls the model, runs the gate, and opens the app. Re-running it is safe.
Then `.\scripts\run.ps1` (add `-Cli` for the self-building CLI).

**macOS / Linux** — `docker compose up app`, or the venv path in the [README](../../README.md).

**The gate runs everywhere.** Its logic lives in `scripts/check.py` (Python, cross-platform);
`check.sh` and `check.ps1` are three-line wrappers. That is deliberate: a second copy in Bash would
drift from the first within weeks, and the next developer may have no Bash at all.

```powershell
.\scripts\check.ps1          # Windows
./scripts/check.sh           # macOS / Linux
python scripts/check.py      # anywhere
```

> **Honest limit:** the PowerShell scripts were written against the Windows API surface but have
> **not been executed on a Windows machine** — the author's box is a Mac without `pwsh`. Their logic
> is straightforward and the known traps are handled (Store stub `python`, `PATH` refresh after
> `winget`, execution policy). If one breaks on first contact, fix it and say so here rather than
> working around it silently.

---

## 1. What this project is

A Hebrew private tutor (**יוני**) for a student aged roughly 10–16, running **entirely on local
hardware**. No cloud. No student data leaving the machine. Two stacks in one package:

- **student-facing** — teach · test · reason, under a constitution enforced by code;
- **self-building** — the system writes its own code, but only through an explicit human gate.

**Children use this.** That single fact outranks every other consideration in this file. When a
trade-off appears between elegance and a child's safety, safety wins without discussion.

---

## 2. The five non-negotiables

Break any of these and the project stops being what it is. Each is enforced — the enforcement is
named so you can check that it still exists.

### 2.1 A closed question never reaches the model

Multiple-choice and exact-answer questions are graded **in code**, by string comparison. Only open
questions go to the LLM, and only against an explicit rubric.

*Enforcement:* `ExactGrader` (in `agents/quiz.py`) has **no model attribute at all**. It cannot call
an LLM even if you asked it to. An unknown question type **raises** rather than falling through.
Tests assert both.

*If you touch this:* never give `ExactGrader` a model reference "for convenience". The absence is
the mechanism.

### 2.2 Distress is checked before anything else

`SafetyPolicy.inspect()` runs **before routing and before any model call**. On a hit, no agent is
invoked at all; the student is directed to a responsible adult and an alert is written to their
folder.

*Enforcement:* the first statement of `ConversationService.handle()`. A test proves the model is not
called **while it is available** — availability is not the reason it stays silent.

*If you touch this:* the check stays first. Not "early". First. And the escalation message never
diagnoses, never promises, never counsels — it points at a human.

*Honest limit:* detection is keyword-based and therefore partial. A child who phrases it their own
way will not be caught. It reduces risk; it does not remove it. Never describe it as if it did.

### 2.3 Nothing is written outside the project

Every write target passes `WritePolicy.resolve()` — normalise, resolve symlinks against the nearest
existing ancestor, then one containment check on the resolved path.

*Enforcement:* checked at resolve **and again at commit**, so human approval sits between two checks
and cannot replace either. In the container, only the project is mounted, so a refused path does not
exist in the namespace to begin with.

*If you touch this:* the second check at commit is not redundant. Remove it and approval becomes the
only barrier again — which is exactly the hole this closed.

### 2.4 Student data never leaves the machine

Raw text stays in the student's folder. SQLite gets facts and counts, not sensitive content
(see `SqliteConversationLog.log_alert` — it deliberately stores the category, not the child's words).
`students/real/*` is gitignored. Web fonts are served locally so a child's browser never calls Google.

*Enforcement:* the gate fails if anything under `students/real/` other than the README is tracked,
or if a `.db` file is committed.

### 2.5 The core does not know about infrastructure

`domain/`, `application/` and `agents/` import no `requests`, no `sqlite3`, no `streamlit`, and
nothing from `infrastructure/`. They talk to ports.

*Enforcement:* two checks in the gate — a grep on the layer folders, and loading the core with
`requests` neutralised. If it ever breaks, the gate goes red.

*Why it matters practically:* the whole test suite runs **without `requests` installed**. That is not
a party trick — it is what makes the tests fast, hermetic, and free of module patching.

---

## 3. The gate

```powershell
.\scripts\check.ps1          # Windows
./scripts/check.sh           # macOS / Linux
python scripts/check.py      # anywhere — 25 checks
```

Green or red, no interpretation. It verifies: dependencies pinned · guards exist · **guards are
wired** · architecture · **types** · tests · known debt · privacy.

**Types are checked, not just written.** `mypy` runs against `src/` with the core
(`domain`/`application`/`agents`) held to a stricter setting than the edges. Annotations without a
checker are documentation that can lie; the checker is what turns them into a mechanism. It is a dev
dependency — if absent, that check warns instead of blocking, so running the app never requires it.

```bash
pip install -r requirements-dev.txt    # mypy
```

The "guards are wired" group exists because of a real incident: `auth.py` was correct, tested, and
**imported nowhere** for weeks. A file that exists but is not connected protects nothing. Whenever
you add a guard, add the check that proves it is connected.

If the gate is red, the project is not in a working state. Do not "fix it later".

---

## 4. Architecture — where things go

```
src/yoni/
├── domain/          entities + ports        ← knows nothing, imports nothing external
├── application/     use cases               ← orchestration; knows domain only
├── agents/          LLM judgment            ← knows domain only
├── infrastructure/  Ollama · SQLite · files · crypto · guards   ← implements ports
├── interfaces/      cli/ · web/             ← in and out; knows the container
├── config/          Settings                ← an object, never module globals
└── container.py     composition root        ← THE ONLY place that instantiates concrete classes
```

**Dependencies point inward.** Interfaces → application → domain. Infrastructure plugs in from
outside by implementing ports. Nothing in the core reaches outward.

### Decide where your code goes

| Your code… | Goes in |
|---|---|
| is a fact about the subject (a student, a question, a brick) | `domain/models.py` |
| is a contract someone else will implement | `domain/ports.py` |
| orchestrates a use case, calls no library directly | `application/` |
| builds a prompt and interprets a model's answer | `agents/` |
| touches the network, disk, database, or crypto | `infrastructure/` |
| renders or reads input | `interfaces/` |
| decides which concrete class to use | `container.py` — nowhere else |

---

## 5. How to add things

### Add an agent

1. Subclass `StudentAgent` (talks to a child → gets the constitution automatically) or `DevAgent`
   (tooling → deliberately does not).
2. Implement `build_prompt()`. Call `self._ask()` — never a client directly.
3. Register it in `AgentFactory._registry`: one line, `role → (class, model selector)`.
4. Add the model name to `Settings`.

You never write the model call. That is the point: a new student agent cannot forget the
constitution, because it does not write the code that would omit it.

### Add a capability that touches the outside world

1. Declare the **port** in `domain/ports.py` — but only if it will have a real second implementation
   or a real second consumer. Do not create a port "for flexibility"; that is speculative
   abstraction and it costs more than it gives.
2. Implement it in `infrastructure/`.
3. Wire it in `container.py` as a lazy property.
4. Inject a fake in tests. Do **not** patch modules — if you find yourself reaching for `patch`, the
   dependency is not injected and that is the actual bug.

### Add a check to the gate

Whenever something breaks in a way that could break again, add a check. Four of the current ones
exist for exactly that reason. A lesson written in a commit message will not be there next time; a
check will be.

---

## 6. Conventions

- **Language.** Hebrew for docstrings and comments (this project's readers think in Hebrew). English
  for identifiers, file names, and this documentation. Never mix inside one artefact.
- **Comments explain *why*, never *what*.** If a line needs a comment to say what it does, rename
  something instead. The comments worth writing are the ones that stop a future reader from
  "simplifying" a deliberate decision.
- **Immutability.** Domain objects are `frozen dataclass`. Return a new object; never mutate a shared
  one.
- **Dependencies are pinned with `==`.** Always. No exceptions, no `>=`, no `^`.
- **Tests live in `tests/`.** A `test_*.py` at the root is not collected by the runner — it would
  look like it passes while being dead. `check.sh` refuses it.
- **No `.py` at the project root.** The CLI entry point is `python -m yoni`.
- **No stub that pretends to exist.** A `NotImplementedError` exported in a public API is worse than
  a missing feature: it looks like a capability. If it is not implemented, delete it.

---

## 7. Lessons paid for in this codebase

Real incidents. Each cost time; each now has a guard.

| What happened | What it teaches |
|---|---|
| `auth.py` was correct, tested, and imported nowhere | Existing ≠ wired. Check the connection, not the file |
| A `yes/no` prompt was the only barrier on file writes | A human's attention is not a security mechanism |
| Rule 5 of the constitution lived only inside a prompt | An instruction to a 4B model is a hope, not a guarantee |
| `with sqlite3.connect(...)` — 10 sites leaking | That context manager closes the *transaction*, not the connection |
| `/_stcore/health` returned 200 while the page crashed | Health endpoints prove the server, not the app. Render the page |
| Streamlit entry point used relative imports | `streamlit run` executes a **script**; there is no package parent |
| Two memory stores, written side by side by the UI | Duplication that no single place owns will drift |
| Test files left at the root after a move | A test that is not collected looks green forever |
| A capability vanished in a refactor, its data file stayed | An orphan data file means something was deleted unnoticed |
| `StudentRepository` used a method its contract never declared | A port that omits a method lets a second implementation break the feature silently |

---

## 8. Definition of done

A change is done when **all** of these hold:

- [ ] `./scripts/check.sh` is green
- [ ] New behaviour has a test that fails without your change
- [ ] No new import from `infrastructure/` inside `domain/`, `application/` or `agents/`
- [ ] No `patch()` of a module in your tests — you injected instead
- [ ] Dependencies still pinned
- [ ] `mypy` is clean — a new public method carries its types
- [ ] Docstrings in Hebrew, identifiers in English
- [ ] `Documentation/Roadmap_Status/` reflects what you changed (status · roadmap · diagrams)
- [ ] If you added a guard, you also added the check that proves it is wired

---

## 9. Where to look

| You want | Read |
|---|---|
| Current state, metrics, open items | `Documentation/Roadmap_Status/status.md` |
| What is planned and why | `Documentation/Roadmap_Status/roadmap.md` |
| How the parts fit (diagrams) | `Documentation/Roadmap_Status/status-diagrams.md` |
| The contracts | `src/yoni/domain/ports.py` |
| How things are assembled | `src/yoni/container.py` |
| What the system promises a child | `src/yoni/agents/base.py` → `CONSTITUTION` |

---

## 10. One thing that is not yours to decide

`data/safety.json` contains the emergency hotline numbers shown to a child in distress. Every entry
carries `"verified": false` until **Jhonny** confirms them against the official source.

Do not clear that flag. Do not "clean up" the warning `check.sh` prints about it. Those three numbers
are the last thing between a child and someone who picks up the phone, and they are not verified by
whoever wrote the code around them.
