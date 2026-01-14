#!/bin/sh
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$HOME/bin"

mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/yordam-agent" <<EOW
#!/bin/sh
export PYTHONPATH="$ROOT_DIR/src"
exec /usr/bin/env python3 -m yordam_agent.cli "\$@"
EOW

chmod +x "$BIN_DIR/yordam-agent"

echo "Installed: $BIN_DIR/yordam-agent"
