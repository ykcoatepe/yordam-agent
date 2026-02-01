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
- `Yordam - Rename`
- `Yordam - Coworker`
- `Yordam - Doc Task`

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

### Rename files (AI-assisted)

1) New Quick Action
2) Workflow receives: "files" in "Finder"
3) Add action: "Run Shell Script" (same settings as above)
4) Paste this script:

```sh
files=("$@")
if [ ${#files[@]} -eq 0 ]; then
  osascript -e 'display dialog "No files or folders selected." with title "Yordam Agent" buttons {"OK"} default button "OK"'
  exit 1
fi

instruction=$(osascript -e 'text returned of (display dialog "Rename instruction (required):" default answer "add date prefix or add suffix or rename by date" with title "Yordam Agent" buttons {"Cancel","Continue"} default button "Continue" cancel button "Cancel")') || exit 0
instruction="$(echo "$instruction" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
if [ -z "$instruction" ]; then
  osascript -e 'display dialog "Rename instruction is required." with title "Yordam Agent" buttons {"OK"} default button "OK"'
  exit 1
fi

if [ ${#files[@]} -eq 1 ] && [ -d "${files[0]}" ]; then
  root="${files[0]}"
else
  resolve_parent() {
    python3 - "$1" <<'PY'
import os
import sys

print(os.path.realpath(os.path.dirname(sys.argv[1])))
PY
  }
  parent="$(resolve_parent "${files[0]}")"
  for f in "${files[@]}"; do
    if [ -d "$f" ]; then
      osascript -e 'display dialog "Select a single folder OR multiple files (no mixed selection)." with title "Yordam Agent" buttons {"OK"} default button "OK"'
      exit 1
    fi
    if [ "$(resolve_parent "$f")" != "$parent" ]; then
      osascript -e 'display dialog "Selected files must be in the same folder." with title "Yordam Agent" buttons {"OK"} default button "OK"'
      exit 1
    fi
  done
  root="$parent"
fi

args=("${files[@]}")
plan_path="$root/.yordam-agent/rename-plan-$(date -u +%Y%m%dT%H%M%SZ).json"
"$HOME/bin/yordam-agent" rename "${args[@]}" --instruction "$instruction" --apply --preview --plan-file "$plan_path" --open-preview
status=$?
if [ $status -ne 0 ]; then
  osascript -e 'display dialog "Yordam rename failed. See Terminal output for details." with title "Yordam Agent" buttons {"OK"} default button "OK"'
fi
```

5) Save as: `Yordam - Rename`

### Ask Yordam (coworker plan)

1) New Quick Action
2) Workflow receives: "files" in "Finder"
3) Add action: "Run Shell Script" (same settings as above)
4) Paste this script:

```sh
files=("$@")
if [ ${#files[@]} -eq 0 ]; then
  osascript -e 'display dialog "No files or folders selected." with title "Yordam Agent" buttons {"OK"} default button "OK"'
  exit 1
fi

instruction=$(osascript -e 'text returned of (display dialog "Ask Yordam:" default answer "summarize these files" with title "Yordam Agent" buttons {"Cancel","Continue"} default button "Continue" cancel button "Cancel")') || exit 0
instruction="$(echo "$instruction" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
if [ -z "$instruction" ]; then
  osascript -e 'display dialog "Instruction is required." with title "Yordam Agent" buttons {"OK"} default button "OK"'
  exit 1
fi

if [ ${#files[@]} -eq 1 ] && [ -d "${files[0]}" ]; then
  root="${files[0]}"
else
  resolve_parent() {
    python3 - "$1" <<'PY'
import os
import sys

print(os.path.realpath(os.path.dirname(sys.argv[1])))
PY
  }
  parent="$(resolve_parent "${files[0]}")"
  for f in "${files[@]}"; do
    if [ -d "$f" ]; then
      osascript -e 'display dialog "Select a single folder OR multiple files (no mixed selection)." with title "Yordam Agent" buttons {"OK"} default button "OK"'
      exit 1
    fi
    if [ "$(resolve_parent "$f")" != "$parent" ]; then
      osascript -e 'display dialog "Selected files must be in the same folder." with title "Yordam Agent" buttons {"OK"} default button "OK"'
      exit 1
    fi
  done
  root="$parent"
fi

plan_path="$root/.yordam-agent/coworker-plan-$(date -u +%Y%m%dT%H%M%SZ).json"
"$HOME/bin/yordam-agent" coworker plan --instruction "$instruction" --paths "${files[@]}" --out "$plan_path"
exit_code=$?
if [ $exit_code -ne 0 ]; then
  osascript -e 'display dialog "Yordam coworker plan failed. See Terminal output for details." with title "Yordam Agent" buttons {"OK"} default button "OK"'
  exit 1
fi

summary_file="$(mktemp)"
checkpoint_id="$(python3 - "$plan_path" "$summary_file" <<'PY'
import json
import sys

plan_path = sys.argv[1]
summary_path = sys.argv[2]

with open(plan_path, "r", encoding="utf-8") as fh:
    plan = json.load(fh)

calls = plan.get("tool_calls", [])
writes = sum(1 for call in calls if call.get("tool") in {"fs.apply_write_file", "fs.move", "fs.rename"})
web_calls = sum(1 for call in calls if call.get("tool") == "web.fetch")
checkpoints = plan.get("checkpoints", [])
checkpoint_id = str(checkpoints[0]) if checkpoints else ""

summary = (
    f"Plan hash: {plan.get('plan_hash', '')}\n"
    f"Tool calls: {len(calls)}\n"
    f"Writes: {writes}\n"
    f"Web calls: {web_calls}\n"
    f"Checkpoints: {len(checkpoints)}"
)

with open(summary_path, "w", encoding="utf-8") as out:
    out.write(summary)

print(checkpoint_id)
PY
)"

summary="$(cat "$summary_file")"
rm -f "$summary_file"
safe_summary="$(printf "%s" "$summary" | sed 's/"/\\"/g')"

choice=$(osascript -e "button returned of (display dialog \"Plan ready:\\n${safe_summary}\" with title \"Yordam Agent\" buttons {\"Cancel\",\"Open Plan\",\"Apply\"} default button \"Apply\" cancel button \"Cancel\")") || exit 0
if [ "$choice" = "Open Plan" ]; then
  open "$plan_path"
  exit 0
fi
if [ "$choice" != "Apply" ]; then
  exit 0
fi

approval_path="${plan_path%.json}.approval.json"
if [ -n "$checkpoint_id" ]; then
  "$HOME/bin/yordam-agent" coworker approve --plan "$plan_path" --approval-file "$approval_path" --checkpoint-id "$checkpoint_id"
  "$HOME/bin/yordam-agent" coworker apply --plan "$plan_path" --approval-file "$approval_path" --paths "${files[@]}" --checkpoint
else
  "$HOME/bin/yordam-agent" coworker approve --plan "$plan_path" --approval-file "$approval_path"
  "$HOME/bin/yordam-agent" coworker apply --plan "$plan_path" --approval-file "$approval_path" --paths "${files[@]}"
fi
exit_code=$?
if [ $exit_code -ne 0 ]; then
  osascript -e 'display dialog "Yordam coworker apply failed. See Terminal output for details." with title "Yordam Agent" buttons {"OK"} default button "OK"'
fi
```

5) Save as: `Yordam - Coworker`

### Doc Task (summary/outline/report)

1) New Quick Action
2) Workflow receives: "files" in "Finder"
3) Add action: "Run Shell Script" (same settings as above)
4) Paste this script:

```sh
files=("$@")
if [ ${#files[@]} -eq 0 ]; then
  osascript -e 'display dialog "No files selected." with title "Yordam Agent" buttons {"OK"} default button "OK"'
  exit 1
fi

task=$(osascript -e 'choose from list {"summary","outline","report"} with title "Yordam Agent" with prompt "Document task:" default items {"summary"}') || exit 0
task="$(printf "%s" "$task" | tr -d '\r')"
if [ "$task" = "false" ] || [ -z "$task" ]; then
  exit 0
fi

resolve_parent() {
  python3 - "$1" <<'PY'
import os
import sys

import urllib.parse

raw = sys.argv[1]
if raw.startswith("file://"):
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme == "file":
        raw = urllib.parse.unquote(parsed.path)
raw = os.path.expanduser(raw)
print(os.path.realpath(os.path.dirname(raw)))
PY
}
normalize_path() {
  python3 - "$1" <<'PY'
import os
import sys
import urllib.parse

raw = sys.argv[1]
if raw.startswith("file://"):
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme == "file":
        raw = urllib.parse.unquote(parsed.path)
raw = os.path.expanduser(raw)
print(os.path.realpath(raw))
PY
}
normalized_files=()
for f in "${files[@]}"; do
  normalized_files+=("$(normalize_path "$f")")
done
parent="$(resolve_parent "${normalized_files[0]}")"
for f in "${files[@]}"; do
  nf="$(normalize_path "$f")"
  if [ -d "$nf" ]; then
    osascript -e 'display dialog "Select files only (no folders)." with title "Yordam Agent" buttons {"OK"} default button "OK"'
    exit 1
  fi
done

root="$parent"
plan_path="$root/.yordam-agent/coworker-plan-$(date -u +%Y%m%dT%H%M%SZ).json"
"$HOME/bin/yordam-agent" coworker summarize --paths "${normalized_files[@]}" --task "$task" --out "$plan_path"
exit_code=$?
if [ $exit_code -ne 0 ]; then
  osascript -e 'display dialog "Yordam doc task plan failed. See Terminal output for details." with title "Yordam Agent" buttons {"OK"} default button "OK"'
  exit 1
fi

summary_file="$(mktemp)"
checkpoint_id="$(python3 - "$plan_path" "$summary_file" <<'PY'
import json
import sys

plan_path = sys.argv[1]
summary_path = sys.argv[2]

with open(plan_path, "r", encoding="utf-8") as fh:
    plan = json.load(fh)

calls = plan.get("tool_calls", [])
writes = sum(1 for call in calls if call.get("tool") in {"fs.apply_write_file", "fs.move", "fs.rename"})
web_calls = sum(1 for call in calls if call.get("tool") == "web.fetch")
checkpoints = plan.get("checkpoints", [])
checkpoint_id = str(checkpoints[0]) if checkpoints else ""

summary = (
    f"Plan hash: {plan.get('plan_hash', '')}\n"
    f"Tool calls: {len(calls)}\n"
    f"Writes: {writes}\n"
    f"Web calls: {web_calls}\n"
    f"Checkpoints: {len(checkpoints)}"
)

with open(summary_path, "w", encoding="utf-8") as out:
    out.write(summary)

print(checkpoint_id)
PY
)"

summary="$(cat "$summary_file")"
rm -f "$summary_file"
summary="Task: ${task}\n${summary}"
safe_summary="$(printf "%s" "$summary" | sed 's/"/\\"/g')"

choice=$(osascript -e "button returned of (display dialog \"Plan ready:\\n${safe_summary}\" with title \"Yordam Agent\" buttons {\"Cancel\",\"Open Plan\",\"Apply\"} default button \"Apply\" cancel button \"Cancel\")") || exit 0
if [ "$choice" = "Open Plan" ]; then
  open "$plan_path"
  exit 0
fi
if [ "$choice" != "Apply" ]; then
  exit 0
fi

approval_path="${plan_path%.json}.approval.json"
if [ -n "$checkpoint_id" ]; then
  "$HOME/bin/yordam-agent" coworker approve --plan "$plan_path" --approval-file "$approval_path" --checkpoint-id "$checkpoint_id"
  "$HOME/bin/yordam-agent" coworker apply --plan "$plan_path" --approval-file "$approval_path" --paths "${normalized_files[@]}" --checkpoint
else
  "$HOME/bin/yordam-agent" coworker approve --plan "$plan_path" --approval-file "$approval_path"
  "$HOME/bin/yordam-agent" coworker apply --plan "$plan_path" --approval-file "$approval_path" --paths "${normalized_files[@]}"
fi
exit_code=$?
if [ $exit_code -ne 0 ]; then
  osascript -e 'display dialog "Yordam doc task apply failed. See Terminal output for details." with title "Yordam Agent" buttons {"OK"} default button "OK"'
fi
```

Notes:
- Files can be in different folders; the plan file is written next to the first selected file.

5) Save as: `Yordam - Doc Task`
