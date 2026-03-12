# GameForge: AI Game Development Pipeline

> AI Agent Team that auto-generates complete game design documents and Unity C# source code from a single concept sentence.

```
Input:  "Make an Idle RPG with AFK income + character collection."
Output: 3-Layer Design Docs + 54 Unity C# Systems + Validation Reports
```

---

## Overview

GameForge is a **self-reinforcing AI pipeline** that automates game development — from design documentation to production-ready code generation.

A single game concept is transformed into **3-Layer design documents** (Game Design → System Spec → AI YAML), then compiled into Unity C# source code via parallel AI agent teams. Every output is validated through multi-stage quality gates and accumulated into a knowledge database that **improves quality with each project**.

### Supported Platforms

| Platform | Output | Use Case |
|----------|--------|----------|
| **Unity** | C# MonoBehaviour source code | Mobile / PC games |
| **Playable** | Single HTML5 file | Playable ads (Meta, Google, IronSource, AppLovin) |

### Supported Genres

Generic, RPG, Idle, SLG, Simulation, Tycoon, Merge, Puzzle, Casual — **9 genres**.

### Key Metrics

| Metric | Scale |
|--------|-------|
| Code Knowledge Base | 958+ reference files across 8 genres |
| Expert Knowledge Base | 20+ verified high-quality files |
| Design Knowledge Base | 97+ design documents |
| Automation Scripts | 18 scripts + 4 shared libraries |
| AI Agents | 9 specialized roles |
| Verified Projects | 6+ (Puzzle, RPG, Idle, Match3, Playable Ads) |

---

## Core Architecture

### 3-AI Role Separation (Anti-Hallucination)

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   AI Stage 1    │    │   AI Stage 2    │    │   AI Stage 3    │
│   DB Processing │ →  │   Generation    │ →  │   Validation    │
│                 │    │                 │    │                 │
│ • Source parse  │    │ • Design docs   │    │ • Consistency   │
│ • Classify/tag  │    │ • Code gen      │    │ • Balance sim   │
│ • DB store      │    │ • DB reference  │    │ • Feedback gen  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

Each AI focuses on a **single role** to prevent context contamination and hallucination.

### Dual Pipeline

```
Design Workflow (8 Stages)              Code Workflow (4 Phases)
──────────────────────────             ────────────────────────
Stage 0: Design Standards               Phase 0: Core Architecture (Lead Coder)
Stage 1: Knowledge Processing           Phase 1: Domain Systems (Lead + Sub ×2)
Stage 2: Design Generation              Phase 2: Upper Domain (Parallel)
Stage 3: Cross-Validation               Phase 3: Game Layer & UI (Parallel)
Stage 4: Director Review                    + Multi-stage Validation
Stage 5: Regeneration Evaluation            + Knowledge Accumulation
Stage 6: Expert DB Accumulation
Stage 7: AI Play Verification
Stage 8: Live Sync
```

### Self-Reinforcing Knowledge Loop

```
Project A → Generate → Validate → Expert DB
                                      ↓
Project B → Generate ← Expert DB Reference (quality ↑)
         → Validate → Expert DB (scale ↑)
                           ↓
Project C → Generate ← Expert DB Reference (quality ↑↑)
```

Quality improves naturally as the knowledge base grows across projects.

---

## Agent Team

```
                    ┌──────────────────────────┐
                    │   Lead (Opus)             │
                    │   PM — task distribution   │
                    └─────────┬────────────────┘
         ┌──────────┬────────┼────────┬──────────┐
    ┌────┴─────┐ ┌──┴───┐   │   ┌────┴────┐ ┌───┴────────┐
    │ Designer │ │ Main │   │   │ Sub     │ │ Playable   │
    │          │ │Coder │   │   │Coder ×2 │ │ Coder      │
    │ Design   │ │ Core │   │   │ Parallel│ │ HTML5 ads  │
    └──────────┘ │ Arch │   │   └─────────┘ └────────────┘
                 └──────┘   │
         ┌──────────┐  ┌────┴─────┐  ┌──────────────┐
         │ Design   │  │Validator │  │ DB Builder   │
         │Validator │  │ Code QA  │  │ On-demand    │
         │ Quality  │  └──────────┘  └──────────────┘
         │ Gates    │
         └──────────┘
```

| Agent | Role |
|-------|------|
| **Lead** | PM — task distribution, output evaluation, phase gate management |
| **Designer** | 3-Layer design docs (Game Design → System Spec → AI YAML) |
| **Main Coder** | Core architecture + complex systems |
| **Sub Coder ×2** | Follow Main Coder patterns, parallel implementation |
| **Playable Coder** | HTML5 single-file playable ads |
| **Validator** | 5+1 stage code validation |
| **Design Validator** | 6-stage design validation, Quality Gates owner |
| **DB Builder** | Source parsing → Knowledge DB (on-demand) |

---

## Classification System

### Code Taxonomy

| Axis | Categories |
|------|-----------|
| **Layer** (3) | Core / Domain / Game |
| **Genre** (9) | Generic / RPG / Idle / SLG / Simulation / Tycoon / Merge / Puzzle / Casual |
| **Role** (21) | Manager, Controller, Calculator, Processor, Handler, Factory, Service, Validator, etc. |
| **Behavior Tags** | 7 macro tags + 11 micro tags |

### Design Taxonomy

| Axis | Categories |
|------|-----------|
| **Domain** (9) | InGame / OutGame / Balance / Content / BM / LiveOps / UX / Social / Meta |
| **Data Type** | formula / table / rule / flow / config / content_data |
| **Source** (6) | original / produced / live / observed / community / generated |

---

## Knowledge Database

### 5-Level Search Priority

| Priority | Source | Condition |
|----------|--------|-----------|
| 1 | Expert DB (matching genre) | genre match AND score >= 0.6 |
| 2 | Expert DB (Generic) | genre = Generic AND score >= 0.6 |
| 3 | Base DB (matching genre) | genre match |
| 4 | Base DB (Generic) | genre = Generic |
| 5 | AI generation | No reference found (last resort) |

### Trust Score System

| Event | Score Change |
|-------|-------------|
| Initial save | +0.3 ~ 0.4 |
| Feedback applied | +0.1 ~ 0.2 |
| Director approval | +0.2 |
| Reuse success | +0.1 |
| Reuse failure | -0.1 ~ -0.15 |
| **Expert promotion** | **>= 0.6** |

---

## AI Tester (Virtual Player)

AI-powered autonomous game testing system.

### 4-Layer Intelligence

```
Layer 4: Genre Schema       — RPG / Idle / Merge / SLG / Puzzle strategies
Layer 3: Adaptive Learning  — failure memory, loop detection, spatial memory
Layer 2: Reasoning          — GOAP Planner, goal library, utility scoring
Layer 1: Perception         — OCR, gauge reading, state detection, screen analysis
```

### Capabilities

- **10 AI observers** estimating 32 game parameters (~85-89.5% accuracy)
- **Genre-specific strategies** for 5 game genres
- **Adaptive learning** with failure memory and loop detection
- **GOAP (Goal-Oriented Action Planning)** for decision making
- **Computer vision** based screen analysis (YOLOv11)
- Autonomous play testing from Level 1 to Level 30+

---

## Quality Assurance

### Code Validation (5+1 Stages)

1. **Syntax** — Compile errors, grammar
2. **Dependency** — Missing references, circular dependencies
3. **Contract** — provides/requires interface matching
4. **Null Safety** — Null reference protection
5. **Pattern** — Architecture pattern compliance
6. **Build** (Optional) — Unity batchmode verification

### Design Validation (6 Stages)

1. **Cross-Consistency** — System↔Balance, Content↔System, BM↔Balance
2. **User Journey Simulation** — Day 1~30 persona tracking
3. **Gap Detection** — Missing references, undefined items
4. **Self-Verification** — Internal contradictions, completeness
5. **Quality Gates** (6 types) — Naming / Completeness / Dependency / Logic Flow / Copy-Paste / Cross-Doc
6. **Build Verification** (Optional) — Full balance simulator run

---

## Automation

### Commands

| Command | Purpose |
|---------|---------|
| `/parse-source` | C# source → Code Knowledge DB |
| `/parse-design` | Design docs → Design Knowledge DB |
| `/generate-design` | Generate 3-layer design documents |
| `/generate-design-v2` | Full 8-stage design workflow |
| `/generate-code` | YAML spec → Unity C# code generation |
| `/validate-code` | 5-stage code validation |
| `/validate-design` | 6-stage design validation |
| `/sync-live` | Live data synchronization |

### Scripts

| Category | Purpose |
|----------|---------|
| **DB Parsing** | C# source code & design document parsing into knowledge DB |
| **DB Search** | Multi-genre, multi-domain search with priority ranking |
| **Simulation** | Economy balance simulation, play verification |
| **Quality** | KPI report generation, quality metrics, versioning |
| **Shared Libraries** | YAML utils, safe I/O, domain classification, score management |

---

## Verified Projects

| Project | Genre | Scale | Result |
|---------|-------|-------|--------|
| Puzzle Game A | Puzzle | 50 C# files | 26 systems, full pipeline |
| Puzzle Game B | Puzzle | 37 C# files | Sort puzzle complete system |
| RPG Game | RPG (Idle) | 51 C# files | 41 systems, battle/character/equipment |
| Match3 Game | Match3 | 34 modified files | Large-scale modification, 83 issues resolved |
| Idle Game | Idle | Reverse-engineered | 54 systems, 89 design entries, B+ grade |
| Playable Ads | Various | 8+ HTML5 files | Multiple ad formats for major networks |

---

## Technical Decisions

| Decision | Reason |
|----------|--------|
| **YAML** for design docs | Human-readable + AI-parseable, supports comments |
| **3-Layer design docs** | Gradual transformation from human intent → code-ready structure |
| **Dual model strategy** | High-reasoning model for architecture; fast model for parallel implementation |
| **JavaScript for balance sim** | LLMs accumulate errors in iterative math; JS gives exact results |
| **Index-file separation** | Lightweight search via index; detail loaded on-demand |
| **Mandatory deduction reasoning** | Prevents false pattern learning from unexplained failures |

---

## Getting Started

### Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- Node.js 18+
- Python 3.13+ (for AI Tester)
- Android emulator + ADB (for play verification)

### Quick Start

```bash
# Generate a game from concept
/generate-design "Idle RPG with AFK income + character collection" --genre idle

# Generate with full agent team (parallel)
Make a game. Idle RPG with AFK income. Use Agent Team with 3 Coders.

# Generate playable ad
Match3 playable ad, candy theme. Use Agent Team.
```

### Parse & Search

```bash
# Parse existing C# into knowledge DB
/parse-source path/to/scripts --genre rpg

# Search code knowledge
node scripts/db-search.js --genre idle --layer Domain --role Manager --top 10

# Search design knowledge
node scripts/design-db-search.js --genre idle --domain balance --top 20
```

### Balance Simulation

```bash
node scripts/balance-simulator.js --input balance.yaml --mode economy --seed 42
```

---

## License

MIT License

---

*GameForge v2.3 — 2026.03*
