#!/bin/zsh
# Backup af de lokale databaser, der hverken ligger i skyen eller git:
#   garmin-coach  ~/.garmin-coach/coach.db  Garmin-historik, kalender og 14-dages rapporter med vurderinger
#   overblik      ~/.overblik/liv.db        ugetabellen og ugereviewene
# Én pr. dag, gzippet, i $KOMPAS_BACKUP (gerne en mappe, der synkes til OneDrive/iCloud). De nyeste 14 pr.
# database beholdes.
# Køres af opdater.sh (første gang hver dag) og af kompas-stop.sh. --tving laver en ny, selv om dagens findes.
#
# Gendan (luk først det, der bruger databasen):
#   gunzip -c "<backup>.db.gz" > ~/.garmin-coach/coach.db
set -euo pipefail
DEST="${KOMPAS_BACKUP:-$HOME/Backup/kompas}"
KEEP=14
mkdir -p "$DEST"
d=$(date +%F)
for navn src in garmin-coach "$HOME/.garmin-coach/coach.db" overblik "$HOME/.overblik/liv.db"; do
  [[ -f $src ]] || continue
  ud="$DEST/$navn-$d.db.gz"
  [[ -f $ud && ${1:-} != --tving ]] && continue
  tmp=$(mktemp -t kompas-backup)
  # .backup giver et konsistent øjebliksbillede, også mens databasen er i brug
  sqlite3 "$src" ".backup '$tmp'"
  # En ødelagt kopi må aldrig erstatte en god
  [[ $(sqlite3 "$tmp" "PRAGMA integrity_check") == ok ]] || { rm -f "$tmp"; print -u2 "$navn: integritetstjek fejlede"; exit 1; }
  gzip -c "$tmp" > "$ud.partial" && mv "$ud.partial" "$ud"
  rm -f "$tmp"
  gamle=( "$DEST"/$navn-*.db.gz(NOn) )
  (( ${#gamle} > KEEP )) && rm -f -- ${gamle[KEEP+1,-1]}
  print "$navn → $ud ($(du -h "$ud" | cut -f1))"
done
