#!/bin/zsh
# Backup af de lokale data, der hverken ligger i skyen eller git:
#   garmin-coach  ~/.garmin-coach/coach.db  Garmin-historik, kalender og perioder med vurderinger
#   overblik      ~/.overblik/liv.db        ugetabellen og ugereviewene
#   sprog         ~/kompas/sprog/data/      kortene, dine svar og ugens tekster (en mappe; gemmes som .tar.gz)
#   activitywatch ~/Library/Application Support/activitywatch/aw-server/peewee-sqlite.v2.db
#                                           al skærmtid fra alle enheder (Skærmtid regner forfra fra den)
# Én pr. dag, gzippet, i $KOMPAS_BACKUP (gerne en mappe, der synkes til OneDrive/iCloud). De nyeste 14 pr.
# kilde beholdes.
# Køres af opdater.sh (første gang hver dag) og af kompas-stop.sh. --tving laver en ny, selv om dagens findes.
# Tidspunktet for dagens backup noteres i ~/.kompas/backup-sidst til siden Forbindelser.
#
# Gendan (luk først det, der bruger databasen):
#   gunzip -c "<backup>.db.gz" > ~/.garmin-coach/coach.db
#   tar xzf "<backup>.tar.gz" -C ~/kompas/sprog          (Sprog: luk først local.kompas.sprog)
#   gunzip -c "<backup>.db.gz" > "$HOME/Library/Application Support/activitywatch/aw-server/peewee-sqlite.v2.db"
#                                                        (ActivityWatch: luk først appen, og slet -wal og -shm ved siden af)
set -euo pipefail
zmodload zsh/datetime
DEST="${KOMPAS_BACKUP:-$HOME/Backup/kompas}"
KEEP=14
STATE=$HOME/.kompas
mkdir -p "$DEST" "$STATE"
d=$(date +%F)
strftime -r -s middag '%F %T' "$d 12:00:00"
sidst=
for navn src in garmin-coach "$HOME/.garmin-coach/coach.db" overblik "$HOME/.overblik/liv.db" sprog "$HOME/kompas/sprog/data" \
                activitywatch "$HOME/Library/Application Support/activitywatch/aw-server/peewee-sqlite.v2.db"; do
  [[ -e $src ]] || continue
  [[ -d $src ]] && ext=tar.gz || ext=db.gz
  ud="$DEST/$navn-$d.$ext"
  sidst=$ud
  [[ -f $ud && ${1:-} != --tving ]] && continue
  if [[ -d $src ]]; then
    # En mappe med tekstfiler, som serveren skriver atomisk (log.jsonl tilføjes kun). Den midlertidige fil ligger
    # lokalt, så en halvt skrevet kopi aldrig når skyen, og den tjekkes, før den erstatter gårsdagens
    tmp=$(mktemp -t kompas-backup)
    tar czf "$tmp" -C "${src:h}" --exclude '.*.tmp' "${src:t}"
    tar tzf "$tmp" >/dev/null || { rm -f "$tmp"; print -u2 "$navn: arkivet kan ikke læses"; exit 1; }
    cp "$tmp" "$ud.partial" && mv "$ud.partial" "$ud"
  else
    tmp=$(mktemp -t kompas-backup)
    # .backup giver et konsistent øjebliksbillede, også mens databasen er i brug
    sqlite3 "$src" ".backup '$tmp'"
    # En ødelagt kopi må aldrig erstatte en god
    [[ $(sqlite3 "$tmp" "PRAGMA integrity_check") == ok ]] || { rm -f "$tmp"; print -u2 "$navn: integritetstjek fejlede"; exit 1; }
    gzip -c "$tmp" > "$ud.partial" && mv "$ud.partial" "$ud"
  fi
  rm -f "$tmp"
  # De nyeste KEEP beholdes. Mappen kan ikke listes, når launchd kører os (se nederst), så navnene prøves dag for
  # dag et år tilbage, regnet fra middag, så sommertid ikke springer en dato over. Sletning er heller ikke tilladt
  # under launchd ("Operation not permitted"); det må ikke stoppe de næste kilders backup, så det tælles kun op,
  # og oprydningen sker, når scriptet kører fra Luk Kompas eller en terminal
  antal=0 gamle=0
  for (( i = 0; i <= 366; i++ )); do
    strftime -s dag %F $(( middag - i * 86400 ))
    if [[ -f $DEST/$navn-$dag.$ext ]] && (( ++antal > KEEP )); then rm -f -- "$DEST/$navn-$dag.$ext" 2>/dev/null || (( ++gamle )); fi
  done
  print "$navn → $ud ($(du -h "$ud" | cut -f1))"
  if (( gamle )); then print "$navn: $gamle gamle backups kunne ikke slettes herfra; de ryddes af Luk Kompas eller \`~/kompas/bin/backup-data.sh --tving\` i en terminal"; fi
done
# Hertil kommer vi kun, når alle backups for i dag findes. Forbindelser kan ikke selv liste OneDrive-mappen:
# når launchd starter noget, tillader macOS' privatlivsbeskyttelse stat og skrivning der, men hverken læsning
# af mappen eller sletning
[[ -n $sidst ]] && touch -r "$sidst" "$STATE/backup-sidst"
