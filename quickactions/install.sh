#!/bin/sh
set -e

BIN_PATH="$HOME/bin/yordam-agent"
SERVICES_DIR="$HOME/Library/Services"
TEMPLATE_INFO="/System/Library/Services/Show Map.workflow/Contents/Info.plist"
TEMPLATE_WFLOW="/System/Library/Services/Show Map.workflow/Contents/Resources/document.wflow"
TEMPLATE_VERSION="/System/Library/Services/Show Map.workflow/Contents/version.plist"

if [ ! -x "$BIN_PATH" ]; then
  echo "yordam-agent not found at $BIN_PATH"
  echo "Run ./scripts/install.sh first."
  exit 1
fi

if [ ! -f "$TEMPLATE_INFO" ] || [ ! -f "$TEMPLATE_WFLOW" ]; then
  echo "Automator template files not found. This script requires macOS Automator."
  exit 1
fi

mkdir -p "$SERVICES_DIR"

cleanup_legacy_workflows() {
  for legacy in \
    "$SERVICES_DIR/Yordam - Reorg (Dry Run).workflow" \
    "$SERVICES_DIR/Yordam - Reorg (Apply + Preview).workflow" \
    "$SERVICES_DIR/Yordam - Reorg Selected Files.workflow"
  do
    if [ -d "$legacy" ]; then
      rm -r "$legacy"
    fi
  done
}

cleanup_legacy_workflows

install_workflow() {
  name="$1"
  bundle_id="$2"
  send_types="$3"
  input_type="$4"
  command="$5"
  workflow_dir="$SERVICES_DIR/${name}.workflow"

  COMMAND="$command" python3 - "$name" "$bundle_id" "$send_types" "$input_type" "$workflow_dir" "$TEMPLATE_INFO" "$TEMPLATE_WFLOW" "$TEMPLATE_VERSION" <<'PY'
import os
import plistlib
import sys
import uuid
from pathlib import Path

name, bundle_id, send_types, input_type, workflow_dir, template_info, template_wflow, template_version = sys.argv[1:9]
command = os.environ.get("COMMAND", "")

workflow_dir = Path(workflow_dir)
contents_dir = workflow_dir / "Contents"
resources_dir = contents_dir / "Resources"
resources_dir.mkdir(parents=True, exist_ok=True)

with open(template_info, "rb") as f:
    info = plistlib.load(f)

info["CFBundleIdentifier"] = bundle_id
info["CFBundleName"] = name
info["CFBundleShortVersionString"] = "1.0"
info["CFBundleDevelopmentRegion"] = "en_US"

services = info.get("NSServices") or [{}]
info["NSServices"] = services
service = services[0]
service["NSMenuItem"] = {"default": name}
service["NSMessage"] = "runWorkflowAsService"
service.pop("NSRequiredContext", None)
service.pop("NSSendTypes", None)
service["NSSendFileTypes"] = [s for s in send_types.split(",") if s]

with open(contents_dir / "Info.plist", "wb") as f:
    plistlib.dump(info, f)

with open(template_wflow, "rb") as f:
    workflow = plistlib.load(f)

action = workflow["actions"][0]["action"]
action["AMAccepts"] = {
    "Container": "List",
    "Optional": False,
    "Types": ["com.apple.cocoa.path"],
}
action["AMProvides"] = {
    "Container": "List",
    "Types": ["com.apple.cocoa.string"],
}

params = action.get("ActionParameters", {})
params["COMMAND_STRING"] = command
params["CheckedForUserDefaultShell"] = True
params["inputMethod"] = 1
params["shell"] = "/bin/zsh"
params["source"] = ""
action["ActionParameters"] = params

for key in ("InputUUID", "OutputUUID", "UUID"):
    action[key] = str(uuid.uuid4()).upper()

workflow["workflowMetaData"] = {
    "serviceApplicationBundleID": "com.apple.finder",
    "serviceApplicationPath": "/System/Library/CoreServices/Finder.app",
    "serviceInputTypeIdentifier": input_type,
    "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
    "serviceProcessesInput": 0,
    "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
}

with open(resources_dir / "document.wflow", "wb") as f:
    plistlib.dump(workflow, f)

try:
    with open(template_version, "rb") as f:
        version = plistlib.load(f)
    with open(contents_dir / "version.plist", "wb") as f:
        plistlib.dump(version, f)
except FileNotFoundError:
    pass
PY
}

reorg_files=$(cat <<'EOF'
files=("$@")
if [ ${#files[@]} -eq 0 ]; then
  osascript -e 'display dialog "No files or folders selected." with title "Yordam Agent" buttons {"OK"} default button "OK"'
  exit 1
fi

context=$(osascript -e 'text returned of (display dialog "Reorg context (optional):" default answer "" with title "Yordam Agent" buttons {"Cancel","Continue"} default button "Continue" cancel button "Cancel")') || exit 0

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
if [ -n "$context" ]; then
  args+=("--context" "$context")
fi

plan_path="$root/.yordam-agent/plan-$(date -u +%Y%m%dT%H%M%SZ).json"
"$HOME/bin/yordam-agent" reorg "${args[@]}" --apply --preview --plan-file "$plan_path" --open-preview --ocr-ask
exit_code=$?
if [ $exit_code -ne 0 ]; then
  osascript -e 'display dialog "Yordam reorg failed. See Terminal output for details." with title "Yordam Agent" buttons {"OK"} default button "OK"'
fi
EOF
)

rewrite_prompt=$(cat <<'EOF'
tone=$(osascript -e 'text returned of (display dialog "Rewrite tone:" default answer "clear, friendly, professional")')
for f in "$@"; do
  "$HOME/bin/yordam-agent" rewrite --input "$f" --tone "$tone"
done
EOF
)

rename_prompt=$(cat <<'EOF'
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

if [ ${#files[@]} -eq 1 ] && [ -d "${files[1]}" ]; then
  root="${files[1]}"
else
  resolve_parent() {
    python3 - "$1" <<'PY'
import os
import sys

print(os.path.realpath(os.path.dirname(sys.argv[1])))
PY
  }
  parent="$(resolve_parent "${files[1]}")"
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
"$HOME/bin/yordam-agent" rename "${args[@]}" --instruction "$instruction" --apply --preview --plan-file "$plan_path" --open-preview > /tmp/yordam_debug.log 2>&1
exit_code=$?
if [ $exit_code -ne 0 ]; then
  osascript -e 'display dialog "Yordam rename failed. See Terminal output for details." with title "Yordam Agent" buttons {"OK"} default button "OK"'
fi
EOF
)

co_worker_prompt=$(cat <<'EOF'
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

if [ ${#files[@]} -eq 1 ] && [ -d "${files[1]}" ]; then
  root="${files[1]}"
else
  resolve_parent() {
    python3 - "$1" <<'PY'
import os
import sys

print(os.path.realpath(os.path.dirname(sys.argv[1])))
PY
  }
  parent="$(resolve_parent "${files[1]}")"
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
EOF
)

doc_task_prompt=$(cat <<'EOF'
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
EOF
)

install_workflow "Yordam - Reorg" "com.yordam.agent.reorg" "public.item" "com.apple.Automator.fileSystemObject" "$reorg_files"
install_workflow "Yordam - Rewrite" "com.yordam.agent.rewrite" "public.text" "com.apple.Automator.fileSystemObject" "$rewrite_prompt"
install_workflow "Yordam - Rename" "com.yordam.agent.rename" "public.item" "com.apple.Automator.fileSystemObject" "$rename_prompt"
install_workflow "Yordam - Coworker" "com.yordam.agent.coworker" "public.item" "com.apple.Automator.fileSystemObject" "$co_worker_prompt"
install_workflow "Yordam - Doc Task" "com.yordam.agent.doctask" "public.item" "com.apple.Automator.fileSystemObject" "$doc_task_prompt"

LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [ -x "$LSREGISTER" ]; then
  "$LSREGISTER" -f "$SERVICES_DIR" >/dev/null 2>&1 || true
fi

echo "Installed Quick Actions in $SERVICES_DIR"
echo "If they don't appear in Finder, restart Finder: killall Finder"
