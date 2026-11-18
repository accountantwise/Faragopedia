#!/usr/bin/env bash
# Nightly off-site backup of the Faragopedia production data (VPS).
# Installed by docs/backup.md. Config comes from /etc/faragopedia-backup.env:
#   RESTIC_REPOSITORY, RESTIC_PASSWORD_FILE, provider credentials,
#   optional HEALTHCHECK_URL (pinged on success, /fail on failure).
set -euo pipefail

DATA_DIR="${DATA_DIR:-/home/ubuntu/faragopedia-data}"

ping() { [ -n "${HEALTHCHECK_URL:-}" ] && curl -fsS -m 10 --retry 3 "${HEALTHCHECK_URL}$1" >/dev/null || true; }
trap 'ping /fail' ERR

# The wiki is a few MB of markdown and JSON. Writes are rare and small, so a live
# file-level copy is consistent enough; restic records each file as it reads it.
restic backup "$DATA_DIR" --tag faragopedia --host faragopedia-vps \
  --exclude "$DATA_DIR/**/__pycache__"

restic forget --tag faragopedia --host faragopedia-vps \
  --keep-daily 14 --keep-weekly 8 --keep-monthly 12 --prune

# Read back a sample of the data each run, so a broken repository is noticed
# the next morning rather than on the day we need it.
restic check --read-data-subset=5%

ping ""
