# Økonomi

Kompas' økonomidel bygger på [Sure](https://github.com/we-promise/sure), et open source-budgetprogram (AGPL-3.0),
der kører i Docker på din egen Mac og henter bankens posteringer. Sure selv er **ikke** med her. Mappen indeholder
kun det, der ligger rundt om den: tre egne sider (**Forbrug**, **SU-vagt** og **Gennemgang**) på `/forbrug/` i
Kompas, et udtræk fra Sures database til siderne, månedens gennemgang, to små tilføjelser, der monteres ind i Sure,
og scripts, der starter og lukker det hele.

## Hvad er Sure, og hvad er dit eget
| | Hvad | Hvor |
|---|---|---|
| Sure | Selve budgetprogrammet: konti, posteringer, kategorier, regler, budgetter, mål og rapporter. Kompas viser Sures sider (Oversigt, Transaktioner, Plan) i sin ramme. Rapporter findes stadig i Sure, men står ikke i Kompas' menu, fordi Forbrug dækker det samme | `compose.yml` og `.env` fra Sures repo (ikke her) |
| Udtrækket | `dashboard/export.sh` laver `dashboard/public/data.json` fra Sures database | `dashboard/` |
| Siderne | Forbrug, SU-vagt og Gennemgang. Rene HTML-filer uden byg; `common.js`/`common.css` deles af SU-vagt og Gennemgang | `dashboard/public/` |
| Månedens gennemgang | `dashboard/gennemgang.py` regner tallene, rutinen Kompas · Økonomi skriver teksten (`RUTINE.md`) | `dashboard/`, `gennemgang/` (ikke i git) |
| Tilføjelser i Sure | `custom/dashboard_tabs.rb` sætter Forbrug og SU-vagt ind i Sures venstremenu og gemmer sidernes indstillinger. `custom/sure_tweaks.rb` retter tre småting i Sure (se toppen af filen) | `custom/`, monteres af `compose.override.yml` |
| Drift | Start, luk, backup af databasen, Excel-regnskaber og tags (`scripts/tag.rb`) | `bin/`, `scripts/` |

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
| `accounts` | Aktive konti med saldo |
| `goals` | Aktive opsparingsmål med dato og de konti, der hører til målet |
| `budgets` | Månedsbudgetter: forbrug, forventet indkomst og budgettet for gruppen "Variable udgifter" |
| `budget_categories` | Hver kategoris eget budget pr. måned (underkategorierne lægger sig til deres gruppe), til månedens gennemgang |
| `faste` | Faste betalinger, fundet i posteringerne (se nedenfor), og hvad de koster pr. måned |
| `categories` | Alle kategorier med deres gruppe (overkategori), til at rette en postering på Forbrug |
| `transactions` | Alle posteringer med id, dato, beløb (udgifter positive, som i Sure), tekst, konto, kategori, gruppe (overkategori), modtager og tags |

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
  tæller ikke som forbrug, og refusioner trækker fra i deres egen kategori. Søjlerne i udviklingen er delt som
  fordelingen ovenfor, med samme farver (resten som Andet). Står en postering i den forkerte kategori, kan den rettes
  direkte på siden. Panelet **Uge for uge** viser det variable forbrug for de seneste 12 uger, som Overblik har regnet
  det til ugereviewet (`/form/liv.json`); siden regner ikke selv, og kan filen ikke læses, er panelet skjult.
  Panelet **Rejser og begivenheder** samler forbruget pr. tag i Sure, uanset periode. Klikker du på et tag, viser
  hele siden kun det tag, fra dets første til dets sidste måned; en rejses samlede pris er netto, så penge, venner
  har betalt tilbage, trækkes fra. Du tagger selv i Sure eller med `scripts/tag.rb` (prøvekørsel først, se toppen af
  filen). Panelet **Faste betalinger** viser, hvad udtrækket har fundet, med næste dato og prisændringer, og et klik
  viser betalingens posteringer. De tre paneler kan foldes sammen; browseren husker, hvad du har åbent.
- **SU-vagt**: holder årets indkomst op mod fribeløbet med SU-satserne for 2026 (offentlige satser fra su.dk), regner
  udbetalt løn om til indkomst før skat og viser, om det kan betale sig at fravælge SU i nogle måneder.
- **Gennemgang** (`gennemgang/`): månedens gennemgang med månedens tal, budget mod forbrug pr. kategori og
  forslag til nyt budget. Siden viser kun det, der er gemt (se Månedens gennemgang); den ændrer intet i Sure.

SU-vagt gemmer dine valg (trækprocent, lønsedler) som `dashboard/public/state/<navn>.json`
gennem `PUT /dashboard-state/<navn>` i Sure (fra `custom/dashboard_tabs.rb`, kræver at du er logget ind i Sure).
Caddy viser filerne skrivebeskyttet på `/forbrug/state/`, så siderne kan læse dem, også når Sure er lukket.
Indtil noget er gemt, lægger `export.sh` en tom `{}` dér (siderne læser den som "intet gemt"), så browseren ikke
logger en 404 ved hvert besøg; en fil, Sure har skrevet, erstattes aldrig. Svarer
Sure ikke, gemmes ændringen i browseren, og et banner siger hvorfor (ikke logget ind, Sure lukket, intet net). Den
sendes først til Sure, når du trykker "Prøv igen" eller "Gem på serveren"; lokale tal sendes aldrig af sig selv.

Forbrug retter en posterings kategori gennem `PUT /dashboard-category/<id>` i Sure (samme fil, samme login). Det er
de samme trin som Sures egen formular: kategorien låses, så regler og banksync lader den være, og kontoen
synkroniseres igen. Siden viser rettelsen med det samme; næste udtræk har den med.

### Faste betalinger
Sure finder selv kun få gentagne betalinger, så `export.sh` finder dem i posteringerne. En modtager er Sures modtager
eller bankteksten uden `VD`/`BS` og kortnumre, inden for én kategori. Månedlig: betalt i mindst 3 af de 6 måneder op
til seneste betaling og højst 1,5 gang om måneden i snit. Årlig: alle betalinger 300-400 dage fra hinanden. Begge
steder skal de sidste tre betalinger (årlige: to) ligge inden for 15 % af deres median, så en butik, du tilfældigt
kommer i hver måned, falder fra. En betaling er aktiv, til seneste betaling er over 45 dage gammel (årlige: 400), og
stoppede bliver stående i et år. `pr_maaned` tæller de årlige med en tolvtedel.

### config.json (valgfri)
Forbrug-sidens personlige indstillinger. `config.json` er i `.gitignore`; `config.example.json` viser formatet.

| Nøgle | Hvad |
|---|---|
| `flytning` | Måned (`ÅÅÅÅ-MM`) for periodeknappen "Siden flytning". Uden den er knappen væk |
| `modtagere` | `[mønster, navn]`-par, der gør bankteksten til et modtagernavn i fanen Modtagere, når Sure ikke selv har en modtager på posteringen. Mønstrene er regulære udtryk uden hensyn til store og små bogstaver, og det første, der passer, vinder |

Siderne regner med disse kategorinavne fra Sure: grupperne `Indtægter`, `Faste udgifter`, `Variable udgifter`,
`Opsparing og investering` og `Indflytning`, og kategorierne `SU` og `Løn`.

## Månedens gennemgang
Rutinen Kompas · Økonomi (`okonomi-maaneden`) kører den 1. i måneden og gennemgår måneden før. Instruktionerne står i
`RUTINE.md`. Rutinen ændrer intet i Sure; det, der bør ændres, skriver den som forslag.

- `python3 dashboard/gennemgang.py rapport [--maaned ÅÅÅÅ-MM] [--gem]` regner hele månedens tal som JSON (standard:
  sidste måned) ud fra `data.json` alene, så det virker, mens Sure er slukket. Forbrug tælles som på Forbrug, pr.
  kalendermåned som Sures budgetter; SU tæller for den måned, den er til. Med `--gem` kommer tallene i
  `gennemgang/<maaned>.tal.json`. Rutinen lægger ikke selv tal sammen.
- Rutinen skriver teksten som `gennemgang/<maaned>.md` og `gennemgang/<maaned>.json`.
- `python3 dashboard/gennemgang.py byg` samler det hele i `dashboard/public/gennemgang/gennemgange.json`, som siden
  Gennemgang læser.

Forslag til budgettet står kun, hvor snittet af de tre måneder ligger mindst 50 kr. og 20 % fra budgettet, og aldrig
for faste udgifter eller når kun én af månederne havde forbrug. `gennemgang/` og `gennemgange.json` er dine rigtige
tal og kommer aldrig i git (`.gitignore`). Demoen laver opdigtede gennemgange med samme kode.

## Start og luk
Programmet **Kompas** (en lille app i `/Applications`) kører `bin/kompas-start.sh`. Der er ingen app til at lukke;
kør `bin/kompas-stop.sh` i en terminal, når alt skal slukkes. De samler hele Kompas, ikke kun Sure:

- **kompas-start.sh** starter Caddy (`brew services`); har Tailscale taget port 443, mens Caddy var nede, får Caddy
  porten først, og Tailscale sættes på igen bagefter. Så slår den Kompas' baggrundsjob til igen (LaunchAgents
  `local.kompas.studie`, `.sprog`, `.skaermtid`, `.opdater` og Sures `local.sure.dashboard-export`), starter Colima og Sure,
  venter på at Sure svarer, beder Sure hente nye posteringer fra banken, laver et nyt udtræk (og igen to minutter
  senere, når banken er hentet, sammen med Excel-regnskaberne og backup (`$KOMPAS_HOME/bin/backup-data.sh`)) og åbner `https://kompas.localhost/`. Hvert trin logges med tidspunkt i
  `dashboard/kompas-start.log`, så en start, der går i stå, kan ses bagefter.
- **kompas-stop.sh** laver et sidste udtræk, Excel-regnskaber og backup af Sures database, stopper Colima, stopper
  en Garmin- eller kalenderhentning, der er i gang, tager backup af Kompas' egne databaser
  (`$KOMPAS_HOME/bin/backup-data.sh`), slår baggrundsjobbene fra (så de også er slukket efter en genstart) og
  stopper Caddy. Data bliver i Docker-volumerne.

`bin/backup-db.sh` gemmer én `pg_dump` om dagen som `sure-ÅÅÅÅ-MM-DD.dump`, tjekker den med `pg_restore --list`,
før den erstatter noget, og beholder de nyeste 30. Den køres af Kompas' `bin/backup-data.sh` og af `kompas-stop.sh`.
Hvordan du gendanner, står øverst i filen.

`bin/refresh-excel.sh` trækker månedstal og saldi ud af Sure (`scripts/monthly.csv`, `scripts/balances.csv`, ikke i
git) og bygger med `scripts/yearly_excel.py` og `scripts/yearly_overview.py` (kræver `openpyxl`: `pip install -r scripts/requirements.txt`) et Excel-regnskab
pr. år og en oversigt over alle år. Findes der en `Budget <år>.xlsx` med fanen *Månedsbudget*, kommer budgettet med
ved siden af årets tal. Den fil læses kun.

## Miljøvariabler
| Variabel | Standard | Bruges af |
|---|---|---|
| `KOMPAS_HOME` | `~/kompas` | `kompas-start.sh` og `kompas-stop.sh` (Kompas' `bin/backup-data.sh` og `bin/opdater.sh`) |
| `SURE_BACKUP` | `~/Backup` | `backup-db.sh`: mappen til databasens backup. Gerne en mappe, der synkes til skyen |
| `SURE_EXCEL` | `~/Budget` | `refresh-excel.sh`: mappen med `Budget <år>.xlsx` og regnskaberne (`Tidligere år/` for de gamle år) |
| `SURE_PYTHON` | `python3` | `refresh-excel.sh`: den Python, der har `openpyxl` |

Apps og LaunchAgents får ikke din shells miljø. Vil du ændre en standard, så sæt variablen i appen eller i
LaunchAgentens `EnvironmentVariables`.
