# Coworker Runtime CLI Contract
Last updated: 2026-01-20

## Commands
- `coworker-runtime submit --plan <path> [--bundle-root <dir>] [--metadata <json>]`
- `coworker-runtime status [--state <state>]`
- `coworker-runtime list [--state <state>]`
- `coworker-runtime logs --task <id>`
- `coworker-runtime approve --plan-hash <hash> [--checkpoint-id <id>] [--approved-by <name>]`
- `coworker-runtime cancel --task <id>`
- `coworker-runtime daemon [--worker-id <id>] [--once]`
- `coworker-runtime daemon [--worker-id <id>] [--workers <n>] [--once] [--state-dir <dir>]`
- `coworker-runtime print-plist [--label <label>] [--program <path>] [--state-dir <dir>]`

## Semantics
- `submit`: creates a task record and bundle; task starts in `queued`.
- `daemon`: claims queued tasks and executes them; pauses on approvals.
- `approve`: records approval for plan hash + optional checkpoint.
- `cancel`: moves task to `canceled` from a non-terminal state.
- `logs`: tails events.jsonl for a task.
- `print-plist`: emits a LaunchAgent plist for running the daemon.
- Runtime commands are blocked unless `coworker_runtime_enabled` is true.

## Exit Codes
- 0: success
- 1: validation error / policy error
- 2: task not found
