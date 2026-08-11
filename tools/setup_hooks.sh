#!/usr/bin/env bash
# Point git at the tracked hooks. Run once per clone.
set -euo pipefail
cd "$(dirname "$0")/.."
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
echo "core.hooksPath -> .githooks (pre-commit refuses real personal data)"
