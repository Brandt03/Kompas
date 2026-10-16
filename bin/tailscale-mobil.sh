#!/bin/zsh
# Gør På farten (Studie på telefonen) og Sprog tilgængelige gennem Tailscale. Køres én gang, når Tailscale er installeret
# og logget ind på både Mac'en og telefonen, og HTTPS er slået til under DNS i Tailscale's admin-side.
# Køres igen, hvis Mac'en skifter navn i tailnettet.
#
#   1. `tailscale serve` tager imod på https://<mac>.<tailnet>.ts.net (kun dine egne enheder) og sender videre til
#      Caddy på 127.0.0.1:8768, som kun har Studie, Sprog og designkittet (se Caddyfile).
#   2. Studie- og Sprog-serveren får adressen i STUDIE_ORIGINS og SPROG_ORIGINS, så de tager imod svar fra telefonen.
#
# Fjern igen:  tailscale serve reset   (og slet EnvironmentVariables i de to plist'er)
set -euo pipefail
TS=/Applications/Tailscale.app/Contents/MacOS/Tailscale
[[ -x $TS ]] || TS=$(command -v tailscale || true)
[[ -n $TS ]] || { echo "Tailscale er ikke installeret (https://tailscale.com/download)"; exit 1; }

navn=$("$TS" status --json | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
[[ $navn == *.ts.net ]] || { echo "Fandt ikke Mac'ens Tailscale-navn (er du logget ind?)"; exit 1; }
origin="https://$navn"

"$TS" serve --bg --https=443 http://127.0.0.1:8768
for server var in studie STUDIE_ORIGINS sprog SPROG_ORIGINS; do
  PLIST="$HOME/Library/LaunchAgents/local.kompas.$server.plist"
  /usr/libexec/PlistBuddy -c "Delete :EnvironmentVariables" "$PLIST" 2>/dev/null || true
  /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables dict" -c "Add :EnvironmentVariables:$var string $origin" "$PLIST"
  launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
done

echo "Åbn på telefonen (Chrome):  $origin  (Studie)  og  $origin/sprog/mobil.html  (Sprog)"
echo "Menu ⋮ → Føj til startskærm / Installer app"
