#!/bin/bash
# Sætter Kompas op på bærbaren (Arch Linux; pacman). Køres én gang, når Syncthing har hentet ~/KompasKopi:
#   bash ~/KompasKopi/baerbar/opsaet.sh
# Installerer Caddy, hvis den mangler, og starter tjenesten kompas-kopi, som også starter ved login.
set -euo pipefail
MAPPE="$HOME/KompasKopi"
[[ -f $MAPPE/baerbar/Caddyfile && -f $MAPPE/site/kompas/shell.html ]] || {
  echo "Kopien er ikke hentet endnu: $MAPPE mangler. Tjek Syncthing (mappen KompasKopi, ID kompas-kopi)."; exit 1; }
command -v caddy >/dev/null || sudo pacman -S --needed --noconfirm caddy
# Pakkens egen Caddy-tjeneste bruges ikke; den lytter på port 80 som root
systemctl is-enabled caddy >/dev/null 2>&1 && echo "Bemærk: systemets caddy.service er slået til; kompas-kopi er en anden tjeneste."
mkdir -p "$HOME/.config/systemd/user"
cp "$MAPPE/baerbar/kompas-kopi.service" "$HOME/.config/systemd/user/kompas-kopi.service"
systemctl --user daemon-reload
systemctl --user enable --now kompas-kopi.service
sleep 2
if curl -fsS -o /dev/null http://kompas.localhost:8780/kompas/projekter.json; then
  echo "Kompas kører: http://kompas.localhost:8780"
else
  echo "Tjenesten svarer ikke. Se: journalctl --user -u kompas-kopi -n 50"; exit 1
fi
