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

reorg_dry=$(cat <<'EOF'
for f in "$@"; do
  "$HOME/bin/yordam-agent" reorg "$f"
done
EOF
)

reorg_apply_preview=$(cat <<'EOF'
for f in "$@"; do
  "$HOME/bin/yordam-agent" reorg "$f" --apply --preview
done
EOF
)

rewrite_prompt=$(cat <<'EOF'
tone=$(osascript -e 'text returned of (display dialog "Rewrite tone:" default answer "clear, friendly, professional")')
for f in "$@"; do
  "$HOME/bin/yordam-agent" rewrite --input "$f" --tone "$tone"
done
EOF
)

install_workflow "Yordam - Reorg (Dry Run)" "com.yordam.agent.reorgDryRun" "public.folder" "com.apple.Automator.fileSystemObject.folder" "$reorg_dry"
install_workflow "Yordam - Reorg (Apply + Preview)" "com.yordam.agent.reorgApplyPreview" "public.folder" "com.apple.Automator.fileSystemObject.folder" "$reorg_apply_preview"
install_workflow "Yordam - Rewrite" "com.yordam.agent.rewrite" "public.text" "com.apple.Automator.fileSystemObject.text" "$rewrite_prompt"

LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [ -x "$LSREGISTER" ]; then
  "$LSREGISTER" -f "$SERVICES_DIR" >/dev/null 2>&1 || true
fi

echo "Installed Quick Actions in $SERVICES_DIR"
echo "If they don't appear in Finder, restart Finder: killall Finder"
