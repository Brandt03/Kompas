# overblik

Én række pr. uge på tværs af træning, økonomi og studie, så en ugentlig
gennemgang kan lede efter sammenhænge på faste tal i stedet for gæt.

Som i garmin-coach ligger beregningerne i Python. Modellen får den færdige
ugetabel og fortolker den. Alt kører lokalt.

## Kilder

| Kilde | Hvorfra | Kolonner |
|---|---|---|
| garmin | `~/.garmin-coach/coach.db` (læses kun) | søvn, HRV, hvilepuls, stress, skridt, træning |
| sure | `~/kompas/okonomi/dashboard/public/data.json` | take-away, café/bar, dagligvarer, variable køb |
| kalender | garmin-coach's `calendar_events` | undervisning (begivenheder, garmin-coach har givet en `fag_kode`) og selvstudie (CalTask-begivenheder der starter med `Selvstudie ·`) |

**En tom celle (`–`) betyder at kilden ikke dækker ugen, ikke 0.** Selvstudie
før `LIV_SELVSTUDIE_FRA`, dagen logningen i CalTask begyndte, er ukendt. Undervisning før kalendervinduet er ukendt.

Kalenderen i garmin-coach dækker kun ca. 14 dage bagud. Derfor overskriver en
tom værdi aldrig et gemt tal: en uge beholder sin undervisning efter at være
faldet ud af vinduet, så længe `liv opdater` har kørt mens den var inden for.

Sures eksport opdateres kun mens Sure kører. `liv status` viser hvor friske
kilderne er.

Kør `liv opdater` mindst hver anden uge. Ellers når en uge at falde ud af
kalendervinduet, før den er gemt.

## Brug

```bash
python3 -m venv .venv && .venv/bin/pip install -e .

liv opdater                         # genberegn ugetabellen
liv uger -n 8                       # vis de seneste 8 uger
liv rapport --opdater               # review af sidste hele uge, som JSON
liv status
```

Selvstudie logges i CalTask, som lægger en begivenhed i kalenderen, fx
"Selvstudie · Alfa" fra 08:00 til 09:30. Varigheden er de loggede timer. Kun
begivenheder der er slut tæller, og de skal være synket ind i garmin-coach.

## Definitioner

- **variabelt_kr**: positive beløb i "Variable udgifter", uden "Deling med
  venner". Refusioner tæller ikke, fordi de hører til en anden uges udgift.
- **takeaway_kr** m.fl.: netto for kategorien, så MobilePay tilbage fra en
  ven trækkes fra. Kan derfor blive en smule negativ.
- **belastning**: træningsbelastning (TRIMP), regnet af garmin-coach og læst fra
  `~/.garmin-coach/site/belastning.json` (`LIV_BELASTNING_JSON`). Styrkepas er med
  via Hevy. Garmins egen training load bruges ikke: den mangler på styrkepas.
- Uger er ISO-uger, mandag til søndag.

Stier, datoer og titelmønstre kan overstyres med miljøvariabler (se `overblik/config.py`):

| Variabel | Standard | Hvad |
|---|---|---|
| `LIV_DB` | `~/.overblik/liv.db` | egen database med én række pr. uge og de gemte reviews |
| `LIV_GARMIN_DB` | `~/.garmin-coach/coach.db` | garmin-coach's database (læses kun) |
| `LIV_BELASTNING_JSON` | `~/.garmin-coach/site/belastning.json` | træningsbelastning pr. dag og pr. pas, skrevet af garmin-coach's `site byg` |
| `LIV_SURE_JSON` | `~/kompas/okonomi/dashboard/public/data.json` | Sures eksport |
| `LIV_SITE` | `~/.garmin-coach/site` | hvor `liv eksport` lægger `liv.json` |
| `LIV_SELVSTUDIE_PRAEFIKS` | `Selvstudie ·` | titlen, CalTask-begivenheder starter med |
| `LIV_SELVSTUDIE_FRA` | `2026-09-28` | dagen logningen af selvstudie begyndte |
| `LIV_FRA` | `2025-06-02` | første uge, der beregnes |

## Det ugentlige review

Reviewet skrives af den planlagte opgave "Overblik" mandag morgen efter `RUTINE.md`.
`liv rapport` tager sidste hele uge og regner to ting ud:

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

Den planlagte opgave "Ugentligt overblik" kører mandag kl. 7 i
Claude-appen. Den synker Garmin og kalenderen, kører `liv rapport --opdater`,
læser næste uges kalender og skriver reviewet til `reviews/<uge>.md`.

## På Form & Fokus

Reviewet vises også grafisk under "Ugen" på `https://localhost/form/#ugen`.

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

`eksport` skriver `liv.json` til `~/.garmin-coach/site` (overstyr med
`LIV_SITE`): alle uger, kilder og de gemte reviews. Er der ikke skrevet
review for sidste hele uge, kommer den med som tal uden tekst. Kompas.app
kører `liv opdater` og `liv eksport` i baggrunden, efter Garmin og Sure har
synket.
