#!/usr/bin/env bash
set -euo pipefail

repository="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_path="$repository/.venv/bin/python"
if [[ ! -x "$python_path" ]]; then
    echo 'Prepare .venv first. See docs/linux-server.md.' >&2
    exit 1
fi

exec "$python_path" "$repository/tools/start_server.py" "$@"
