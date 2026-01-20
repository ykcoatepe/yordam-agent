# Coworker Runtime Schema (SQLite)
Last updated: 2026-01-19

## Database File
- Default location: `~/.config/yordam-agent/coworker/tasks.db`

## Migrations
- Versioned migrations in `schema_migrations`.
- Current schema version: **1**.

## Tables

### schema_migrations
Tracks applied migrations.
- `version` INTEGER PRIMARY KEY
- `applied_at` TEXT NOT NULL (UTC timestamp)

### tasks
Durable task lifecycle state.
- `id` TEXT PRIMARY KEY
- `state` TEXT NOT NULL
- `created_at` TEXT NOT NULL
- `updated_at` TEXT NOT NULL
- `plan_hash` TEXT NOT NULL
- `plan_path` TEXT NOT NULL
- `bundle_path` TEXT NOT NULL
- `current_step` INTEGER NOT NULL DEFAULT 0
- `checkpoint_id` TEXT
- `next_checkpoint` TEXT
- `locked_by` TEXT
- `locked_at` TEXT
- `error` TEXT
- `metadata_json` TEXT

Indexes:
- `tasks_state_idx` on `state`
- `tasks_plan_hash_idx` on `plan_hash`

### approvals
Recorded approvals for plan hash and optional checkpoint.
- `id` TEXT PRIMARY KEY
- `plan_hash` TEXT NOT NULL
- `checkpoint_id` TEXT
- `approved_at` TEXT NOT NULL
- `approved_by` TEXT NOT NULL

Indexes:
- `approvals_lookup_idx` on `(plan_hash, checkpoint_id)`

## Notes
- Timestamps are stored in UTC format: `YYYYMMDDTHHMMSSZ`.
- `metadata_json` stores optional JSON-encoded payloads.
