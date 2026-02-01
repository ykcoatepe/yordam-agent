# Coworker Runtime Lifecycle
Last updated: 2026-01-19

## Task States
- **queued**: task accepted, waiting to be claimed.
- **running**: worker claimed task and is executing steps.
- **waiting_approval**: execution paused; approval required for plan hash / checkpoint.
- **completed**: task finished successfully.
- **failed**: task ended with error; error field populated.
- **canceled**: task canceled by user/CLI.

## State Transitions (Allowed)
- queued -> running
- running -> waiting_approval
- waiting_approval -> running (after approval matches)
- running -> completed
- running -> failed
- queued -> canceled
- waiting_approval -> canceled
- running -> canceled

## Transition Rules
- **Claiming**: a worker can only claim tasks in `queued` state.
- **Approval gate**: `waiting_approval` resumes only if approval matches plan hash and checkpoint (if any).
- **Failure**: errors are recorded; retry policy is out of scope for v1.
- **Cancel**: cancel is allowed from any non-terminal state; terminal states are `completed`, `failed`, `canceled`.

## Checkpoint Semantics
- Task records store `checkpoint_id` (current) and `next_checkpoint` (pending).
- When a checkpoint is hit, state flips to `waiting_approval` and `next_checkpoint` is set.
- On approval, `next_checkpoint` is cleared and state returns to `running`.

## Event Emission Strategy
- Emit an event on every state transition and on each tool call start/finish.
- Events are appended to per-task JSONL logs.
