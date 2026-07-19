#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="${NYANYA_DASHBOARD_DB_PATH:-${ROOT_DIR}/data/nyanya_dashboard.db}"
STAMP="$(date '+%Y%m%d_%H%M%S')"
BACKUP_DIR="${1:-${ROOT_DIR}/data/backups/${STAMP}}"
BACKUP_DB="${BACKUP_DIR}/nyanya_dashboard.db"

if [[ ! -f "${DB_PATH}" ]]; then
  printf 'Database not found: %s\n' "${DB_PATH}" >&2
  exit 1
fi

umask 077
mkdir -p "${BACKUP_DIR}"
sqlite3 "${DB_PATH}" ".backup '${BACKUP_DB}'"

if [[ "$(sqlite3 "${BACKUP_DB}" 'PRAGMA integrity_check;')" != "ok" ]]; then
  printf 'Backup integrity check failed: %s\n' "${BACKUP_DB}" >&2
  rm -f "${BACKUP_DB}"
  exit 1
fi

chmod 600 "${BACKUP_DB}"
printf 'backup=%s\n' "${BACKUP_DB}"
printf 'sha256=%s\n' "$(shasum -a 256 "${BACKUP_DB}" | awk '{print $1}')"
