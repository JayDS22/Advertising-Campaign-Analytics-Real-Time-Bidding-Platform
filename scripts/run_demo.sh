#!/usr/bin/env bash
# Boot the API + dashboard against a local virtualenv.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d ".venv" ]; then
  echo "[+] creating virtualenv .venv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[+] installing dependencies"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

export PYTHONPATH="$ROOT_DIR:${PYTHONPATH:-}"
echo "[+] uvicorn listening on http://localhost:8000"
exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
