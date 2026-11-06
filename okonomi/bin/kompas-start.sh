#!/bin/zsh
# Starts everything Kompas runs: Caddy, the background jobs (LaunchAgents local.kompas.* and Sure's export),
# Docker (Colima) + Sure. Waits until Sure answers, refreshes the dashboard and opens Kompas.
# Used by /Applications/Kompas.app. kompas-stop.sh (run it in a terminal) turns it all off again.
# Log: dashboard/kompas-start.log (each step with a timestamp, plus whatever the commands write to stderr;
# stderr still reaches Kompas.app too, so its error alert shows the message).
set -eu
export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
cd "$(dirname "$0")/.."
KOMPAS_HOME=${KOMPAS_HOME:-$HOME/kompas}   # the Kompas folder (public/, bin/)
U=gui/$(id -u)
LOG=dashboard/kompas-start.log
exec 2> >(tee -a "$LOG" >&2) >> "$LOG"
logline() { echo "$(date '+%F %T') $*"; }
trap 'st=$?; ((st)) && logline "stoppede med fejl (status $st)" || logline "færdig"' EXIT
logline "starter"

logline "Caddy"
brew services list | grep -q '^caddy.*started' || brew services start caddy >/dev/null 2>&1 || true

# The phone's `tailscale serve` on 443 ($KOMPAS_HOME/bin/tailscale.sh) takes port 443 if it is set up while Caddy is down
# (on every address, or only on the Mac's Tailscale addresses, e.g. after a restart), and then Caddy can't start
# ("address already in use"). Take serve off, let Caddy have the
# port, and put serve back on; with Caddy holding the port, Tailscale leaves it alone.
caddy_svarer() {   # up to $1 seconds; launchd retries a failed Caddy about every 10 s
  for i in {1..$1}; do
    [ "$(curl -s -o /dev/null -w '%{http_code}' https://kompas.localhost/)" != "000" ] && return 0
    sleep 1
  done
  return 1
}
if ! caddy_svarer 10; then
  TS=/Applications/Tailscale.app/Contents/MacOS/Tailscale
  if netstat -anv -p tcp | grep -E '\.443 .*LISTEN' | grep -q io.tailscale; then
    logline "port 443 er taget af Tailscale; giver den til Caddy"
    "$TS" serve --https=443 off >/dev/null
    for i in {1..15}; do
      netstat -anv -p tcp | grep -E '\.443 .*LISTEN' | grep -q io.tailscale || break
      sleep 1
    done
    sleep 2
    brew services restart caddy >/dev/null 2>&1 || true
    caddy_svarer 60 && ok=1 || ok=0
    "$TS" serve --bg --https=443 http://127.0.0.1:8768 >/dev/null
    ((ok)) || { echo "Caddy starter ikke, se /opt/homebrew/var/log/caddy.log" >&2; exit 1; }
  else
    echo "Caddy starter ikke, se /opt/homebrew/var/log/caddy.log" >&2
    exit 1
  fi
fi

# The background jobs: the update every 30 minutes, the Studie, Sprog and Skærmtid servers and Sure's export.
# kompas-stop.sh disables them (so they stay off after a restart); enable and load them again here.
# The update fetches Garmin now instead of waiting up to 3 hours, and from the last successful fetch,
# so a period with Kompas closed leaves no gap.
logline "baggrundsjobbene"
mkdir -p "$HOME/.kompas" && touch "$HOME/.kompas/hent-garmin-nu"
for l in local.kompas.studie local.kompas.sprog local.kompas.skaermtid local.kompas.opdater local.sure.dashboard-export; do
  launchctl enable $U/$l
  if launchctl print $U/$l >/dev/null 2>&1; then
    [[ $l == local.kompas.opdater ]] && launchctl kickstart $U/$l
  else
    launchctl bootstrap $U "$HOME/Library/LaunchAgents/$l.plist"   # RunAtLoad: starts right away
  fi
done

logline "Docker (Colima) og Sure"
colima status >/dev/null 2>&1 || colima start >/dev/null 2>&1
docker compose up -d >/dev/null 2>&1

# Wait for Sure (max ~2 min)
for i in {1..60}; do
  [ "$(curl -s -o /dev/null -w '%{http_code}' https://localhost/up)" = "200" ] && { logline "Sure svarer"; break; }
  (( i < 60 )) || logline "Sure svarer ikke efter 2 min"
  sleep 2
done

# Ask Sure to fetch new bank transactions now, then refresh the dashboard (again once the sync is done).
# After the sync: back up Sure's database, the local data and the code (backup-data.sh, which also runs Sure's
# backup-db.sh), and clear out the old backups. Deleting in a cloud folder may only be allowed when the app runs it,
# not under launchd, so this is where the cleanup happens.
docker compose exec -T web bin/rails runner 'Family.first.sync_later' >/dev/null 2>&1 &
dashboard/export.sh || logline "dashboard/export.sh fejlede"
( sleep 120; dashboard/export.sh; bin/refresh-excel.sh >> dashboard/excel.log 2>&1
  "$KOMPAS_HOME/bin/backup-data.sh" --tving >> dashboard/backup.log 2>&1 ) >/dev/null 2>&1 &!

# Form & Fokus, overblik and Studie are refreshed by the update started above (~/.kompas/opdater.log).

# Kompas (~/kompas, https://kompas.localhost): økonomi, studie, sprog, form og skærmtid samlet bag én menu
open "https://kompas.localhost/"
