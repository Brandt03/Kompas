#!/bin/zsh
# Starts everything Kompas runs: Caddy, the background jobs (LaunchAgents local.kompas.* and Sure's export),
# Docker (Colima) + Sure. Waits until Sure answers, refreshes the dashboard and opens Kompas.
# Used by /Applications/Kompas.app. kompas-stop.sh (Luk Kompas.app) turns it all off again.
set -eu
export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
cd "$(dirname "$0")/.."
U=gui/$(id -u)

brew services list | grep -q '^caddy.*started' || brew services start caddy >/dev/null 2>&1

# The background jobs: the update every 30 minutes, the Karriere and Genkald servers and Sure's export.
# Luk Kompas disables them (so they stay off after a restart); enable and load them again here.
# The update fetches Garmin now instead of waiting up to 3 hours, and from the last successful fetch,
# so a period with Kompas closed leaves no gap.
mkdir -p "$HOME/.kompas" && touch "$HOME/.kompas/hent-garmin-nu"
for l in local.kompas.karriere local.kompas.studie local.kompas.opdater local.sure.dashboard-export; do
  launchctl enable $U/$l
  if launchctl print $U/$l >/dev/null 2>&1; then
    [[ $l == local.kompas.opdater ]] && launchctl kickstart $U/$l
  else
    launchctl bootstrap $U "$HOME/Library/LaunchAgents/$l.plist"   # RunAtLoad: starts right away
  fi
done

colima status >/dev/null 2>&1 || colima start >/dev/null 2>&1
docker compose up -d >/dev/null 2>&1

# Wait for Sure (max ~2 min)
for i in {1..60}; do
  [ "$(curl -s -o /dev/null -w '%{http_code}' https://localhost/up)" = "200" ] && break
  sleep 2
done

# Ask Sure to fetch new bank transactions now, then refresh the dashboard (again once the sync is done)
docker compose exec -T web bin/rails runner 'Family.first.sync_later' >/dev/null 2>&1 &
dashboard/export.sh || true
( sleep 120; dashboard/export.sh; bin/refresh-excel.sh >> dashboard/excel.log 2>&1 ) >/dev/null 2>&1 &!

# Form & Fokus, overblik and Studie are refreshed by the update started above (~/.kompas/opdater.log).

# Kompas (~/kompas, https://kompas.localhost): økonomi, studie og form samlet bag én menu
open "https://kompas.localhost/"
