# Kompas

Én side, der samler økonomi, studie, sprog og form fra projekterne. Ordlisten gælder på tværs af
projekterne, så sider, rutiner og samtaler bruger de samme ord.

## Platformen

**Kompas**:
Den samlede side, der viser projekternes sider bag én menu og selv ejer forsiden I dag og Forbindelser.
_Avoid_: portal, dashboard

**Projekt**:
Et selvstændigt program, der regner sine egne tal og leverer ét område til Kompas.
_Avoid_: app, modul, service

**Område**:
En gruppe i menuen, som ét projekt leverer: Økonomi, Studie, Sprog eller Form & fokus.
_Avoid_: sektion, fane

**Rutine**:
En planlagt Claude-kørsel, der skriver nyt indhold til et projekt: Studie, Træning, Overblik eller Sprog.
_Avoid_: planlagt opgave, job, agent

**Forbindelse**:
Noget, Kompas henter fra eller kører på (en datakilde, en rutine, en server eller et baggrundsjob), med en status:
ok, advarsel, fejl eller info.
_Avoid_: integration

**På farten**:
Studie på telefonen: dagens kort hentes, mens Mac'en er vågen, og svarene sendes, når den er det igen.
_Avoid_: mobilappen, mobilsiden

## Studie

**Fag**:
Et af semestrets kurser, kendt ved sit kortnavn (i demoen Alfa, Beta og Gamma).
_Avoid_: kursus

**Køreplan**:
Ugens plan for de tre fag med læsning, noter, frister og det vigtigste i ugen. Vises på Ugeoverblik.
_Avoid_: ugeplan

**Fagnoter**:
Det løbende notedokument for et fag, som udvides uge for uge efter undervisningen.
_Avoid_: noter, resumé

**Opgave**:
Arbejde, du selv skal løse: drills, øvelsessæt, nummererede afleveringer og projektopgaver. Facit til en opgave gives aldrig
på forhånd.
_Avoid_: aflevering (om drills og øvelsessæt)

**Aflevering**:
En nummereret godkendelsesopgave i et fag (1, 2, …), der afleveres i skolens system.
_Avoid_: godkendelse

**Drill**:
Et tjek i et programmeringsfag, hvor du gætter, hvad et JavaScript-udtryk giver, før det køres.
_Avoid_: øvelse, quiz

**Begreb**:
Et fagbegreb, som du definerer med egne ord. Et tomt begreb er meningen, ikke et efterslæb.
_Avoid_: definition, glose

**Genkald**:
En uges spørgsmål til et fag, der besvares fra hukommelsen og markeres ✓, ~ eller ✗.
_Avoid_: quiz, overhøring

**Kort**:
Ét genkaldsspørgsmål, begreb, drill eller eksamensopgave, som repetitionen planlægger. I Sprog: ét sprogkort (se
Sprogkort). Bruges ikke om sidernes felter eller om fagenes forkortelser.
_Avoid_: flashcard

**Repetition**:
Planlægningen af, hvornår et kort kommer igen, ud fra de tidligere svar på det.
_Avoid_: genkald (om det hele)

**Dagens kort**:
De kort, repetitionen har planlagt til i dag.

**Læst uge**:
En uge, du har markeret som læst i et fag. Først da kommer ugens genkald med i dagens kort.

**Frist**:
Et tidspunkt, hvor en aflevering, præsentation eller eksamen skal være klar. Kan markeres færdig.
_Avoid_: deadline

**Prøveeksamen**:
Et gammelt eksamenssæt taget på tid som generalprøve; din egen plan, ikke en frist fra universitetet.
_Avoid_: øvelseseksamen

**Selvstudie**:
Studietid uden for undervisningen, logget i kalenderen.
_Avoid_: læsetid

## Sprog

**Aktivt sprog**:
Det fremmedsprog, der bygges op lige nu, med flest nye kort og ugens tekst. Ét ad gangen.
_Avoid_: hovedsprog, fokussprog

**Holdes ved lige**:
Rollen for et fremmedsprog, der ikke er aktivt: få nye kort, gentagelsen fortsætter.
_Avoid_: sovende

**På pause**:
Rollen for et fremmedsprog, der hverken bygges op eller holdes ved lige: ingen nye kort; de kort, der er, bliver
liggende.

**Eksamensperiode**:
Fra 14 dage før en eksamen i Studie til og med eksamensdagen: ingen nye sprogkort og ingen ny tekst, kun gentagelse.

**Studiesprog**:
Dansk og engelsk: kort af dine egne fejl i det, du skriver i Studie, ugens ord og akademisk engelsk.

**Sprogkort**:
Et kort i Sprog: en frase (dansk → sproget), en sætning at rette, en sætning at udfylde, ugens ord eller et kort i
niveautesten.
_Avoid_: flashcard, glose

**Sprogregel**:
En regel under Regler i Sprog: kort forklaring på dansk, eksempler og typiske fejl, gerne dine egne. Øves med
udfyld-kort, der peger på den. Én ny om ugen på spansk og én på dansk.
_Avoid_: grammatikside, lektion

**Situation**:
Det, et frasekort hører til i hverdagen eller på rejsen: restaurant, transport, indkøb … Kortene ordnes efter
situation, ikke efter grammatik.
_Avoid_: emne, tema

**Niveautest**:
De første kort i et fremmedsprog, på stigende niveau, som rutinen sætter niveauet (A1-C2) ud fra. Besvares én gang.
_Avoid_: indplacering, quiz

**Ugens tekst**:
En kort tekst på det aktive sprog, som du svarer på i et par sætninger. Rutinen giver feedback på svaret.
_Avoid_: læseopgave, artikel

**Lært**:
Et kort, du med 90 % sandsynlighed stadig kan om tre uger. Samme grænse i Studie og Sprog.

## Form & fokus

**Periode**:
14 dage fra lørdag til fredag, som Træning-rutinen vurderer under ét.
_Avoid_: 14-dages rapport, uge

**Vurdering**:
Rutinens skrevne bedømmelse af en periode: resumé, hvad der går godt og dårligt, forbedringer og fokus.
_Avoid_: rapport

**Fokus**:
To til tre målbare mål til næste periode, som også vises på forsiden.
_Avoid_: mål, fokuspunkter

**Belastning**:
Træningsbelastning på én fælles skala for alle pas, også styrketræning.
_Avoid_: load, Garmins load

**Dagens råd**:
Rådet for dagens træning, rolig, moderat eller klar, med grundene.
_Avoid_: anbefaling

## Overblik

**Ugereview**:
Overblik-rutinens gennemgang af sidste uge på tværs af træning, søvn, økonomi og studie, med plan for den
kommende uge.
_Avoid_: livsoverblik, ugerapport

**Afvigelse**:
Et tal, der i en uge skiller sig tydeligt ud fra de foregående uger.
_Avoid_: udsving

**Sammenhæng**:
En fast hypotese om to tal, testet på tværs af uger: stærk, en antydning eller for få uger til at sige noget.

## Økonomi

**SU-vagt**:
Overvågningen af årets indkomst mod SU-fribeløbet.
_Avoid_: fribeløbsberegner

## Tekniske navne

Ordene ovenfor gælder for tekst, du læser: sider, rapporter, rutinernes prosa og svar. Navne, som scripts læser
eller skriver, bliver stående, selv om de bruger et ord fra en _Avoid_-linje, fordi en omdøbning kræver samtidige
ændringer i parsere, data og rutiner. De vigtigste:

- **Studie**: køreplanens faste overskrifter (`## Deadlines …`, `## Genkaldelse …`, `## Vigtigst i ugen`) og
  kolonner (`| Uge | Dato | Fag | Aktivitet | Bemærkning |`), filnavnene `Ugeplan_ugeNN_*.md`, `deadlines.html`,
  `deadlines-status.json` og `begreber.md` med kolonnen `Din definition`, API-stierne under `/studie/api/` og
  JSON-felter som `deadlines` og `definition`.
- **Form & fokus**: MCP-værktøjer og -prompts (`periode`, `sync`, `ugeplan`, `evaluering` …), CLI-kommandoerne
  (`byg`, `gem-periode` …), JSON-felterne (`vurdering`, `fokus`, `garmin_load`, `load`, `rapport` …) og tabellen
  `perioder`. Garmins egne navne (Training readiness, Body Battery) står uændret.
- **Overblik**: kommandoen `liv`, pakken og mappen `overblik`, `~/.overblik/liv.db` og felterne
  `rapport`, `vurdering` (godt/skidt på en afvigelse), `metode` og `genereret`.
- **Sprog**: kommandoerne i `sprog.js` (`rapport`, `tilfoej`, `tekst`, `feedback`, `regel`, `niveau`, `aktivt`, `rolle`), korttyperne
  (`frase`, `ret`, `ord`, `udfyld`, `test`), `regel` (kommandoen og kortenes felt), rollerne (`aktiv`, `vedligehold`, `pause`, `studie`) og felterne i `data/` (`forside`,
  `bagside`, `situation`, `nye_pr_dag`, `laert` …).
- **På tværs**: rutinernes id'er (`studie-koereplan`, `traening-rapport`, `overblik-ugereview`, `sprog-ugen`),
  Sures `dashboard/`, `/dashboard-state/<navn>` og `/dashboard-category/<id>`, `mobil.html` og manifest-nøglen `fane`.
