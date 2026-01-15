#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

PROJECT_DIR="${HOME}/fractalmesh"
ENV_FILE="${PROJECT_DIR}/.env"
BACKUP_DIR="${PROJECT_DIR}/backups_$(date +%Y%m%d_%H%M%S)"
SAFE_MODE=true

echo "SAFE DEPLOY TEMPLATE"
echo "Project dir: ${PROJECT_DIR}"
echo "Env file: ${ENV_FILE}"
echo "Backup dir: ${BACKUP_DIR}"
echo ""
echo "This script is interactive. It will not run actions without confirmation."
