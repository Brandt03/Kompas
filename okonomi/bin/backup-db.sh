#!/bin/zsh
# Dumps the Sure database to $SURE_BACKUP/sure-YYYY-MM-DD.dump (one per day, newest 30 kept). Point SURE_BACKUP
# at a folder that is synced off the machine (OneDrive, iCloud ...).
# Run by $KOMPAS_HOME/bin/backup-data.sh: once a day from the update (~/.kompas/opdater.log), 2 min after Kompas.app
# starts (dashboard/backup.log), and by kompas-stop.sh before the VM is stopped.
#
# Restore (overwrites the current database):
#   docker compose up -d db
#   docker compose exec -T db pg_restore -U sure_user -d sure_production --clean --if-exists --no-owner < "<dump-fil>"
#   docker compose up -d
set -euo pipefail
export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
cd "$(dirname "$0")/.."
DEST="${SURE_BACKUP:-$HOME/Backup}"
KEEP=30

colima status >/dev/null 2>&1 || exit 0   # Sure is stopped – nothing new to back up
mkdir -p "$DEST"
file="$DEST/sure-$(date +%F).dump"
tmp="$DEST/.sure-$(date +%F).dump.partial"
docker compose exec -T db pg_dump -U sure_user -d sure_production -Fc > "$tmp"
# pg_restore --list fails on a truncated/corrupt dump, so a bad backup never replaces a good one
docker compose exec -T db pg_restore --list < "$tmp" >/dev/null
mv "$tmp" "$file"

# Keep the newest $KEEP daily dumps; only ever touches files named sure-YYYY-MM-DD.dump in $DEST. Under launchd
# (the daily update via backup-data.sh) macOS may allow writing to a cloud folder but neither listing nor deleting,
# so the cleanup is skipped there and happens when Kompas.app runs this.
{ ls -1 "$DEST" | grep -E '^sure-[0-9]{4}-[0-9]{2}-[0-9]{2}\.dump$' | sort -r | tail -n +$((KEEP + 1)) | while read -r old; do
  rm -f "$DEST/$old"
done } 2>/dev/null || true
echo "$(date '+%F %T') backup $(basename "$file") ($(du -h "$file" | cut -f1))"
