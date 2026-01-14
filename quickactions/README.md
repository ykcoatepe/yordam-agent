# Finder Quick Actions

## Install (recommended)

Run the installer to add ready-to-use Finder right-click actions:

```bash
cd /Users/yordamkocatepe/Projects/yordam-agent
./quickactions/install.sh
```

This installs:
- `Yordam - Reorg (Dry Run)`
- `Yordam - Reorg (Apply + Preview)`
- `Yordam - Rewrite`

If they do not appear, restart Finder:

```bash
killall Finder
```

## Manual setup

These Quick Actions let you right-click in Finder and run the agent.

### Reorganize folder (dry-run by default)

1) Open Automator
2) New Document -> Quick Action
3) Workflow receives: "folders" in "Finder"
4) Add action: "Run Shell Script"
   - Shell: `/bin/zsh`
   - Pass input: `as arguments`
5) Paste this script:

```sh
for f in "$@"; do
  "$HOME/bin/yordam-agent" reorg "$f"
done
```

6) Save as: `Yordam - Reorg (Dry Run)`

If you want an Apply action, duplicate and change the command to:

```sh
"$HOME/bin/yordam-agent" reorg "$f" --apply
```

Optional: add a Finder dialog preview before applying:

```sh
"$HOME/bin/yordam-agent" reorg "$f" --apply --preview
```

### Rewrite text files

1) New Quick Action
2) Workflow receives: "files" in "Finder"
3) Add action: "Run Shell Script" (same settings as above)
4) Paste this script (prompts for tone):

```sh
tone=$(osascript -e 'text returned of (display dialog "Rewrite tone:" default answer "clear, friendly, professional")')
for f in "$@"; do
  "$HOME/bin/yordam-agent" rewrite --input "$f" --tone "$tone"
done
```

5) Save as: `Yordam - Rewrite`

Tip: The rewrite command creates a new file next to the original. Use `--in-place` to overwrite.
