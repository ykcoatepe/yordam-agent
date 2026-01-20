# Agent Loop Design (Discovery -> Commit)
Last updated: 2026-01-20

## Goal
Define a safe, resumable agent loop that turns a user request into a plan, approval,
execution, and optional commit while preserving the coworker safety contract.

## Loop Stages
1) **Discovery**: normalize user intent and gather context (paths, repo, constraints).
2) **Plan**: produce `plan.json` + `plan_hash` with explicit tool calls.
3) **Preview**: generate human-readable preview (diffs + summary).
4) **Approval**: require plan hash approval (and checkpoint approvals if needed).
5) **Apply**: execute tool calls with policy enforcement + checkpoints.
6) **Verify**: optional post-checks (tests, lint, diff sanity).
7) **Summarize**: write an outcome summary + next steps to events.
8) **Commit (optional)**: produce or apply a git commit if allowed.

## Runtime Integration
- Each loop iteration is a runtime task with:
  - `task.json` snapshot (state, plan_hash, metadata).
  - `plan.json` + `preview.md` in bundle.
  - `events.jsonl` with stage-level events.
- Checkpoints map to stages (e.g., after Plan, after Preview, before Apply).

## Data Model Extensions (future)
- `tasks.metadata.stage`: current loop stage string.
- `tasks.metadata.intent`: normalized user request.
- `tasks.metadata.repo_root`: if a repo is in scope.
- New optional table `task_checks` for verification results.

## Safety Invariants
- Plan hash is immutable once approved.
- Policy checks run before every tool invocation.
- No execution without explicit approval tokens.
- File writes remain bounded and non-destructive.

## Open Questions
- Should verification results gate commit by default?
- How to store/retain redacted context for audit without leaking secrets?

## Rollout Plan (Phase 5)
- Start with plan/preview/approval/apply only (no commit).
- Add verify step with explicit flag.
- Add commit stage behind config flag + explicit approval.
