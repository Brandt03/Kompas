#!/bin/zsh
# Gør Kompas tilgængelig gennem Tailscale, kun for dine egne enheder. Køres én gang, når Tailscale er installeret og
# logget ind på Mac'en og enhederne, og HTTPS er slået til under DNS i Tailscale's admin-side. Køres igen, hvis Mac'en
# skifter navn i tailnettet. Kan køres flere gange.
#
#   Telefonen  https://<mac>.<tailnet>.ts.net        → Caddy 127.0.0.1:8768: På farten, Sprog, Skærmtid og designkittet
#   Bærbaren   https://<mac>.<tailnet>.ts.net:8443   → Caddy 127.0.0.1:8771: hele Kompas, som på Mac'en
#
# Siderne kender forskel på porten: uden port er det telefonudgaven (På farten med service worker), med port er det
# Mac-udgaven. Serverne får adresserne i deres LaunchAgent, så de tager imod svar og valg derfra: Studie, Sprog og
# Skærmtid begge adresser (STUDIE_ORIGINS, SPROG_ORIGINS, SKAERMTID_ORIGINS).
# Sure har sit eget login og skal logges ind én gang på bærbaren.
#
# Fjern igen:  tailscale serve reset   (og slet de tre variabler i plist'erne)
set -euo pipefail
TS=/Applications/Tailscale.app/Contents/MacOS/Tailscale
[[ -x $TS ]] || TS=$(command -v tailscale || true)
[[ -n $TS ]] || { echo "Tailscale er ikke installeret (https://tailscale.com/download)"; exit 1; }

navn=$("$TS" status --json | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
[[ $navn == *.ts.net ]] || { echo "Fandt ikke Mac'ens Tailscale-navn (er du logget ind?)"; exit 1; }
telefon="https://$navn"
baerbar="https://$navn:8443"

"$TS" serve --bg --https=443 http://127.0.0.1:8768
"$TS" serve --bg --https=8443 http://127.0.0.1:8771

for server var origins in \
  studie STUDIE_ORIGINS "$telefon,$baerbar" \
  sprog SPROG_ORIGINS "$telefon,$baerbar" \
  skaermtid SKAERMTID_ORIGINS "$telefon,$baerbar"; do
  PLIST="$HOME/Library/LaunchAgents/local.kompas.$server.plist"
  /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables dict" "$PLIST" 2>/dev/null || true
  /usr/libexec/PlistBuddy -c "Delete :EnvironmentVariables:$var" "$PLIST" 2>/dev/null || true
  /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:$var string $origins" "$PLIST"
  launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
done

echo "Telefonen (Chrome):  $telefon  (På farten),  $telefon/sprog/mobil.html  (Sprog)  og  $telefon/skaermtid/  (Skærmtid)"
echo "                     Menu ⋮ → Føj til startskærm / Installer app"
echo "Bærbaren:            $baerbar  (hele Kompas; Økonomi beder om Sures login første gang)"
