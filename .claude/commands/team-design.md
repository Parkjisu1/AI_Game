---
description: Orchestrate Designer + Design Validator for design workflow
---

# Team Design

Launch design generation + validation workflow.

## Input
$ARGUMENTS — project path [stage: concept|systems|balance|content|bm]

## Workflow

0. **Representative new-production / reverse-engineering handoff** (when applicable):
   - Before Stage 2, have Designer create/update `{project}/designs/flow-contract.json`, a JSON sidecar separate from design YAML. Follow the field mapping in `.claude/commands/generate-design-v2.md` and the intent/evidence rules in `.claude/agents/designer.md` and `.claude/agents/lead.md`; do not impose the whole contract on an unrelated small edit.
   - Preserve `intent.user_request`, goals, non-goals, constraints, and explicit assumptions. Link reference observations/inferences to intended `keep|adapt|replace|omit|new` decisions, requirements, relevant discipline work items, and observable acceptance. DB matches do not override user intent.
   - Set top-level `version: 1` and `project`. Require each requirement's `delivery_scope` to match its linked acceptance `scope` (`placeholder_functional` or `production_experience`). CLI `--scope` instead selects `requirements[].category`; acceptance `kind` identifies the appropriate check, as documented in `/generate-design-v2`.
   - Keep claim `basis` (`observed|inferred|designed|unknown`) separate from `verification` (`untested|reproduced|contradicted`). Distinguish `placeholder_functional` from `production_experience`; retain missing evidence without inventing results or approval.
   - Have Design Validator run `node scripts/validate-flow-contract.js --input {project}/designs/flow-contract.json --stage handoff` before passing the generated design onward. Fix reported contract problems; do not bypass validation by dropping an applied contract.
   - If invoking `design-to-code-bridge.js`, pass `--flow-contract {project}/designs/flow-contract.json` with its existing project/input/output arguments. The JSON contract travels with the generated YAML rather than replacing it.
   - Handoff PASS checks reference and record integrity only. Executed acceptance requires artifact/version and observed evidence, with separate technical, behavior, art, experience, and market judgments. Use `--stage acceptance --scope technical` (or one of `behavior`, `art`, `experience`, `market`) for the applicable recorded acceptance; script PASS does not prove meaningful gameplay or market success.
   - Resolve relative evidence/input `locator` values from the contract JSON's directory and pin local files with `sha256`. Record the handoff result's `acceptance_basis[id]` as the case's `basis_hash` only with an actual check against those inputs; changing the hash alone is not revalidation. Common intent/constraint/assumption changes conservatively stale all acceptance, while work-item changes stale affected cases.

1. **Stage 2 — Designer generates**:
   - 2-1: Concept (core fun + pillars)
   - 2-2: Systems (system_spec.yaml)
   - 2-3: Balance (curves, economy) — parallel with 2-4
   - 2-4: Content (levels, progression) — parallel with 2-3
   - 2-5: BM + LiveOps
   - Each outputs YAML + triggers Docx generation
2. **Stage 3 — Design Validator validates**:
   - Cross-consistency check (all systems reference each other correctly)
   - User journey simulation (new player → day-30 veteran)
   - Gap detection (missing systems, undefined currencies, dead-end flows)
   - Score calculation (logic_completeness, balance_stability, impl_complexity)
3. **Stage 4 — Director review gate** (human):
   - Present validation report to user
   - Wait for approval or feedback
   - Apply that wait only when a human decision remains required for the current task under repository rules. Existing authorization carries through reversible local work; do not request it again at every stage or treat silence as approval. Record assumptions and continue independent authorized work.
4. **Stage 5 — If feedback**:
   - Designer applies changes
   - Design Validator re-validates
   - Feedback history recorded
5. **Stage 6 — DB accumulation**:
   - Design DB Builder saves to design_base
   - Score >= 0.6 → promote to design_expert
   - Extract reusable rules

## Agent Configuration
```
Designer: subagent_type=designer, model=sonnet
Design Validator: subagent_type=design-validator, model=sonnet
Design DB Builder: subagent_type=design-db-builder, model=sonnet (Stage 6 only)
```
