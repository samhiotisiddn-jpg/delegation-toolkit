#!/usr/bin/env bash
set -euo pipefail

python -m pip install --upgrade pip
pip install -e ".[dev]"

ruff check .
mypy .
bandit -q -r .
pytest
pip-audit
