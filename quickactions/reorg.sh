#!/bin/zsh
files=("$@")
if [ ${#files[@]} -eq 0 ]; then
  osascript -e 'display dialog "No files or folders selected." with title "Yordam Agent" buttons {"OK"} default button "OK"'
  exit 1
fi

context=$(osascript -e 'text returned of (display dialog "Reorg context (optional):" default answer "" with title "Yordam Agent" buttons {"Cancel","Continue"} default button "Continue" cancel button "Cancel")') || exit 0

if [ ${#files[@]} -eq 1 ] && [ -d "${files[1]}" ]; then
  root="${files[1]}"
else
  parent="$(dirname "${files[1]}")"
  for f in "${files[@]}"; do
    if [ -d "$f" ]; then
      osascript -e 'display dialog "Select a single folder OR multiple files (no mixed selection)." with title "Yordam Agent" buttons {"OK"} default button "OK"'
      exit 1
    fi
    if [ "$(dirname "$f")" != "$parent" ]; then
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
