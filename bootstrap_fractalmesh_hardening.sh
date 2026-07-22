#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# FractalMesh / Delegation Toolkit - All-in-one hardening bootstrap
# Target repo path: run from repository root
# Safe scope: CI, security, docs, issue templates, helper scripts
# ============================================================

REPO_ROOT="$(pwd)"

echo "==> Starting hardening bootstrap in: ${REPO_ROOT}"

mkdir -p .github/workflows
mkdir -p .github/ISSUE_TEMPLATE
mkdir -p scripts
mkdir -p tests

# ------------------------------------------------------------
# 1) .gitignore
# ------------------------------------------------------------
cat > .gitignore <<'EOF2'
# Python
__pycache__/
*.py[cod]
*.so
.venv/
venv/
.env
.env.*
!.env.example
.pytest_cache/
.mypy_cache/
.ruff_cache/
coverage.xml
htmlcov/
dist/
build/
*.egg-info/

# Editors/OS
.DS_Store
.vscode/
.idea/

# Secrets / artifacts
*.pem
*.key
*.p12
*.sqlite3
*.db
EOF2

# ------------------------------------------------------------
# 2) Python project baseline via pyproject.toml
# ------------------------------------------------------------
cat > pyproject.toml <<'EOF2'
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "delegation-toolkit"
version = "0.1.0"
description = "Security-hardened toolkit baseline."
readme = "README.md"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = [
  "pytest>=8.0.0",
  "pytest-cov>=5.0.0",
  "ruff>=0.5.0",
  "mypy>=1.10.0",
  "bandit>=1.7.9",
  "pip-audit>=2.7.0",
  "pre-commit>=3.7.0",
  "detect-secrets>=1.5.0"
]

[tool.ruff]
line-length = 100
target-version = "py310"
exclude = [".venv", "venv", "build", "dist"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false
ignore_missing_imports = true
pretty = true

[tool.pytest.ini_options]
addopts = "-q --maxfail=1 --disable-warnings"
testpaths = ["tests"]
EOF2

# ------------------------------------------------------------
# 3) Pre-commit baseline
# ------------------------------------------------------------
cat > .pre-commit-config.yaml <<'EOF2'
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: check-merge-conflict
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-yaml
      - id: check-json

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.7
    hooks:
      - id: ruff
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.1
    hooks:
      - id: mypy
        additional_dependencies: []

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.9
    hooks:
      - id: bandit
        args: ["-q", "-r", "."]

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ["--baseline", ".secrets.baseline"]
EOF2

# ------------------------------------------------------------
# 4) CI workflow
# ------------------------------------------------------------
cat > .github/workflows/ci.yml <<'EOF2'
name: ci

on:
  pull_request:
  push:
    branches: ["**"]

jobs:
  test-and-quality:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Ruff
        run: ruff check .

      - name: Mypy
        run: mypy .

      - name: Bandit
        run: bandit -q -r .

      - name: Tests
        run: pytest

      - name: pip-audit
        run: pip-audit
EOF2

# ------------------------------------------------------------
# 5) Security workflow (CodeQL + secret scan quick gate)
# ------------------------------------------------------------
cat > .github/workflows/security.yml <<'EOF2'
name: security

on:
  push:
    branches: ["**"]
  pull_request:
  schedule:
    - cron: "0 4 * * 1"

jobs:
  codeql:
    name: CodeQL
    runs-on: ubuntu-latest
    permissions:
      actions: read
      contents: read
      security-events: write
    strategy:
      fail-fast: false
      matrix:
        language: ["python"]
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Initialize CodeQL
        uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}

      - name: Autobuild
        uses: github/codeql-action/autobuild@v3

      - name: Analyze
        uses: github/codeql-action/analyze@v3

  secret-scan:
    name: Detect secrets
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install detect-secrets
        run: |
          python -m pip install --upgrade pip
          pip install detect-secrets
      - name: Scan repository
        run: |
          if [ -f .secrets.baseline ]; then
            detect-secrets scan --baseline .secrets.baseline
            detect-secrets audit .secrets.baseline || true
          else
            detect-secrets scan > .secrets.baseline
            echo "Created .secrets.baseline. Commit this file."
          fi
EOF2

# ------------------------------------------------------------
# 6) Dependabot
# ------------------------------------------------------------
cat > .github/dependabot.yml <<'EOF2'
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
EOF2

# ------------------------------------------------------------
# 7) Security docs
# ------------------------------------------------------------
cat > SECURITY.md <<'EOF2'
# Security Policy

## Supported Versions
Use the latest default branch.

## Reporting a Vulnerability
Please report vulnerabilities privately via GitHub Security Advisories (preferred) or repository contact channel.
Do not open public issues for sensitive vulnerabilities.

## Secret Handling
- Never commit API keys, wallet secrets, or private certificates.
- Use environment variables and a managed secrets vault.
- Rotate credentials immediately on exposure.

## Secure Development Baseline
- PR review required
- CI checks required
- Dependency and secret scanning enabled
EOF2

cat > CONTRIBUTING.md <<'EOF2'
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
EOF2

# ------------------------------------------------------------
# 8) Env template
# ------------------------------------------------------------
cat > .env.example <<'EOF2'
# Do not put secrets in this file.
APP_ENV=development
LOG_LEVEL=INFO

# Exchange/API placeholders
KUCOIN_API_KEY=
KUCOIN_API_SECRET=
CRYPTOCOM_API_KEY=
CRYPTOCOM_API_SECRET=
PIONEX_API_KEY=
PIONEX_API_SECRET=

# Optional model/service endpoints
SGLANG_ENDPOINT=
EOF2

# ------------------------------------------------------------
# 9) Simple smoke test
# ------------------------------------------------------------
cat > tests/test_smoke.py <<'EOF2'
def test_smoke():
    assert True
EOF2

# ------------------------------------------------------------
# 10) Script: local verification
# ------------------------------------------------------------
cat > scripts/verify_local.sh <<'EOF2'
#!/usr/bin/env bash
set -euo pipefail

python -m pip install --upgrade pip
pip install -e ".[dev]"

ruff check .
mypy .
bandit -q -r .
pytest
pip-audit
EOF2
chmod +x scripts/verify_local.sh

# ------------------------------------------------------------
# 11) Issue templates (for the 14-item plan kickoff)
# ------------------------------------------------------------
cat > .github/ISSUE_TEMPLATE/architecture_ownership_map.md <<'EOF2'
---
name: Architecture ownership map
about: Define canonical repo ownership and boundaries
title: "architecture: define canonical ownership and boundaries across FractalMesh repos"
labels: architecture, governance, priority:P0
assignees: ""
---

## Scope
Create ARCHITECTURE.md with repo boundaries, owners, anti-overlap rules, and diagrams.

## Acceptance Criteria
- [ ] Ownership matrix defined
- [ ] Boundary rules documented
- [ ] System/dependency diagram included
EOF2

cat > .github/ISSUE_TEMPLATE/security_baseline.md <<'EOF2'
---
name: Security baseline controls
about: Enforce branch protections and secret/security controls
title: "security: enforce branch protections, CODEOWNERS, secret scanning, signed commits"
labels: security, compliance, priority:P0
assignees: ""
---

## Scope
Enable protection, CODEOWNERS, signing guidance, and scanning.

## Acceptance Criteria
- [ ] Protection rules enabled
- [ ] CODEOWNERS added
- [ ] Security docs updated
EOF2

# ------------------------------------------------------------
# 12) Optional: CLAUDE.md safety check helper
# ------------------------------------------------------------
cat > scripts/check_claude_md.sh <<'EOF2'
#!/usr/bin/env bash
set -euo pipefail

FILE="CLAUDE.md"
if [ ! -f "$FILE" ]; then
  echo "CLAUDE.md not found; skipping."
  exit 0
fi

echo "Scanning CLAUDE.md for risky patterns..."
grep -Ein "(api[_ -]?key|secret|private[_ -]?key|seed phrase|mnemonic|password|dark web|credential harvesting|exploit)" "$FILE" || true
echo "Manual review still required."
EOF2
chmod +x scripts/check_claude_md.sh

echo "==> Bootstrap complete."
echo "Next steps:"
echo "1) python -m pip install --upgrade pip"
echo "2) pip install -e '.[dev]'"
echo "3) detect-secrets scan > .secrets.baseline"
echo "4) pre-commit install"
echo "5) ./scripts/verify_local.sh"
echo "6) git add . && git commit -m 'chore: bootstrap CI/security/docs baseline'"
