#!/usr/bin/env bash
# gates.sh — every gate, in sequence. Exit 0 only when all are green. Run it before any deploy.
# Adapt the commands to your stack; keep the shape: each gate prints one line, the first red one stops the run,
# and a gate whose tool is missing says SKIPPED rather than passing.
set -u
cd "$(dirname "$0")/.."

echo "[1/5] boot";     node gates/boot-check.js || { echo "== BOOT RED ==";  exit 1; }
echo "[2/5] lint";     npx -y eslint@9 --no-config-lookup --rule '{"no-undef":"error","no-dupe-keys":"error"}' \
                         --global require,module,process,console,Buffer,__dirname,setTimeout,setInterval src \
                         || { echo "== LINT RED =="; exit 1; }
echo "[3/5] tests";    NODE_OPTIONS='--require ./gates/strict-schemas.js' node --test tests/ || { echo "== SUITE RED =="; exit 1; }
echo "[4/5] shape";    node --test gates/require-exports.test.js gates/route-shape.test.js || { echo "== SHAPE RED =="; exit 1; }
if command -v gitleaks >/dev/null; then
  echo "[5/5] secrets"; gitleaks git --pre-commit --staged --no-banner || { echo "== SECRETS RED =="; exit 1; }
else
  echo "[5/5] secrets: SKIPPED (gitleaks not installed)"; exit 1
fi
# Untracked source files are invisible to a scanner that reads the index: refuse until they are staged.
u=$(git status --porcelain src tests | grep '^??' || true); [ -z "$u" ] || { echo "untracked files — stage them first:"; echo "$u"; exit 1; }
echo "== ALL GATES GREEN =="
