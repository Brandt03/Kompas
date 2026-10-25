# overblik

Projektet bag ugereviewet i Overblik: én række pr. uge på tværs af træning,
økonomi og studie, så ugereviewet kan lede efter sammenhænge på faste tal i
stedet for gæt.

Som i garmin-coach ligger beregningerne i Python. Modellen får den færdige
ugetabel og fortolker den. Alt kører lokalt.

## Kilder

| Kilde | Hvorfra | Kolonner |
|---|---|---|
| garmin | `~/.garmin-coach/coach.db` (læses kun) | søvn, HRV, hvilepuls, stress, skridt, træning |
| sure | `~/kompas/okonomi/dashboard/public/data.json` | take-away, café/bar, dagligvarer, variable køb |
| kalender | garmin-coach's `calendar_events` | undervisning (begivenheder, garmin-coach har givet en `fag_kode`) og selvstudie (CalTask-begivenheder der starter med `Selvstudie ·`) |
| skærmtid | `~/.kompas/skaermtid/skaermtid.json` (læses kun) | endnu ingen ugekolonner; sen skærmtid pr. aften i `naetter` og dagens forløb i `dagsplan` (se På Kompas) |
| studie | `~/.kompas/studie/studie.json` (læses kun) | endnu ingen ugekolonner; svar pr. dag i Træning og På farten i `dagsplan` |

**En tom celle (`–`) betyder at kilden ikke dækker ugen, ikke 0.** Selvstudie
før `LIV_SELVSTUDIE_FRA`, dagen logningen i CalTask begyndte, er ukendt. Undervisning før kalendervinduet er ukendt.

Kalenderen i garmin-coach dækker kun ca. 14 dage bagud. Derfor overskriver en
tom værdi aldrig et gemt tal: en uge beholder sin undervisning efter at være
faldet ud af vinduet, så længe `liv opdater` har kørt mens den var inden for.

Sures eksport opdateres kun mens Sure kører. `liv status` viser hvor friske
kilderne er: Garmin og Sure efter `data_til`, kalenderen efter hvornår den sidst
blev hentet. Den tid gemmer garmin-coach ikke (endnu: `sync_state`
`last_calendar_sync` bruges, hvis den findes), så indtil da er det hvornår
kalenderens indhold sidst ændrede sig. Kalendervinduet rykker en dag frem ved
hver hentning, så det sker normalt dagligt; i en ferie uden nye begivenheder kan
en hentet kalender stå som gammel. En kilde er gammel efter 3 dage.

Hver kilde læses for sig. Fejler én (fx en Sure-eksport i et andet format),
skriver `liv opdater` fejlen på stderr og i `liv status`, gemmer de andre og
slutter med exit-kode 1. Den fejlende kildes tal står som ved sidste vellykkede
læsning.

Kør `liv opdater` mindst hver anden uge. Ellers når en uge at falde ud af
kalendervinduet, før den er gemt.

## Brug

```bash
python3 -m venv .venv && .venv/bin/pip install -e .

liv opdater                         # genberegn ugetabellen
liv uger -n 8                       # vis de seneste 8 uger
liv rapport --opdater               # review af sidste hele uge, som JSON
liv status

.venv/bin/pip install --group dev   # pytest
.venv/bin/pytest
```

Selvstudie logges i CalTask, som lægger en begivenhed i kalenderen, fx
"Selvstudie · Alfa" fra 08:00 til 09:30. Varigheden er de loggede timer. Kun
begivenheder der er slut tæller, og de skal være synket ind i garmin-coach.

## Definitioner

- **variabelt_kr**: positive beløb i "Variable udgifter", uden "Deling med
  venner". Refusioner tæller ikke, fordi de hører til en anden uges udgift.
- **takeaway_kr** m.fl.: netto for kategorien, så MobilePay tilbage fra en
  ven trækkes fra. **takeaway_kr** og **cafe_bar_kr** bliver dog aldrig
  negative: er tilbagebetalingen eller refusionen større end ugens køb (fx
  300 kr. tilbage i en uge med 40 kr. take-away), hører resten til en anden
  uges udgift, ligesom refusionerne under variabelt_kr, og ugen står til 0.
  Et negativt tal ville ellers trække Forbrug (Uge for uge) og afvigelserne
  skævt. Dagligvarer er stadig netto uden grænse.
- **belastning**: træningsbelastning (TRIMP), regnet af garmin-coach og læst fra
  `~/.garmin-coach/site/belastning.json` (`LIV_BELASTNING_JSON`). Styrkepas er med
  via Hevy. Garmins egen belastning bruges ikke: den mangler på styrkepas.
- Uger er ISO-uger, mandag til søndag.

Stier, datoer og titelmønstre kan overstyres med miljøvariabler (se `overblik/config.py`):

| Variabel | Standard | Hvad |
|---|---|---|
| `LIV_DB` | `~/.overblik/liv.db` | egen database med én række pr. uge og de gemte reviews |
| `LIV_GARMIN_DB` | `~/.garmin-coach/coach.db` | garmin-coach's database (læses kun) |
| `LIV_BELASTNING_JSON` | `~/.garmin-coach/site/belastning.json` | træningsbelastning pr. dag og pr. pas, skrevet af garmin-coach's `site byg` |
| `LIV_SURE_JSON` | `~/kompas/okonomi/dashboard/public/data.json` | Sures eksport |
| `LIV_SKAERMTID_JSON` | `~/.kompas/skaermtid/skaermtid.json` | Skærmtids eksport (læses kun): sen skærmtid pr. aften og dagens forløb |
| `LIV_STUDIE_JSON` | `~/.kompas/studie/studie.json` | Studies eksport (læses kun): svar pr. dag i Træning og På farten |
| `LIV_SITE` | `~/.garmin-coach/site` | hvor `liv eksport` lægger `liv.json` |
| `LIV_TZ` | `Europe/Copenhagen` | vægtiden, som dagsplanen regner i, uanset maskinens tidszone |
| `LIV_SELVSTUDIE_PRAEFIKS` | `Selvstudie ·` | titlen, CalTask-begivenheder starter med |
| `LIV_SELVSTUDIE_FRA` | `2026-09-28` | dagen logningen af selvstudie begyndte |
| `LIV_FRA` | `2025-06-02` | første uge, der beregnes |

## Ugereviewet

Ugereviewet skrives af rutinen Overblik mandag morgen efter `RUTINE.md`.
`liv rapport` tager sidste hele uge (eller `--uge`) og regner to ting ud. Den
kommende uge (`kommende_uge`) er ugen efter, regnet fra rapportens mandag og ikke
fra dagen rapporten køres:

- **Afvigelser**: hver kolonne sammenlignes med medianen af de 8 foregående
  uger (robust z-score). Kun |z| ≥ 1,5 regnes som tydelig. Er de fleste uger
  ens (fx 0 kr. på café), er ugen kun tydelig, når den ligger uden for alle 8
  uger og mindst en fast forskel fra medianen (fx 100 kr.).
- **Sammenhænge**: 11 faste hypoteser (fx søvn ↔ take-away) testes med
  Spearman på ugens afvigelse fra medianen af op til 4 nærmeste uger, lige
  mange på hver side, så en fælles udvikling over tid (sommer mod semester) ikke
  tæller som en sammenhæng. De to første og sidste uger er ikke med. p-værdien
  findes ved blok-permutation (blokke af 3 uger), fordi uger, der ligger tæt,
  ligner hinanden. Kun uger med mindst 5 dages Garmin-data, og mindst 18 uger.
  "stærk" skal klare p < 0,05/11, "antydning" p < 0,05, og begge |rho| ≥ 0,3.
  Studiehypoteserne venter på nok ugers selvstudielogning.

Faste hypoteser frem for alle par mod alle, fordi 153 par ville give ca. 8
falske fund ved rent tilfælde.

Rutinen Overblik synker Garmin og kalenderen, kører `liv rapport --opdater`,
læser næste uges kalender og skriver reviewet til `reviews/<uge>.md`.
Tidsplanen styres i Claude-appen; siden Forbindelser i Kompas viser den aktuelle.

## På Kompas

Ugereviewet vises på forsiden I dag og grafisk under Form & fokus → Ugereview
(`https://kompas.localhost/form/uge.html`). Økonomi → Forbrug viser ugernes `variabelt_kr`, `takeaway_kr` og
`cafe_bar_kr` under Uge for uge, så en ændring af de felter rammer også dén side.

```bash
liv gem-review reviews/2026-W39.json --uge 2026-09-21   # gem teksten med ugens tal
liv eksport                                             # skriv liv.json til siden
```

`gem-review` tager reviewets tekst som JSON (`saetning`, `udskilte`,
`sammenhaenge`, `kommende_uge`, `en_ting`, `forbehold`) og gemmer den sammen
med et øjebliksbillede af tallene, regnet her: rapporten, ugens dage og pas
fra Garmin og kalenderen for ugen og ugen efter. Kalenderen i garmin-coach
dækker kun ca. 14 dage bagud, så en gammel uges kalender ville ellers
forsvinde fra siden.

Hvert review gemmes også med `genereret`, tidspunktet med tidszone, og
`metode`, den metode afvigelser og sammenhænge er regnet efter
(`rapport.METODE`, datoen for seneste metodeændring). Et review bygger på
metoden fra dagen, det blev skrevet: et review fra før en metodeændring kan
nævne en sammenhæng, den nuværende metode ikke finder. Hæv `METODE`, hver gang
det ændres, hvordan afvigelser eller sammenhænge regnes. Reviews gemt, før
feltet fandtes, har ingen `metode` og et `genereret` i lokal tid uden
tidszone; de får intet påført bagefter.

`eksport` skriver `liv.json` til `~/.garmin-coach/site` (overstyr med
`LIV_SITE`): alle uger, kilder, den nuværende `metode` og de gemte reviews
med deres `genereret` og `metode`. Er der ikke skrevet review for sidste hele
uge, kommer den med som tal uden tekst (og uden `genereret` og `metode`).

`dagsplan` er planlagt mod faktisk for de seneste 14 døgn (kl. 6 til kl. 6, som Skærmtid) til Ugereview og til I dag, der
viser `faktisk` under hver af dagens blokke, når den er begyndt (blokken findes på dato og starttid). Plan er
undervisningen og dine egne blokke i kalenderen; faktisk er Skærmtids forløb i kvarterer, det, CalTask har logget som
selvstudie, og Garmins pas. Hver planlagt blok får `faktisk`: minutterne pr. gruppe og kategori, der faldt i den, minutter
uden skærm, logget selvstudie og træning. Uden forløb fra Skærmtid er `skaerm` null, ikke en dag uden skærm. En blok med
`plan: true` er en studieblok: den har mærket `#kompas-plan` i kalenderens note (garmin-coach gemmer det som `plan_blok`).

`glippede` er til I dag (Står stille): de seneste 3 afsluttede døgn i `dagsplan`, og hvilke af dem der havde studieblokke,
men intet selvstudie logget i CalTask i hele døgnet. `vis` er sand fra 2 sådanne døgn (`GLIPPET_DAGE` og
`GLIPPET_GRAENSE` i `side.py`). Er kalenderen ikke hentet siden i går, er `vis` falsk, og `status` siger hvorfor.

`studieuge` er til I dag (Selvstudie i ugen): denne ISO-uges loggede selvstudie (`selvstudie_timer` og `selvstudie_dage` fra
ugetabellen) mod ugens planlagte studieblokke (`planlagt_timer` og `planlagt_blokke`), dvs. alle blokke med planmærket fra
mandag til søndag, også dem, der ikke er kommet endnu. En blok tæller under den dato, den starter. Er kalenderen ikke hentet
siden i går, har `studieuge` en `status`, der siger hvorfor.

`studietid` er til Studies side Selvstudie: undervisningen pr. kursuskode (`fag_kode`), det, CalTask har logget som
selvstudie pr. titel ("Selvstudie · Beta🤖" bliver "Beta", også pr. dag i `dage` og antal logninger pr. dag i `sessioner`) og studieblokkene pr. det, der står før " · " i titlen, i alt og pr.
ISO-uge, og undervisningen også pr. slags (`former`: garmin-coach's `art` og `form`, fx Forelæsning · forudindspillet).
Undervisning og selvstudie tæller, når de er slut; studieblokkene både planlagt i alt og forbi. Navnene
oversættes ikke her; Studies eksport knytter dem til fagene (`kursuskode`, `kort` og `alias` i fag.json) og stiller dem
mod kursusbeskrivelsernes arbejdstimer.

`naetter` er de seneste 28 nætter til Form & fokus → Kroppen i tal, hver under aftenens dato: Garmins sengetid
(`sengetid` som kl. og `sengetid_t` som timer efter kl. 18, fra `raw` → `sleep.dailySleepDTO`), søvnen fra Garmins
række dagen efter (Garmin daterer natten ved opvågningen) og `sen_skaermtid_t`, Skærmtids sene skærmtid samme aften.
En aften uden måling står som null, også en dag, hvor ingen enhed sendte skærmtid.

`nat_sammenhaeng` er én fast hypotese pr. nat: sen skærmtid ↔ søvnscore samme nat, på alle de nætter Skærmtid dækker
(op til 56). Spearman med permutation i blokke af 3 nætter, mindst 28 nætter; "stærk" ved p < 0,01 og "antydning"
ved p < 0,05, begge med |rho| ≥ 0,3. Den vises som punktdiagram på Kroppen i tal under Søvn.
Kompas' opdatering hvert 30. minut (`~/kompas/bin/opdater.sh`) kører
`liv opdater` og `liv eksport` efter kalenderen og, når den hentes, Garmin.
