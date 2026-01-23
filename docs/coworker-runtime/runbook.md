# Coworker Runtime Runbook
Last updated: 2026-01-20

## Start/Stop
- Start daemon (single worker):
  - `yordam-agent coworker-runtime daemon`
- Stop daemon: Ctrl+C
- Optional LaunchAgent plist:
  - `yordam-agent coworker-runtime print-plist > ~/Library/LaunchAgents/com.yordam.agent.coworker-runtime.plist`

## Worker Count
- Configure `coworker_runtime_workers` in config or use `--workers` on the daemon.

## Enable Runtime
- Set `coworker_runtime_enabled` to true in config or export:
  - `export YORDAM_COWORKER_RUNTIME_ENABLED=1`

## State Directory Override
- Config: `coworker_runtime_state_dir`
- CLI: `--state-dir /path/to/state`

## Submit a Task
- `yordam-agent coworker-runtime submit --plan /path/to/plan.json`

## Approvals
- Approve a plan hash:
  - `yordam-agent coworker-runtime approve --plan-hash <hash>`
- Approve a checkpoint:
  - `yordam-agent coworker-runtime approve --plan-hash <hash> --checkpoint-id <id>`

## Stuck in waiting_approval
1) Verify approval recorded for the plan hash (+ checkpoint id).
2) Run `daemon --once` to resume if approved.

## Cancel a Task
- `yordam-agent coworker-runtime cancel --task <id>`

## Lock Conflicts
- If tasks stay queued due to lock conflicts, check `state_dir/locks/`.
- Lock files include `task_id` and `owner` for manual inspection.
- Only remove lock files for tasks that are canceled/failed.

## Logs
- `yordam-agent coworker-runtime logs --task <id>`

## Recovery
- Task state is stored in `tasks.db` under the runtime state dir.
- Bundle artifacts live in `state_dir/bundles/<task_id>/`.
