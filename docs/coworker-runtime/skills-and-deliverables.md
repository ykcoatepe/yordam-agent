# Skills + Deliverables Design
Last updated: 2026-01-20

## Goal
Define a minimal, typed skill system that declares inputs, outputs, and guardrails
without expanding the existing tool surface.

## Skill Definition (draft)
Each skill is a JSON object with:
- `id`: stable identifier (e.g., `docs.summarize`).
- `description`: one-line summary for planners.
- `inputs`: typed parameters (string/number/enum/path list).
- `outputs`: declared deliverables (files or reports).
- `tools`: allowed tool IDs from the registry.
- `policy_overrides`: optional tighter limits (never broader than global policy).
- `checks`: optional validation steps (regexes, file existence, schema).

## Deliverable Types
- `file`: a concrete file path (e.g., summary markdown).
- `plan`: plan.json + preview artifacts.
- `report`: structured JSON or markdown summary.
- `patch`: diff output (when git is available).

## Validation Rules
- All outputs must be under allowed roots.
- Tool calls must be in the skill's allowlist.
- Output size limits enforced per policy.
- Deliverables must be declared up front.

## Example (conceptual)
```json
{
  "id": "docs.summarize",
  "description": "Summarize selected documents into a report.",
  "inputs": {"tone": "string", "max_words": "number"},
  "outputs": [{"type": "file", "path": "summary.md"}],
  "tools": ["doc.extract_text", "doc.summarize", "fs.write_text"],
  "checks": [{"type": "regex", "path": "summary.md", "pattern": "^# Summary"}]
}
```

## Future Work
- Skill registry discovery + per-skill templates.
- Skill-level test fixtures.
- UI surfacing for available skills.
