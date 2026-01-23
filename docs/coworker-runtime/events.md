# Coworker Runtime Event Log (JSONL)
Last updated: 2026-01-19

## Format
- One JSON object per line.
- UTF-8 encoded.
- Append-only per task (stored at `task_bundle/events.jsonl`).

## Required Fields
- `ts`: UTC timestamp (`YYYYMMDDTHHMMSSZ`).
- `task_id`: task id.
- `event`: event name (see below).
- `state`: task state after the event (if applicable).

## Optional Fields
- `message`: human-readable note.
- `tool`: tool name when event relates to a tool call.
- `tool_call_id`: id from plan tool_calls.
- `checkpoint_id`: checkpoint involved (if any).
- `error`: error string for failures.
- `metadata`: arbitrary JSON payload.

## Event Names
- `task_created`
- `task_queued`
- `task_claimed`
- `task_state_changed`
- `task_waiting_approval`
- `task_resumed`
- `task_completed`
- `task_failed`
- `task_canceled`
- `tool_call_started`
- `tool_call_finished`

## Example
{"ts":"20260119T101530Z","task_id":"tsk_123","event":"task_state_changed","state":"running"}
{"ts":"20260119T101531Z","task_id":"tsk_123","event":"tool_call_started","state":"running","tool":"fs.read_text","tool_call_id":"1"}
{"ts":"20260119T101532Z","task_id":"tsk_123","event":"tool_call_finished","state":"running","tool":"fs.read_text","tool_call_id":"1"}
