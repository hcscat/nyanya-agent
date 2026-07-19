#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="${NYANYA_DASHBOARD_DB_PATH:-${ROOT_DIR}/data/nyanya_dashboard.db}"
BACKUP_DB="${1:-}"

if [[ -z "${BACKUP_DB}" || ! -f "${BACKUP_DB}" ]]; then
  printf 'Usage: NYANYA_RESTORE_CONFIRM=YES %s BACKUP_DB\n' "$0" >&2
  exit 2
fi

if [[ "${NYANYA_RESTORE_CONFIRM:-}" != "YES" ]]; then
  printf 'Restore refused. Set NYANYA_RESTORE_CONFIRM=YES after stopping NyaNya services.\n' >&2
  exit 3
fi

if [[ "$(sqlite3 "${BACKUP_DB}" 'PRAGMA integrity_check;')" != "ok" ]]; then
  printf 'Backup integrity check failed: %s\n' "${BACKUP_DB}" >&2
  exit 4
fi

umask 077
mkdir -p "$(dirname "${DB_PATH}")"
RESTORE_TMP="${DB_PATH}.restore.$$"
cp "${BACKUP_DB}" "${RESTORE_TMP}"
chmod 600 "${RESTORE_TMP}"
mv "${RESTORE_TMP}" "${DB_PATH}"
rm -f "${DB_PATH}-wal" "${DB_PATH}-shm"
printf 'restored=%s\n' "${DB_PATH}"
