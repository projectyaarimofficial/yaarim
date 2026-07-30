---
last_update: 2026-07-30
active: true
owner: jhonny
scope: global-diagrams
tags: diagrams, architecture, hexagonal, yaarim, yoni, mermaid
---

# Status Diagrams — YAARIM

> **Last updated:** 2026-07-30 (rewritten after the hexagonal refactor)

Diagrams derived from the code as it stands. Where a diagram claims a guarantee, the guarantee is
enforced by `scripts/check.sh` — noted on the diagram itself.

## Layers — one direction of dependency

```mermaid
graph TB
    subgraph interfaces["interfaces/ — in and out"]
        CLI["cli/app.py<br/>python -m yoni"]
        WEB["web/app.py<br/>streamlit"]
    end

    subgraph container["container.py"]
        C["Container<br/>the only place that<br/>instantiates concrete classes"]
    end

    subgraph application["application/ — orchestration"]
        CONV["ConversationService"]
        ASSESS["AssessmentService"]
        AUTH["AuthoringService"]
    end

    subgraph agents["agents/ — judgment"]
        FACT["AgentFactory"]
        TUT["Tutor"]
        QZ["Quiz"]
        RSN["Reasoning"]
        BLD["Planner · Coder"]
    end

    subgraph domain["domain/ — the core"]
        MOD["models<br/>frozen dataclasses"]
        PORTS["ports<br/>7 abstractions"]
    end

    subgraph infra["infrastructure/ — the hands"]
        OLL["OllamaLanguageModel"]
        FILES["FileStudentRepository<br/>FileConversationLog"]
        SQL["SqliteConversationLog<br/>SqlitePasswordStore"]
        PATH["ProjectWritePolicy"]
        SAFE["KeywordSafetyPolicy"]
    end

    CLI --> C
    WEB --> C
    C --> CONV & ASSESS & AUTH
    C -.->|injects| infra
    CONV & ASSESS & AUTH --> FACT
    FACT --> TUT & QZ & RSN & BLD
    CONV & ASSESS & AUTH --> PORTS
    TUT & QZ & RSN & BLD --> PORTS
    infra -.->|implements| PORTS
    PORTS --- MOD

    style domain fill:#2d5016,color:#fff
    style PORTS fill:#2d5016,color:#fff
```

Green = the layer that knows nothing about the outside. **`check.sh` verifies this twice**: by grep
on the layer folders, and by loading the core with `requests` neutralised. The arrows into `domain`
only ever point inward.

## The ports and their implementations

```mermaid
graph LR
    subgraph P["domain/ports.py"]
        LM["LanguageModel"]
        SR["StudentRepository"]
        CL["ConversationLog"]
        SP["SafetyPolicy"]
        WP["WritePolicy"]
        PS["PasswordStore"]
        CK["Clock"]
    end

    LM --> OLL["OllamaLanguageModel"]
    LM --> FAKE["FakeLanguageModel<br/>(records if it was called)"]
    SR --> FSR["FileStudentRepository"]
    CL --> FCL["FileConversationLog<br/>human-readable"]
    CL --> SCL["SqliteConversationLog<br/>queryable"]
    CL --> CCL["CompositeConversationLog<br/>writes to both, in one place"]
    SP --> KSP["KeywordSafetyPolicy"]
    WP --> PWP["ProjectWritePolicy"]
    WP --> ROP["ReadOnlyWritePolicy"]
    PS --> SPS["SqlitePasswordStore"]
    CK --> SC["SystemClock"]
    CK --> FC["FakeClock"]

    style FAKE fill:#2d5016,color:#fff
    style CCL fill:#2d5016,color:#fff
```

Every port has a real second case — none is speculative. `FakeLanguageModel` is what makes "the model
was not called" a **measured** claim. `CompositeConversationLog` is where the old two-store debt
became one explicit decision.

## Quiz grading — the iron rule, now structural

```mermaid
graph TD
    ANS["Student answer"] --> TYPE{"question.type"}
    TYPE -->|multiple_choice| EG["ExactGrader"]
    TYPE -->|exact| EG
    TYPE -->|open| RG["RubricGrader"]
    TYPE -->|unknown| RAISE["raise ValueError"]
    EG --> STR["string comparison<br/>no model attribute exists"]
    RG --> MOD["model + explicit rubric"]
    STR --> OUT["GradeResult<br/>graded_by='code'"]
    MOD --> OUT2["GradeResult<br/>graded_by='model'"]

    style EG fill:#2d5016,color:#fff
    style STR fill:#2d5016,color:#fff
    style RAISE fill:#4a3800,color:#fff
```

Before the refactor this was a convention held by discipline. Now `ExactGrader` has **no model
attribute at all** — a closed question cannot reach the LLM even by mistake. A test asserts the
absence directly.

## Distress — the door that precedes everything

```mermaid
sequenceDiagram
    participant S as Student
    participant CS as ConversationService
    participant SP as SafetyPolicy
    participant R as Router
    participant A as Agents
    participant L as ConversationLog

    S->>CS: message
    CS->>SP: inspect(text)
    alt distress found
        SP-->>CS: SafetyFinding
        CS->>L: log_alert (text→files, fact→sql)
        CS-->>S: escalation to an adult
        Note over R,A: never reached — proven with the model available
    else nothing found
        SP-->>CS: None
        CS->>R: route(text)
        R->>A: tutor · quiz · reasoning
        A-->>S: reply
    end
```

## Dependency injection — who builds what

```mermaid
graph TD
    ENV["Settings.from_env()"] --> CONT["Container"]
    CONT -->|lazy, once| LLM["LanguageModel"]
    CONT -->|lazy, once| REPO["StudentRepository"]
    CONT -->|lazy, once| LOG["ConversationLog"]
    CONT -->|lazy, once| POL["WritePolicy"]
    CONT -->|lazy, once| SAFE["SafetyPolicy"]
    CONT --> SERV["Services + AgentFactory"]
    LLM & REPO & LOG & POL & SAFE --> SERV

    TEST["Test"] -.->|Container(language_model=Fake…)| CONT

    style TEST fill:#2d5016,color:#fff
```

No class builds its own dependencies. That is why the whole suite runs with **zero `patch` of
modules** — a test injects a different object and nothing else changes.

## The `/build` write gate

```mermaid
graph TD
    REQ["Request"] --> PLAN["Planner → BuildPlan"]
    PLAN --> A1{"Human approves plan?"}
    A1 -->|no| STOP1["cancelled"]
    A1 -->|yes| RES["WritePolicy.resolve(target)"]
    RES -->|denied| REFUSE["refused — no confirmation offered"]
    RES -->|allowed| GEN["Coder → code"]
    GEN --> A2{"Human approves write?"}
    A2 -->|no| STOP2["cancelled"]
    A2 -->|yes| RES2["WritePolicy.resolve AGAIN"]
    RES2 --> BAK["backup existing"]
    BAK --> WRITE["write inside the project"]
    WRITE --> LOG["log_change → SQLite"]

    style RES fill:#2d5016,color:#fff
    style RES2 fill:#2d5016,color:#fff
```

The policy runs **twice** — at resolve and at commit. Human approval sits between them and cannot
replace either. In the container, only the project is mounted, so what the policy refuses does not
exist in the namespace to begin with.

## Student data perimeter

```mermaid
graph TB
    subgraph machine["Local machine — nothing leaves"]
        subgraph tracked["Tracked in git"]
            DEMO["students/demo/"]
            CODE["src/ · tests/"]
            FONTS["fonts served locally"]
        end
        subgraph ignored["gitignored"]
            REAL["students/real/*"]
            DB[("data/*.db")]
            BAK2["data/backups/"]
        end
    end
    CLOUD["☁️ any cloud"]
    machine -.->|"no path exists"| CLOUD

    style REAL fill:#2d5016,color:#fff
    style CLOUD fill:#333,color:#888
```

Hebrew web fonts are embedded from `src/yoni/interfaces/web/fonts/` — a child's browser never calls
Google to draw letters.

## What the gate checks

```mermaid
graph LR
    G["the gate<br/>check.py"] --> D["deps pinned"]
    G --> E["guards exist"]
    G --> W["guards wired"]
    G --> A["architecture"]
    G --> TY["types — mypy"]
    G --> T["tests + no stray test files"]
    G --> DEBT["known debt"]
    G --> P["privacy"]

    A --> A1["core imports no infrastructure"]
    A --> A2["core loads without requests"]
    A --> A3["no .py at the root"]
    A --> A4["streamlit entry uses absolute imports"]

    style A fill:#2d5016,color:#fff
```

Four of these exist because something actually broke during the session that produced them. That is
the intent: what must hold goes into code, because vigilance already failed once.

## Links

- [Global Status](status.md)
- [Global Roadmap](roadmap.md)

---

## How to Update

1. These diagrams are derived from source. Re-derive after structural change — do not patch them.
2. A green fill means the property is enforced by `check.sh`. Only colour a node green when a check
   actually exists; otherwise it is a wish wearing the costume of a guarantee.
3. `Documentation/CodeReference/` was generated **before** the refactor and its module map is stale.
