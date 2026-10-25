# skaermtid

Projektet bag området Skærmtid i Kompas: hvor tiden går hen på Mac, stationær, bærbar og telefon, regnet ud fra
ActivityWatch. Beregningen ligger her; siden viser kun tallene. Alt kører lokalt.

## Hvor tallene kommer fra

[ActivityWatch](https://activitywatch.net) kører på hver enhed og logger det aktive vindue (Mac, Windows) eller
den åbne app (Android) sammen med, om du er væk fra skærmen. De andre enheders data havner i Mac'ens
ActivityWatch gennem aw-sync og Syncthing (se Enheder nedenfor). Projektet læser derfor kun ét sted:
den lokale server på `http://localhost:5600`.

| Enhed | Hvad tæller | Hjemmesider |
|---|---|---|
| Computer | tid, hvor aw-watcher-afk siger, at du er aktiv | kræver ActivityWatch' browserudvidelse (Edge: fra Chrome Web Store); uden den matches fanens titel |
| Telefon | tid med skærmen tændt (ingen afk-måler) | kun appen, ikke sider |

`slags` i `regler.json` (`computer` eller `telefon`) afgør, hvordan en enhed tæller. En computer med vinduer, men uden
afk-data i perioden, tæller ikke (aktiv tid kan ikke afgøres); siden siger det, så en afk-måler, der ikke kører eller
ikke synkes, bliver opdaget. En vært uden `slags` (fx en ukendt enhed) er telefon, når den ingen afk-bucket har.

- **Døgnet skifter kl. 06.00** (samme som ActivityWatch på Mac'en), så en nat kl. 01 hører til aftenens dag. **Sen skærmtid** er tiden fra kl. 23.00 til
  døgnet skifter. Begge står i `regler.json` (`doegn_skifter`, `sen_fra`).
- **Tid på flere enheder på én gang tæller én gang** i alt, i grupperne, kategorierne og programmerne (`_fordel`):
  er telefonens skærm tændt, går tiden til telefonen (computerens "aktive" tid er dér som regel kun de 3 minutter,
  afk-måleren venter); ellers deles den ligeligt mellem computerne i brug. Hver enhed viser sin fulde tid
  (`dage[].enheder`, enhederne på siden), så enhederne tilsammen kan give mere end i alt; `samtidig_timer` (pr. dag og
  periode) er tiden med mere end én enhed i brug. Telefonen ved siden af computeren står stadig for sig under enhederne.
  Senere kan aw-watcher-input (tastetryk og klik pr. interval) afgøre, hvilken computer du faktisk brugte; den kører
  endnu ikke på nogen af dem.
- Låseskærm, notifikationer og startmenu (`ignorer` i `regler.json`) tæller slet ikke.
- **Kun summer forlader ActivityWatch:** timer pr. dag, enhed, kategori og program (eller hjemmesidens vært), og
  dagens forløb (`dage[].forloeb`, de seneste 28 dage): hvert kvarter med mindst 5 minutters skærmtid står med sin
  største kategori og gruppe, nabokvarterer med samme kategori lagt sammen. Siden viser det som **Dagens forløb**
  (de seneste 7 døgn, kl. 6 til kl. 6, farvet efter gruppe med samme farver som Planlagt mod faktisk på Ugereview),
  og Overblik (`overblik`) bruger det til planlagt mod faktisk.
  Vinduestitler bruges alene til at matche en regel og skrives aldrig.

## Kategorier: regler.json

`regler.json` (dine enheder, kategorier og regler) og `valg.json` (dine valg på siden) er personlige og ligger ikke i
git. Uden dem bruges `regler.example.json` og `valg.example.json`, så projektet, testene og demoen virker i et frisk
klon. Kopiér `regler.example.json` til `regler.json`, og sæt dine egne værtsnavne i `enheder`; `valg.json` skriver
serveren selv ved dit første valg (med eksemplets valg, som du kan fortryde).

Den første regel, der passer, bestemmer kategorien; alt andet er **Ukategoriseret**. Reglerne prøves i to gennemløb:
først alle regler med `app`, `domaene` eller `sti`, i rækkefølge; så reglerne med `titel` alene. En svag titelregel i en
tidlig kategori kan derfor aldrig slå en programregel i en senere (Mail med "Moodle" i titlen er Kommunikation, ikke
Studie). En regel er et eller flere
mønstre (regulære udtryk, uden forskel på store og små bogstaver), som alle skal passe:

| Felt | Matches mod | Bemærk |
|---|---|---|
| `app` | programmets navn: Mac `Microsoft Edge`, Windows `msedge.exe`, Android pakkenavnet (`com.instagram.android`) eller appens navn | samme regel dækker alle enheder med `\|` |
| `domaene` | hjemmesidens vært (`www.youtube.com`) | kun med browserudvidelsen |
| `sti` | resten af adressen efter værten, fx `/#/studie/` på Kompas | |
| `titel` | vinduets titel | kun når der **ikke** er en adresse, så en kendt adresse aldrig overtrumfes af titlen; alene prøves den sidst |

Reglerne ligger i projektet og ikke i ActivityWatch, fordi ActivityWatch ikke synkroniserer sine indstillinger
mellem enheder, og fordi en rettet regel så gælder bagud ved næste byg. `browsere` siger, hvilke programmer der er
browsere (deres tid deles efter fanens adresse); navnene står med ordgrænser, så fx "arc" ikke rammer "searchbox".

Telefonens browser melder kun et øjeblik, når fanen skifter, og kun værten (`github.com`). En fane gælder derfor på
telefonen, til den næste kommer, højst 30 minutter, inden for browserens skærmtid; søgefeltets tekst tælles ikke som
adresse.

## Grupper og korte tjek

Siden viser først **grupper**, som samler kategorierne efter, hvad tiden er: Produktiv, Passiv (uproduktiv, passiv
underholdning: Sociale medier, Video & streaming og Nyheder), Gaming og Praktisk (`grupper` i `regler.json`; hver
kategori i præcis én gruppe, det tjekker en test). En gruppe foldes ud til sine kategorier, og en kategori til sine
programmer og sider.

Tjek måles som antal, ikke som tid: det meste af tiden på sociale medier er lange sessioner, ikke tjek, så korte tjek
og oplåsninger pr. dag (nedenfor) er målet for tjek, og tiden tæller under Passiv.

En regel med både `domaene` og `titel` kræver begge, også når adressen kendes. Sådan bliver YouTube-videoer med fx
"CS50", "lecture" eller "forelæsning" i titlen Studie, mens resten af YouTube er Video & streaming. Titlen er fanens
egen, når browserudvidelsen kender den, ellers vinduets. YouTube-appen på telefonen sender ingen titel og kan ikke deles.

**Korte tjek** tælles kun på telefonen (`korte_tjek` i `regler.json`): en åbning er sammenhængende tid i samme app
(pauser under 10 sekunder lægges sammen; et skift til en anden app eller hjemmeskærmen afslutter den), og åbninger
af apps i Sociale medier og Nyheder under 60 sekunder er korte tjek. Ved siden af står oplåsningerne fra
Android-appens `aw-watcher-android-unlock`. Tallene står pr. dag i `dage[].tjek` og pr. periode, også pr. dag med
telefondata, i `perioder.*.tjek`; diagrammet viser korte tjek som stiplet linje.

## Siden

Alt står på én side, `/skaermtid/`, i denne rækkefølge: enhedernes status (sidst set, antal hele dage og browsertid
uden adresse), nøgletal, ugens gennemgang (uge og datoer), Dag for dag, Dagens forløb, **Hvor tiden går hen** (grupper,
kategorier og dine valg), enhederne (nedenfor), Dine valg, Reglerne og nederst **Mangler en kategori** (foldet
sammen; flisen Ukategoriseret springer derned og folder den ud). Perioden (I dag, Denne uge, 4 uger) er fælles: et
klik i ét panel skifter alle dem, der har den. `/skaermtid/#enheder` springer ned til enhederne.

Enhederne (feltet `enhedsside` i `skaermtid.json`):

- **Hvad du bruger hver enhed til:** en bjælke pr. enhed delt i grupperne (Timer: på samme akse; Andel: hver bjælke
  er hele enhedens tid), timer i perioden, timer pr. hel dag og de fem mest brugte programmer og sider. Der er ingen
  visning pr. gruppe på tværs af enhederne: det ville kræve, at siden lagde enhedernes tid sammen, og samtidig tid ville
  tælle to gange. Enhederne har farver, som ingen gruppe har.
- **Telefonen ved siden af computeren:** telefonens tid, mens en computer samtidig var aktiv, hvad telefonen blev
  brugt til, hvad computeren imens blev brugt til, og fordelingen mellem enhederne de samme dage.
- **Døgnrytme:** minutter pr. klokketime pr. enhed i gennemsnit pr. hel dag, de seneste 4 uger, fra døgnskiftet.
- **Uge for uge:** timer pr. hel dag pr. enhed, de seneste 8 uger.

Enhederne har data fra forskellige dage. Derfor bruger gennemsnit kun **hele dage**: i dag tæller ikke, fordi den
ikke er slut, og en enheds første dag tæller ikke, hvis dens første data kom mere end fire timer efter døgnskiftet.
Alt, der sammenligner enhederne, bruger kun **fælles hele dage**, hvor telefonen og mindst én computer har data,
undtagen "I dag", som er dagen indtil nu for alle. Under 7 hele dage (`FORELOEBIG_UNDER`) mærkes tallene foreløbige.

## Dine valg på siden: valg.json

På siden kan hver kategori foldes ud, så du ser, hvad der tæller i den, og hvorfor: **dit valg**, en regel på
**program** eller **side**, eller kun **vinduestitel** (den svageste; markeret gul). Ved hvert program og hver side, også
under **Mangler en kategori** (de seneste 14 dage), vælger du kategori, **Tæller ikke med** eller **Fjern mit valg**.
**Dine valg** viser alt, du har valgt, med Fortryd.

Et valg gælder præcis ét program (`app`: pakkenavnet på telefonen, programmets navn på computerne) eller én side
(`domaene`: værten), på alle enheder og bagud. Valg går forud for reglerne. En browser kan ikke få én kategori; dens
tid uden adresse vælges ikke, kun de enkelte sider. Derfor står den ikke under Mangler en kategori (`ukategoriseret`),
men for sig pr. enhed i `browser_uden_adresse` (de seneste 14 dage, hver enheds fulde tid), som enhedernes status
øverst viser ("Telefon · … · 54 min i Edge uden adresse").

Valgene gemmes i `valg.json` af `server.py` (Skærmtid-serveren, 127.0.0.1:8770, `/skaermtid/api/` bag Caddy,
LaunchAgent `local.kompas.skaermtid`, log `~/.kompas/skaermtid-server.log`), som bagefter bygger siden igen, så valget
ses med det samme. Serveren skriver kun `valg.json`; `regler.json` rettes kun i hånden. Den tager kun imod fra
`https://kompas.localhost` og kun kendte kategorier.

På telefonen: `https://<mac>.<tailnet>.ts.net/skaermtid/` gennem Tailscale (Caddys blok på 127.0.0.1:8768); serveren
tager imod valg derfra, fordi `bin/tailscale.sh` sætter adressen i `SKAERMTID_ORIGINS` i LaunchAgent'en. Bærbaren
når Skærmtid i hele Kompas på samme adresse med `:8443`, som også står i `SKAERMTID_ORIGINS`.

Test mod en kopi, aldrig de rigtige filer:

```bash
SKAERMTID_PORT=8771 SKAERMTID_VALG=/tmp/x/valg.json SKAERMTID_UD=/tmp/x/ud /usr/bin/python3 server.py
```

`enheder` giver værtsnavnene (ActivityWatch' `hostname`) deres navn på siden: Mac, Stationær, Telefon, Bærbar. `vaert` er
ét navn eller en liste, for aw-sync giver en synkroniseret enheds vinduer dens værtsnavn (små bogstaver, punktum
bliver `_`), men dens browserfaner og telefonens app dens enheds-id; alle navnene lægges sammen til én enhed, før
der regnes, så faner og vinduer kan klippes mod hinanden. Buckets på Mac'en selv uden vært (`unknown`, fx
browserudvidelsens) regnes som Mac'en. En enhed uden `vaert` forventes, men har ingen data endnu; en vært, der
sender data uden at stå her, vises som ukendt enhed, så den kan få et navn.

## Brug

```bash
/usr/bin/python3 skaermtid.py byg                  # ~/.kompas/skaermtid/: skaermtid.json, kompas.json, siden
/usr/bin/python3 skaermtid.py byg --ud /tmp/x --dage 14 --server http://localhost:5600
/usr/bin/python3 -m unittest discover -s tests     # uden ActivityWatch
```

Kun standardbiblioteket, så macOS' egen `/usr/bin/python3` er nok; ingen venv. Alt regnes forfra for de seneste
56 dage ved hvert byg (samme sammenligningsgrundlag som Overblik). `dage` (og dermed `uger`) starter ved den
første dag med data: en dag før den mangler, for uden data er tiden ukendt, ikke 0 timer; Dag for dag viser dagene
derfra, højst de seneste 28. Svarer ActivityWatch ikke, skrives intet:
de gamle filer bliver stående, og kommandoen slutter med exit 1, så Forbindelser viser trinnet som fejlet. Svarer
den ikke, når du vælger på siden, gemmes valget alligevel og slår igennem ved næste byg.

Kompas' opdatering hvert 30. minut (`~/kompas/bin/opdater.sh`) kører først trinnet `aw-sync` (de andre enheder ind)
og så trinnet `skaermtid` (byg). Siden ligger på https://kompas.localhost/#/skaermtid/ (Caddy serverer
`~/.kompas/skaermtid`) og står i menuen under Form & fokus (`omraade` i `KOMPAS`), efter coachs sider.

## Drift

- ActivityWatch er et loginelement og skal altid køre, også når Kompas er lukket; "Luk Kompas" rører den ikke.
  Den skal have tilladelsen **Tilgængelighed** (Systemindstillinger → Anonymitet og sikkerhed) for at se
  vinduer.
- Al historik ligger i `~/Library/Application Support/activitywatch/aw-server/peewee-sqlite.v2.db`, som
  `~/kompas/bin/backup-data.sh` tager med i den daglige backup (`activitywatch-<dato>.db.gz`). Gendan-kommandoen
  står øverst i scriptet.
- `skaermtid.json` er det eneste, projektet skriver; det kan altid bygges igen fra ActivityWatch.

## Enheder: Mac, Stationær, Telefon og Bærbar

Opsætningen trin for trin, også for de to andre enheder, står i `OPSAETNING.md`. Sådan hænger det sammen:

- **ActivityWatch kører på hver enhed** og logger lokalt. Bærbaren (Linux med Hyprland) bruger awatcher i stedet for
  ActivityWatch' egne målere, som ikke kan se Wayland-vinduer. Windows får browserudvidelsen til Edge fra Chrome Web
  Store; Android-appen (fra 0.14.0) har sync indbygget og skal have "Adgang til brugsdata" og være undtaget
  batterioptimering.
- **Syncthing holder én mappe ens** på alle tre enheder: `~/ActivityWatchSync` på Mac'en (Syncthing-mappen
  `aw-sync`, Syncthing.app fra Homebrew, starter ved login, side på http://127.0.0.1:8384),
  `C:\Users\<navn>\ActivityWatchSync` på stationæren (Syncthing Windows Setup) og
  `Intern lagerplads/ActivityWatchSync` på telefonen (Syncthing-Fork). Ikke OneDrive: macOS lader ikke et
  launchd-job læse OneDrive-mappen, så Mac'en kunne aldrig hente de andres data. Mappens `.stignore` har
  `(?d)*.tmp`, så aw-syncs midlertidige filer ikke flyttes.
- **aw-sync lægger hver enheds data i mappen og henter de andres ind**: hver enhed skriver kun i sin egen
  undermappe `<vært>/<enheds-id>/test.db`, så der er aldrig konflikter. På Mac'en kører
  `/Applications/ActivityWatch.app/Contents/Resources/aw-sync --sync-dir ~/ActivityWatchSync sync` fra
  opdater.sh (trinnet `aw-sync`), på stationæren samme kommando fra Opgavestyring hvert 30. minut, og
  telefonens app skriver selv. Det skal være bare `aw-sync sync`: med `--mode`, `--buckets` m.fl. bruger den
  et andet mappelayout og ser hverken telefonen eller de andre; `aw-sync daemon` kan heller ikke (derfor er
  den ikke slået til i ActivityWatch). `aw-sync --sync-dir ~/ActivityWatchSync status` forklarer pr. fil, hvad
  der blev hentet og hvorfor ikke.
- Hentede buckets hedder `…-synced-from-<vært>` i Mac'ens ActivityWatch og tæller som enheden i `regler.json`
  (se `enheder` ovenfor). De er med i backuppen af ActivityWatch' database, og de skal behandles som
  skrivebeskyttede: næste sync skriver over lokale rettelser.
- Syncthing-id'er er offentlige fingeraftryk; Mac'ens skal bruges i `OPSAETNING.md`. Ingen af delene bruger konti.

## Rutinen: Kompas · Skærmtid

Rutinen `skaermtid-ugen` (Claude-appen, mandag kl. 6.30, lige efter døgnskiftet, så søndagen er med) følger
`RUTINE.md`. Den kører `skaermtid.py rapport` (bygger og skriver den sidste hele uge mod ugen før som JSON, så den
ikke selv lægger tal sammen), vælger kategori for det tydelige gennem Skærmtid-serveren (så det står under "Dine
valg" og kan fortrydes), foreslår resten, siger til, hvis en enhed er faldet ud, og gemmer ugens gennemgang i
`rapporter/<uge>.md` og `.json`. Den nyeste vises øverst på Skærmtid-siden. Den committer ikke; `valg.json` og
`rapporter/` er personlige og ligger ikke i git.

## Senere

Skærmtid som kilde i Overblik (`kilder.py`), så ugereviewet kan finde afvigelser og teste hypoteser som
"sover du mindre i uger med meget sen skærmtid?". Det kræver 8 ugers data til afvigelser og 18 til sammenhænge.
