# Yordam Agent Docs

Local macOS helper that uses your Ollama model to reorganize folders and rewrite text.
No cloud calls; everything runs against your local Ollama instance.

## Requirements

- macOS (clipboard + Finder preview rely on pbcopy/pbpaste/osascript).
- Ollama running (default base URL: http://localhost:11434).

## Install

```bash
cd /Users/yordamkocatepe/Projects/yordam-agent
./scripts/install.sh
```

Verify:

```bash
yordam-agent --help
```

## Commands

### Reorganize a folder or selected files

Dry-run (default):

```bash
yordam-agent reorg /path/to/folder
```

Reorganize selected files (all must be in the same parent folder):

```bash
yordam-agent reorg /path/to/file1 /path/to/file2
```

Apply changes:

```bash
yordam-agent reorg /path/to/folder --apply
```

Preview in Finder (dialog) before applying:

```bash
yordam-agent reorg /path/to/folder --apply --preview
```

Interactive CLI preview (paged list + confirm):

```bash
yordam-agent reorg /path/to/folder --apply --preview-cli
```

Write a plan file (JSON):

```bash
yordam-agent reorg /path/to/folder --plan-file /path/to/plan.json
```

Open a plan file after writing:

```bash
yordam-agent reorg /path/to/folder --plan-file /path/to/plan.json --open-plan
```

Open an HTML preview diagram:

```bash
yordam-agent reorg /path/to/folder --plan-file /path/to/plan.json --open-preview
```

Enable OCR fallback (if `tesseract` is installed):

```bash
yordam-agent reorg /path/to/folder --ocr
```

Ask before enabling OCR (last resort):

```bash
yordam-agent reorg /path/to/folder --ocr-ask
```

When `ocr_prompt` is enabled (default), the app will prompt for OCR only after
Spotlight text extraction fails.

Common flags:

- `--apply`: execute moves (otherwise dry-run only).
- `--recursive`: include subfolders.
- `--include-hidden`: include hidden files.
- `--max-files N`: cap number of files.
- `--max-snippet-chars N`: cap snippet chars sent to the model.
- `--preview`: Finder dialog preview (macOS only).
- `--preview-cli`: interactive terminal preview.
- `--plan-file /path/to/plan.json`: write a JSON plan.
- `--open-plan`: open the plan file after writing.
- `--open-preview`: open an HTML preview diagram.
- `--ocr`: enable OCR fallback for non-text files (requires `tesseract`).
- `--ocr-ask`: ask to enable OCR when text extraction fails.
- `--model MODEL`: override Ollama model.
- `--policy /path/to/policy.json`: override policy path.
- `--context "..."`: extra context for the AI (e.g., “organize by person name”).

If `--open-plan` or `--open-preview` is set without `--plan-file`, a plan file is created
under `<target-folder>/.yordam-agent/plan-*.json`. The preview is written alongside it as
`plan-*.html` when `--open-preview` is used.

If `--context` is provided, the AI is free to choose the best category/subcategory
scheme based on your instruction. If it can’t decide, it falls back to the default
type-based categories.

If `--context` mentions organizing by person, the tool groups files under `People/<Name>`.
If a name cannot be extracted, it uses `People/Unknown`.
If `--context` is omitted, the tool falls back to `reorg_context` in config (if set).

Notes:

- If both `--preview` and `--preview-cli` are set, Finder dialog is used.
- If `--apply` is not set, the command prints the plan and exits.

### Rename files

Rename all files in a folder (dry-run):

```bash
yordam-agent rename /path/to/folder --instruction "add date prefix"
```

Rename selected files (same parent folder):

```bash
yordam-agent rename /path/to/file1 /path/to/file2 --instruction "add suffix _final"
```

Example (remove trailing time tokens cleanly):

```bash
yordam-agent rename /path/to/folder --instruction "remove trailing time tokens like 'at HH.MM.SS' and any dangling words"
```

Preview and apply:

```bash
yordam-agent rename /path/to/folder --instruction "rename by date" --apply --preview
```

Common flags:

- `--apply`: execute renames (otherwise dry-run only).
- `--recursive`: include subfolders.
- `--include-hidden`: include hidden files.
- `--max-files N`: cap number of files.
- `--preview`: Finder dialog preview (macOS only).
- `--preview-cli`: interactive terminal preview.
- `--plan-file /path/to/plan.json`: write a JSON plan.
- `--open-plan`: open the plan file after writing.
- `--open-preview`: open an HTML preview diagram.
- `--model MODEL`: override Ollama model.
- `--policy /path/to/policy.json`: override policy path.
- `--instruction "..."`: required rename instruction for the AI.

### Undo a reorg

Undo the most recent run in a folder:

```bash
yordam-agent undo --folder /path/to/folder
```

Undo with a specific id or path:

```bash
yordam-agent undo --id /path/to/undo-20240101T000000Z.json
```

Undo logs are stored in the target folder under `.yordam-agent/undo-*.json`.

### Rewrite text

Rewrite a file into a tone (new file by default):

```bash
yordam-agent rewrite --input /path/to/file.txt --tone "calm, friendly"
```

Rewrite from clipboard and copy back to clipboard:

```bash
yordam-agent rewrite --tone "concise, professional"
```

Rewrite with explicit output:

```bash
yordam-agent rewrite --input /path/to/file.txt --output /path/to/out.txt
```

### Coworker runtime (queued tasks)

Enable runtime (default is off):

```bash
export YORDAM_COWORKER_RUNTIME_ENABLED=1
```

Submit a task:

```bash
yordam-agent coworker-runtime submit --plan /path/to/plan.json
```

Run the daemon (single worker):

```bash
yordam-agent coworker-runtime daemon
```

List or check status:

```bash
yordam-agent coworker-runtime list
yordam-agent coworker-runtime status
```

Approve a plan hash:

```bash
yordam-agent coworker-runtime approve --plan-hash <hash>
```

Rewrite in place:

```bash
yordam-agent rewrite --input /path/to/file.txt --in-place
```

Notes:

- If `--input` is omitted, stdin is used if piped; otherwise clipboard is used.
- Use `--copy` to always copy output to clipboard.
- `--model MODEL` overrides the rewrite model.

### Show configuration

```bash
yordam-agent config
```

Prints the config path, values, and whether the policy file exists.

### Policy wizard

```bash
yordam-agent policy-wizard
```

Interactive generator for a policy file. Use `--policy` to override the path.

## Files and paths

- Config: `~/.config/yordam-agent/config.json`
- Policy: `~/.config/yordam-agent/policy.json`
- Undo logs: `<target-folder>/.yordam-agent/undo-*.json`
- AI logs: `<target-folder>/.yordam-agent/ai-interactions.jsonl` (metadata only)
- Plan file: user-provided path via `--plan-file`

Relative `ai_log_path` values resolve to the reorg target folder or, for rewrite,
the input file's folder (or current working directory when using stdin/clipboard).

## Configuration keys

- `ollama_base_url` (default `http://localhost:11434`)
- `model` (default `gpt-oss:20b`)
- `model_secondary` (default `gpt-oss:20b`)
- `gpt_oss_think_level` (default `low`, accepts `low|medium|high|off`)
- `available_models` (default list, used for chooser prompts)
- `reasoning_level_models` (default list, enables think-level prompt)
- `rewrite_model` (default `gpt-oss:20b`)
- `rewrite_model_secondary` (default `gpt-oss:20b`)
- `max_snippet_chars` (default 4000)
- `max_files` (default 200)
- `policy_path` (default `~/.config/yordam-agent/policy.json`)
- `reorg_context` (default empty string)
- `ai_log_path` (default `.yordam-agent/ai-interactions.jsonl`)
- `ai_log_include_response` (default `false`)
- `ocr_enabled` (default `false`)
- `ocr_prompt` (default `true`)
- `coworker_allowed_paths` (default `[]`)
- `coworker_require_approval` (default `true`)
- `coworker_max_read_bytes` (default `200000`)
- `coworker_max_write_bytes` (default `200000`)
- `coworker_web_enabled` (default `false`)
- `coworker_web_allowlist` (default `[]`)
- `coworker_web_max_bytes` (default `200000`)
- `coworker_web_max_query_chars` (default `256`)
- `coworker_checkpoint_every_writes` (default `5`, set `0` to disable)
- `coworker_ocr_enabled` (default `false`)
- `coworker_ocr_prompt` (default `true`)

Override any value via env vars:

- `YORDAM_OLLAMA_BASE_URL`
- `YORDAM_MODEL`
- `YORDAM_MODEL_SECONDARY`
- `YORDAM_GPT_OSS_THINK_LEVEL`
- `YORDAM_REWRITE_MODEL`
- `YORDAM_REWRITE_MODEL_SECONDARY`
- `YORDAM_AI_LOG_PATH`

If the primary model fails, the secondary model is tried.
Ensure models are available in Ollama, for example:

```bash
ollama pull deepseek-r1:8b
ollama pull gpt-oss:20b
```

## Coworker (experimental)

Coworker mode generates and applies explicit plans with approval tokens.
Web access (if enabled) is GET-only, requires a per-task allowlist, and rejects extra fields or local data.
Checkpointed plans can pause mid-execution and write a resume state file for the next segment.

### Coworker specs (v1)

Tool surface (allowlisted primitives):

- `fs.read_text`
- `fs.list_dir`
- `fs.propose_write_file`
- `fs.apply_write_file`
- `fs.move`
- `fs.rename`
- `doc.extract_pdf_text`
- `web.fetch`

Policy rules (deny-by-default):

- Paths must resolve under allowed roots (`coworker_allowed_paths` + selected paths).
- Read/write sizes are capped by config (`coworker_max_read_bytes`, `coworker_max_write_bytes`).
- Writes require approvals and cannot overwrite existing files in v1.
- `web.fetch` is GET-only, requires a per-task allowlist, blocks body/payload fields, and
  requires `allow_query: true` for URLs with query strings. Query length is capped by
  `coworker_web_max_query_chars`.

Plan schema (JSON):

- `version` (int, required)
- `created_at` (UTC timestamp string, required)
- `instruction` (string, optional)
- `tool_calls` (list of `{id, tool, args}`, required)
- `checkpoints` (list of tool call ids, optional)
- `model` (string, optional)
- `gpt_oss_think_level` (string, optional)
- `plan_hash` (string, required for approvals)

Example:

```json
{
  "version": 1,
  "created_at": "20250115T120000Z",
  "instruction": "summarize selected documents",
  "tool_calls": [
    {"id": "1", "tool": "fs.propose_write_file", "args": {"path": "/tmp/a.md", "content": "..." }},
    {"id": "2", "tool": "fs.apply_write_file", "args": {"path": "/tmp/a.md", "content": "..." }}
  ],
  "checkpoints": ["2"],
  "plan_hash": "sha256:..."
}
```

Generate a plan from an instruction:

```bash
yordam-agent coworker plan --instruction "summarize these PDFs" --paths /path/to/file1.pdf /path/to/file2.pdf
```

Preview a plan (with diffs when available):

```bash
yordam-agent coworker preview --plan /path/to/coworker-plan.json --paths /path/to/file1.pdf --include-diffs
```

Approve and apply:

```bash
yordam-agent coworker approve --plan /path/to/coworker-plan.json
yordam-agent coworker apply --plan /path/to/coworker-plan.json --approval-file /path/to/coworker-plan.approval.json --paths /path/to/file1.pdf
```

Generate a summary plan (writes summaries next to the files):

```bash
yordam-agent coworker summarize --paths /path/to/file.pdf
```

Generate outline/report plans (writes next to the files):

```bash
yordam-agent coworker summarize --paths /path/to/file.pdf --task outline
yordam-agent coworker summarize --paths /path/to/file.pdf --task report
```

### Coworker demo (end-to-end)

```bash
# 1) Create a plan (LLM-driven)
yordam-agent coworker plan --instruction "summarize these files" --paths /path/to/file1.pdf /path/to/file2.pdf

# 2) Preview the plan
yordam-agent coworker preview --plan /path/to/coworker-plan.json --paths /path/to/file1.pdf /path/to/file2.pdf --include-diffs

# 3) Approve the plan (generates approval token)
yordam-agent coworker approve --plan /path/to/coworker-plan.json

# 4) Apply the plan (requires matching approval)
yordam-agent coworker apply --plan /path/to/coworker-plan.json --approval-file /path/to/coworker-plan.approval.json --paths /path/to/file1.pdf /path/to/file2.pdf
```

List checkpoints for a plan:

```bash
yordam-agent coworker checkpoints --plan /path/to/coworker-plan.json
```

Checkpoint apply (requires a checkpoint id from the plan, writes resume state):

```bash
# Approve the next checkpoint (use the id listed in plan.checkpoints)
yordam-agent coworker approve --plan /path/to/coworker-plan.json --checkpoint-id <checkpoint-id>

# Apply until checkpoint and write state
yordam-agent coworker apply --plan /path/to/coworker-plan.json --approval-file /path/to/coworker-plan.approval.json --checkpoint

# Resume next checkpoint (use the generated .state.json)
yordam-agent coworker apply --plan /path/to/coworker-plan.json --approval-file /path/to/coworker-plan.approval.json --checkpoint --resume-state /path/to/coworker-plan.state.json
```

### Coworker runbooks

- Policy denial: run `yordam-agent coworker preview --plan ... --paths ...` to see which call fails,
  then adjust paths/allowlist/config and regenerate the plan.
- Plan hash mismatch: re-run `coworker approve` after regenerating the plan; approvals are bound to
  the current plan hash.
- OCR fallback: set `coworker_ocr_enabled=true` to force OCR, or keep `coworker_ocr_prompt=true` to
  prompt only when text extraction fails.
- Web blocked: ensure `coworker_web_enabled=true`, add domains to `coworker_web_allowlist`, and include
  a per-task allowlist in the plan; add `allow_query: true` for query URLs.
- Checkpoint resume: use `coworker checkpoints` to list IDs, approve the next checkpoint, then resume
  with `--resume-state` until completion.

Example plans:

Document task (outline):

```json
{
  "version": 1,
  "created_at": "20250115T120000Z",
  "instruction": "outline selected documents",
  "tool_calls": [
    {
      "id": "doc-outline-propose",
      "tool": "fs.propose_write_file",
      "args": {
        "path": "/path/to/report.outline.md",
        "content": "# Outline: report.pdf\n\n- Section 1\n- Section 2\n"
      }
    },
    {
      "id": "doc-outline-apply",
      "tool": "fs.apply_write_file",
      "args": {
        "path": "/path/to/report.outline.md",
        "content": "# Outline: report.pdf\n\n- Section 1\n- Section 2\n"
      }
    }
  ],
  "plan_hash": "sha256:..."
}
```

Web fetch with query allowlist:

```json
{
  "version": 1,
  "created_at": "20250115T120000Z",
  "instruction": "fetch release notes",
  "tool_calls": [
    {
      "id": "web-1",
      "tool": "web.fetch",
      "args": {
        "url": "https://example.com/search?q=release+notes",
        "allowlist": ["example.com"],
        "allow_query": true,
        "max_bytes": 20000
      }
    }
  ],
  "plan_hash": "sha256:..."
}
```

## Testing & Quality

Unit tests:

```bash
ruff check .
pytest
```

Integration tests (local):

- `tests/test_coworker_executor.py` covers approval enforcement, hash mismatches, and checkpoints.
- `tests/test_coworker_policy.py` covers allowlist, deny-by-default rules, and web guards.

E2E (manual) Quick Action:

1) Install Quick Actions: `./quickactions/install.sh`
2) Right-click a couple of files in Finder -> `Yordam - Doc Task`
3) Choose `summary`, approve, and verify `*.summary.md` appears next to the files.

Test data & environments:

- `tests/fixtures/prompt_injection.txt` for prompt-injection regressions.
- `tests/fixtures/sample.txt` for summarize/outline/report smoke tests.

Performance sanity:

- Run on 50+ files and inspect plan/apply times; keep logs in `.yordam-agent/`.

Security testing:

- Ensure prompt-injection fixtures do not bypass allowlisted tools (policy should block).
- Verify approval mismatch fails closed (`tests/test_coworker_executor.py`).

## Troubleshooting

- "Preview failed: osascript not available.": Finder preview requires macOS.
- "No moves planned.": Try `--recursive`, `--include-hidden`, or increase `--max-files`.
- "No input text found.": Provide `--input`, pipe stdin, or copy text to clipboard.
- Ollama errors: ensure the model exists and the Ollama server is running.
