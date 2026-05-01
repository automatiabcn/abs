#!/usr/bin/env bash
# 020 — Documentation site build (mkdocs material + auto api-reference).
set -euo pipefail

cd "$(dirname "$0")/.."

# 1. mkdocs deps (idempotent — pip skip if up-to-date)
python -m pip install --quiet --upgrade mkdocs mkdocs-material

# 2. Auto-generate API reference from MCP tool registry
python scripts/gen_api_reference.py

# 3. Build static site → site/
mkdocs build --strict 2>&1 | tee /tmp/abs-mkdocs-build.log

echo
echo "Built site/ — entry: site/index.html"
ls -la site/index.html
