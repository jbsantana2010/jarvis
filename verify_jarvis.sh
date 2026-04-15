#!/usr/bin/env bash
# verify_jarvis.sh — full smoke test for JARVIS (WSL/Windows build)
# Checks Python syntax, key imports, server.py feature flags, TypeScript, and app registry.
# Run after a pull or before pushing to confirm nothing is broken.
# Works from any clone location (no hardcoded paths)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

echo "=== Python syntax check ==="
cd "$SCRIPT_DIR"
python3 -m py_compile platform_adapter.py  && echo "  platform_adapter.py ✓"
python3 -m py_compile actions.py           && echo "  actions.py ✓"
python3 -m py_compile server.py            && echo "  server.py ✓"
python3 -m py_compile conversation_db.py   && echo "  conversation_db.py ✓"

echo ""
echo "=== Import check ==="
python3 - <<PYEOF
import sys
sys.path.insert(0, '$SCRIPT_DIR')
import platform_adapter as pa

required = [
    'open_windows_app', '_WIN_APP_REGISTRY', 'open_url', 'open_terminal',
    'take_screenshot_wsl', 'read_clipboard_wsl', 'write_clipboard_wsl',
]
for sym in required:
    assert hasattr(pa, sym), f"platform_adapter missing: {sym}"
    print(f"  platform_adapter.{sym} ✓")

import actions as a
assert hasattr(a, 'open_app'), "actions missing: open_app"
print("  actions.open_app ✓")

import conversation_db as db
for sym in ['init_db', 'load_recent', 'save_turn', 'prune']:
    assert hasattr(db, sym), f"conversation_db missing: {sym}"
print("  conversation_db ✓")
PYEOF

echo ""
echo "=== server.py feature check ==="
python3 - <<PYEOF
import re, sys
src = open('$SCRIPT_DIR/server.py').read()
checks = [
    (r'take_screenshot_wsl',       'screenshot (WSL)'),
    (r'_execute_browse',           'browse executor'),
    (r'_execute_open_app',         'open_app executor'),
    (r'_execute_read_clipboard',   'clipboard read'),
    (r'_execute_write_clipboard',  'clipboard write'),
    (r'_WORK_STOP_PHRASES',        'work-mode stop phrases'),
    (r'conversation_db',           'conversation persistence'),
    (r'speakingWatchdog|watchdog', 'speaking watchdog (note: in frontend)'),
]
all_ok = True
for pattern, label in checks:
    if re.search(pattern, src):
        print(f"  {label} ✓")
    else:
        print(f"  {label} ✗  (pattern: {pattern})")
        all_ok = False
if not all_ok:
    sys.exit(1)
PYEOF

echo ""
echo "=== App registry check ==="
python3 - <<PYEOF
import sys
sys.path.insert(0, '$SCRIPT_DIR')
import platform_adapter as pa
registry = pa._WIN_APP_REGISTRY
expected = ['chrome', 'calculator', 'discord', 'spotify', 'file explorer', 'vscode']
for app in expected:
    assert app in registry, f"'{app}' missing from _WIN_APP_REGISTRY"
    print(f"  {app} ✓")
print(f"  ({len(registry)} total entries)")
PYEOF

echo ""
echo "=== TypeScript check ==="
cd "$SCRIPT_DIR/frontend"
npx tsc --noEmit 2>&1 && echo "  TypeScript ✓"

echo ""
echo "✅  All checks passed"
echo ""
echo "Start JARVIS:"
echo "  Terminal 1: cd $SCRIPT_DIR && DEV_MODE=1 python3 server.py"
echo "  Terminal 2: cd $SCRIPT_DIR/frontend && npm run dev"
echo "  Browser   : http://localhost:5173"
