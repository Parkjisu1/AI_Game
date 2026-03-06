# GameForge: AI Game Development Pipeline

> AI Agent Team that auto-generates game design documents and Unity C# source code from a single concept sentence.

```
Input:  "Make an Idle RPG with AFK income + character collection."
Output: 3-Layer Design Docs + 54 Unity C# Systems + Validation Reports
```

---

## Overview

GameForge is a **self-reinforcing AI pipeline** that automates game development — from design docs to code generation.

A single game concept is transformed into 3-Layer design docs (Game Design → System Spec → AI YAML), then compiled into Unity C# source code via parallel agent teams, validated, and accumulated into a knowledge DB that improves quality over time.

### Supported Platforms

| Platform | Output | Use Case |
|----------|--------|----------|
| **Unity** | C# MonoBehaviour source code | Mobile / PC games |
| **Playable** | Single HTML5 file (`playable.html`) | Playable ads (Meta, Google, IronSource, AppLovin) |

### Supported Genres

Generic, RPG, Idle, SLG, Simulation, Tycoon, Merge, Puzzle, Casual — 9 genres.

### Numbers

| Metric | Scale |
|--------|-------|
| Code DB (Base) | 958 files across 8 genres |
| Code DB (Expert) | 20 verified files (score >= 0.6) |
| Design DB (Base) | 97 files |
| Automation Scripts | 18 (17 JS + 1 Python) + 4 shared libraries |
| Custom AI Agents | 9 (including Lead) |
| Slash Commands | 8 |
| Verified Projects | 6 (Puzzle ×2, RPG ×1, Idle ×1, Match3 ×1, Playable ×8+) |

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

Each AI focuses on a single role to prevent context contamination and hallucination.

### Dual Pipeline

```
Design Workflow (Stage 0~8)          Code Workflow (Phase 0~3)
─────────────────────────           ────────────────────────
Stage 0: Design Standards            Phase 0: Core (Main Coder solo)
Stage 1: DB Processing               Phase 1: Domain (Main + Sub ×2)
Stage 2: Design Generation           Phase 2: Upper Domain (parallel)
Stage 3: Cross-Validation            Phase 3: Game Layer UI (parallel)
Stage 4: Director Review                 + Validation + DB Accumulation
Stage 5: Regen Evaluation
Stage 6: Expert DB Accumulation
Stage 7: Play Verification (AI Tester)
Stage 8: Live Sync
```

### Self-Reinforcing Loop

```
Project A → Generate → Validate → Expert DB
                                      ↓
Project B → Generate ← Expert DB Reference (quality ↑)
         → Validate → Expert DB (scale ↑)
                           ↓
Project C → Generate ← Expert DB Reference (quality ↑↑)
```

Quality improves naturally as the Expert DB grows across projects.

---

## Agent Team (AI-Game-Creator)

```
                    ┌──────────────────────────┐
                    │   Lead (Opus 4.6)         │
                    │   PM — task distribution   │
                    └─────────┬────────────────┘
         ┌──────────┬────────┼────────┬──────────┐
    ┌────┴─────┐ ┌──┴───┐   │   ┌────┴────┐ ┌───┴────────┐
    │ Designer │ │ Main │   │   │ Sub     │ │ Playable   │
    │(Son 4.6) │ │Coder │   │   │Coder ×2 │ │ Coder      │
    │ Design   │ │(Opus)│   │   │(Son 4.6)│ │ (Son 4.6)  │
    └──────────┘ │ Core │   │   │ Parallel│ │ HTML5 ads  │
                 └──────┘   │   └─────────┘ └────────────┘
         ┌──────────┐  ┌────┴─────┐  ┌──────────────┐
         │ Design   │  │Validator │  │ DB Builder   │
         │Validator │  │(Son 4.6) │  │ (Son 4.6)    │
         │(Son 4.6) │  │ Code QA  │  │ On-demand    │
         │Quality   │  └──────────┘  └──────────────┘
         │Gates     │
         └──────────┘
```

| Agent | Model | Role |
|-------|-------|------|
| **Lead** | claude-opus-4-6 | PM — task distribution, output evaluation, phase gate management |
| **Designer** | claude-sonnet-4-6 | 3-Layer design docs (Game Design → System Spec → AI YAML) |
| **Main Coder** | claude-opus-4-6 | Core architecture + complex systems + `_ARCHITECTURE.md` |
| **Sub Coder ×2** | claude-sonnet-4-6 | Follows Main Coder patterns, parallel node implementation |
| **Playable Coder** | claude-sonnet-4-6 | HTML5 single-file playable ads |
| **Validator** | claude-sonnet-4-6 | 5+1 stage code validation |
| **Design Validator** | claude-sonnet-4-6 | 6-stage design validation, Quality Gates owner |
| **DB Builder** | claude-sonnet-4-6 | C# source parsing → Code DB (on-demand) |
| **Design DB Builder** | claude-sonnet-4-6 | Design doc parsing → Design DB (on-demand) |

---

## Classification System

### Code Taxonomy

```
Layer (3)   → Core / Domain / Game
Genre (9)   → Generic / RPG / Idle / SLG / Simulation / Tycoon / Merge / Puzzle / Casual
Role (21)   → Manager, Controller, Calculator, Processor, Handler, ...
Tag         → 7 macro + 11 micro behavior tags
```

### Design Taxonomy

```
Domain (9)  → InGame / OutGame / Balance / Content / BM / LiveOps / UX / Social / Meta
data_type   → formula / table / rule / flow / config / content_data
source (6)  → internal_original / internal_produced / internal_live / observed / community / generated
```

---

## Database Architecture

```
db/
├── base/                    # Code Base DB (958 files, 8 genres)
│   ├── generic/core/        #   index.json + files/{fileId}.json
│   ├── rpg/, idle/, puzzle/, tycoon/, playable/, simulation/, slg/, merge/
├── expert/                  # Code Expert DB (score >= 0.6)
├── rules/                   # Accumulated feedback rules
└── design/
    ├── base/{genre}/{domain}/   # Design Base DB (97 files)
    ├── expert/                  # Design Expert DB
    ├── standards/               # Genre design standards (Stage 0)
    ├── directions/              # Direction history
    └── rules/                   # Design feedback rules
```

### Search Priority (5-level)

| Priority | Source | Condition |
|----------|--------|-----------|
| 1 | Expert DB (matching genre) | genre match AND score >= 0.6 |
| 2 | Expert DB (Generic) | genre = Generic AND score >= 0.6 |
| 3 | Base DB (matching genre) | genre match |
| 4 | Base DB (Generic) | genre = Generic |
| 5 | AI generation | No reference (last resort) |

### Trust Score System

| Event | Code | Design |
|-------|------|--------|
| Initial save | 0.4 | 0.3~0.4 (based on auto-score) |
| Feedback applied | +0.2 | +0.1 |
| Director approval (no feedback) | — | +0.2 |
| Reuse success | +0.1 | +0.1 |
| Reuse failure | -0.15 | -0.1 |
| **Expert promotion threshold** | **>= 0.6** | **>= 0.6** |

---

## AI Tester & Virtual Player

AI-powered game testing system using BlueStacks + ADB.

### Two Roles

| Role | Description |
|------|-------------|
| **Primary** | External game → Design DB data collection (Stage 1). 10 AI observers estimate 32 parameters (~85-89.5% accuracy) |
| **Secondary** | Internal build verification (Stage 7). Predicted vs actual balance comparison |

### 4-Layer Intelligence Architecture

```
Layer 4: Genre Schema       — RPG / Idle / Merge / SLG / Puzzle strategies
Layer 3: Adaptive Learning  — failure_memory, loop_detector, spatial_memory, plan_adapter
Layer 2: Reasoning          — GOAP Planner, goal_library, utility_scorer
Layer 1: Perception         — OCR Reader, Gauge Reader, State Reader, Screen Analyzer
```

### Verified Games

- **Ash & Veil** (RPG) — Full autonomous play tested (Lv.25→31), 7 action types verified
- **CarMatch** (Match3) — Board recognition + color detection (7 colors), automated play loop

---

## Automation Scripts

### Slash Commands

| Command | Purpose |
|---------|---------|
| `/parse-source [path]` | C# source → Code DB |
| `/parse-design [path]` | Design docs → Design DB |
| `/generate-design [input]` | Generate design docs |
| `/generate-design-v2 [input]` | Full 8-stage design workflow |
| `/generate-code [yaml]` | YAML → C# code generation |
| `/validate-code [path]` | 5-stage code validation |
| `/validate-design [project]` | 6-stage design validation |
| `/sync-live [project]` | Live data → DB sync |

### Node.js Scripts (`scripts/`)

| Category | Scripts |
|----------|---------|
| **DB Parsing** | `parser.js`, `design-parser.js`, `batch-parse-project.js`, `batch-parse-yaml-designs.js` |
| **DB Search** | `db-search.js`, `design-db-search.js`, `format-search.js` |
| **Simulation** | `balance-simulator.js`, `play-verification.js`, `virtual-player-bridge.js` |
| **Quality** | `design-version.js`, `generate-kpi.js`, `quality_report.js`, `c10-to-design-db.js` |
| **Shared Libs** | `lib/yaml-utils.js`, `lib/safe-io.js`, `lib/domain-utils.js`, `lib/score-manager.js` |

---

## Quality Assurance

### Code Validation (5+1 stages)

1. **Syntax** — Compile errors, grammar
2. **Dependency** — Missing references, circular deps
3. **Contract** — provides/requires matching
4. **NullSafety** — Null reference checks
5. **Pattern** — Architecture pattern compliance
6. **Build** (Optional) — Unity batchmode verification

### Design Validation (6 stages)

1. **Cross-Consistency** — System↔Balance, Content↔System, BM↔Balance
2. **User Journey Simulation** — Day 1~30 persona tracking
3. **Gap Detection** — Missing references, undefined items
4. **Self-Verification** — Internal contradictions, completeness
5. **Quality Gates** (6 types) — Cross-Layer Naming / L3 Completeness / Dependency / logicFlow / Copy-Paste / Cross-Doc
6. **Build Verification** (Optional) — Full balance simulator run

---

## Project Structure

```
.
├── CLAUDE.md                     # Master context (taxonomy, rules, settings)
├── README.md
│
├── .claude/
│   ├── agents/                   # 9 custom AI agents
│   ├── commands/                 # 8 slash commands
│   └── skills/                   # 3 auto-trigger skills
│
├── db/                           # Knowledge database
│   ├── base/                     #   Code Base DB (958 files)
│   ├── expert/                   #   Code Expert DB
│   ├── rules/                    #   Code feedback rules
│   └── design/                   #   Design DB (base + expert + standards + rules)
│
├── scripts/                      # 18 automation scripts + 4 shared libs
│   └── lib/                      #   yaml-utils, safe-io, domain-utils, score-manager
│
├── virtual_player/               # AI Virtual Player (Python)
│   ├── brain/                    #   Intelligence engine (Vision AI)
│   ├── perception/               #   Screen recognition (OCR, Gauge, State)
│   ├── reasoning/                #   Decision making (GOAP, Goals, Utility)
│   ├── adaptive/                 #   Adaptive learning
│   ├── genre/                    #   Genre-specific schemas
│   ├── navigation/               #   Screen navigation
│   └── data/games/               #   Per-game profiles
│
├── projects/                     # Per-project workspaces
│   ├── CleanRoomTest/            #   Clean room test project
│   └── IdleMoney/                #   Idle Money reverse-engineering
│
├── docs/                         # Documentation
│   └── WORKFLOW.md               #   Integrated workflow reference
│
├── proposal/                     # Workflow design documents
│   └── workflow/                 #   Canonical workflow specs (v2.2)
│
├── History/                      # Per-project KPI reports
└── Feedback/                     # Workflow improvement feedback
```

---

## Getting Started

### Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- Node.js 18+
- Python 3.13+ (for AI Tester / Virtual Player)
- BlueStacks + ADB (for play verification)

### Generate a Game (Unity)

```bash
# Single session
/generate-design "Idle RPG, AFK income + character collection" --genre idle

# Agent Team parallel generation
Make a game. Idle RPG with AFK income + character collection. Use Agent Team with 3 Coders.
```

### Generate Playable Ad (HTML5)

```bash
Match3 playable ad, candy theme. Use Agent Team.
```

### Parse Existing Code/Design into DB

```bash
# C# source
/parse-source E:\Projects\MyGame\Assets\Scripts --genre rpg

# Design docs
/parse-design E:\Docs\GameDesign --genre idle

# Batch parse
node scripts/batch-parse-project.js --tables <path> --genre idle --project MyGame
```

### Search DB

```bash
# Code DB
node scripts/db-search.js --genre idle --layer Domain --role Manager --top 10

# Design DB
node scripts/design-db-search.js --genre idle --domain balance --top 20 --json
```

### Balance Simulation

```bash
node scripts/balance-simulator.js --input balance.yaml --mode economy --seed 42
```

---

## Verified Projects

| Project | Genre | Files | Result |
|---------|-------|-------|--------|
| **DropTheCat** | Puzzle | 50 C# | 26 nodes, full pipeline completed |
| **MagicSort** | Puzzle | 37 C# | Sort puzzle full system |
| **VeilBreaker** | RPG (Idle) | 51 C# | 41 nodes, battle/character/equipment |
| **CarMatch** | Match3 | 34 modified | Large-scale code modification, 83 issues resolved |
| **IdleMoney** | Idle | Reverse-engineered | 54 systems, 89 Design DB entries, B+ grade |
| **Playable Ads** | Various | 8+ HTML5 | pin_pull, match3, runner, SLG mechanics |

---

## Technical Decisions

| Decision | Reason |
|----------|--------|
| **YAML** for design docs | Human-readable + AI-parseable, supports comments (unlike JSON) |
| **3-Layer design docs** | Gradual transformation from human intent → code-ready structure |
| **Opus for Main Coder** | Core architecture needs high reasoning; Sub Coders follow patterns at speed |
| **JS for balance simulation** | LLMs accumulate errors in iterative math; JS gives exact results |
| **Index-file separation** | Lightweight search via index.json; detail loaded on-demand per file |
| **Mandatory deduction reasoning** | Prevents false pattern learning from unexplained failures |
| **Separate market labels from score** | Market success ≠ design quality (marketing, timing, competition factors) |

---

## License

This project is proprietary software. All rights reserved.

---

*GameForge v2.3 — 2026.03*
