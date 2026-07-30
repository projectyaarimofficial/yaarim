---
last_update: 2026-07-30
active: true
owner: jhonny
scope: global-status
tags: status, yaarim, yoni, tutor, ollama, hebrew, local-first, hexagonal
---

# Project Status — YAARIM (יערים) / יוני

> **Last updated:** 2026-07-30
> **Phase:** Phase 3 closed (safety) · Phase 4 next (memory that recalls)

## Overview

| Metric | Value |
|--------|-------|
| Overall Progress | ~85% of the prototype's own scope |
| Architecture | hexagonal — `domain · application · agents · infrastructure · interfaces` |
| Source | 39 modules · 2 606 lines under `src/yoni/` |
| Tests | **122 cases, all green** · under `tests/` |
| Types | `mypy` clean on 40 modules · 80% of public methods annotated |
| Ports declared | 7, with 12 implementations (incl. test doubles) |
| Deterministic gate | `python scripts/check.py` — **green** (Windows · macOS · Linux) |
| Runtime | 100% local — Ollama, zero cloud egress |
| Target hardware | RTX 5060 (8 GB VRAM) · 32 GB RAM · i5-14400F |
| Entry points | `python -m yoni` (CLI) · `docker compose up app` (web) |
| Open P0 issues | 0 in code — 1 pending **your** verification |

## Current Phase

**Phase 3 (identity & safety) closed 2026-07-30. Phase 4 (memory) is next.**

Three holes were shut in code and each closure is proven by a test:

| Constitution rule | Was | Is now |
|---|---|---|
| 1 · I do not modify myself | a human reading one `yes/no` line | `ProjectWritePolicy` — a path escaping the project root is refused before the confirmation is even offered, and re-checked at write time so approval cannot bypass it |
| 5 · distress → responsible adult | one sentence in a prompt, hoping a 4B model notices | `SafetyPolicy.inspect()` runs **before routing and before any model call**. On a hit no agent is asked; the student is pointed at an adult and an alert lands in their folder |
| — · student identity | ID + name, no password | `SqlitePasswordStore` wired into the entry screen (pbkdf2, 200k iterations); login and registration are separate acts; the error never reveals whether an ID exists |

Then the code itself was restructured (2026-07-30) so those guarantees are **structural**, not
conventional — see Architecture below.

## Architecture

Five layers, one direction of dependency: interfaces → application → domain, with infrastructure
plugged in from outside through ports.

| Layer | Holds | Knows about |
|-------|-------|-------------|
| `domain/` | entities (frozen dataclasses) + the 7 ports | nothing — not even `requests` |
| `application/` | conversation · assessment · authoring | domain only |
| `agents/` | tutor · quiz · reasoning · builder + factory | domain only |
| `infrastructure/` | Ollama · SQLite · files · pbkdf2 · path guard · keyword safety | domain (implements its ports) |
| `interfaces/` | CLI · Streamlit web | container |
| `container.py` | the single composition root | everything (that's its job) |

**Two structural guarantees**, each verified by the gate:

- **The core cannot import infrastructure.** Checked twice — by a grep on the layer folders, and by
  loading the core with `requests` neutralised. If the separation ever erodes, the gate goes red.
- **Polymorphism where it earns its keep.** `ExactGrader` has no model attribute at all, so a
  closed-answer question *cannot* reach the LLM even by mistake. `CompositeConversationLog` makes the
  two-store decision explicit in one place instead of asking the UI to remember both.

## Feature Status

| Feature | Status | Notes |
|---------|--------|-------|
| Constitution enforcement | 🟢 Done | `StudentAgent` injects it at the single choke point; `DevAgent` deliberately does not. Both directions tested |
| Quiz — deterministic grading | 🟢 Done | Type routes to a grader; `ExactGrader` holds no model; unknown type raises |
| Write perimeter | 🟢 Done | Injected policy, checked at resolve **and** at commit |
| Distress safety net | 🟢 Done | Runs before routing; proven with the model *available* |
| Authentication | 🟢 Done | Wired; uniform error message |
| VRAM budget | 🟢 Done | Enforced before every call; budget logic is pure and testable |
| Student profiles + logs | 🟢 Done | `FileStudentRepository` + composite log (files + SQLite) |
| Brick loop | 🟢 Done | A wrong answer **opens a brick**; the brick reaches the next lesson's prompt |
| Web UI (RTL Hebrew) | 🟢 Done | Brick-wall design system, fonts served locally |
| Self-building CLI | 🟢 Done | `python -m yoni` — plan → approve → code → approve → backup → write → log |
| Containerised | 🟢 Done | Only the project is mounted; Ollama stays on the host with the GPU |
| RAG / embeddings | ⏳ Planned | `embed()` exists on the port; nothing consumes it |
| demo/real namespace | 🔴 Open | Lookup searches `demo/` before `real/` — a real student sharing an ID is masked |

## Recently Completed (2026-07-30)

| Item | Evidence |
|------|----------|
| Write perimeter confined | 13 tests incl. symlink escape, shared-prefix sibling, `~/.zshrc` |
| Distress safety net | Proven with `gemma3:4b` loaded and reachable — no agent called |
| Authentication wired | Password never stored in clear (asserted against the DB) |
| Hexagonal refactor | Core loads without `requests` — enforced in the gate |
| `benchmark` restored | Lost in the refactor; its data file survived and gave it away. Measured live: 116.8 tok/s |
| Types checked, not just written | `mypy` wired into the gate; two real errors found and fixed |
| `open_brick()` added to its port | It was used but never declared on the contract |
| Brick loop closed | Wrong answer → open brick → next prompt (asserted end to end) |
| Two stores reconciled | `CompositeConversationLog`, decision in one place |
| `Critic` removed | Was unreachable; an architecture with declared consumers left it nowhere to hide |
| SQLite leak fixed | `with connect()` closes the transaction, not the connection — 10 sites |
| Streamlit entry-point import | Script execution has no package parent; guarded now |

## Open Items

| Item | Priority | Notes |
|------|----------|-------|
| Verify the three hotline numbers | **P0 — yours** | Each carries `"verified": false` in `data/safety.json`. The mechanism is tested; the numbers are not mine to certify. the gate warns until you clear them |
| demo/real namespace collision | P2 | `FileStudentRepository.directory()` searches `demo/` first |
| Test coverage measurement | P2 | The ratio of test to source lines is not coverage; branch coverage never measured |
| Root README | P3 | Install, models to pull, how to run |
| `דף-היכרות-תלמיד.pdf` duplicated | P3 | Present at the root and in `students/` |

## Key Metrics

- **Tests:** 122 cases, green, zero `ResourceWarning` (verified with `-W error::ResourceWarning`).
  They run **without `requests` installed** — the separation is executable, not aspirational.
- **Types:** `mypy` clean on 40 modules. 80% of public methods annotated; the remaining 20% are
  trivial constructors and container properties, left deliberately.
- **Gate:** `python scripts/check.py` — deps · guards exist · guards wired · architecture · types ·
  tests · debt · privacy. Logic in Python so it runs on Windows without Bash; `check.sh` and
  `check.ps1` are thin wrappers. Green, 1 warning.
- **Dependencies:** pinned — `requests==2.34.2`, `streamlit==1.60.0`.
- **Cloud egress:** none. Every model call goes to `OLLAMA_HOST` (default localhost). Web fonts are
  served from `src/yoni/interfaces/web/fonts/` — no browser call to Google.
- **Legacy:** the pre-refactor package, its tests and a stale data dir are kept at
  `/tmp/yaarim-legacy-20260730-221446/`. Nothing was deleted.

## Links

- [Global Roadmap](roadmap.md)
- [Status Diagrams](status-diagrams.md)
- [Code Reference](../CodeReference/portal.html) — ⚠️ generated **before** the refactor; regenerate
  it (`dockit --repo . --out Documentation/CodeReference`) before trusting its module map
