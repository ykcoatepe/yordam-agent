# Implementation Plan: Yordam Agent Coworker + Runtime
Last updated: 2026-01-20

## 1) Executive Summary
- **Goal:** Integrate the shipped coworker feature set with a durable task runtime (queue, daemon, approvals) for resumable, auditable automation.
- **Why now:** The coworker foundation is complete; a runtime unlocks long-running tasks, pause/resume, and history without expanding tool surface risk.
- **Who benefits:** macOS CLI/Quick Action users who want safe automation with progress visibility and recovery.
- **High-level approach (1-3 bullets):**
  - Preserve plan -> preview -> approve -> apply as the safety contract.
  - Add a SQLite task store, per-task bundle, and daemon worker loop.
  - Keep web and file policies deny-by-default with explicit approvals and bounded reads/writes.
- **Key risks (top 3):** task state corruption, approval mismatches on resume, and file conflicts with parallel workers.
- **Target milestones (high-level):** Runtime MVP -> approvals/resume hardening -> rollout + docs.

## 2) Scope
### In Scope
- Existing coworker tool registry, policy engine, plan/preview/apply, file/doc/web tools.
- Durable task runtime: SQLite task store, task bundles, daemon worker, CLI orchestration.
- Approval storage and resume (plan hash + checkpoints).
- Logs/events and runbooks.

### Out of Scope
- Shell execution tool.
- Cloud LLM calls or remote execution.
- SwiftUI/menubar UI in v1 (CLI only).
- Automatic launchd install (optional print-plist only).

### Assumptions
- Ollama remains the default local model.
- Default state dir: `~/.config/yordam-agent/coworker/`.
- Single-worker default with opt-in parallelism.

### Constraints
- Minimal diffs; no expansion of tool surface.
- No destructive operations (delete/overwrite) in v1.
- No raw local content sent to web tools.

## 3) Success Criteria
- **Functional acceptance criteria:**
  - Coworker CLI continues to generate plan.json and previews; approvals remain hash-bound.
  - Runtime can queue, execute, pause for approval, resume, and cancel safely.
  - Task history and logs survive restarts.
- **Non-functional requirements (NFRs):** safety by default, bounded I/O, durable task state.
- **Observability criteria:** per-task JSONL events + stable task metadata snapshots.
- **Operational criteria:** documented runbooks for stuck tasks, approval mismatches, and daemon control.

## 4) Current State
- **Existing architecture/components:** coworker CLI, registry, policy engine, executor, file/doc/web tools.
- **Relevant systems/integrations:** Finder Quick Actions (Automator), local config.
- **Data flows & storage:** plan artifacts near files; approvals via token files.
- **Known pain points/limitations:** no task queue, no daemon, no resume across runs.

## 5) Proposed Solution Overview
### Architecture (Conceptual)
- **Key components:** coworker CLI + tools, SQLite task store, task bundle, daemon worker, approval store.
- **Interfaces/APIs:** `yordam-agent coworker` + `yordam-agent coworker-runtime` (submit/status/list/logs/cancel/approve/daemon).
- **Data model changes:** tasks + approvals tables; plan_hash stored in plan.json and task metadata.
- **Security & access control:** existing policy enforcement; per-task web allowlist intersected with global allowlist.
- **Failure modes & resilience:** fail closed on policy/approval mismatch; idempotent state transitions.

### Tradeoffs Considered
- Option A: project-local task storage (brittle for Quick Actions).
- Option B: global state dir with SQLite (chosen).
- Option C: SwiftUI app hosting runtime (deferred).
- Decision + rationale: Python daemon + SQLite minimizes risk and integrates with existing CLI.
- What would change the decision (trigger conditions): UI-first adoption or OS sandboxing requirements.

## 6) Work Breakdown Structure
Provide a phased plan with epics and tasks. Include dependencies and acceptance criteria.

### 6.1 Phases & Milestones
- **Phase 0 - Discovery/Alignment:** integrated scope + runtime lifecycle agreed.
- **Phase 1 - Design:** runtime schema, event format, CLI contract.
- **Phase 2 - Build:** runtime MVP + coworker foundation (already shipped).
- **Phase 3 - Test & Hardening:** recovery, cancel, concurrency, security gates.
- **Phase 4 - Rollout:** feature flag + docs/runbooks.
- **Phase 5 - Post-Launch:** agent loop + skills + UI planning.

### 6.2 Detailed Task Plan (Table)
Status legend (ANSI): [90mNot Started[0m | [34mIn Progress[0m | [31mBlocked[0m | [32mDone[0m
Status legend (plain fallback): Not Started | In Progress | Blocked | Done

| ID | Status | Work Item | Owner Role | Est. | Dependencies | Deliverables | Acceptance Criteria |
| ---: | -------- | ----------- | ------------ | ------ | -------------- | -------------- | -------------------- |
| P0.1 | [32mDone[0m | Confirm integrated scope + sequencing | PM/Eng Lead | S | - | Scope notes | Scope and milestones signed off |
| P0.2 | [32mDone[0m | Define runtime lifecycle + states | Backend Eng | S | P0.1 | Lifecycle spec | States and transitions documented |
| P0.3 | [32mDone[0m | Define task bundle layout | Backend Eng | S | P0.1 | Layout doc | task.json/plan.json/events/scratch/staging defined |
| P0.4 | [32mDone[0m | Plan schema + approval contract | Backend Eng | S | - | Plan schema doc | Plan hash enforced in approvals |
| P1.1 | [32mDone[0m | Tool registry + policy engine | Backend Eng | M | P0.4 | Registry + policy modules | Disallowed tools/paths blocked |
| P1.2 | [32mDone[0m | Plan/preview/apply executor | Backend Eng | M | P0.4 | Executor + tests | Hash mismatch fails closed |
| P1.3 | [32mDone[0m | Design SQLite schema (tasks, approvals) | Backend Eng | S | P0.2 | Schema doc | Pause/resume + approvals supported |
| P1.4 | [32mDone[0m | Define event log format | Backend Eng | S | P0.2 | JSONL spec | Event fields/levels documented |
| P1.5 | [32mDone[0m | Runtime CLI contract | Backend Eng | S | P0.2 | CLI spec | Submit/status/list/logs/cancel/approve defined |
| P1.6 | [32mDone[0m | Model I/O hardening spec | Backend Eng | S | P0.2 | I/O spec | Untrusted delimiter + fixed instruction documented |
| P2.1 | [32mDone[0m | Coworker CLI (plan/preview/apply) | Backend Eng | M | P1.1,P1.2 | CLI command | Plan + preview emitted |
| P2.2 | [32mDone[0m | Core file tools | Backend Eng | M | P1.1 | File tools | Reads/writes/moves/renames gated |
| P2.3 | [32mDone[0m | Finder Quick Action | macOS Eng | S | P2.1 | Automator action | Works on selected items |
| P2.4 | [32mDone[0m | PDF extract + OCR fallback | Backend Eng | M | P2.1 | PDF/OCR pipeline | Handles large PDFs safely |
| P2.5 | [32mDone[0m | Document tasks (summary/outline/report) | Backend Eng | M | P2.4 | Task recipes | Outputs generated via propose/apply |
| P2.6 | [32mDone[0m | Web fetch + sanitization + egress guard | Backend Eng | M | P1.1 | Web tool + tests | Allowlist + size limits enforced |
| P2.7 | [32mDone[0m | Workflow checkpoints + resume metadata | Backend Eng | M | P2.1 | Checkpoint support | Approval per checkpoint |
| P2.8 | [32mDone[0m | Implement task store + migrations | Backend Eng | M | P1.3 | task_store module | CRUD + durability tests pass |
| P2.9 | [32mDone[0m | Implement task bundle writer | Backend Eng | S | P0.3 | task_bundle module | task.json/plan.json/events written |
| P2.10 | [32mDone[0m | Implement daemon worker loop | Backend Eng | M | P2.8 | daemon module | Claims/executes queued tasks |
| P2.11 | [32mDone[0m | Implement runtime CLI commands | Backend Eng | M | P1.5,P2.8 | CLI commands | Submit/status/list/logs/cancel/approve work |
| P2.12 | [32mDone[0m | Approval resume integration | Backend Eng | M | P2.10 | Approval handler | Resumes only on matching plan hash |
| P2.13 | [32mDone[0m | Staging outputs + atomic move | Backend Eng | M | P2.10 | staging/atomic writes | Outputs moved only after approval |
| P3.1 | [32mDone[0m | Crash/restart recovery tests | Backend Eng | M | P2.10 | Tests | Restarts keep task integrity |
| P3.2 | [32mDone[0m | Cancel semantics + cleanup | Backend Eng | S | P2.10 | Cancel path | Canceled tasks stop safely |
| P3.3 | [32mDone[0m | Config/env overrides | Backend Eng | S | P2.8 | Config updates | state-dir/worker count overrides |
| P3.4 | [32mDone[0m | Concurrency strategy (path locks) | Backend Eng | S | P2.8 | Locking plan | Conflicts prevented or detected |
| P3.5 | [32mDone[0m | Implement model I/O hardening | Backend Eng | S | P1.6 | Prompt wrapper | Untrusted outputs isolated |
| P4.1 | [32mDone[0m | Runtime docs + runbooks | Tech Writer/Eng | S | P2.11 | DOCS updates | CLI + recovery runbooks included |
| P4.2 | [32mDone[0m | Feature flag runtime | Backend Eng | S | P2.11 | Config flag | Safe opt-in; default off |
| P4.3 | [32mDone[0m | Optional launchd print-plist | Backend Eng | S | P2.11 | plist generator | Manual install instructions |
| P5.1 | [32mDone[0m | Agent loop design (discovery -> commit) | Backend Eng | M | P2.10 | Design doc | Tool-output capture defined |
| P5.2 | [32mDone[0m | Skills + deliverables design | Backend Eng | S | P2.10 | Design doc | Skill specs + validation rules |
| P5.3 | [32mDone[0m | Optional UI client discovery | PM/Eng Lead | S | P4.2 | Decision memo | Go/no-go with criteria |

### 6.3 Dependency Graph (Optional but Recommended)
- Critical path: P0.1 -> P0.2 -> P1.3 -> P2.8 -> P2.10 -> P2.11 -> P2.12 -> P3.1.
- Parallelizable: P0.3, P1.4, P1.5 after P0.2; P3.2-P3.3 after P2.10.

### 6.4 Completion Checklist (Plan Hygiene)
- [x] Status column updated for tasks touched this go
- [x] "Last updated" line refreshed
- [x] Sub-plans summary updated and links valid (if sub-plans exist)
- [ ] Completed sub-plans summarized and deleted (retained per request)

## 7) Testing & Quality Strategy
- **Test pyramid plan:** unit (task store), integration (daemon + executor), e2e (submit -> complete).
- **Test data & environments:** temp dirs; SQLite in temp; fake plans/tools.
- **Performance testing:** 50 sequential tasks; ensure no DB lock errors.
- **Security testing:** policy enforcement + approval mismatches + web allowlist regression.
- **Quality gates:** `ruff check .`, `pytest`, manual daemon smoke test.

## 8) Rollout Plan
- **Release strategy:** feature-flagged runtime; opt-in CLI usage.
- **Migration strategy:** none (new state dir); document upgrades for schema changes.
- **Monitoring during rollout:** task status summary + events log.
- **Rollback plan:** disable runtime flag; keep existing coworker flow.
- **Communication plan:** README/DOCS + Quick Action notes.

## 9) Operations
- **Runbooks:** daemon start/stop; stuck tasks; approval mismatch recovery.
- **On-call readiness:** maintainer-owned.
- **SLOs/SLIs:** optional (e.g., 95% tasks complete without manual intervention).
- **Cost considerations:** local compute only; SQLite footprint small.

## 10) Risks, Mitigations, and Contingencies

| Risk | Likelihood | Impact | Mitigation | Contingency/Trigger |
| ------ | ------------ | -------- | ------------ | --------------------- |
| Task state corruption | Medium | High | Atomic updates + durable events | Requeue or mark failed |
| Approval mismatch on resume | Medium | High | Strict plan hash checks | Require fresh approval |
| Concurrent file conflicts | Low | Medium | Default single worker + locks | Force single worker |
| Web exfiltration | Medium | High | Allowlist + egress guard | Disable web globally |

## 11) Open Questions
Locked decisions:
- Q1 (high): Yes. Require per-path locking before enabling multi-worker; keep default single worker.
- Q2 (medium): No. Previews stay as bundle files; SQLite keeps metadata + pointers only.
- Q3 (low): Yes. Include `launchd print-plist` in v1 (optional/manual).

## 12) Sub-plans Summary
- `subplans/implementation-plan-yordam-coworker-2026-01-18.md` (completed; retained for reference per request)
- `subplans/implementation-plan-yordam-coworker-runtime-2026-01-18.md` (runtime track reference)

## 13) Next Actions
All items complete.
