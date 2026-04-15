#!/usr/bin/env bash
# setup_dev_env.sh — first-time dev environment setup for JARVIS (WSL/Windows)
# Run once after cloning to install frontend deps and verify backend imports.
# Works from any clone location (no hardcoded paths)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

echo "=== Node version ==="
node --version
npm --version

echo ""
echo "=== Installing frontend packages ==="
cd "$SCRIPT_DIR/frontend"
npm install

echo ""
echo "=== Verifying backend imports ==="
cd "$SCRIPT_DIR"
python3 - <<PYEOF
import sys
sys.path.insert(0, '.')
import platform_adapter
print('  platform_adapter OK — platform:', platform_adapter.PLATFORM)
import actions
print('  actions OK')
print('  open_terminal WSL-ready:', not platform_adapter.is_macos())
print('  open_url WSL-ready:     ', not platform_adapter.is_macos())
PYEOF

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Copy .env.example to .env and fill in your API keys, then:"
echo "  Terminal 1: cd $SCRIPT_DIR && DEV_MODE=1 python3 server.py"
echo "  Terminal 2: cd $SCRIPT_DIR/frontend && npm run dev"
echo "  Browser   : http://localhost:5173"
