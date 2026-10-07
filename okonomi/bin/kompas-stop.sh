#!/bin/zsh
# Turns off everything Kompas runs in the background: Sure and the Docker VM, the update every 30 minutes,
# the Karriere and Genkald servers, Sure's export and Caddy. The jobs are disabled, so they stay off after
# a restart until Kompas.app (kompas-start.sh) is opened again. Data stays in the Docker volumes,
# ~/.garmin-coach and ~/.overblik. The scheduled Claude routines are not affected.
# Used by /Applications/Luk Kompas.app.
set -eu
export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
cd "$(dirname "$0")/.."
KOMPAS_HOME=${KOMPAS_HOME:-$HOME/kompas}   # the Kompas folder (public/, bin/)
dashboard/export.sh >/dev/null 2>&1 || true
bin/refresh-excel.sh >> dashboard/excel.log 2>&1 || true
bin/backup-db.sh >> dashboard/backup.log 2>&1 || true
colima stop >/dev/null 2>&1 || true

# Form & Fokus: stop a Garmin or calendar sync still running from the update (data is saved day by day,
# so stopping midway loses nothing). The garmin_coach.server processes belong to Claude and are left alone.
pkill -f 'garmin_coach\.(ingest_garmin|ingest_calendar|site)' >/dev/null 2>&1 || true

# Backup of the local databases that aren't in OneDrive or git (garmin-coach, overblik)
"$KOMPAS_HOME/bin/backup-data.sh" --tving >> dashboard/backup.log 2>&1 || true

# Kompas' background jobs. disable keeps them off after a restart; bootout stops them now.
U=gui/$(id -u)
for l in local.kompas.opdater local.kompas.karriere local.kompas.studie local.sure.dashboard-export; do
  launchctl disable $U/$l
  launchctl bootout $U/$l 2>/dev/null || true
done
# An update stopped midway leaves its lock behind; without it the next update would wait up to an hour
pgrep -f "$KOMPAS_HOME/bin/opdater.sh" >/dev/null || rmdir "$HOME/.kompas/opdater.lock" 2>/dev/null || true

# Caddy (https://kompas.localhost). brew services stop also keeps it from starting at login.
brew services stop caddy >/dev/null 2>&1 || true
