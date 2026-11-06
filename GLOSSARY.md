# Kompas

Én side, der samler økonomi, studie, sprog, form og skærmtid fra projekterne. Ordlisten gælder på tværs af
projekterne, så sider, rutiner og samtaler bruger de samme ord.

## Platformen

**Kompas**:
Den samlede side, der viser projekternes sider bag én menu og selv ejer forsiden I dag og Forbindelser.
_Avoid_: portal, dashboard

**Projekt**:
Et selvstændigt program, der regner sine egne tal og leverer sider til ét område i Kompas.
_Avoid_: app, modul, service

**Område**:
En gruppe i menuen: Økonomi, Studie, Sprog eller Form & fokus. Flere projekter kan dele et område; Skærmtid står
under Form & fokus.
_Avoid_: sektion, fane

**Rutine**:
En planlagt Claude-kørsel, der skriver nyt indhold til et projekt: Studie, Træning, Overblik, Sprog eller Skærmtid.
_Avoid_: planlagt opgave, job, agent

**Forbindelse**:
Noget, Kompas henter fra eller kører på (en datakilde, en rutine, en server eller et baggrundsjob), med en status:
ok, advarsel, fejl eller info.
_Avoid_: integration

**Står stille**:
Det, der ikke er rørt i flere dage, selvom der venter noget: Sprog og Genkald efter 3 dage uden svar, en enhed
efter 2 dage uden skærmtid (ikke en enhed, du sjældent bruger: `sjaelden` i `regler.json`), og studieblokke, når 2
af de seneste 3 døgn havde studieblokke uden logget selvstudie. Vises på I dag; tidspunkterne kommer fra projekterne
(`sidst_svar`, `enheder[].sidst`), grænserne står i `STILLE_DAGE` i I dag. Studieblokkene regner overblik selv (`glippede` i `liv.json`).
_Avoid_: inaktiv, glemt

**På farten**:
Studie på telefonen: dagens kort hentes, mens Mac'en er vågen, og svarene sendes, når den er det igen.
_Avoid_: mobilappen, mobilsiden

## Studie

**Fag**:
Et af semestrets kurser, kendt ved sit kortnavn (i demoen Alfa, Beta og Gamma).
_Avoid_: kursus

**Køreplan**:
Ugens plan for de tre fag med læsning, træning, frister og det vigtigste i ugen. Ugens noter står i fagnoterne.
Vises på Ugeoverblik.
_Avoid_: ugeplan

**Fagnoter**:
Det løbende notedokument for et fag med ugens noter: skrevet foreløbigt søndagen før ugen og rettet søndagen efter,
når slides og øvelser er lagt op. Det er også dokumentet til USB'en.
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

**Sikkerhed**:
Hvor sandsynligt du tror, dit svar på et kort er rigtigt, sat på skyderen fra 0 til 100 % (rød til grøn), før svaret
vises. Fra 70 % hedder det sikker, fra 30 % usikker, ellers gætter; "Kan ikke" er 0 %. Kalibreringen på Træning viser,
hvor tit det sad ved hver sikkerhed. Står i `genkald-log.jsonl`.
_Avoid_: confidence (i tekst til brugeren)

**Tænk højt**:
Feltet under svaret på et kort, hvor du skriver eller dikterer, hvordan du tænkte, og hvad du er i tvivl om. Valgfrit.
Står kun i `genkald-log.jsonl`, ikke i genkaldsfilen.
_Avoid_: noter, refleksion

**Tjek ugen først**:
Knappen over "Sådan lærer du uge N" på Fag i fag med genkald: ugens genkaldsspørgsmål fra hukommelsen og med
sikkerhed, før du læser ugen, så du kan springe de skridt over, du var sikker på og havde ret i.
_Avoid_: forhåndstest, probe

**Dine huller**:
Første trin i en uges studieguide, når du har svaret sikkert, men forkert i faget de sidste 14 dage (fra 70 % og
halvt eller blankt, eller et forkert drill-gæt uden flueben i *gættede*): højst tre kort med hvad der gik galt, ud fra
Tænk højt, og hvor du læser det igen. Studie-rutinen skriver det.
_Avoid_: fejl, svagheder

**Læst uge**:
En uge, du har markeret som læst i et fag under Styr på. I fag med genkald kommer ugens genkald først da med i dagens
kort; i alle fag planlægger Studie-rutinen indhentningen efter de uger, der ikke er læste.

**Frist**:
Et tidspunkt, hvor en aflevering, præsentation eller eksamen skal være klar. Kan markeres færdig.
_Avoid_: deadline

**Prøveeksamen**:
Et gammelt eksamenssæt taget på tid som generalprøve; din egen plan, ikke en frist fra universitetet.
_Avoid_: øvelseseksamen

**Selvstudie**:
Studietid uden for undervisningen, logget med stopuret på Studies side Selvstudie.
_Avoid_: læsetid

**Session** (Selvstudie):
Én gang selvstudie i ét fag, fra du starter timeren, til du stopper den, eller som du selv har tilføjet bagefter. En
pause deler sessionen i stykker; kun stykkerne tæller. Kan have en aktivitet (fx Øvelser) og en note. Står i Studies
`Scripts/sessioner.json`.
_Avoid_: logning, blok

**Timer**:
Knappen under Frister i Kompas' menu, der logger en session: et stopur, der tæller op, eller Pomodoro (fokus på fx 25,
45 eller 60 minutter, et antal fokus og en pause imellem, som du vælger i timeren). Mens den kører, står en tæller
øverst over siden, og fanens titel tæller med. Stop åbner Gem session, hvor du kan rette start, slut, pause og fag og
skrive en aktivitet og en note. ▶ på knappen starter det sidste fag med dine sidste valg. Studie-serveren holder den,
så den kan startes på Mac'en og stoppes på bærbaren.

**Stopur**:
Timeren, når den tæller op i stedet for Pomodoro.

**Rytme** (Selvstudie):
Hvornår du studerer: timerne pr. ugedag og pr. time på døgnet (samlet i tidsrum på fire timer, 2-6, 6-10 …) for denne
uge, denne måned eller det hele, efter uret og ikke efter den dag, sessionen begyndte. Regnet af Studies eksport.
_Avoid_: mønster, vane

**Forslag** (Selvstudie):
Selvstudie, Kompas foreslår ud fra tidspunkterne på dine svar (Dagens kort, Genkald, drills, sprogkort), også fra
telefonen, og som først tæller, når du gemmer det på Selvstudie. Svar med højst 10 minutter imellem hører sammen; tid,
der allerede er logget, trækkes fra. Et forslag i flere fag gemmes som én session pr. fag. Sprogs forslag gemmes hos
Sprog og tæller ikke i dagsmålet. Et afvist forslag kommer ikke igen.
_Avoid_: auto-log, automatisk session

**Dagsmål**:
De timers logget selvstudie, du sigter efter på dine studiedage. Sættes under Indstillinger på Selvstudie (Studies
`Scripts/studiemaal.json`, som går forud for `studiemaal` i fag.json).
_Avoid_: daglig kvote

**Fremmøde** (Studie):
Om du var til en undervisningsgang. Du markerer de gange, du ikke var til, i Ugeoverblik (klik på undervisningen), også
bagud; de tæller så ikke som brugt tid på Selvstudie. Slags, du aldrig bruger, står i `fravaer.json` og kan ikke markeres. Gemmes i Studies `Scripts/fremmoede.json`.
_Avoid_: tilstedeværelse, check-in

**Fridag** (Selvstudie):
En dag uden dagsmål, fordi den ikke er valgt under Indstillinger. Den trækker ikke saldoen ned og bryder ikke dage i
træk; det, du alligevel studerer, tæller. Vises med en kop.
_Avoid_: hviledag, pausedag

**Dage i træk**:
Antal dage i træk med logget selvstudie, talt fra i dag, eller fra i går, når der ikke er logget noget i dag endnu.
_Avoid_: streak (i tekst til brugeren)

**Medalje**:
Dagens bronze, sølv eller guld efter, hvor meget selvstudie der er logget (fra 2, 3 og 4 timer).

**Semester**:
En semestermappe med sine egne fag, frister og sessioner (`Scripts/fag.json`). Det aktuelle er det, `~/kompas/studie`
peger på, og alt under Studie viser det; de tidligere står samlet på siden Semestre. Perioden går fra første
undervisningsdag til sidste eksamen.
_Avoid_: term, termin

**Saldo** (Studie):
Den samlede forskel mellem logget selvstudie og dagsmålet, dag for dag, siden logningen begyndte.
_Avoid_: share price

**Studieblok**:
En blok i skolekalenderen, lagt efter en studieplan, med mærket `#kompas-plan` sidst i noten. Mærket gør, at
blokkene kan findes og erstattes uden at røre dine andre aftaler, og at overblik kan se, hvilke blokke der glipper.
I dag måler ugens selvstudie mod ugens studieblokke (`studieuge` i `liv.json`).
_Avoid_: planblok, indhentningsblok

**Minimumsdag**:
Det mindste, der tæller som en god studiedag: Dagens kort og ét lille skridt (et begreb eller et
drill-tjek), højst 15 minutter. Køreplanen skriver ugens minimumsdag under Vigtigst i ugen.
_Avoid_: nødplan, minimumsplan

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
To til tre handlinger til næste periode, hver med dag og tidspunkt, så man bagefter kan se, om de skete. Vises på
Perioder og forsiden.
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

## Skærmtid

**Skærmtid**:
Tiden, du bruger en enhed, regnet af ActivityWatch: på computerne kun tid, hvor du er aktiv; på telefonen tiden med
skærmen tændt. Tid på flere enheder på én gang tæller én gang; hver enhed har stadig sin fulde tid.
_Avoid_: screen time, forbrug (om tid)

**Enhed**:
Mac, Stationær, Bærbar eller Telefon: det, ActivityWatch logger på. Navnet står i `regler.json` ud for værtsnavnet.
_Avoid_: device, maskine

**Kategori**:
Det, skærmtiden går til: Studie, Sprog, Økonomi, Form & fokus, Egne projekter, Kommunikation, Sociale medier,
Video & streaming, Spil, Nyheder, Indkøb eller Hverdag (kort, kamera, billeder, musik, filer, fjernbetjeninger,
indstillinger og den slags praktiske ting). Dit valg bestemmer den, ellers den første regel i `regler.json`, der passer (regler med titel alene prøves sidst); resten er
ukategoriseret. Hver kategori hører til én gruppe.
_Avoid_: tag, label

**Gruppe** (Skærmtid):
Det, kategorierne samles i, og som Skærmtid viser øverst: **Produktiv** (Studie, Sprog, Egne projekter,
Form & fokus, Økonomi), **Passiv** (uproduktiv, passiv underholdning: Sociale medier, Video & streaming, Nyheder),
**Gaming** (Spil) og **Praktisk** (Kommunikation, Hverdag, Indkøb). Grupperne er bevidst ikke neutrale: de svarer på,
hvor meget af tiden der er produktiv. Tjek er ikke en gruppe, men et antal (se Kort tjek). Står i `regler.json` under
`grupper`.
_Avoid_: hovedkategori, type, Dopamin-tjek, Passiv underholdning

**Kort tjek** (Skærmtid):
En åbning af en app i Sociale medier eller Nyheder på telefonen, der varer under et minut. En åbning er sammenhængende
tid i samme app; et skift til en anden app eller hjemmeskærmen afslutter den. Vises pr. dag ved siden af oplåsningerne.
_Avoid_: check, session

**Valg** (Skærmtid):
Det, du vælger på Skærmtid-siden for ét program eller én side: en kategori eller "tæller ikke med". Går forud for
reglerne og gemmes i `skaermtid/valg.json`.
_Avoid_: override, undtagelse

**Sen skærmtid**:
Skærmtid efter kl. 23, til døgnet skifter kl. 6. Hører til aftenens dag.
_Avoid_: natskærmtid

## Økonomi

**SU-vagt**:
Overvågningen af årets indkomst mod SU-fribeløbet.
_Avoid_: fribeløbsberegner

**Fast betaling**:
En udgift, der kommer igen: samme modtager og kategori i mindst 3 af 6 måneder (eller én gang om året) til omtrent samme
beløb. Sures eksport finder dem; Forbrug viser de aktive og dem, der ikke er betalt i over halvanden måned (årlige: et år).
_Avoid_: abonnement (et abonnement er én slags fast betaling), tilbagevendende transaktion (Sures egen, der kun finder få)

**Tag** (Økonomi):
En rejse eller begivenhed i Sure, fx "Sommerferie", sat på forbruget mellem to datoer, så Forbrug kan vise det samlet
uanset periode. Claude sætter det, når du beder om det, eller du tagger selv i Sure.
_Avoid_: etiket, label

**Månedens gennemgang**:
Økonomi-rutinens gennemgang af den måned, der lige er slut: forbrug mod budget, faste betalinger og forslag til
budgettet. Den foreslår kun; du retter selv i Sure. Står på siden Gennemgang under Økonomi.
_Avoid_: månedsrapport, budgetrevision

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
- **Skærmtid**: felterne i `regler.json` (`app`, `domaene`, `sti`, `titel`, `vaert`, `sjaelden`, `ignorer`, `browsere`) og i
  `skaermtid.json` (`dage`, `uger`, `perioder`, `sen_timer`, `ukategoriseret`, `stoerste`), ActivityWatch' egne navne
  (bucket, watcher, afk, `hostname`) og trinnet `skaermtid` i opdater.sh.
- **På tværs**: rutinernes id'er (`studie-koereplan`, `traening-rapport`, `overblik-ugereview`, `sprog-ugen`, `skaermtid-ugen`,
  `okonomi-maaneden`), Sures `dashboard/`, `/dashboard-state/<navn>` og `/dashboard-category/<id>`, `mobil.html` og manifest-nøglen `fane`.
