#!/bin/sh
set -e

LABEL="com.yordam.documents-organizer"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$LABEL.plist"
BIN_PATH="$HOME/bin/yordam-agent"
ROOT_PATH="$HOME/Documents"
LOG_DIR="$HOME/Documents/Logs.nosync"
OUT_LOG="$LOG_DIR/organizer.log"
ERR_LOG="$LOG_DIR/organizer.error.log"

if [ ! -x "$BIN_PATH" ]; then
  echo "yordam-agent not found at $BIN_PATH. Run ./scripts/install.sh first."
  exit 1
fi

mkdir -p "$PLIST_DIR" "$LOG_DIR"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$BIN_PATH</string>
    <string>documents</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>WatchPaths</key>
  <array>
    <string>$ROOT_PATH</string>
  </array>
  <key>StandardOutPath</key>
  <string>$OUT_LOG</string>
  <key>StandardErrorPath</key>
  <string>$ERR_LOG</string>
</dict>
</plist>
PLIST

launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl load "$PLIST_PATH"

echo "Installed LaunchAgent: $PLIST_PATH"
