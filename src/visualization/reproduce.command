#!/bin/zsh
set -eu
FIGURE_CODE_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
FIGURE_REPO_DIR="$(cd -- "$FIGURE_CODE_DIR/../.." && pwd)"
FIGURE_PYTHON="$FIGURE_REPO_DIR/.venv/bin/python"
if [[ ! -x "$FIGURE_PYTHON" ]]; then
  FIGURE_PYTHON="$(command -v python3)"
fi
cd -- "$FIGURE_REPO_DIR"
exec "$FIGURE_PYTHON" "$FIGURE_CODE_DIR/reproduce.py" --build-documents "$@"
