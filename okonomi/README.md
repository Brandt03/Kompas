# Økonomi

Kompas' økonomidel bygger på [Sure](https://github.com/we-promise/sure), et open source-budgetprogram (AGPL-3.0),
der kører i Docker på din egen Mac og henter bankens posteringer. Sure selv er **ikke** med her. Mappen indeholder
kun det, der ligger rundt om den: tre egne sider (**Forbrug**, **Scenarier** og **SU-vagt**) på `/forbrug/` i
Kompas, et udtræk fra Sures database til siderne, to små tilføjelser, der monteres ind i Sure, og scripts, der
starter og lukker det hele.

## Hvad er Sure, og hvad er dit eget
| | Hvad | Hvor |
|---|---|---|
| Sure | Selve budgetprogrammet: konti, posteringer, kategorier, regler, budgetter, mål og rapporter. Kompas viser Sures sider (Oversigt, Transaktioner, Rapporter, Plan) i sin ramme | `compose.yml` og `.env` fra Sures repo (ikke her) |
| Udtrækket | `dashboard/export.sh` laver `dashboard/public/data.json` fra Sures database | `dashboard/` |
| Siderne | Forbrug, Scenarier og SU-vagt. Rene HTML-filer uden byg; `common.js`/`common.css` deles af Scenarier og SU-vagt | `dashboard/public/` |
| Tilføjelser i Sure | `custom/dashboard_tabs.rb` sætter de tre sider ind i Sures venstremenu og gemmer sidernes indstillinger. `custom/sure_tweaks.rb` retter tre småting i Sure (se toppen af filen) | `custom/`, monteres af `compose.override.yml` |
| Drift | Start, luk, backup af databasen og Excel-regnskaber | `bin/`, `scripts/` |

Tilføjelserne monteres skrivebeskyttet ind i Sures container af `compose.override.yml`, som Docker Compose selv
lægger oven i Sures `compose.yml`. Sures image er urørt, så `docker compose pull` virker stadig, og hver ændring
tjekker først, at det, den ændrer, findes. Har Sure ændret sig, slår den sig fra og skriver det i loggen.

## Sæt op
1. Læg Sures `compose.example.yml` som `compose.yml` og en `.env` i denne mappe, som Sures
   [Docker-vejledning](https://github.com/we-promise/sure/blob/main/docs/hosting/docker.md) beskriver. Docker
   kører i [Colima](https://github.com/abiosoft/colima) (`brew install colima docker`).
2. `docker compose up -d`, og opret dig i Sure på `http://localhost:3000`.
3. Kompas' `Caddyfile` sender `/forbrug/` til `dashboard/public/` her og resten videre til Sure.
4. Kopiér `dashboard/public/config.example.json` til `config.json`, hvis du vil have knappen "Siden flytning" og
   pænere modtagernavne (se nedenfor).

## Fra Sure til data.json
`dashboard/export.sh` kører én SQL-forespørgsel mod Sures Postgres (`docker compose exec db psql`) og skriver
resultatet til `dashboard/public/data.json` (via en midlertidig fil, så siderne aldrig ser en halv fil):

| Nøgle | Hvad |
|---|---|
| `generated_at`, `last_sync` | Hvornår udtrækket blev lavet, og hvornår Sure sidst hentede fra banken |
| `accounts` | Aktive konti med saldo (Scenariers startformue) |
| `goals` | Aktive opsparingsmål (Scenariers mål og dato) |
| `budgets` | Månedsbudgetter: forbrug, forventet indkomst og budgettet for gruppen "Variable udgifter" |
| `transactions` | Alle posteringer med dato, beløb (udgifter positive, som i Sure), tekst, konto, kategori, gruppe (overkategori) og modtager |

Overførsler mellem egne konti, betaling af kreditkort og lån, indskud på investeringer, udelukkede posteringer og
konti, der er holdt ude af rapporterne, kommer ikke med. Scriptet køres hvert 5. minut af LaunchAgent
`local.sure.dashboard-export` (`~/Library/LaunchAgents/local.sure.dashboard-export.plist`, `StartInterval` 300,
`RunAtLoad`, programmet er den fulde sti til `export.sh`) og springer stille over, når Colima ikke kører. Siderne
virker derfor også, når Sure er lukket, med de seneste tal.

`data.json` er dine rigtige posteringer og kommer aldrig i git (`.gitignore`). Demoen laver en opdigtet udgave
(`demo/projekter/forbrug.py`).

## Siderne
- **Forbrug** (`index.html`): forbruget fordelt på grupper, kategorier eller modtagere for en måned, siden
  flytning, år til dato, 12 måneder eller alt, udviklingen pr. måned og posteringerne bag. Indtægter og opsparing
  tæller ikke som forbrug, og refusioner trækker fra i deres egen kategori.
- **Scenarier**: 1.000 simulerede forløb af din formue, måned for måned, ud fra budgettet i Sure. Det variable
  forbrug svinger som i din egen historik, og du kan lægge job efter studiet, sabbatår, engangsudgifter, inflation,
  rente og investering ind. Siden finder også den mindste ekstra opsparing, der giver 80 % chance for at nå målet.
- **SU-vagt**: holder årets indkomst op mod fribeløbet med SU-satserne for 2026 (offentlige satser fra su.dk), regner
  udbetalt løn om til indkomst før skat og viser, om det kan betale sig at fravælge SU i nogle måneder.

Scenarier og SU-vagt gemmer dine valg (trækprocent, lønsedler, scenarier) som `dashboard/public/state/<navn>.json`
gennem `PUT /dashboard-state/<navn>` i Sure (fra `custom/dashboard_tabs.rb`, kræver at du er logget ind i Sure).
Caddy viser filerne skrivebeskyttet på `/forbrug/state/`, så siderne kan læse dem, også når Sure er lukket. Svarer
Sure ikke, gemmes ændringen kun i browseren, indtil næste gang.

### config.json (valgfri)
Forbrug-sidens personlige indstillinger. `config.json` er i `.gitignore`; `config.example.json` viser formatet.

| Nøgle | Hvad |
|---|---|
| `flytning` | Måned (`ÅÅÅÅ-MM`) for periodeknappen "Siden flytning". Uden den er knappen væk |
| `modtagere` | `[mønster, navn]`-par, der gør bankteksten til et modtagernavn i fanen Modtagere, når Sure ikke selv har en modtager på posteringen. Mønstrene er regulære udtryk uden hensyn til store og små bogstaver, og det første, der passer, vinder |

Siderne regner med disse kategorinavne fra Sure: grupperne `Indtægter`, `Faste udgifter`, `Variable udgifter`,
`Opsparing og investering` og `Indflytning`, og kategorierne `SU` og `Løn`.

## Start og luk
Programmerne **Kompas** og **Luk Kompas** (to små apps i `/Applications`) kører `bin/kompas-start.sh` og
`bin/kompas-stop.sh`. De samler hele Kompas, ikke kun Sure:

- **kompas-start.sh** starter Caddy (`brew services`), slår Kompas' baggrundsjob til igen (LaunchAgents
  `local.kompas.karriere`, `.studie`, `.opdater` og Sures `local.sure.dashboard-export`), starter Colima og Sure,
  venter på at Sure svarer, beder Sure hente nye posteringer fra banken, laver et nyt udtræk (og igen to minutter
  senere, når banken er hentet, sammen med Excel-regnskaberne) og åbner `https://kompas.localhost/`.
- **kompas-stop.sh** laver et sidste udtræk, Excel-regnskaber og backup af Sures database, stopper Colima, stopper
  en Garmin- eller kalenderhentning, der er i gang, tager backup af Kompas' egne databaser
  (`$KOMPAS_HOME/bin/backup-data.sh`), slår baggrundsjobbene fra (så de også er slukket efter en genstart) og
  stopper Caddy. Data bliver i Docker-volumerne.

`bin/backup-db.sh` gemmer én `pg_dump` om dagen som `sure-ÅÅÅÅ-MM-DD.dump`, tjekker den med `pg_restore --list`,
før den erstatter noget, og beholder de nyeste 30. Hvordan du gendanner, står øverst i filen.

`bin/refresh-excel.sh` trækker månedstal og saldi ud af Sure (`scripts/monthly.csv`, `scripts/balances.csv`, ikke i
git) og bygger med `scripts/yearly_excel.py` og `scripts/yearly_overview.py` (kræver `openpyxl`: `pip install -r scripts/requirements.txt`) et Excel-regnskab
pr. år og en oversigt over alle år. Findes der en `Budget <år>.xlsx` med fanen *Månedsbudget*, kommer budgettet med
ved siden af årets tal. Den fil læses kun.

## Miljøvariabler
| Variabel | Standard | Bruges af |
|---|---|---|
| `KOMPAS_HOME` | `~/kompas` | `kompas-stop.sh` (Kompas' `bin/backup-data.sh` og `bin/opdater.sh`) |
| `SURE_BACKUP` | `~/Backup` | `backup-db.sh`: mappen til databasens backup. Gerne en mappe, der synkes til skyen |
| `SURE_EXCEL` | `~/Budget` | `refresh-excel.sh`: mappen med `Budget <år>.xlsx` og regnskaberne (`Tidligere år/` for de gamle år) |
| `SURE_PYTHON` | `python3` | `refresh-excel.sh`: den Python, der har `openpyxl` |

Apps og LaunchAgents får ikke din shells miljø. Vil du ændre en standard, så sæt variablen i appen eller i
LaunchAgentens `EnvironmentVariables`.
