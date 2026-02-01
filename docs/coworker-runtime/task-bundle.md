# Coworker Runtime Task Bundle Layout
Last updated: 2026-01-19

## Overview
Each task gets a bundle directory containing immutable artifacts (plan/preview) and
mutable runtime artifacts (events, resume state, staging outputs).

## Directory Layout
```
<bundle_root>/
  task.json
  plan.json
  preview.txt
  events.jsonl
  resume_state.json
  scratch/
  staging/
```

## File Semantics
- `task.json`: task metadata snapshot (id, plan_hash, state, timestamps, optional metadata).
- `plan.json`: approved plan payload (canonical plan hash embedded).
- `preview.txt`: human-readable plan preview.
- `events.jsonl`: append-only runtime event log.
- `resume_state.json`: checkpoint resume metadata when pause/resume is active.
- `scratch/`: transient artifacts (inputs, temp outputs).
- `staging/`: outputs written before atomic move into final location.

## Notes
- `events.jsonl` is append-only and should survive crashes.
- `staging/` should be used for output writes before approval or finalization.
- Apply writes use a temp file in the target directory and replace atomically.
