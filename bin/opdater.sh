#!/bin/zsh
# Holder Kompas frisk i baggrunden, også når Sure er lukket. Køres hvert 30. minut af LaunchAgent
# local.kompas.opdater (~/Library/LaunchAgents). Log: ~/.kompas/opdater.log. Luk Kompas slår den fra, Kompas-appen til.
#
#   kalender + Form & Fokus-siderne   hver gang (hurtigt, kun kalenderfeeds og lokale beregninger)
#   Garmin                            højst hver 3. time (logger ind hos Garmin; tokens caches), og med det
#                                     samme, når Kompas-appen åbnes (~/.kompas/hent-garmin-nu). Henter fra
#                                     sidste vellykkede hentning, så en periode med Kompas lukket ikke giver hul
#   overblik (liv.json)               hver gang
#   Studie-eksporten                  hver gang
#   backup af databaserne             første kørsel hver dag
#   status til Forbindelser           hver gang: trinnenes udfald i ~/.kompas/opdater-status.json, som
#                                     bin/forbindelser.py læser og skriver videre til public/forbindelser.json
# Sure og forbrugssiden opdateres ikke her; de kræver Docker og hører til Kompas-appen.
set -u
export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
GC=$HOME/kompas/coach
SEM="${KOMPAS_SEMESTER:-$HOME/kompas/studie}"   # semestermappen, der har Scripts/ (se studie/README.md)
STATE=$HOME/.kompas
LOCK=$STATE/opdater.lock
log() { print -r -- "$(date '+%F %T') $*"; }
# trin <id> <fejltekst> <kommando …>: kører kommandoen og noterer ok/fejl under id'et til statusfilen.
# Forbindelser kender trinnene på id'et, så det ændres begge steder; fejlteksten er kun til loggen.
typeset -A STATUS
trin() { local id=$1 fejltekst=$2; shift 2; if "$@"; then STATUS[$id]=ok; else STATUS[$id]=fejl; log "$fejltekst"; return 1; fi }
garmin()   ( cd $GC && .venv/bin/python -m garmin_coach.ingest_garmin --days $dage >/dev/null )
kalender() { local ud; ud=$(cd $GC && .venv/bin/python -m garmin_coach.ingest_calendar) || return 1
             # Uden kalender sat op svarer den uden fejlede_feeds; trinnet er stadig ok
             if [[ $ud =~ '"fejlede_feeds": ([0-9]+)' ]]; then feeds_fejlede=$match[1]; fi; }
form_byg() ( cd $GC && .venv/bin/python -m garmin_coach.site byg >/dev/null )
liv()      { $HOME/kompas/overblik/.venv/bin/liv opdater >/dev/null && $HOME/kompas/overblik/.venv/bin/liv eksport >/dev/null }
studie()   { /usr/local/bin/node "$SEM/Scripts/kompas-eksport.js" >/dev/null }
feeds_fejlede=null

mkdir -p $STATE
# Én kørsel ad gangen; en lås ældre end en time er efterladt af en kørsel, der døde
if ! mkdir $LOCK 2>/dev/null; then
  (( $(date +%s) - $(stat -f %m $LOCK) > 3600 )) && rmdir $LOCK && mkdir $LOCK || { log "springer over: kører allerede"; exit 0; }
fi
trap 'rmdir $LOCK' EXIT

if [[ -f $STATE/hent-garmin-nu || ! -f $STATE/garmin-sidst ]] || (( $(date +%s) - $(stat -f %m $STATE/garmin-sidst) > 10800 )); then
  # Dage siden sidste vellykkede hentning, plus én for en nat, Garmin har synket sent; mindst 2, højst 30
  dage=2
  [[ -f $STATE/garmin-sidst ]] && dage=$(( ($(date +%s) - $(stat -f %m $STATE/garmin-sidst)) / 86400 + 2 ))
  (( dage > 30 )) && dage=30
  rm -f $STATE/hent-garmin-nu
  trin garmin "Garmin fejlede ($dage dage)" garmin && touch $STATE/garmin-sidst
fi
trin kalender "kalenderen fejlede" kalender
trin form-byg "Form & Fokus-byg fejlede" form_byg
trin overblik "overblik fejlede" liv
trin studie-eksport "studie-eksporten fejlede" studie
$HOME/kompas/bin/backup-data.sh | while read -r l; do log "backup: $l"; done
log "ok"
# Status for siden Forbindelser: kun faste id'er og tal, aldrig fejltekster (kalenderens indeholder hemmelige adresser)
par=(); for id in ${(ok)STATUS}; do par+=("\"$id\": \"$STATUS[$id]\""); done
print -r -- "{\"slut\": \"$(date -u +%FT%TZ)\", \"trin\": {${(j:, :)par}}, \"kalenderfeeds_fejlede\": $feeds_fejlede}" \
  > $STATE/opdater-status.tmp && mv $STATE/opdater-status.tmp $STATE/opdater-status.json
/usr/bin/python3 $HOME/kompas/bin/forbindelser.py || log "forbindelser fejlede"
