# Yordam Agent (local)

Local macOS helper that uses your Ollama model to:
- Reorganize folders by filetype + context (AI-assisted)
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

## Reorganize a folder

Dry-run (default):

```bash
yordam-agent reorg /path/to/folder
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

Undo last run for a folder:

```bash
yordam-agent undo --folder /path/to/folder
```

## Rewrite text

Rewrite a file into a tone (new file by default):

```bash
yordam-agent rewrite --input /path/to/file.txt --tone "calm, friendly"
```

Rewrite from clipboard (no input file) and copy back to clipboard:

```bash
yordam-agent rewrite --tone "concise, professional"
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
- `model` (default `gpt-oss:20b`)
- `rewrite_model` (default `gpt-oss:20b-instruct`)
- `max_snippet_chars` (default 4000)
- `max_files` (default 200)
- `policy_path` (default `~/.config/yordam-agent/policy.json`)
- `ai_log_path` (default `.yordam-agent/ai-interactions.jsonl`)

Override any value via env vars:
- `YORDAM_OLLAMA_BASE_URL`
- `YORDAM_MODEL`
- `YORDAM_REWRITE_MODEL`
- `YORDAM_AI_LOG_PATH`

AI interaction logs (metadata only; no prompts or responses) are appended to
`.yordam-agent/ai-interactions.jsonl` relative to the reorg target folder or, for rewrite,
the input file's folder (or current working directory if using stdin/clipboard).
Set `ai_log_path` to an absolute path to centralize logs, or to an empty string to disable.

## Finder Quick Actions

See `quickactions/README.md` for setup steps (right-click menu).

## Tests

```bash
python3 -m unittest discover -s tests
```

## Optional Scheduling (manual)

See `scripts/launchd/README.md` for an opt-in LaunchAgent template and manual run steps.
