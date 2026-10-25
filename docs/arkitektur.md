# Kompas: sådan hænger det sammen

Én side på **https://kompas.localhost** med økonomi, studie, sprog, form og skærmtid bag samme menu, i Sures farver og
skrift. Alt kører lokalt og svarer kun på den Mac, det kører på.

Kompas ejer kun selve rammen, siden "I dag" og designkittet. **Hvert projekt leverer selv sine sider** og
fortæller Kompas om dem i en `kompas.json`. Projekternes egne rutiner holder dem opdaterede.

I dette repo ligger projekterne som undermapper. I brug har hvert sit eget git-repo under `~/kompas`, og Kompas'
`.gitignore` holder dem ude af Kompas' git.

```
I dag           dagen på tværs: kalender med det faktiske, frister, form, selvstudie,  public/index.html
                skærmtid, står stille, fokus, Genkald og sprogkort
Forbindelser    om datakilder, Claude, baggrundsjob og værktøjer virker              bin/forbindelser.py
Økonomi         Oversigt, Transaktioner, Rapporter, Plan (Sure)                       Sure (ikke i repoet)
                Forbrug, Scenarier, SU-vagt                                           okonomi/
Studie          Ugeoverblik, Fag, Træning, Eksamen, Selvstudie, USB-noter, Frister,  studie/
                På farten (telefon)
Sprog           Oversigt, Dagens kort og Ugens tekst (også telefon), Regler          sprog/
Form & fokus    Perioder, Ugereview, Kroppen i tal                                    coach/ + overblik/
Skærmtid        Skærmtid (alle enheder, også på telefonen)                           skaermtid/
```

## Kontrakten: kompas.json

Hvert projekt skriver en `kompas.json` ved siden af sine sider. `public/projekter.json` lister, hvor de ligger.
Menuen bygges ud fra dem, hver gang Kompas åbnes.

```json
{
  "omraade": "Studie", "ikon": "graduation-cap", "raekkefoelge": 20,
  "kilde": "hvem der skriver filen", "opdateret": "2026-09-28T09:30:00Z",
  "sider": [
    { "titel": "Ugeoverblik", "ikon": "calendar", "sti": "/studie/" },
    { "titel": "Noget planlagt", "ikon": "book-open" }
  ]
}
```

- `sti` er adressen på kompas.localhost. En side uden `sti` vises som "snart".
- `match` (valgfri) er stier, der også tæller som siden, når man klikker rundt inde i den (bruges til Sure).
- `praecis` (valgfri) betyder, at kun præcis den sti tæller.
- `fane` (valgfri) er id'et på en fane (`role="tab"`) i siden. Kompas klikker på den for at vise visningen.
- `nyt` (valgfri) er en nøgle for sidens nyeste indhold, fx `"2026-W40"`. Skifter den, viser menuen en prik
  ud for siden (og på menuknappen på telefonen), til siden er åbnet. Hvad du sidst har set, huskes kun i browseren.
  Brug den til nyt indhold (et ugereview, en køreplan, ugens tekst), ikke til tal, der ændrer sig hele tiden.
- Ikonerne er navnene i `public/assets/icons.js` (Lucide).
- Kan et manifest ikke læses, viser menuen "Ikke tilgængelig" under området, og resten virker.

| Område | kompas.json skrives af | Hvornår |
|---|---|---|
| Økonomi | håndskrevet: `okonomi/dashboard/public/kompas.json` | ændres sjældent |
| Studie | `studie/Scripts/kompas-eksport.js` → `~/.kompas/studie/` | hvert 30. min, efter hver gemning i Genkald, og af Studie-rutinen søndag |
| Form & fokus | `python -m garmin_coach.site byg` → `~/.garmin-coach/site/` | hvert 30. min, og når Træning-rutinen gemmer en vurdering |
| Sprog | `sprog/server.js` (live, port 8769) | læser Sprogs data ved hvert besøg |

## Designkittet

Projekternes sider linker til `/kompas/assets/`. Så ser de ens ud og følger lyst og mørkt tema.

| Fil | Hvad |
|---|---|
| `tokens.css` | Sures farver, flader og skrift (Geist) som CSS-variabler |
| `page.css` | kort, fliser, lister, badges, segmenter, grafer og markdown |
| `icons.js` | `icon(navn)` |
| `chart.js` | `barChart` og `lineChart` med hover. Én serie pr. graf |
| `liv.js` | fælles hjælpere: `esc`, tal- og datoformater, `nedtaelling`, `parseEvent` (fag-felterne fra garmin-coach), `loadLiv()` til overbliks `liv.json`, `latestReview` (det nyeste ugereview med tekst) og `reviewKilde` ("Skrevet <dato> · metode <metode>") |
| `md.js` | `md(tekst)`: markdown til HTML, escapet (køreplaner, fagnoter, sprogregler) |

## Rammen og adresserne

Rammen (`public/shell.html`) har menuen til venstre og en iframe til højre. Alt ligger på samme adresse bag Caddy
(`Caddyfile`), så rammen kan vise Sure og projekternes sider og følge med i, hvor du klikker hen.

| Sti | Hvad | Hvorfra |
|---|---|---|
| `/` | rammen | `public/shell.html` |
| `/okonomi` | Sures egen forside | Sure (`127.0.0.1:3000`) |
| `/kompas/…` | I dag, designkittet og `projekter.json` | `public/` |
| `/studie/…` | Studie | `~/.kompas/studie` (skrevet af eksporten) |
| `/studie/api/…` | Genkald, færdig-markering og telefonens synk | `127.0.0.1:8767` |
| `/forbrug/…` | Forbrug, Scenarier, SU-vagt | `okonomi/dashboard/public` |
| `/form/…` | Perioder, Ugereview, Kroppen i tal, `liv.json` | `~/.garmin-coach/site` |
| `/sprog/…` | Sprog (sider og API) | `127.0.0.1:8769` |
| `/skaermtid/…` | Skærmtid | `~/.kompas/skaermtid` (skrevet af `skaermtid.py byg`) |
| `/skaermtid/api/…` | dit kategorivalg for et program eller en side | `127.0.0.1:8770` |
| alt andet | Sure | `127.0.0.1:3000` |

Adressen i browseren følger siden, så `https://kompas.localhost/#/transactions` åbner direkte på
transaktionerne, og et bogmærke virker.

Inde i rammen skjules Sures egen ikonmenu, fordi Kompas' menu erstatter den. Det sker med
`public/assets/embed-sure.css`, som rammen lægger ind i Sures sider. Sures image er urørt. Hvis Sure ændrer sin
markup, dukker ikonmenuen bare op igen.

Siderne skriver kun det, brugeren selv taster eller klikker, og kun gennem fire servere: Studie-serveren
(Genkald-svar og -markeringer, begreber, drill-gæt, læste uger, I egne ord, prøveeksamener, din vurdering af
USB-noterne, telefonens sync og færdig-markering af frister), Sprog-serveren (karakter og svar på sprogkort, svar på
ugens tekst og telefonens sync), Skærmtid-serveren (dit kategorivalg for ét program eller én side, i `valg.json`; den
bygger siden igen bagefter) og Sure (input på Scenarier og SU-vagt gennem `PUT /dashboard-state/<navn>` og kategorien på en postering under
Forbrug gennem `PUT /dashboard-category/<id>`, begge bag Sures login). Resten er læsning, og siderne regner ikke
selv videre på tal; de viser det, projekterne har beregnet. Sprogkort, ugens tekst og niveau skriver Sprog-rutinen
kun gennem `sprog.js`.

## Telefonen

**På farten** (`/studie/mobil.html`) og **Sprog** (`/sprog/mobil.html`) henter hver en pakke med dagens kort,
mens Mac'en er vågen, virker uden net og sender svarene bagefter med `/sync`. Telefonen når Mac'en gennem
Tailscale: `tailscale serve` sender videre til en ekstra Caddy-blok på `127.0.0.1:8768`, der kun har Studie, Sprog,
Skærmtid og designkittet. Økonomi og Form er aldrig på telefonen. Sættes op med `bin/tailscale.sh`, som også sætter
`*_ORIGINS` for de skrivende servere.

## Bærbaren

Bærbaren får hele Kompas på `https://<mac>.<tailnet>.ts.net:8443`: `tailscale serve` sender porten videre til en
Caddy-blok på `127.0.0.1:8771`, der bruger samme stykke `(kompas)` som `kompas.localhost`. Siderne kender telefonen
på, at adressen ikke har en port. Alle enheder i tailnettet kan nå porten, så begræns den med Tailscales ACL'er,
hvis andre er med i dit tailnet; de skrivende servere tjekker stadig Origin, og Sure kræver login.

Når Mac'en er slukket, viser bærbaren en læsekopi: `bin/kopi.py` skriver siderne og deres data til `~/KompasKopi`
sidst i hver opdatering, Syncthing sender mappen over, og Caddy på bærbaren (`baerbar/`) viser kopien, når Mac'en
ikke svarer. Rammen skriver "Kopi fra …", og intet kan gemmes. En ny side, der henter fra en server, skal på listen
`API` i `kopi.py`.

## Drift: hvad kører hvornår

Alt kører i baggrunden, også efter en genstart, til det lukkes med programmet **Luk Kompas**. Det lukker Sure og
Docker-maskinen, slår baggrundsjobbene fra og stopper Caddy. Programmet **Kompas** starter det hele igen, henter
Garmin med det samme og åbner siden (`okonomi/bin/kompas-start.sh` og `kompas-stop.sh`).

| Hvad | Hvordan |
|---|---|
| Caddy (https://kompas.localhost) | `brew services` |
| Studie-serveren (`/studie/api/`) | LaunchAgent `local.kompas.studie` |
| Sprog-serveren (`/sprog/`) | LaunchAgent `local.kompas.sprog` |
| Skærmtid-serveren (`/skaermtid/api/`) | LaunchAgent `local.kompas.skaermtid` |
| ActivityWatch og Syncthing | egne apps, starter ved login |
| Opdatering hvert 30. min (`bin/opdater.sh`) | LaunchAgent `local.kompas.opdater` |
| Sure + forbrugssiden | Kompas-appen |

`bin/opdater.sh` henter kalenderen, de andre enheders skærmtid (aw-sync) og bygger Form & fokus-siderne,
Skærmtid, overblikkets `liv.json`, studie-eksporten og læsekopien til bærbaren hver gang, Garmin højst hver 3. time, og tager dagens backup ved første kørsel. Alt, den og trinnene
skriver til loggen, går gennem et filter, der kun lader skema og vært stå i adresser, så kalenderens hemmelige
iCal-adresser aldrig havner i `opdater.log`.

Planlagte Claude-rutiner står for det, der kræver vurdering: køreplanen for studieugen (søndag), vurderingen
af perioden i Form & fokus (hver anden lørdag), ugereviewet (mandag), nye sprogkort med ugens tekst (søndag) og ugens skærmtid med kategorierne (mandag). De skriver filer,
som projekterne viser; de sender eller indsender aldrig noget.

**Backup:** `bin/backup-data.sh` gemmer `~/.garmin-coach/coach.db` og `~/.overblik/liv.db` og ActivityWatch' database
gzippet og Sprogs `data/` som `.tar.gz` i `$KOMPAS_BACKUP` (14 dage tilbage), én gang om dagen og igen ved "Luk Kompas".

**Forbindelser** (`/kompas/forbindelser.html`) viser, om alt det, Kompas henter fra og kører på, virker:
datakilderne (Garmin, Hevy, kalendere, banken via Sure, Canvas, hver enhed i Skærmtid), Claude (MCP-serveren og rutinerne),
baggrundsjobbene og værktøjerne på Mac'en, plus en MCP-guide til Claude-appen og `claude` i Terminal. Statussen
regnes af `bin/forbindelser.py`, som `opdater.sh` kører til sidst hver gang, og skrives til
`public/forbindelser.json` (ikke i git). Datakilderne vises ud fra seneste vellykkede hentning, serverne spørges
direkte, garmin-coach testes med et rigtigt MCP-håndtryk, og rutinerne læses fra Claude-appens egne tidsplaner;
ret `RUTINE_INFO` i scriptet, så id'erne passer til dine planlagte opgaver. Hver planlagt opgave peger kun på sit
projekts `RUTINE.md`, så instruktionerne versioneres med koden. Scriptet læser aldrig hemmeligheder
som kalender-adresser og API-nøgler, kun om de findes, og viser aldrig rå loglinjer. Rutinestatussen har tests
(`python3 -m unittest tests.test_forbindelser`), og I dag har `node tests/test_i_dag.js`: hver sektion bygges for sig,
så én defekt frist kun koster Frister, ikke hele siden.

## Opsætning

Repoet forventes at ligge i `~/kompas`. Caddy-blokken hentes ind fra `/opt/homebrew/etc/Caddyfile` med
`import /Users/<dig>/kompas/Caddyfile`. Efter ændringer:

```bash
caddy reload --config /opt/homebrew/etc/Caddyfile
```

| Variabel | Bruges af | Standard |
|---|---|---|
| `KOMPAS_SEMESTER` | `bin/opdater.sh`, `bin/forbindelser.py` | `~/kompas/studie` |
| `KOMPAS_BACKUP` | `bin/backup-data.sh`, `bin/forbindelser.py` | `~/Backup/kompas` |

Hvert projekt har sin egen README med sine variabler. Node og Python behøver ikke komme fra Homebrew: Forbindelser
kender også installerne fra nodejs.org (`/usr/local/bin/node`) og python.org
(`/Library/Frameworks/Python.framework/Versions/3.x/bin/python3`) og viser dem som installeret.

Ordene, siderne og rutinerne bruger (kort, genkald, frist, periode, vurdering …), står i `GLOSSARY.md`, også de
tekniske navne, der bliver stående, selv om de bruger et fravalgt ord.

## Tilføj et projekt

1. Lad projektet skrive sine sider og en `kompas.json` til en mappe.
2. Server mappen i `Caddyfile` under en sti (se `/studie/`).
3. Tilføj stien til dens `kompas.json` i `public/projekter.json`.
4. Kør projektets byg fra dets egen rutine, så siden holdes frisk.
