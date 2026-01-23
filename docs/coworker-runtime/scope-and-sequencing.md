# Coworker Runtime Scope + Sequencing
Last updated: 2026-01-19

## Scope (Integrated)
### In Scope
- Existing coworker plan -> preview -> approve -> apply flow (unchanged).
- Durable runtime: SQLite task store, per-task bundle, daemon worker, runtime CLI.
- Approval storage and resume (plan hash + checkpoints).
- JSONL events + runbooks.

### Out of Scope
- Shell execution tool.
- Cloud LLM calls or remote execution.
- SwiftUI/menubar UI in v1.
- Automatic launchd install (optional print-plist only).

### Constraints
- Deny-by-default policy enforcement.
- No destructive ops (delete/overwrite) in v1.
- No raw local content sent to web tools.

## Sequencing (High-Level)
1) **Discovery/Alignment**
   - Confirm integrated scope and runtime lifecycle.
2) **Design**
   - Task store schema, event log format, CLI contract, I/O hardening spec.
3) **Build**
   - Task store + migrations.
   - Bundle writer + daemon loop + runtime CLI.
   - Approval resume integration + staging/atomic outputs.
4) **Test & Hardening**
   - Crash/restart recovery, cancel semantics, config overrides, locks.
5) **Rollout**
   - Feature flag + docs/runbooks + optional print-plist.

## Dependencies
- Runtime CLI depends on schema + task store.
- Daemon loop depends on task store and bundle writer.
- Approval resume depends on daemon loop and approval storage.
