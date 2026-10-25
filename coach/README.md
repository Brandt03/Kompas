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
  iCal-format". Kan udelades hvis du ikke vil have kalenderen med. Står
  `#kompas-plan` i en begivenheds beskrivelse, gemmes den med `plan_blok = 1`:
  en studieblok fra Kompas' studieplan, som overblik holder øje med.

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
| `periode` | Alle nøgletal for en periode, som rutinen Træning vurderer |
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

## Form & fokus

Tre sider i Kompas: Perioder (perioder på 14 dage fra lørdag til fredag, tal plus en skrevet vurdering),
Ugereview og Kroppen i tal. Siderne ligger i `site/`; `byg` kopierer dem og bygger data til
`~/.garmin-coach/site`, som Caddy leverer på `https://kompas.localhost/form/`. `/form/` selv
(`site/index.html`) sender videre til Perioder; den gamle samlede side og `maaneder.json` er væk, og `byg`
fjerner en gammel `maaneder.json`.

```bash
.venv/bin/python -m garmin_coach.site byg        # byg siden med de nyeste tal
.venv/bin/python -m garmin_coach.site perioder   # vis gemte perioder
```

Mappen kan flyttes med `GC_SITE` (standard `~/.garmin-coach/site`).

Kompas.app bygger siden, henter nye data i baggrunden og åbner den.
Perioderne skrives af rutinen Træning hver anden søndag med `gem-periode`, som
selv regner tallene, så kun vurderingen kommer fra modellen. Rutinens
instruktioner står i `RUTINE.md`.

Siden "Perioder" (`/form/perioder.html`) viser vurderingen af hver periode med fokus og opfølgningen på
perioden før lige under resuméet (opfølgningen er åben, når et fokus ikke blev nået), styrken (arbejdssæt, RPE og
e1RM pr. løft), løb og svømning (`kondition` i perioden: distance, længste tur, tempo, puls, løbets hurtigste
1 og 5 km og kadence, svømningens SWOLF) mod perioden før, træningen fordelt på sport, studie og kalender og det
lange perspektiv. Perioder gemt før `kondition` kom med, får den regnet af `byg` ud fra aktiviteterne.
Søvn, puls, stress og belastning står på "Kroppen i tal".

Siden "Ugereview" (`/form/uge.html`) viser ugereviewet fra ~/kompas/overblik:
afvigelser fra det normale (kun de tydelige som fliser, resten samlet på én linje), dag for dag,
ugekalenderen, sammenhænge og udviklingen uge for uge. Nederst står planlagt mod faktisk for de seneste
14 døgn til i dag; det følger ikke den valgte uge. Undervisning og selvstudie har faste farver
(`--undervisning`, `--selvstudie` i `site/form.css`), som Skærmtids grupper ikke bruger. Den henter `liv.json`, som overblik skriver i
samme mappe med `liv eksport` eller `liv gem-review`; `byg` rører ikke filen.

Siden "Kroppen i tal" (`/form/kroppen.html`) er idéen fra garmin-grafana: alle Garmins døgn- og
nattemålinger på én side, og man kan gå tilbage i tid. Allerøverst står dagens råd og flagene om HRV,
hvilepuls og søvn. Så ét døgn ad gangen (pil, kalenderen eller klik
på en dag i ugetabellen eller heatmappet; kalenderen har en prik pr. aktivitet). Har døgnet en aktivitet, står den
først med Garmins tal for passet (tid, distance, tempo, puls, træningseffekt, belastning og det, der er målt for
netop den sport), tid i pulszoner (med hvor meget af passet, der var i zone 1–5), pulsen under passet og Hevy-øvelserne. Derefter puls hen over døgnet, farvet efter Garmins aktivitetsniveau og med
dine pulszoner i baggrunden, stress i Garmins egne niveauer, body battery, skridt pr. kvarter og natten
(søvnfaser, puls, HRV, SpO2, åndedræt, stress, body battery). Nedenunder en periode, de seneste 60 dage
eller én kalendermåned: ugen i overblik (med snittet for ugen før), heatmappet, træningsbelastning (TRIMP dag for dag og uge for uge),
aktivitet, stress og body battery, puls og helbred, søvn (med sengetid og sen skærmtid fra overblik) og
aktiviteternes pulszoner. Det, der er målt mod i dag, står kun under de seneste 60 dage: belastningen nu
(ACWR), intensiteten de seneste 28 dage og grundniveauet for HRV og hvilepuls. VO2max og vægt står altid
med hele historikken. Hvert mål har samme farve
overalt på siden.

`byg` skriver `kroppen.json` (de seneste 60 dage) og under `kroppen/` én fil pr. døgn (`dag/<dato>.json`) og
pr. måned (`maaned/<ÅÅÅÅ-MM>.json`) plus `index.json`. Alt regnes i `garmin_coach/kroppen.py`, også snit,
min og maks; siden regner ikke selv. Kun filer, hvis kilde har ændret sig, skrives igen (`kilder.json`
holder styr på det; hæv `FORMAT` i `kroppen.py`, når filernes indhold ændres). I dag er kun indtil nu, så
dagens døgntal (skridt, kalorier, stress …) tæller ikke med i snittene.

Døgnets kurver (puls hvert 2. min, stress og body battery hvert 3. min, skridt pr. kvarter) hentes med den
almindelige sync, tre kald mere pr. døgn, og fylder omkring 60 KB pr. døgn i databasen og 40 KB pr. døgn i
siden. Til dage, der blev hentet før kurverne kom med:

```bash
.venv/bin/python -m garmin_coach.ingest_garmin --fra 2025-01-01 --kurver
```

Den tager nyeste dag først, springer dage med kurver over og stopper, hvis Garmin afviser kald; kør den
bare igen. GPS-kort og løbsprognoser er ikke med, fordi de ikke hentes fra Garmin.

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

Tallene har kendte begrænsninger, så brug dem til at se retning, ikke som
facit:

- **ACWR** er et groft pejlemærke, og litteraturen om det som
  skadesforudsigelse er omdiskuteret. Her er det de seneste 7 dages belastning
  delt med snittet pr. uge over 28 dage, og de 7 dage indgår selv i de 28. Det
  trækker tallet mod 1, så et stort spring ser mindre ud, end det er.
- **HRV og hvilepuls** er Garmins egne natlige tal fra en lukket algoritme.
  Afvigelsen er snittet af de seneste 7 dage målt i standardafvigelser for
  enkelte dage i de 53 dage før, uden logaritme. Et 7-dages snit svinger mindre
  end enkelte dage, så afvigelsen er forsigtig, og én usædvanlig nat i
  grundniveauet gør målestokken bredere.
- **Estimeret 1RM** er Epleys formel, vægt × (1 + gentagelser / 30), på det
  bedste sæt, uden RPE-justering og kun op til 12 gentagelser. Et sæt, der ikke
  er taget til grænsen, giver et for lavt tal, og formlen passer forskelligt
  til forskellige øvelser og personer. Den er god til at følge den samme øvelse
  over tid, ikke til at kende din max.

Dine helbredsdata indgår i samtalen og forlader dermed maskinen. Vil du undgå
det, kan serveren tales med af en lokal model gennem en MCP-klient der peger på
Ollama, med samme værktøjer.

Det her er et værktøj til at se mønstre i dine egne tal. Vedvarende afvigelser,
smerter eller symptomer hører hjemme hos en læge.
