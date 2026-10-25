# Træning-rutinen: periodens vurdering

Instruktionerne til rutinen Træning (`traening-rapport`) i Claude-appen. Rutinen selv peger kun hertil, så
rutinen ændres her og versioneres med projektet.

Du skriver vurderingen af brugerens seneste periode (14 dage fra lørdag til fredag) om træning, søvn/sundhed og studie til Form & fokus. Svar og skriv på dansk. Brugeren er ikke til stede, så stil ingen spørgsmål.

Vurderingen vises på Kompas under Form & fokus → Perioder (https://kompas.localhost/form/perioder.html), og fokus også på forsiden I dag. Siderne leveres af Caddy fra ~/.garmin-coach/site og bygges af `site byg` / `gem-periode`. Perioderne ligger i tabellen `perioder` i garmin-coach-databasen og gemmes kun med kommandolinjeværktøjet nedenfor.

Kør alle kommandoer fra repoet: cd ~/kompas/coach && .venv/bin/python -m garmin_coach.site <kommando>

Værktøjer: garmin-coach-serveren kører lokalt som `mcp__garmin-coach__*` (indlæs dem via ToolSearch). Læs først ~/kompas/coach/.claude/skills/garmin-coach-data/SKILL.md — den beskriver faldgruberne, også hvad felterne betyder, og hvornår de er null.

## 0. Skal der køres i dag?
Rutinen kører hver søndag, men en periode gemmes kun hver anden uge. Perioderne går lørdag til fredag, og en periode slutter altid på en fredag, så fredagens træning er med. Søvn, HRV og hvilepuls står på den dato, brugeren vågner: en periode har natten til sin første lørdag med og slutter med natten til sin sidste fredag. Natten til lørdagen efter hører til næste periode. `gem-periode` afviser en slutdato, der ikke er en fredag, og en start, der ikke er dagen efter forrige endelige periodes slut.
- Kør `.venv/bin/python -m garmin_coach.site perioder` — den udskriver alle perioder som JSON, ældste først.
- E = den seneste fredag før i dag ('YYYY-MM-DD'). Kører rutinen søndag, er det i forgårs; kører den for sent (fx mandag, fordi Claude-appen var lukket), er det stadig fredagen før, så perioden ikke forskubber sig.
- Find den nyeste periode med status "endelig". Er E minus dens `slut` under 12 dage: STOP. Skriv intet og afslut kort.
- Ellers er den nye periode: S = forrige endelige `slut` + 1 dag, slut = E.

## 1. Friske data
Kald `mcp__garmin-coach__sync` med dage=16 (henter Garmin, Hevy og kalender). Svarer den med status "kører", så kald den igen til den er færdig. Står der `fejlede` i svaret (fx Hevy eller kalenderen), er Garmin hentet, men de kilder ikke: fortsæt, og nævn i resume, hvilke tal der kan mangle (Hevy: styrkepassenes sæt, vægt og RPE; kalenderen: studie).
Fejler sync, så kald `mcp__garmin-coach__restitution` og se på `datafriskhed.seneste_data`. Er den ældre end E: gem INTET og afslut med én linje: "Periodens vurdering blev ikke lavet, fordi sync mod Garmin fejlede (<kort årsag>). Skriv 'kør Træning-rutinen' for at prøve igen." Er data fra E eller senere, så fortsæt og nævn den fejlede sync i resume.

## 2. Tal
Kald `mcp__garmin-coach__periode` med start=S og slut=E for at se periodens tal og `forbehold`. Du skal IKKE gemme tallene selv — `gem-periode` i trin 4 regner dem igen og gemmer dem. Brug dem kun til vurderingen.
Bemærk: `styrke.haarde_saet` er antal arbejdssæt, og `studie` er null, hvis kalenderen ikke dækker perioden.

## 2b. Brugerens træningsmål
Vurderingen måler træningen mod målet her. Brugeren har selv sat det. Ret det kun, når brugeren beder om det.

| Del | Pr. uge | Hvad tæller |
|---|---|---|
| Gulv | 2 styrkepas | `strength_training`. Et kort pas tæller, uanset længden |
| Kondition | 1 løb eller cykling | `running` eller `road_biking` (ikke `e_bike_fitness`) |
| Bonus | svømning om morgenen | `lap_swimming`, der starter før kl. 10 |

- En uge er en halvdel af perioden, lørdag til fredag: S til S+6 og S+7 til E. Er perioden ikke 14 dage, så tæl pr. 7 dage fra S, og sig det.
- Tæl pasene med `mcp__garmin-coach__opslag`:
  SELECT date, time(start_local) kl, sport, round(duration_s/60) min FROM activities WHERE date BETWEEN 'S' AND 'E' ORDER BY start_local
  Ligner et pas en fejlregistrering (få minutter og ingen sæt i Hevy), så tæl det ikke, og sig det.
- Gulvet er det vigtigste. Er det nået i begge uger, er det en god træningsperiode, også selvom kondition eller bonus mangler.
- Bonussen er bonus. Den nævnes under gaar_godt, når den er der, og står aldrig under gaar_daarligt eller som fokus, når den mangler.

## 3. Vurdering
Målet først: resume begynder med én sætning om målet pr. uge, fx "Målet: styrke 2 og 1 pas, løb/cykling 1 og 0, morgensvømning 0." Er gulvet ikke nået i en uge, står det under gaar_daarligt, og mindst ét fokus handler om gulvet. Fokus sætter ikke en højere barre for antal pas end målet. Vil du skærpe noget, så gør det inden for målet, fx at løbeturen er rolig, eller at styrkepassene ligger på faste dage.
Sammenlign med alle tidligere perioder fra trin 0 (retning over flere perioder, ikke kun forrige). Alle perioder er regnet med samme metode, også belastning. Har du brug for længere perspektiv, så kald `mcp__garmin-coach__maanedsoversigt` — brug dens "udvikling" frem for selv at regne.
Forklar afvigelser i søvn/HRV ved at krydse med kalenderen: hent dag-for-dag med `mcp__garmin-coach__opslag`, fx
  SELECT date, round(sleep_s/3600.0,1) sovn_t, sleep_score, hrv_last_night, training_readiness FROM daily WHERE date BETWEEN 'S' AND 'E' ORDER BY date
  SELECT date(start_local) d, time(start_local) kl, summary, all_day FROM calendar_events WHERE date(start_local) BETWEEN 'S' AND 'E' ORDER BY start_local
Se efter fester, tidlig undervisning og tunge studiedage. Tag punkterne i `forbehold` med hvor de betyder noget. Vær konkret med tal, kort og ærlig; sig det, hvis data ikke rækker. Ingen medicinske påstande.
Er perioden ikke 14 dage, så nævn det kort i resume, når du sammenligner med andre perioder.
Skriv datoer, ikke relative ord: "natten til 26/9", aldrig "i dag", "i går", "i nat" eller "denne uge". Vurderingen læses i to uger og længere, også på forsiden.

Fokus er handlinger, ikke tærskler. Brugeren kender tallene, og et mål som "højst 3 nætter under 7 timer" ændrer ikke, hvad brugeren gør:
1. Hvert punkt er noget, brugeren gør, med dag og tidspunkt og gerne sted, fx "Styrke mandag 26/10 og onsdag 28/10 efter undervisningen, ca. kl. 16". Find pladsen i kalenderen for de næste 14 dage, fra dagen efter E (F) til 14 dage efter E (T). Rutinen kører søndag, så læg ingen punkter på dage før i dag:
   SELECT date(start_local) d, time(start_local) kl, summary, all_day FROM calendar_events WHERE date(start_local) BETWEEN 'F' AND 'T' ORDER BY start_local
   Et punkt er målbart, når man bagefter kan se, om det skete.
2. Træning først. Fokus handler om at nå målet i 2b: hvornår passene ligger, og hvad der gør dem lettere. Gentag ikke selve målet ("2 styrkepas om ugen") som fokus.
3. Søvn og selvstudie er ikke fokus. Søvn står i resume og under gaar_daarligt, når den afviger, med årsagen fra kalenderen. Selvstudie hører under Studie-rutinen.
4. Fokus passer til de næste 14 dage og tager højde for det, der ligger i kalenderen (undervisning, arrangementer, rejser). Gentag ikke et punkt fra forrige periodes fokus, medmindre det er skåret ned, så det kan nås.

vurdering = {
  resume: 2–3 sætninger om perioden,
  gaar_godt: 2–4 punkter, gaar_daarligt: 2–4 punkter, forbedring: 2–4 konkrete handlinger,
  fokus: 2–3 handlinger til næste periode (se "Fokus er handlinger" ovenfor),
  opfoelgning: for hvert punkt i forrige endelige periodes vurdering.fokus (hvis den har nogen): {fokus: teksten, status: "naaet"|"delvist"|"ikke", note: kort begrundelse med tal}
}

## 4. Gem perioden
Skriv vurderingen som JSON til filen ~/.garmin-coach/vurdering-S.json (kun vurdering-objektet), og kør:
  .venv/bin/python -m garmin_coach.site gem-periode S E ~/.garmin-coach/vurdering-S.json
Den regner tallene, gemmer perioden som endelig, fjerner foreløbige perioder og bygger siden igen. Tjek at svaret siger "status": "endelig". Kør derefter `perioder` og bekræft at perioden står der med din resume.

## 5. Afslut
Svar til sidst med 3–4 linjer: periodens vigtigste pointe, én ting der går godt, én der skal forbedres, og at vurderingen ligger på https://kompas.localhost/form/perioder.html.
