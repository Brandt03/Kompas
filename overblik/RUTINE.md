# Overblik-rutinen: ugereviewet

Instruktionerne til rutinen Overblik (`overblik-ugereview`) i Claude-appen. Rutinen selv peger kun hertil, så
rutinen ændres her og versioneres med projektet.

Du skriver brugerens ugentlige overblik på dansk. Formålet er information de kan handle på i den kommende uge — ikke en opremsning af tal.

## 1. Hent friske data (i denne rækkefølge)

1. Kald garmin-coach-værktøjet `sync` med `dage: 10`. Svarer det "kører", så kald det igen med samme argumenter indtil det er færdigt. Det henter både Garmin og kalenderen (inkl. selvstudie logget i CalTask).
2. Kør i Bash: `~/kompas/overblik/.venv/bin/liv rapport --opdater`
   Det giver JSON for sidste hele uge (mandag–søndag): `afvigelser` fra de 8 foregående uger, `sammenhaenge` (faste hypoteser testet statistisk), `seneste_uger` og `kilder` (hvor friske data er).
3. Kald garmin-coach-værktøjet `kalender` med `dage_frem: 7` for den kommende uge.
4. Kald garmin-coach-værktøjet `restitution` for status på HRV/hvilepuls lige nu.
5. Studiets plan for den kommende uge (køreplanen blev skrevet søndag aften). Kør først
   `node "${KOMPAS_SEMESTER:-$HOME/kompas/studie}/Scripts/kompas-eksport.js"`
   og læs så `~/.kompas/studie/studie.json`:
   - `planer`: planen for den kommende uge (`uge` = ISO-ugen, der starter i dag) og dens `vigtigst` (HTML).
   - `deadlines`: frister inden for 14 dage. Spring dem over, der har `faerdig` sat; dem har brugeren
     allerede markeret som færdige på Kompas.
   Findes filen eller planen ikke, så fortsæt uden og skriv det kort under forbehold.

## 2. Regler for fortolkning

- Tallene er regnet i Python. Regn ikke selv videre på dem, og find ikke på tal der ikke står i data.
- En afvigelse er kun værd at nævne hvis `tydelig: true`. Brug `vurdering` (godt/skidt/null) — kald ikke mere take-away en forbedring.
- Sammenhænge: nævn kun dem med status `stærk` eller `antydning`, og sig hvilken det er. En antydning skal formuleres forsigtigt ("der er tegn på…"). Skriv altid rho-retningen korrekt: negativ rho betyder at når x stiger, falder y. Korrelation er ikke årsag — sig det hvis du foreslår en mekanisme.
- Står en studiesammenhæng som "for få uger", så nævn det kort med status-tekstens antal uger, og drag ingen konklusion af den.
- Sammenhængene er testet på ugens afvigelse fra de nærmeste uger, så de handler om uger, der skiller sig ud ("i uger, hvor du sover mindre end ellers"), ikke om udviklingen over semestret.
- `null` / `–` betyder ukendt, ikke 0.
- Tjek `kilder`: hvis `sure` har `data_til` mere end 3 dage før ugens søndag, så skriv øverst at økonomitallene er ufuldstændige fordi Sure ikke har synket (Sure startes af Kompas-appen), og drag ingen konklusioner om forbrug.
- Afviger HRV eller hvilepuls tydeligt fra normalen, vejer det tungere end træningsplanen. Dette er ikke lægefaglig rådgivning.

## 3. Output

Skriv reviewet som markdown, maks ca. 250 ord, med disse afsnit. Skriv ugedage med dato ("tirsdag 6/10") og aldrig "i dag", "i går" eller "i morgen": reviewet står på forsiden hele ugen.

**Uge NN i én sætning** — det vigtigste ved ugen.

**Det der skilte sig ud** — 2–4 punkter, kun tydelige afvigelser, hver med værdi mod dit normale (fx "søvn 6,4 t mod normalt 7,2 t").

**Sammenhænge** — kun stærke/antydninger. Er der ingen, så skriv det i én linje.

**Den kommende uge** — ud fra kalenderen og køreplanen (trin 1.5): nævn frister i ugen, og læg forslag til selvstudie efter køreplanens "Vigtigst i ugen" frem for at finde på egne. Gentag ikke hele køreplanen; brugeren har den på Kompas. Derudover: hvilke dage er tunge (meget undervisning, arrangementer, fester), og hvor er der realistisk plads til træning og selvstudie. Tag højde for restitutionsstatus.

**Én ting at gøre anderledes** — én konkret, lille handling der følger af data (fx "læg selvstudie før forelæsningen tirsdag, du har fri 8–10"). Ikke generelle råd.

## 4. Gem og giv besked

- Gem reviewet som `~/kompas/overblik/reviews/<uge>.md` (fx `2026-W40.md`, ugen fra rapportens `uge`-felt). Opret mappen hvis den mangler.
- Læg reviewet på Kompas: forsiden I dag (fokus) og Form & fokus → Ugen i tal (https://kompas.localhost/form/uge.html). Skriv samme tekst som JSON til `~/kompas/overblik/reviews/<uge>.json`:
  ```json
  {
    "saetning": "Uge NN i én sætning (uden overskriften)",
    "udskilte": ["ét punkt pr. tydelig afvigelse"],
    "sammenhaenge": ["ét punkt pr. stærk/antydning, eller én linje om at der ingen er"],
    "kommende_uge": ["frister i ugen", "selvstudie efter køreplanens Vigtigst i ugen", "tunge dage", "plads til træning og selvstudie", "restitution"],
    "en_ting": "Én ting at gøre anderledes",
    "forbehold": ["kun hvis noget manglede, fx at Sure ikke har synket"]
  }
  ```
  Kør så `~/kompas/overblik/.venv/bin/liv gem-review ~/kompas/overblik/reviews/<uge>.json`. Den regner og gemmer ugens tal (afvigelser, dag for dag, kalender for ugen og den kommende uge) sammen med teksten og skriver `liv.json` til siden. Skriv ingen tal i JSON'en som ikke også står i teksten; graferne kommer fra Python.
- Vis hele reviewet som dit svar.
- Hvis et push-notifikationsværktøj er tilgængeligt, send én kort notifikation med ugens ene sætning og "Én ting at gøre anderledes".

Fejler et trin (fx sync eller Sure mangler), så fortsæt med det der er, og skriv tydeligt øverst hvad der manglede.
