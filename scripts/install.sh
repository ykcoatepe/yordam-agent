#!/bin/sh
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$HOME/bin"

mkdir -p "$BIN_DIR"

PYTHON_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "python3 not found on PATH."
  exit 1
fi

if ! "$PYTHON_BIN" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
then
  echo "python3 >= 3.10 is required. Found: $("$PYTHON_BIN" -V)"
  exit 1
fi

cat > "$BIN_DIR/yordam-agent" <<EOW
#!/bin/sh
export PYTHONPATH="$ROOT_DIR/src"
exec "$PYTHON_BIN" -m yordam_agent.cli "\$@"
EOW

chmod +x "$BIN_DIR/yordam-agent"

echo "Installed: $BIN_DIR/yordam-agent"

if [ -f "$ROOT_DIR/quickactions/install.sh" ]; then
  echo "Installing Finder Quick Actions..."
  if ! /bin/sh "$ROOT_DIR/quickactions/install.sh"; then
    echo "Quick Actions install failed (see output above)."
  fi
fi
