---
name: "garmin-coach-data"
description: "Brug ved alle spørgsmål om brugerens træning, søvn, restitution, pulszoner eller styrkeprogression fra garmin-coach-værktøjerne. Sikrer friske data og undgår kendte faldgruber i datasættet."
---

# Garmin-coach: data og faldgruber

Svar på dansk. Værktøjerne hedder `garmin-coach__*` (lokalt `mcp__garmin-coach__*`) og rammer en lokal database på brugerens computer. Kilden til sandheden om hvad felterne betyder er værktøjsbeskrivelserne; denne fil samler det der er let at gå galt i.

## 1. Tjek altid om data er friske

`dagens_status`, `traeningsbelastning` og `restitution` returnerer `datafriskhed`. Står status til andet end "aktuel", eller beder brugeren om friske tal, så kald `sync` **først**. En sync tager 1–3 minutter og kører i baggrunden. Svarer `sync` med status "kører", så kald den igen med samme argumenter, indtil status er "færdig". Det starter ikke en ny sync. Sig til brugeren at du henter nye data, frem for at lade dem vente i tavshed. `sync` henter også Hevy.

Kald ikke `sync` hvis data er aktuelle og brugeren ikke har bedt om det.

## 2. Brug det rigtige værktøj

| Spørgsmål | Værktøj |
|---|---|
| Bred briefing, "hvad skal jeg træne i dag" | `dagens_status` |
| Træthed, søvn, overtræning, HRV | `restitution` |
| Volumen, opbygning, nedtrapning, ACWR, styrke pr. uge | `traeningsbelastning` |
| Enkelte pas | `seneste_traening` |
| **Intensitet, zoner, polarisering** | **`pulszoner`** |
| Nøgletal for en afgrænset periode (fx 14 dage) | `periode` |
| Lange tendenser, "er jeg i bedre form end sidste år" | `maanedsoversigt` |
| Vægt, VO2max | `kropsudvikling` |
| Zonegrundlag, makspuls, hvilepuls | `profil` |
| Planlægning af pas i ugen | `kalender` |
| Alt andet | `opslag` (skrivebeskyttet SQL) |

**Konstruér aldrig selv pulszoner ud fra procent af makspuls.** Brug `pulszoner`, som returnerer Garmins egen sekund-for-sekund-måling mod brugerens faktiske grænser.

Er et felt `null`, så står begrundelsen i et nabofelt (fx `acwr_fortolkning`, `rpe_note`, `forbehold`). Gæt ikke selv et tal.

## 3. Makspulsen

Beregningerne bruger Garmins konfigurerede makspuls (`profil` viser kilden, fx "Garmins zoneopsætning"). Den højeste registrerede puls er et gulv, ikke en testet maks. Foreslå ikke at rette makspulsen ned ud fra registrerede pulstal; brug `profil` til at se, hvilket tal der regnes med og hvorfor.

## 4. Zonerne og laktattærsklen

Konstruér ikke selv zoner; brug grænserne fra `pulszoner`. Ligger laktattærsklen under grænsen for zone 5, er arbejde mellem de to tal over tærskel, men tælles som zone 4. `pulszoner` siger det selv i `forbehold_zoner`; nævn det når zone 4 fortolkes.

## 5. Zonegrænserne kan have ændret sig over tid

`pulszoner` returnerer `zonegrænser_ændret` med de forskellige sæt, og `periode` skriver det i `forbehold`. Er ældre pas målt mod lavere grænser, **flytter det kunstigt tid fra Z2 op i Z3**. Tag forbehold når en periode spænder over flere sæt.

## 6. Belastning og styrke

- **Belastning er TRIMP-enheder for alle pas.** Konditionspas regnes ud fra puls. Styrkepas med Hevy-data regnes ud fra arbejdssæt med tillæg for sæt med RPE eller til failure, omregnet til samme skala. `belastning_kilde` pr. pas siger hvilken ("hevy", "puls" eller "ingen").
- **Garmins egen `garmin_load` er en anden skala** og mangler på styrkepas. Summér eller sammenlign den aldrig med `belastning`.
- **Manglende RPE gættes ikke.** Et sæt uden RPE får intet tillæg, så få RPE-registreringer giver snarere for lav end for høj belastning. RPE-tal pr. uge/periode er `null` når under 60 % af arbejdssættene har RPE.
- **Styrkeprogression vurderes på Hevy-data**, ikke på belastning eller pasnavne: `traeningsbelastning.styrke_ugentligt` (arbejdssæt, volumen, RPE), `periode.styrke.e1rm` med `periode.styrke.loeft` (bedste sæt og dets RPE pr. løft), eller rå sæt i `hevy_sets`.
- **e1RM** (Epley) regnes kun for stang og håndvægt og kun på sæt med højst 12 gentagelser; maskine- og kabelvægte kan ikke sammenlignes på tværs af maskiner og centre. Har bedste sæt ingen RPE (`loeft.<løft>.rpe` er null), ved vi ikke om det var tæt på max: et fald kan bare være et lettere sæt. Konkludér ikke tilbagegang uden at sige det.

```sql
SELECT a.date, s.exercise, s.set_type, s.weight_kg, s.reps, s.rpe
FROM hevy_sets s JOIN hevy_workouts w USING (workout_id)
JOIN activities a ON a.activity_id = w.activity_id
WHERE s.exercise = 'Bench Press (Barbell)' AND s.set_type != 'warmup'
ORDER BY a.date DESC;
```

Hevy-pas er parret med deres kopi i Garmin, så ét pas er én række i `activities`. Hevy-data har ingen puls.

## 7. Kalenderen: undervisning, ikke møder

Brugeren studerer. Kalenderen indeholder **forelæsninger, øvelser og supervision**, plus enkelte sociale arrangementer — ikke arbejdsmøder. Skriv "undervisning", "forelæsning" eller "timer på campus". `kalender` returnerer dagens `program` med tid og titel og antal `begivenheder`.

`calendar_events.start_local` og `end_local` er **lokal tid uden offset** ('2026-09-23T08:00'). `time()`, `date()` og tekstsammenligning giver direkte det klokkeslæt der står i kalenderen — læg ikke noget til. UTC står i `start_utc`/`end_utc`.

```sql
SELECT start_local, summary FROM calendar_events
WHERE date(start_local) >= date('now', 'localtime') ORDER BY start_local;
```

Selvstudie logges i CalTask som begivenheder der hedder "Selvstudie · <fag>". `periode.studie.selvstudie_t` er null før første CalTask-session: det betyder "ikke logget", ikke 0 timer. `studie` er null når kalenderen ikke dækker perioden.

Sociale arrangementer i kalenderen er ofte forklaringen på dårlige nætter — fx en fest aftenen før et fald i søvnscore og training readiness. Kryds kalenderen med `daily`, når et udsving skal forklares, frem for kun at beskrive det.

## 8. Databasen

`opslag` er skrivebeskyttet og svarer `{"rækker", "antal", "afkortet"}`. Står `afkortet` til true, mangler der rækker — aggregér i SQL. Tabeller og kolonner står i `opslag`s beskrivelse: `activities` (inkl. `raw` med Garmins fulde JSON), `daily`, `activity_zones`, `hevy_workouts`, `hevy_sets`, `calendar_events`.

## 9. Forbehold der skal med

- **Svømning:** pulsen måles optisk fra håndleddet i vand og er notorisk upålidelig. Belastning, zonetid og makspuls fra svømmepas skal tages med forbehold — en makspuls nær 200 på et kort svømmepas er sandsynligvis støj.
- **Søvnfaser:** optisk estimat, ikke klinisk registrering. Læs procenter som tendens over uger, ikke som eksakte tal for den enkelte nat.
- **ACWR:** groft pejlemærke, ikke skadesforudsigelse. Vis retning, ikke facit.
- **Pas uden belastning** (hverken puls eller Hevy-sæt) står i `pas_uden_belastning_28d` eller `periode.forbehold`. Nævn dem, for så er belastningen undervurderet.

## 10. Vær ærlig når tallene ikke rækker

Sig tydeligt hvad data ikke kan svare på, frem for at strække dem. Hvis en konklusion hviler på et estimat eller en upålidelig måling, så sig det i samme åndedrag som konklusionen.
