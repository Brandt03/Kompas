#!/bin/zsh
# Backup af de lokale databaser, der hverken ligger i skyen eller git:
#   garmin-coach  ~/.garmin-coach/coach.db  Garmin-historik, kalender og 14-dages rapporter med vurderinger
#   overblik      ~/.overblik/liv.db        ugetabellen og ugereviewene
# Én pr. dag, gzippet, i $KOMPAS_BACKUP (gerne en mappe, der synkes til OneDrive/iCloud). De nyeste 14 pr.
# database beholdes.
# Køres af opdater.sh (første gang hver dag) og af kompas-stop.sh. --tving laver en ny, selv om dagens findes.
# Tidspunktet for dagens backup noteres i ~/.kompas/backup-sidst til siden Forbindelser.
#
# Gendan (luk først det, der bruger databasen):
#   gunzip -c "<backup>.db.gz" > ~/.garmin-coach/coach.db
set -euo pipefail
zmodload zsh/datetime
DEST="${KOMPAS_BACKUP:-$HOME/Backup/kompas}"
KEEP=14
STATE=$HOME/.kompas
mkdir -p "$DEST" "$STATE"
d=$(date +%F)
strftime -r -s middag '%F %T' "$d 12:00:00"
sidst=
for navn src in garmin-coach "$HOME/.garmin-coach/coach.db" overblik "$HOME/.overblik/liv.db"; do
  [[ -f $src ]] || continue
  ud="$DEST/$navn-$d.db.gz"
  sidst=$ud
  [[ -f $ud && ${1:-} != --tving ]] && continue
  tmp=$(mktemp -t kompas-backup)
  # .backup giver et konsistent øjebliksbillede, også mens databasen er i brug
  sqlite3 "$src" ".backup '$tmp'"
  # En ødelagt kopi må aldrig erstatte en god
  [[ $(sqlite3 "$tmp" "PRAGMA integrity_check") == ok ]] || { rm -f "$tmp"; print -u2 "$navn: integritetstjek fejlede"; exit 1; }
  gzip -c "$tmp" > "$ud.partial" && mv "$ud.partial" "$ud"
  rm -f "$tmp"
  # De nyeste KEEP beholdes. Mappen kan ikke listes, når launchd kører os (se nederst), så navnene prøves dag for
  # dag et år tilbage, regnet fra middag, så sommertid ikke springer en dato over
  antal=0
  for (( i = 0; i <= 366; i++ )); do
    strftime -s dag %F $(( middag - i * 86400 ))
    if [[ -f $DEST/$navn-$dag.db.gz ]] && (( ++antal > KEEP )); then rm -f -- "$DEST/$navn-$dag.db.gz"; fi
  done
  print "$navn → $ud ($(du -h "$ud" | cut -f1))"
done
# Hertil kommer vi kun, når alle backups for i dag findes. Forbindelser kan ikke selv liste OneDrive-mappen:
# når launchd starter noget, tillader macOS' privatlivsbeskyttelse stat, skrivning og sletning der, ikke læsning
[[ -n $sidst ]] && touch -r "$sidst" "$STATE/backup-sidst"
