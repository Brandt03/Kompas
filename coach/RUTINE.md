# Træning-rutinen: 14-dages rapporten

Instruktionerne til rutinen Træning (`traening-rapport`) i Claude-appen. Rutinen selv peger kun hertil, så
rutinen ændres her og versioneres med projektet.

Du skriver brugerens 14-dages rapport om træning, søvn/sundhed og studie til Form & Fokus. Svar og skriv på dansk. Brugeren er ikke til stede, så stil ingen spørgsmål.

Rapporten vises på Kompas under Form & fokus → 14-dages perioder (https://kompas.localhost/form/perioder.html), og fokuspunkterne også på forsiden I dag og under Coach. Siderne leveres af Caddy fra ~/.garmin-coach/site og bygges af `site byg` / `gem-periode`. Perioderne ligger i tabellen `perioder` i garmin-coach-databasen og gemmes kun med kommandolinjeværktøjet nedenfor.

Kør alle kommandoer fra repoet: cd ~/kompas/coach && .venv/bin/python -m garmin_coach.site <kommando>

Værktøjer: garmin-coach-serveren kører lokalt som `mcp__garmin-coach__*` (load via ToolSearch). Læs først ~/kompas/coach/.claude/skills/garmin-coach-data/SKILL.md — den beskriver faldgruberne, også hvad felterne betyder, og hvornår de er null.

## 0. Skal der køres i dag?
Opgaven fyrer hver lørdag, men rapporten laves hver anden uge. En periode slutter altid på en fredag, så fredagens træning og natten til lørdag er med, og perioderne går lørdag til fredag.
- Kør `.venv/bin/python -m garmin_coach.site perioder` — den udskriver alle perioder som JSON, ældste først.
- E = den seneste fredag før i dag ('YYYY-MM-DD'). Kører opgaven lørdag, er det i går; kører den for sent (fx mandag, fordi appen var lukket), er det stadig fredagen før, så perioden ikke forskubber sig.
- Find den nyeste periode med status "endelig". Er E minus dens `slut` under 12 dage: STOP. Skriv intet og afslut kort.
- Ellers er den nye periode: S = forrige endelige `slut` + 1 dag, slut = E.

## 1. Friske data
Kald `mcp__garmin-coach__sync` med dage=16 (henter Garmin, Hevy og kalender). Svarer den med status "kører", så kald den igen til den er færdig.
Fejler sync, så kald `mcp__garmin-coach__restitution` og se på `datafriskhed.seneste_data`. Er den ældre end E: gem INTET og afslut med én linje: "Form & Fokus blev ikke lavet, fordi sync mod Garmin fejlede (<kort årsag>). Skriv 'kør Form & Fokus-rapporten' for at prøve igen." Er data fra E eller senere, så fortsæt og nævn den fejlede sync i resume.

## 2. Tal
Kald `mcp__garmin-coach__periode` med start=S og slut=E for at se periodens tal og `forbehold`. Du skal IKKE gemme tallene selv — `gem-periode` i trin 4 regner dem igen og gemmer dem. Brug dem kun til vurderingen.
Bemærk: `styrke.haarde_saet` er antal arbejdssæt, og `studie` er null, hvis kalenderen ikke dækker perioden.

## 3. Vurdering
Sammenlign med alle tidligere perioder fra trin 0 (retning over flere perioder, ikke kun forrige). Alle perioder er regnet med samme metode, også belastning. Har du brug for længere perspektiv, så kald `mcp__garmin-coach__maanedsoversigt` — brug dens "udvikling" frem for selv at regne.
Forklar udsving i søvn/HRV ved at krydse med kalenderen: hent dag-for-dag med `mcp__garmin-coach__opslag`, fx
  SELECT date, round(sleep_s/3600.0,1) sovn_t, sleep_score, hrv_last_night, training_readiness FROM daily WHERE date BETWEEN 'S' AND 'E' ORDER BY date
  SELECT date(start_local) d, time(start_local) kl, summary, all_day FROM calendar_events WHERE date(start_local) BETWEEN 'S' AND 'E' ORDER BY start_local
Se efter fester, tidlig undervisning og tunge studiedage. Tag punkterne i `forbehold` med hvor de betyder noget. Vær konkret med tal, kort og ærlig; sig det, hvis data ikke rækker. Ingen medicinske påstande.
Er perioden ikke 14 dage, så nævn det kort i resume, når du sammenligner med andre perioder.
Skriv datoer, ikke relative ord: "natten til 26/9", aldrig "i dag", "i går", "i nat" eller "denne uge". Rapporten læses i to uger og længere, også på forsiden.
vurdering = {
  resume: 2–3 sætninger om perioden,
  gaar_godt: 2–4 punkter, gaar_daarligt: 2–4 punkter, forbedring: 2–4 konkrete handlinger,
  fokus: 2–3 målbare mål til næste periode,
  opfoelgning: for hvert punkt i forrige endelige periodes vurdering.fokus (hvis den har nogen): {fokus: teksten, status: "naaet"|"delvist"|"ikke", note: kort begrundelse med tal}
}

## 4. Gem perioden
Skriv vurderingen som JSON til filen ~/.garmin-coach/vurdering-S.json (kun vurdering-objektet), og kør:
  .venv/bin/python -m garmin_coach.site gem-periode S E ~/.garmin-coach/vurdering-S.json
Den regner tallene, gemmer perioden som endelig, fjerner foreløbige perioder og bygger siden igen. Tjek at svaret siger "status": "endelig". Kør derefter `perioder` og bekræft at perioden står der med din resume.

## 5. Afslut
Svar til sidst med 3–4 linjer: periodens vigtigste pointe, én ting der går godt, én der skal forbedres, og at rapporten ligger på https://kompas.localhost/form/perioder.html.
