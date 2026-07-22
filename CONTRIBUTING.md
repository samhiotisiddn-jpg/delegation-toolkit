# Contributing

## Development Setup
1. Create a virtual environment
2. Install dependencies:
   pip install -e ".[dev]"

## Quality Gates
Run locally before pushing:
- ruff check .
- mypy .
- bandit -q -r .
- pytest

## Pre-commit
Install hooks:
pre-commit install
