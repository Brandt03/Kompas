# garmin-coach

Lokal MCP-server der giver Claude adgang til dine Garmin- og kalenderdata, så du
kan spørge om træning i almindeligt sprog og få svar der bygger på dine egne tal.

Alt kører på din maskine. Databasen er en SQLite-fil i din hjemmemappe, og kun
de færdigberegnede aggregater sendes med i samtalen — aldrig rå døgndata.

## Princippet

Beregningerne ligger i `metrics.py`, ikke i modellen. Sprogmodeller regner
upålideligt på lange talrækker, så ACWR, HRV-afvigelse, monotoni og trends
udregnes i Python, og modellen får kun færdige tal at fortolke. Det gør
svarene reproducerbare og holder tokenforbruget nede.

## Opsætning

```bash
cd garmin-coach
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env     # udfyld den
```

Kun én ting skal være rigtig i `.env`:

- `GARMIN_EMAIL` — dit Garmin-login.

Makspuls og hvilepuls udleder programmet selv, medmindre du sætter
`GC_HR_MAX`/`GC_HR_REST`. Makspulsen er Garmins konfigurerede (den samme som
pulszonerne bygger på), så belastning og zoner regner med samme tal. Kun hvis
din tredjehøjeste registrerede puls det seneste år ligger over, bruges den i
stedet — en registreret puls er et gulv, ikke en testet makspuls. Hvilepulsen
er medianen af de seneste 60 dages målte hvilepuls, ellers Garmins profil.
Værktøjet `profil` viser hvad der bruges og hvor hvert tal kom fra.
- `GC_ICS_URLS` — den hemmelige iCal-adresse til din kalender. I Google Kalender
  ligger den under Indstillinger → vælg kalenderen → "Hemmelig adresse i
  iCal-format". Kan udelades hvis du ikke vil have kalenderen med.

- `HEVY_API_KEY` — valgfri. Bruger du Hevy til styrketræning, giver nøglen
  (Settings → API, kræver Hevy Pro) sæt, vægt og RPE, som ellers går tabt når
  Hevy synker til Garmin. Hevy-pas parres med deres kopi i Garmin på
  starttidspunkt, så samme træning kun tæller én gang, og styrkebelastningen
  regnes ud fra arbejdssæt med tillæg for sæt med RPE. Manglende RPE giver
  intet tillæg frem for en gættet værdi. Hevy synkes automatisk sammen med
  Garmin, eller alene med `.venv/bin/python -m garmin_coach.ingest_hevy`.

Log ind én gang i en terminal, så MFA kan besvares interaktivt:

```bash
set -a; source .env; set +a
.venv/bin/python -m garmin_coach.ingest_garmin --login
```

Tokens gemmes i `~/.garminconnect` og holder omkring et år. Fjern
`GARMIN_PASSWORD` fra `.env` igen bagefter.

Byg så historikken. HRV- og hvilepuls-baseline kræver mindst 14 målte dage for
at give mening, og ACWR kræver 28, så hent rigeligt første gang:

```bash
.venv/bin/python -m garmin_coach.ingest_garmin --days 180
.venv/bin/python -m garmin_coach.ingest_calendar
```

Første kørsel tager en del minutter. Der er en indbygget pause mellem hvert
Garmin-kald, fordi de ikke tager pænt imod at blive hamret.

Vil du have længere historik senere, så hent fra en bestemt dato. Dage der
allerede har målinger springes over, og kørslen stopper af sig selv hvis
Garmin begynder at afvise kald — kør den bare igen senere, så fortsætter den:

```bash
.venv/bin/python -m garmin_coach.ingest_garmin --fra 2025-06-01
```

Regn med 7-8 sekunder pr. dag.

## Kobl den på Claude Desktop

Settings → Developer → Edit Config. Filen ligger på macOS i
`~/Library/Application Support/Claude/` og på Windows i `%APPDATA%\Claude\`.

```json
{
  "mcpServers": {
    "garmin-coach": {
      "command": "/absolut/sti/til/garmin-coach/.venv/bin/python",
      "args": ["-m", "garmin_coach.server"],
      "env": {
        "GC_DB": "/Users/dig/.garmin-coach/coach.db",
        "GARMINTOKENS": "/Users/dig/.garminconnect",
        "GC_ICS_URLS": "https://calendar.google.com/calendar/ical/.../basic.ics",
        "GC_TZ": "Europe/Copenhagen"
      }
    }
  }
}
```

Absolutte stier er nødvendige. Afslut derefter Claude Desktop helt — at lukke
vinduet er ikke nok, appen kører videre og genindlæser ikke konfigurationen.

Samme server virker i Claude Code med
`claude mcp add garmin-coach /absolut/sti/.venv/bin/python -m garmin_coach.server`.

## Hold data friske

```
0 6 * * * cd /sti/til/garmin-coach && .venv/bin/python -m garmin_coach.ingest_garmin --days 3
5 6 * * * cd /sti/til/garmin-coach && .venv/bin/python -m garmin_coach.ingest_calendar
```

Alternativt kan du bare bede om en `sync` midt i en samtale.

## Værktøjer

| Værktøj | Giver |
|---|---|
| `dagens_status` | Alt på én gang. Start her ved brede spørgsmål. |
| `traeningsbelastning` | Akut/kronisk, ACWR, monotoni, strain, ugefordeling, styrke pr. uge |
| `restitution` | HRV og hvilepuls i SD fra 60-dages baseline, søvn, readiness |
| `seneste_traening` | De enkelte pas med beregnet belastning |
| `periode` | Alle nøgletal for en periode, i Form & Fokus-sidens format |
| `maanedsoversigt` | Det store billede: nøgletal måned for måned og udviklingen fra start til nu |
| `kalender` | Dagens program, optaget tid og frie træningsvinduer |
| `kropsudvikling` | Vægttrend og VO2max |
| `profil` | Hvilke pulstal der regnes med, og hvor de kommer fra |
| `opslag` | Skrivebeskyttet SELECT til alt det andet |
| `sync` | Hent nye data ind |

Prompts: `ugeplan` og `evaluering`.

`.claude/skills/garmin-coach-data/SKILL.md` beskriver faldgruberne i dataene
for en model der bruger værktøjerne. Claude Code-sessioner i projektet får den
automatisk; bruger du den også som skill i Claude-appen, så hold kopien der i
takt med filen her.

## Form & Fokus

En lokal side med 14-dages perioder (tal plus en skrevet vurdering) og det
store billede måned for måned. Siden ligger i `site/index.html`; data bygges
til `~/.garmin-coach/site`, som Caddy leverer på `https://localhost/form/`
(kun tilgængelig fra denne Mac):

```bash
.venv/bin/python -m garmin_coach.site byg        # byg siden med de nyeste tal
.venv/bin/python -m garmin_coach.site perioder   # vis gemte perioder
```

Mappen kan flyttes med `GC_SITE` (standard `~/.garmin-coach/site`).

Kompas.app bygger siden, henter nye data i baggrunden og åbner den.
Perioderne skrives af den planlagte opgave "Form & Fokus" hver anden fredag
med `gem-periode`, som selv regner tallene, så kun vurderingen kommer fra
modellen.

Visningen "Ugen" (`/form/#ugen`) viser mandagsreviewet fra ~/kompas/livsoverblik:
afvigelser fra det normale, dag for dag, ugekalenderen, sammenhænge og
udviklingen uge for uge. Den henter `liv.json`, som livsoverblik skriver i
samme mappe med `liv eksport` eller `liv gem-review`; `byg` rører ikke filen.

## Verificér uden Garmin-adgang

`python smoke_test.py` kører hele beregningslaget på syntetiske data i en
midlertidig database. Brug den hvis du ændrer i `metrics.py`.

## Hvad du skal være opmærksom på

`garminconnect` er uofficielt. Garmins eget Connect Developer Program tager
ikke imod nye ansøgninger i øjeblikket, så det er den eneste praktiske vej til
egne data, men endpoints kan ændre sig uden varsel. Derfor gemmes alt rådata
lokalt som JSON ved siden af de udtrukne felter: bryder en sync, mister du nye
data, ikke din historik. Vær også opmærksom på at det ligger i en gråzone i
forhold til Garmins vilkår.

ACWR er et groft pejlemærke. Litteraturen om det som skadesforudsigelse er
omdiskuteret, og tallet bruges her til at se retning, ikke som facit.

Dine helbredsdata indgår i samtalen og forlader dermed maskinen. Vil du undgå
det, kan serveren tales med af en lokal model gennem en MCP-klient der peger på
Ollama, med samme værktøjer.

Det her er et værktøj til at se mønstre i dine egne tal. Vedvarende afvigelser,
smerter eller symptomer hører hjemme hos en læge.
