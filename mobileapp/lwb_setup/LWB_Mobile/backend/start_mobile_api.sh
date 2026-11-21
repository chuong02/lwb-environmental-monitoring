#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${1:-$HOME/lwb-backend}"
cd "$PROJECT"
if [ ! -x .venv/bin/python ]; then
    echo 'Missing .venv/bin/python. Use the existing Ubuntu WSL lwb-backend folder.' >&2
    exit 1
fi
PYTHON="$PWD/.venv/bin/python"
"$PYTHON" "$HERE/apply_backend.py" --project "$PWD"
"$PYTHON" "$HERE/run_selftest.py" --project "$PWD"
echo 'Starting localhost-only Mobile API on 8001. Existing Web server on 8000 stays unchanged.'
exec "$PYTHON" manage.py runserver 127.0.0.1:8001 --settings=config.lwb_mobile_local --noreload
