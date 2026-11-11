#!/bin/sh
# Daily logical backup of the Pathly database; keeps the newest $BACKUP_KEEP dumps.
# Restore: docs/notes/devops/PRODUCTION.md ("Khôi phục từ backup").
set -eu
KEEP="${BACKUP_KEEP:-7}"
INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
mkdir -p /backups
while :; do
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  file="/backups/${PGDATABASE}-${stamp}.dump"
  if pg_dump --format=custom --no-owner --no-privileges --file="${file}.part"; then
    mv "${file}.part" "$file"
    echo "backup: wrote $file ($(du -h "$file" | cut -f1))"
    # Newest first; prune every dump after the first $KEEP.
    count=0
    for old in $(ls -1t /backups/*.dump 2>/dev/null); do
      count=$((count + 1))
      if [ "$count" -gt "$KEEP" ]; then
        rm -f -- "$old"
      fi
    done
  else
    rm -f -- "${file}.part"
    echo "backup: pg_dump failed" >&2
  fi
  sleep "$INTERVAL"
done
