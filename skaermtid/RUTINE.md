# Skærmtid-rutinen: ugens gennemgang

Instruktionerne til rutinen Skærmtid (`skaermtid-ugen`, Kompas · Skærmtid i Claude-appen), som kører mandag morgen
kl. 6.30, lige efter døgnskiftet kl. 6, så søndagen er med. Rutinen selv peger kun hertil, så den ændres her og
versioneres med projektet. Læs `README.md` for, hvordan projektet hænger sammen, og `OPSAETNING.md` for, hvordan
enhederne er sat op.

Du gør to ting: holder kategorierne og enhederne i orden, og fortæller brugeren kort, hvordan ugen gik med skærmtiden.
Skriv på dansk.

## Regler

- **Opfind aldrig tal.** Alle tal står færdigregnede i rapporten (trin 1). Læg ikke selv tal sammen, og skriv kun
  tal, der står dér. Mangler noget, så sig det.
- **Kategorier vælges kun gennem Skærmtid-serveren** (trin 2), præcis som når brugeren klikker på siden, så valget står
  under "Dine valg" og kan fortrydes. Ret aldrig `regler.json`, `valg.json` eller noget andet i hånden, og rør aldrig
  `grupper`, `doegn_skifter`, `sen_fra` eller `enheder`. Forslag til nye eller rettede regler skriver du i rapporten.
- **Kun det tydelige.** Vælg en kategori, når programmet eller siden klart hører til en af kategorierne i rapportens
  `kategorier` (fx en bank-app under Økonomi, en nyhedsside under Nyheder). Er du i tvivl, så foreslå i stedet.
  "Tæller ikke med" vælger du kun for systemting, der ikke er skærmtid (oplader, låseskærm, tilladelsesdialoger).
- **Browsertid uden adresse** kan ikke få én kategori og står derfor ikke i `ukategoriseret`, men for sig i
  `browser_uden_adresse`; nævn den kun under Vedligehold, hvis den er stor (fx at en computer mangler browserudvidelsen).
- Grupperne er bevidst ikke neutrale (se `GLOSSARY.md` i Kompas), men skriv uden moral: beskriv, hvad tallene viser.

## 1. Rapporten

```bash
/Applications/ActivityWatch.app/Contents/Resources/aw-sync --sync-dir ~/ActivityWatchSync sync >/dev/null 2>&1
/usr/bin/python3 ~/kompas/skaermtid/skaermtid.py rapport
```

Den første henter de andre enheders data ind (fejler den, så fortsæt og sig det). Den anden bygger Skærmtid forfra
og skriver JSON for den sidste hele uge (`uge`, `mandag`, `soendag`):

- `forrige_uge` og `ugen_foer`: timer, sen skærmtid, `grupper`, `kategorier`, `enheder` (timer pr. enhed), `tjek`
  (korte tjek, åbninger og oplåsninger, i alt og pr. dag med telefondata), `samtidig_timer` og `dage_med_data`.
  Fra 20. okt. tæller tid på flere enheder på én gang én gang i `timer`, `grupper` og `kategorier`, mens `enheder`
  er hver enheds fulde tid; enhederne tilsammen kan derfor give mere end `timer`, og forskellen kommer af
  `samtidig_timer`. Sammenlign ikke `enheder`-summen med `timer`, og kald ikke en stigning i `samtidig_timer` mere
  skærmtid. Reviews før 20. okt. er regnet med enhederne lagt sammen.
- `enheder_pr_dag`: timer pr. hel dag pr. enhed og grupperne pr. hel dag.
- `faelles`: kun de fælles hele dage (telefon og mindst én computer): fordelingen mellem enhederne og
  `samtidig` (telefonens tid, mens en computer var i brug, og hvad den gik til). `dage` er antallet; 0 betyder ingen.
- `stoerste`: ugens største programmer og sider med kategori og `kilde` (hvorfor de har kategorien).
- `kun_titel`: det, der kun fik sin kategori ud fra en vinduestitel. Tjek, om det ser rigtigt ud.
- `ukategoriseret` (de seneste 14 dage, størst først, med `type` og `noegle`), `ukategoriseret_antal`.
- `browser_uden_adresse`: browsertid uden adresse de seneste 14 dage, pr. enhed og browser (timer, enhedens fulde tid).
- `enheder` (hvornår hver enhed sidst sendte data), `kategorier` (dem, der kan vælges) og `valg` (det, der allerede
  er valgt).

Svarer ActivityWatch ikke, slutter kommandoen med en fejl. Så kan du intet gøre: skriv det øverst i rapporten og
gem den alligevel (trin 4).

## 2. Kategorier

For hvert program eller hver side i `ukategoriseret` med mindst 1 minut, som ikke er browsertid uden adresse:

- Hører det tydeligt til en kategori, så vælg den:
  ```bash
  curl -s -H "Origin: https://kompas.localhost" -H "Content-Type: application/json" \
    -d '{"type": "app", "noegle": "dk.dba.android", "navn": "DBA", "kategori": "Indkøb"}' \
    https://kompas.localhost/skaermtid/api/valg
  ```
  `type`, `noegle` og `navn` står i rapporten. "Tæller ikke med" er `"ignorer": true` i stedet for `kategori`.
  Svaret har `"gemt": true`; ellers står fejlen i `fejl`. Svarer serveren ikke, så foreslå i stedet og sig det.
- Er du i tvivl, så skriv det som forslag: navn, hvor meget tid, og hvilken kategori du ville vælge og hvorfor.

Gå `kun_titel` igennem. Ser noget forkert ud (fx en video om økonomi under Video & streaming), så skriv det som
forslag. Valg på titel-tid kan ikke laves, så forslaget er en ny eller rettet regel i `regler.json`.

## 3. Enhederne

En enhed i `enheder`, der ikke har sendt data i over to døgn (`sidst`), er faldet ud. Sig hvilken, og hvor man tjekker:
Telefonen: batterioptimering, Syncthing-Fork og Sync Settings i ActivityWatch-appen. Stationær og Bærbar: at
ActivityWatch og Syncthing kører, og at aw-sync kører hvert 30. minut. Se "Hvis noget ikke virker" i `OPSAETNING.md`.

## 4. Gennemgangen

Skriv markdown, højst ca. 200 ord, med disse afsnit:

**Uge NN i én sætning** — det vigtigste ved ugens skærmtid.

**Tallene** — 3–5 punkter: produktiv tid mod ugen før, passiv tid, korte tjek og oplåsninger pr. dag, sen skærmtid,
telefonen samtidig med computeren (kun når `faelles.dage` er over 0), og den enhed, der fyldte mest. Hvert punkt med
tallet og ugen før, når den findes ("produktiv 6,8 t mod 0,4 t"). Er `ugen_foer` tom, så sig, at der ingen
sammenligning er endnu.

**Vedligehold** — hvad du valgte (navn → kategori), hvad du foreslår, og enheder, der er faldet ud. Ingenting? Så
én linje om det.

**Én ting at prøve** — én lille, konkret ting, der følger af tallene (fx "telefonen i en anden stue under selvstudie
tirsdag og torsdag, hvor de korte tjek toppede"). Ikke generelle råd.

Gem gennemgangen som `~/kompas/skaermtid/rapporter/<uge>.md` (uge fra rapportens `uge`, fx `2026-W43.md`) og samme
indhold som `~/kompas/skaermtid/rapporter/<uge>.json`, som Skærmtid-siden viser:

```json
{
  "saetning": "Uge NN i én sætning (uden overskriften)",
  "tal": ["ét punkt pr. tal"],
  "vedligehold": ["ét punkt pr. valg, forslag eller enhed"],
  "en_ting": "Én ting at prøve",
  "forbehold": ["kun hvis noget manglede, fx at aw-sync fejlede"],
  "genereret": "tidspunktet, fx 2026-10-26T06:34"
}
```

Kør så `/usr/bin/python3 ~/kompas/skaermtid/skaermtid.py byg`, så siden viser den. Vis hele gennemgangen som dit
svar, og send én kort push-notifikation med ugens sætning, hvis et værktøj til det er tilgængeligt.

Commit ikke. `valg.json` og `rapporter/` i `~/kompas/skaermtid` er personlige og ligger ikke i git.
