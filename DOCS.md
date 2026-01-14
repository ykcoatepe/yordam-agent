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
- `rewrite_model` (default `gpt-oss:20b-instruct`)
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
- `YORDAM_REWRITE_MODEL`
- `YORDAM_AI_LOG_PATH`

## Troubleshooting

- "Preview failed: osascript not available.": Finder preview requires macOS.
- "No moves planned.": Try `--recursive`, `--include-hidden`, or increase `--max-files`.
- "No input text found.": Provide `--input`, pipe stdin, or copy text to clipboard.
- Ollama errors: ensure the model exists and the Ollama server is running.
