# Yordam Agent Tutorial

This tutorial walks you through the core workflows: reorganizing a folder, undoing changes,
and rewriting text.

## 1) Install and verify

```bash
cd /Users/yordamkocatepe/Projects/yordam-agent
./scripts/install.sh
yordam-agent --help
```

Make sure Ollama is running locally (default base URL: http://localhost:11434).

## 2) Reorganize a folder (dry-run)

Start with a dry-run to see the plan:

```bash
yordam-agent reorg ~/Downloads
```

This prints proposed moves without changing files.

## 3) Preview the plan

Finder dialog preview (macOS):

```bash
yordam-agent reorg ~/Downloads --apply --preview
```

CLI preview (helpful for long lists):

```bash
yordam-agent reorg ~/Downloads --apply --preview-cli
```

If both preview flags are set, Finder preview is used.

## 4) Apply changes

```bash
yordam-agent reorg ~/Downloads --apply
```

After applying, an undo log is written to:

```
~/Downloads/.yordam-agent/undo-*.json
```

AI interaction logs (metadata only) are written to:

```
~/Downloads/.yordam-agent/ai-interactions.jsonl
```

## 5) Undo a reorg

Undo the most recent run for a folder:

```bash
yordam-agent undo --folder ~/Downloads
```

Or undo a specific log:

```bash
yordam-agent undo --id ~/Downloads/.yordam-agent/undo-20240101T000000Z.json
```

## 6) Rewrite text

Rewrite a file into a tone (creates a new file by default):

```bash
yordam-agent rewrite --input ~/Desktop/note.txt --tone "calm, friendly"
```

Rewrite and save to a specific file:

```bash
yordam-agent rewrite --input ~/Desktop/note.txt --output ~/Desktop/note.rewrite.txt
```

Rewrite in place:

```bash
yordam-agent rewrite --input ~/Desktop/note.txt --in-place
```

Rewrite from clipboard and copy back:

```bash
yordam-agent rewrite --tone "concise, professional"
```

Notes:

- If no `--input` is provided, stdin is used if piped; otherwise clipboard is used.
- Use `--copy` to always copy output to clipboard.
- For rewrite, AI logs are written to the input file's folder, or the current working
  directory when using stdin/clipboard.

## 7) Customize policy (optional)

Generate a policy file interactively:

```bash
yordam-agent policy-wizard
```

Then rerun reorg with your policy:

```bash
yordam-agent reorg ~/Downloads --apply --policy ~/.config/yordam-agent/policy.json
```

## 8) Check configuration

```bash
yordam-agent config
```

This prints the config location and current values (including the active policy path).

## 9) Finder right-click actions (optional)

Install Finder Quick Actions for right-click use:

```bash
cd /Users/yordamkocatepe/Projects/yordam-agent
./quickactions/install.sh
```

If they don't appear immediately, restart Finder:

```bash
killall Finder
```
