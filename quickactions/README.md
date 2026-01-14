# Finder Quick Actions

## Install (recommended)

Run the installer to add ready-to-use Finder right-click actions:

```bash
cd /Users/yordamkocatepe/Projects/yordam-agent
./quickactions/install.sh
```

This installs:
- `Yordam - Reorg`
- `Yordam - Rewrite`

If they do not appear, restart Finder:

```bash
killall Finder
```

## Manual setup

These Quick Actions let you right-click in Finder and run the agent.

### Reorganize (single folder OR selected files)

1) Open Automator
2) New Document -> Quick Action
3) Workflow receives: "files" in "Finder"
4) Add action: "Run Shell Script"
   - Shell: `/bin/zsh`
   - Pass input: `as arguments`
5) Paste this script:

```sh
context=$(osascript -e 'text returned of (display dialog "Reorg context (optional):" default answer "" with title "Yordam Agent" buttons {"Cancel","Continue"} default button "Continue" cancel button "Cancel")') || exit 0
if [ -n "$context" ]; then
  set -- "$@" --context "$context"
fi
root="$(dirname "$1")"
plan_path="$root/.yordam-agent/plan-$(date -u +%Y%m%dT%H%M%SZ).json"
"$HOME/bin/yordam-agent" reorg "$@" --apply --preview --plan-file "$plan_path" --open-plan
status=$?
if [ $status -ne 0 ]; then
  osascript -e 'display dialog "Yordam reorg failed. Select files from one folder." with title "Yordam Agent" buttons {"OK"} default button "OK"'
fi
```

6) Save as: `Yordam - Reorg`

Notes:
- You can right-click a single folder **or** select multiple files.
- Selected files must share the same parent folder (no mixed folder+file selection).
- The workflow writes the full plan JSON and opens an HTML preview diagram.
- If text extraction fails, it will ask whether to enable OCR (slower).

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
