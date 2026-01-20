# Implementation Plan: Yordam Agent AI Coworker
Last updated: 2026-01-18

## 1) Executive Summary
- **Goal:** Deliver a local-first AI coworker with explicit plan→preview→approve→apply execution and guarded web access.
- **Why now:** Existing CLI + Finder Quick Actions + local Ollama enable safe, fast iteration with minimal new surface area.
- **Who benefits:** macOS users who need controlled, auditable automation over files and documents.
- **High-level approach (1–3 bullets):**
  - Define a minimal tool surface and deny-by-default policy engine.
  - Enforce plan-hash approvals and checkpointed execution.
  - Add document tasks and guarded web fetch with sanitization.
- **Key risks (top 3):** capability creep, data exfiltration once web is enabled, prompt injection.
- **Target milestones (high-level):** Vertical slice coworker → document tasks → guarded web → workflow checkpoints.

## 2) Scope
### In Scope
- Tool registry + policy engine.
- Plan → preview → approve → apply execution.
- Core file tools (read/list/propose/apply/move/rename).
- PDF extraction, chunking, OCR fallback, document tasks (summary/outline/report).
- Web fetch (GET-only, allowlist, sanitization, size limits, query guard).
- Finder Quick Actions and docs/runbooks.

### Out of Scope
- Shell execution tool.
- Cloud LLM calls.
- Background daemon mode.

### Assumptions
- Ollama is available locally.
- Users opt into web access explicitly.
- Selected file paths are the scope boundary for operations.

### Constraints
- Minimal diffs and safe defaults.
- No destructive operations (delete/overwrite) in v1.
- No raw local content sent to web tools.

## 3) Success Criteria
- **Functional acceptance criteria:**
  - All coworker runs produce a plan.json and human preview.
  - Plan approval is bound to plan hash; mismatches fail closed.
  - Web fetch is blocked unless allowlisted and guarded.
- **Non-functional requirements (NFRs):**
  - Policy validation denies out-of-scope paths and disallowed tools.
  - Size limits enforced for reads/writes/web.
- **Observability criteria:**
  - AI interaction logs and plan artifacts recorded locally.
- **Operational criteria:**
  - Runbooks for policy denials, approval mismatches, and OCR/web failures.

## 4) Current State
- **Existing architecture/components:** Python CLI with reorg/rename/rewrite; Ollama integration.
- **Relevant systems/integrations:** Finder Quick Actions (Automator), local config.
- **Data flows & storage:** Local file reads/writes; local plan artifacts.
- **Known pain points/limitations:** None remaining for coworker scope.

## 5) Proposed Solution Overview
### Architecture (Conceptual)
- **Key components:** Tool registry, policy engine, planner, executor, file/doc/web tools.
- **Interfaces/APIs:** `yordam-agent coworker` CLI + Finder Quick Actions.
- **Data model changes:** Plan JSON schema with tool calls, checkpoints, plan hash.
- **Security & access control:** path allowlist, deny-by-default, web egress guards.
- **Failure modes & resilience:** fail closed on policy/approval mismatch; checkpoint resume.

### Tradeoffs Considered
- Option A: CLI + Finder only (chosen).
- Option B: menubar app.
- Option C: Shortcuts integration.
- Decision + rationale: A minimizes risk and time-to-ship.
- What would change the decision (trigger conditions): demand for richer UI or global hotkeys.

## 6) Work Breakdown Structure
### 6.1 Phases & Milestones
- **Phase 0 — Discovery/Alignment:** tool surface + policy rules.
- **Phase 1 — Design:** plan schema + approval contract.
- **Phase 2 — Build:** coworker CLI + tools.
- **Phase 3 — Test & Hardening:** document tasks + guarded web + tests.
- **Phase 4 — Rollout:** Quick Actions + docs/runbooks.
- **Phase 5 — Post-Launch:** perf and security validation.

### 6.2 Detailed Task Plan (Table)
Status legend (plain fallback): Not Started | In Progress | Blocked | Done

| ID | Status | Work Item | Owner Role | Est. | Dependencies | Deliverables | Acceptance Criteria |
|---:|--------|-----------|------------|------|--------------|--------------|--------------------|
| P0.1 | Done | Define v1 tool surface primitives | PM/Eng Lead | S | — | Tool surface spec | Only allowed primitives listed; no shell tool |
| P0.2 | Done | Define policy rules + default gates | Security/Backend Eng | S | — | Policy spec | Deny-by-default, risk levels documented |
| P0.3 | Done | Define plan schema + plan-hash approval contract | Backend Eng | S | — | Plan schema doc | Plan hash enforced in approval flow |
| P1.1 | Done | Implement tool registry (allowlist + metadata) | Backend Eng | M | P0.1 | Registry module | Only allowlisted tools executable |
| P1.2 | Done | Implement policy engine + validation | Backend Eng | M | P0.2 | Policy module + tests | Blocks traversal, disallowed ops, scope violations |
| P1.3 | Done | Implement plan/preview/apply with approval token | Backend Eng | M | P0.3 | Executor + tests | Plan hash mismatch fails closed |
| P2.1 | Done | Build vertical-slice CLI: `coworker` | Backend Eng | M | P1.1,P1.2,P1.3 | CLI command | Produces plan + preview |
| P2.2 | Done | Add core file tools: read/list/propose-write/apply-write/move/rename | Backend Eng | M | P1.1 | Tool implementations | Writes require approval + rollback info |
| P2.3 | Done | Add Finder Quick Action: “Ask Yordam” | macOS Eng | S | P2.1 | Automator script | Works on selected items only |
| P3.1 | Done | Add PDF extract tool + chunking | Backend Eng | M | P2.1 | PDF pipeline | Handles large PDFs safely |
| P3.2 | Done | Add OCR fallback (optional) | Backend Eng | S | P3.1 | OCR integration | Explicit user opt-in required |
| P3.3 | Done | Add document tasks: summarize/outline/report | Backend Eng | M | P3.1 | Task recipes | Produces summary files via propose/write |
| P4.1 | Done | Add web.fetch tool (GET-only, allowlist) | Backend Eng | M | P1.2 | Web tool | Blocked unless allowlisted + consented |
| P4.2 | Done | Implement egress guard (no raw local content) | Security/Backend Eng | S | P4.1 | Egress filter | Only user-approved excerpts or summaries sent |
| P4.3 | Done | Web sanitization + size limits | Backend Eng | S | P4.1 | Sanitizer + tests | HTML stripped, size/timeouts enforced |
| P5.1 | Done | Multi-step workflow checkpoints | Backend Eng | M | P2.1 | Workflow engine | Approval per checkpoint |
| P5.2 | Done | Resumable batch operations | Backend Eng | M | P5.1 | Resume metadata | Can resume after partial failure |
| P5.3 | Done | Docs + runbooks for coworker mode | Tech Writer/Eng | S | P2.3 | Docs updates | Clear onboarding and safety docs |

### 6.3 Dependency Graph (Optional but Recommended)
- Critical path: P0.1 → P1.1 → P1.2 → P1.3 → P2.1 → P2.3.
- Parallel tracks: P3.* after P2.1; P4.* after P1.2; P5.* after P2.1.

### 6.4 Completion Checklist (Plan Hygiene)
- [x] Status column updated for tasks touched this go
- [x] "Last updated" line refreshed
- [x] Sub-plans summary updated and links valid (if sub-plans exist)
- [x] Completed sub-plans summarized and deleted (if applicable)

## 7) Testing & Quality Strategy
- **Test pyramid plan:** unit (policy + registry), integration (executor + tools), e2e (Quick Action).
- **Test data & environments:** `tests/fixtures/prompt_injection.txt`, `tests/fixtures/sample.txt`. PDF/OCR remain manual.
- **Performance testing:** 20-file plan/apply run completed; 50+ is optional.
- **Security testing:** prompt injection regression checks + deny-by-default policy cases.
- **Quality gates:** `ruff check .`, `pytest`, and a manual Quick Action e2e for doc tasks.

## 8) Rollout Plan
- **Release strategy:** opt-in via config keys.
- **Migration strategy:** none (additive features only).
- **Monitoring during rollout:** local logs + plan artifacts.
- **Rollback plan:** disable coworker/web via config flags.
- **Communication plan:** DOCS + Quick Action setup notes.

## 9) Operations
- **Runbooks:** policy denials, plan hash mismatch, OCR failures, web blocked.
- **On-call readiness:** maintainer-owned.
- **SLOs/SLIs:** optional.
- **Cost considerations:** local compute only.

## 10) Risks, Mitigations, and Contingencies

| Risk | Likelihood | Impact | Mitigation | Contingency/Trigger |
|------|------------|--------|------------|---------------------|
| Capability creep | Medium | High | strict tool surface + allowlist | refuse unapproved tools |
| Web exfiltration | Medium | High | egress guard + allowlist + consent | disable web globally |
| Prompt injection | High | Medium | policy engine + deny-by-default | block unsafe plans |

## 11) Open Questions
- Q1 (low): Do we need a configurable output folder override, or keep “next to files” only?

## 12) Sub-plans Summary
- (none)

## 13) Next Actions
- Top 5 actions to start execution immediately (by ID)
  - P5.3
  - P4.2
  - P3.3
  - P2.3
  - P1.3
