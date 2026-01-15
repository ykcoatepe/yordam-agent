# Yordam Agent (local)

Local macOS helper that uses your Ollama model to:
- Reorganize folders by filetype + context (AI-assisted)
- Rename files via AI instructions (user-confirmed)
- Rewrite text to a desired tone

No cloud. Runs against your local Ollama instance.

## Quick start

1) Install command

```bash
cd /Users/yordamkocatepe/Projects/yordam-agent
./scripts/install.sh
```

2) Verify

```bash
yordam-agent --help
```

## Reorganize a folder or selected files

Dry-run (default):

```bash
yordam-agent reorg /path/to/folder
```

Reorganize selected files (same parent folder):

```bash
yordam-agent reorg /path/to/file1 /path/to/file2
```

Apply changes:

```bash
yordam-agent reorg /path/to/folder --apply
```

Preview in a Finder dialog before applying:

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

Open the plan file after writing:

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

With `--open-plan` or `--open-preview` and no `--plan-file`, a plan is created under
`/path/to/folder/.yordam-agent/plan-*.json`. The preview is written alongside it as
`plan-*.html` when `--open-preview` is used.

Add extra context for the AI:

```bash
yordam-agent reorg /path/to/folder --context "organize by person name"
```

If `--context` is provided, the AI is free to choose the best category/subcategory
scheme based on your instruction. If it can’t decide, it falls back to default
type-based categories.

If `--context` mentions organizing by person, the tool groups files under `People/<Name>`.
If a name cannot be extracted, it uses `People/Unknown`.
If `--context` is omitted, the tool uses `reorg_context` from config (if set).

Undo last run for a folder:

```bash
yordam-agent undo --folder /path/to/folder
```

## Documents organizer (sentinel for ~/Documents)

Run the Documents organizer once (uses its own config and rules):

```bash
yordam-agent documents
```

Config (auto-created, migrates from `~/Projects/DocumentsOrganizer/config.json` if present):

```
~/.config/yordam-agent/documents-organizer.json
```

Install the LaunchAgent watcher (triggers on new files in `~/Documents`):

```bash
./scripts/install-documents-organizer.sh
```

Logs are written to:

```
~/Documents/Logs.nosync/organizer.log
~/Documents/Logs.nosync/organizer.error.log
```

You can add extra AI steering with `ai_context` in the documents config file.
If needed, set `ai_backend` to `cli` (uses `ollama run`) or keep `http` (default, uses
the Ollama HTTP API). `ollama_base_url` and `ai_timeout_seconds` are supported there too.

## Rewrite text

Rewrite a file into a tone (new file by default):

```bash
yordam-agent rewrite --input /path/to/file.txt --tone "calm, friendly"
```

Rewrite from clipboard (no input file) and copy back to clipboard:

```bash
yordam-agent rewrite --tone "concise, professional"
```

## Rename files (AI-assisted)

Rename all files in a folder:

```bash
yordam-agent rename /path/to/folder --instruction "add date prefix"
```

Rename selected files (same parent folder):

```bash
yordam-agent rename /path/to/file1 /path/to/file2 --instruction "add suffix _final"
```

Preview and apply:

```bash
yordam-agent rename /path/to/folder --instruction "rename by date" --apply --preview
```

## Policy (rules + ignores)

Policy file (auto-created):

```
~/.config/yordam-agent/policy.json
```

Example:

```json
{
  "ignore_patterns": ["node_modules", ".git", "*.tmp"],
  "extension_overrides": {
    ".pdf": "Documents",
    ".psd": {"category": "Design", "subcategory": "Assets"}
  },
  "type_group_overrides": {
    "Image": "Images"
  },
  "name_contains_rules": [
    {"contains": "invoice", "category": "Finance"},
    {"contains": "tax", "category": "Finance", "subcategory": "Taxes"}
  ]
}
```

Interactive policy wizard:

```bash
yordam-agent policy-wizard
```

## Configuration

Config file (auto-created on first run):

```
~/.config/yordam-agent/config.json
```

Keys:
- `ollama_base_url` (default `http://localhost:11434`)
- `model` (default `deepseek-r1:8b`)
- `model_secondary` (default `gpt-oss:20b`)
- `rewrite_model` (default `deepseek-r1:8b`)
- `rewrite_model_secondary` (default `gpt-oss:20b`)
- `max_snippet_chars` (default 4000)
- `max_files` (default 200)
- `policy_path` (default `~/.config/yordam-agent/policy.json`)
- `reorg_context` (default empty string)
- `ai_log_path` (default `.yordam-agent/ai-interactions.jsonl`)
- `ai_log_include_response` (default `false`)
- `ocr_enabled` (default `false`)
- `ocr_prompt` (default `true`)

Override any value via env vars:
- `YORDAM_OLLAMA_BASE_URL`
- `YORDAM_MODEL`
- `YORDAM_MODEL_SECONDARY`
- `YORDAM_REWRITE_MODEL`
- `YORDAM_REWRITE_MODEL_SECONDARY`
- `YORDAM_AI_LOG_PATH`

If the primary model fails, the secondary model is tried.
Ensure models are available in Ollama, for example:

```bash
ollama pull deepseek-r1:8b
ollama pull gpt-oss:20b
```

AI interaction logs (metadata only; no prompts or responses) are appended to
`.yordam-agent/ai-interactions.jsonl` relative to the reorg target folder or, for rewrite,
the input file's folder (or current working directory if using stdin/clipboard).
Set `ai_log_path` to an absolute path to centralize logs, or to an empty string to disable.

## Finder Quick Actions

See `quickactions/README.md` for setup steps (single menu for folder or file selection).

## Tests

```bash
python3 -m unittest discover -s tests
```

## Optional Scheduling (manual)

See `scripts/launchd/README.md` for an opt-in LaunchAgent template and manual run steps.
