#!/usr/bin/env bash
# typecheck_frontend.sh — run TypeScript type-check on the JARVIS frontend
# Works from any clone location (no hardcoded paths)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$SCRIPT_DIR/frontend"

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

echo "=== TypeScript check ==="
cd "$FRONTEND"
if npx tsc --noEmit 2>&1; then
  echo "✅ TypeScript OK"
else
  echo "❌ TypeScript errors above"
  exit 1
fi
