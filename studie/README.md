# Studie

Studie-delen af Kompas (`/studie/`): ugeoverblik, fag, genkald med spaced repetition, eksamenstræning, frister,
selvstudie mod kursusbeskrivelsernes timer, semestre, USB-noter og en offline-app til telefonen. Koden ligger i `Scripts/` inde i en semestermappe og læser de filer, man alligevel
arbejder i: køreplaner, genkaldsspørgsmål, begreber, drills og eksamenssæt i markdown og JavaScript.

Kun koden er med her. Kursusmateriale, egne svar og forsøgsloggen hører til semestermappen og er ikke en del af
repoet. Demoen (`demo/projekter/studie.py`) laver opdigtede data i samme form.

## Filerne

| Fil | Hvad den gør |
|---|---|
| `Scripts/semester.js` | Semestret ét sted: fagene fra `fag.json`, frister og eksamensdage fra CLAUDE.md og eksamensformerne fra README.md. De andre scripts spørger herfra i stedet for at have egne lister. |
| `Scripts/sessioner.js` | Formatet på `sessioner.json` (stopuret og de loggede sessioner), hvad en session tæller, og forslagene ud fra tidspunkterne på dine svar. Serveren skriver filen, eksporten læser den. |
| `Scripts/nyt-semester.js` | Semesterskiftet i ét trin (se Nyt semester): laver den nye mappe og peger Studie på den. Prøvekørsel uden `--kør`. |
| `Scripts/fag.example.json` | Eksempel på `fag.json` med demoens tre fag og en forklaring af hvert felt. Kopiér til semestermappens `Scripts/fag.json`. |
| `Scripts/kompas-eksport.js` | Læser semestermappen og skriver `studie.json`, `fagnoter.json`, `resumeer.json`, `kalender.json`, `selvstudie.json`, `semestre.json`, `sessioner.json` og `kompas.json` til `~/.kompas/studie/`, plus en kopi af siderne. Læser kun; ændrer aldrig arbejdsfiler. Al optælling sker her (genkald og drills i alt, rytmen pr. dag, ord pr. fagnote-uge, selvstudiet), så siderne ikke regner selv. |
| `Scripts/kompas-server.js` | Lille server på `127.0.0.1:8767` (Caddy sender `/studie/api/*` hertil). Læser genkald, begreber, drills og eksamenssæt og skriver kun det, brugeren selv taster: svar, markeringer, begreber med egne ord, gæt, ugens I egne ord (`<fagmappe>/egne-ord.md`) og vurderingen af en uge i USB-noterne (`usb-vurdering.json`). Udleverer ugens forelæsninger og øvelser fra `<fagmappe>/Pensum/` til Fag-siden (kun læsning). En genkaldsfil, der ikke kan læses, springes over og står i loggen. Facit udleveres først efter et forsøg. |
| `Scripts/kompas/` | Siderne: Ugeoverblik (`index.html`), Fag (med Rytme og Styr på), USB-noter (`usb.html`, under Fag), Træning (`genkald.html`), Eksamen (med Opgaver efter niveau), Selvstudie (`selvstudie.html`), Semestre (`semestre.html`), Frister (`deadlines.html`) og På farten (`mobil.html` med service worker, manifest og ikoner). De bruger Kompas' designkit fra `/kompas/assets/`. |
| `Scripts/drill-forklaringer.js` | Viser de drill-tjek, der mangler en forklaring, med det JavaScript faktisk giver. Læser kun. |
| `Scripts/canvas-sortering.js` | Flytter Canvas-downloads fra `~/Downloads` ind i fagmapperne og giver dem ensartede navne (macOS; bruger `xattr`, `plutil` og evt. LibreOffice). Prøvekørsel uden `--kør`. |
| `Scripts/undervisningsdage.example.json` | Eksempel på skemaet, `canvas-sortering.js` bruger. Kopiér til `undervisningsdage.json`. Selvstudie tager første undervisningsdag herfra. |
| `Scripts/fravaer.example.json` | Eksempel på `fravaer.json`: uger, du ikke var til stede, og slags undervisning, du ikke bruger. Selvstudie tæller dem ikke som brugt tid. |
| `Scripts/fagnoter/` | Studie-rutinens værktøj til fagnoterne (Python, python-docx): `run_notes.py` sætter en uges noter ind i fagets Word-dokument, `verify_prog.py` kører kodeeksemplerne gennem node, og `labels.json` er skabelonens labels, som eksporten også læser. Formatet står i `Scripts/fagnoter/README.md`. |

JavaScript-delen er CommonJS uden afhængigheder; Node 18 eller nyere. Eksporten bruger `unzip` til fagnoterne (Word).

## Kør

```sh
node Scripts/kompas-eksport.js                 # skriver til ~/.kompas/studie
node Scripts/kompas-server.js                  # API'et på 127.0.0.1:8767

# en testserver på en kopi af semestermappen, så de rigtige filer ikke røres
KOMPAS_SEMESTER=/tmp/kopi STUDIE_PORT=18767 STUDIE_EKSPORT_UD=/tmp/studie-ud node Scripts/kompas-server.js
```

| Env-variabel | Standard | Bruges af |
|---|---|---|
| `KOMPAS_SEMESTER` | mappen over `Scripts/` | alle scripts: semestermappen, der læses og skrives i |
| `STUDIE_EKSPORT_UD` | `~/.kompas/studie` | eksporten (`--ud <mappe>` vinder); serveren sender den videre, når den kører eksporten efter en gemning |
| `LIV_SITE` | `~/.garmin-coach/site` | eksporten: mappen, overblik skriver `liv.json` i (kalenderen til telefonen) |
| `STUDIE_PORT` | `8767` | serveren |
| `STUDIE_ORIGINS` | tom | serveren: ekstra adresser, der må skrive, fx telefonens Tailscale-adresse (kommasepareret) |
| `CANVAS_VAERT` | `canvas.instructure.com` | `canvas-sortering.js` |
| `KOMPAS_STUDIE_LINK` | `~/kompas/studie` | `nyt-semester.js`: symlinket, `--skift` peger om (med et andet link genstartes serveren ikke) |

## Semestermappen

```
<semestermappe>/
  CLAUDE.md                     tabellerne "## Vigtige datoer" og "## Egen plan" (| Uge | Fag | Hvad |)
  README.md                     tabellen "## De tre fag trænes forskelligt" (| Fag | Eksamen | Det der virker |)
  Uge_Overblik/
    Ugeplan_uge12_16-22mar_2027.md
  Alfa/  Beta/  Gamma/          ét fag pr. mappe (fagene står i Scripts/fag.json)
    Fagnoter - Alfa.docx        Word; hver uge er en "Uge NN — …"-overskrift (Overskrift 2)
    Alfa_Eksamener.pdf          gamle eksamenssæt: filer med "eksamen" i navnet (tælles; mappen Eksamenstræning tæller ikke)
    Genkald/
      begreber.md
      genkald-uge10-11.md       spørgsmål  (+ genkald-uge10-11-svar.md med facit)
    Modeller/                   tegnede modeller (tælles)
    Pensum/Forelæsninger/       forelæsninger og øvelser med undervisningsdagen forrest i navnet (20260904_FL1_….pdf);
    Pensum/Øvelser/             Fag-siden viser dem under ugen (canvas-sortering.js lægger dem der)
    egne-ord.md                 I egne ord: én "## Uge NN" pr. uge, skrevet fra Fag-siden eller telefonen
    studieguide.md              hvordan du lærer ugens pensum hurtigst: én "## Uge NN — emne" pr. uge (studieguide i fag.json)
    Resumeer/*.md               kapitelresuméer med ugen i overskriften: "# Kap. 5 — emne (uge 37)" (resumeer i fag.json)
    Eksamenstræning/
      <id>.md, <id>-svar.md     sæt og facit; besvarelser/ skrives af serveren
      niveauer.json             underviserens oversigt over gamle opgaver (niveau, fokus, efter hvilken forelæsning)
  Gamma/vscode/                 faget med kode: drills og nummererede afleveringer
    Drills/kap01-lorem.js       drills  (+ tjek.js og forklaringer/kap01-lorem.md)
    Opgaver/README.md           "## Status"-tabel (| Opgave | Uge | Afleveret | Godkendt | Hvad drillede |)
                                og fx "**4 af 6 skal godkendes**"; Opgave 1/, Opgave 2/ … er mapperne
    Bog/  Øvelser/  *.js        færdige og igangværende øvelser (tælles)
  Scripts/                      koden + semestrets egne filer:
    fag.json                    fagene, og hvad hvert fag har (genkald, begreber, kode, afleveringer, eksamensform)
    genkald-log.jsonl           alle forsøg; Dagens kort regnes ud herfra
    laest.json                  uger markeret som læst
    deadlines-status.json       frister markeret som færdige
    usb-vurdering.json          din vurdering af hver uge i USB-noterne (skrives af serveren)
    fravaer.json                undervisning, der ikke tæller som brugt tid på Selvstudie (se fravaer.example.json)
    fremmoede.json              de undervisningsgange, du har markeret, at du ikke var til (Ugeoverblik; skrives af serveren)
    sessioner.json              selvstudiet: stopuret og sessionerne (formatet står i sessioner.js; skrives af serveren)
    studiemaal.json             dine mål fra Indstillinger på Selvstudie; går forud for studiemaal i fag.json
    fagnoter/vurdering-handlet.json  de vurderinger, Studie-rutinen har rettet fagnoterne efter
    fagnoter/backup/            Studie-rutinens backup af fagnoterne før hver ændring
```

Formaterne, koden forventer:

- **Køreplan** (`Ugeplan_uge*.md`): `# Titel`, et `## <fagnavn>`-afsnit pr. fag (overskriften starter med fagets `fagnoter_overskrift`) med `**Hurtigt overblik**`, `**Kilder**`,
  `**Noter til pensum**`, `**Til rapporten**` og `**Video**`, og evt. øvelsesspørgsmål fra `*Øvelsesspørgsmål …*`
  til `*Svar …*`. Desuden `## Vigtigst i ugen`, `## Genkaldelse …` (med `*Svar*`) og `## Deadlines`
  (`| Uge | Fag | Aktivitet | Dato | Bemærkning |`): fristerne. Et klokkeslæt står i Dato-kolonnen (`06.10 kl. 08:00`) eller i
  teksten; Dato-kolonnen vinder. Planerne skrives af en planlagt Claude-opgave
  (Studie-rutinen, instruktionerne står i `RUTINE.md`) eller i hånden; koden læser dem kun. En frist med en aflevering i teksten (fagets
  præfiks i `fag.json` og et nummer, fx "Opgave 3") kobles til afleveringernes tabel, så den er færdig, når kolonnen Afleveret er udfyldt.
- **Genkald**: `## Uge 10 — emne` og spørgsmål som `**1.** …`. Markeringen står efter nummeret
  (`**1.** [✓] …`, `[~]`, `[✗]`), dit svar nederst som `> **Mit svar** (14.03): …`. `-svar.md` har samme numre.
- **Begreber**: `## Uge 10 — emne` og en tabel, hvis første kolonne hedder `Begreb`:
  `| Begreb | Min definition | Kilde |` (et fag med `ekstra_kolonne` i `fag.json` har også
  den kolonne, fx Beta: `| Hvad det får dig til at se |`).
- **Drills**: `tjek("beskrivelse", () => udtryk, TOM);` under `// ── afsnit ──`-linjer. Gættet skrives i stedet
  for `TOM`. `tjek.js` (i drillmappen, ikke med her) eksporterer `tjek`, `TOM` og `opsummer` og skriver
  `FEJL  <beskrivelse>`, `du gættede …` og `JavaScript: …` ved fejl og til sidst `N rigtige · N forkerte · …`.
- **Eksamenssæt**: `# Titel`, en kursiv metalinje (`*2 timer · …*`), `---`, sektioner som
  `## Del A — Multiple choice (40 %)` og opgaver som `**1.** …` med `*Emne: Tema — detalje · uge 10*` til sidst (samme Tema for samme emne i alle sæt; Til eksamen
  på Fag grupperer efter det) eller `*Emne: … · kap. 4 og 5*` (første kapitel er hovedemnet; `kapitler` i `undervisningsdage.json`
  kobler kapitlerne til ugerne). Sæt med et årstal i navnet er gamle eksamenssæt; de andre er dine egne pensumspørgsmål.

## API

Alle under `/studie/api/`. Skrivninger kræver `Content-Type: application/json` og en tilladt `Origin`.

| GET | Svar |
|---|---|
| `/genkald`, `/facit?fag&fil&nr` | genkaldsfilerne med spørgsmål og markeringer; facit for ét spørgsmål |
| `/begreber` | begreberne pr. fag |
| `/drills` | drillene med status for hvert tjek (filerne køres med Node) |
| `/repetition`, `/repetition/svar?noegle` | Dagens kort og statistik; svaret på ét kort |
| `/laest` | uger markeret som læst |
| `/eksamen`, `/eksamen/saet?fag&id`, `/eksamen/facit?fag&id[&nr]` | sættene, ét sæt, facit |
| `/eksamen/niveauer` | Opgaver efter niveau: hver opgave med sin sektion i sættet og dine seneste markeringer |
| `/eksamen/uger` | Til eksamen på Fag: hvad de gamle sæt har spurgt om fra hver uges stof, pr. fag |
| `/usb-vurdering` | dine vurderinger af USB-noterne pr. fag og uge (eller hovedafsnit) |
| `/egne-ord` | I egne ord pr. fag og uge |
| `/pensum/<fag>/<Forelæsninger\|Øvelser>/<fil>` | én fil fra fagets `Pensum/` (pdf, pptx, docx; øvelsessæt i markdown som ren tekst) |
| `/stopur` | stopuret, dagens loggede tid, forslagene og sessionerne de seneste 14 dage |
| `/fremmoede` | de undervisningsgange, du har markeret, og de slags undervisning, du aldrig bruger |
| `/pakke` | På farten: dagens kort med facit, ekstra genkald, tomme begreber, ugættede drills og I egne ord |

| POST | Skriver |
|---|---|
| `/genkald` | svar og markering i `genkald-*.md` |
| `/begreb` | begrebet med egne ord i `begreber.md` |
| `/egne-ord` | ugens tekst i `<fagmappe>/egne-ord.md` (en tom tekst fjerner ugen) |
| `/drill` | gæt i stedet for `TOM`; filen køres, og går den ned, sættes den tilbage |
| `/repetition`, `/eksamen/resultat` | et forsøg i loggen (og i filen for genkald) |
| `/eksamen/afslut` | besvarelsen i `Eksamenstræning/besvarelser/` |
| `/usb-vurdering` | `usb-vurdering.json`: brugbar, for meget eller mangler noget plus en kommentar (højst 2000 tegn) for et fag med `usb_noter` |
| `/laest`, `/deadline` | `laest.json`; færdig-markering i `deadlines-status.json` eller afleveringernes tabel |
| `/stopur` | start, pause, fortsæt, skift fag, annullér og stop i `sessioner.json` |
| `/session` | en session, du tilføjer, retter eller sletter |
| `/forslag` | et forslag ud fra dine svar, gemt eller afvist |
| `/studiemaal` | dine mål fra Indstillinger på Selvstudie i `studiemaal.json` |
| `/fremmoede` | en undervisningsgang, du ikke var til (eller alligevel var til), i `fremmoede.json` |
| `/sync` | svar givet på telefonen uden net og markeringer sat uden net (læst uge, færdig frist, USB-vurdering), med samme skrivninger som ovenfor |

## Dagens kort

Kortene regnes ud af `genkald-log.jsonl`; der er ingen anden tilstand. Hvert svar har en karakter (1 blankt,
2 halvt, 3 sad, 4 let), og FSRS-6 med standardparametrene planlægger kortet: det kommer igen, når du regnes for at
kunne det med 90 % sandsynlighed, så lette kort venter længere end svære. Står et fags eksamen med dato under
"Vigtige datoer" i semestermappens CLAUDE.md, kommer et kort før eksamen, hvis det ellers ville være under 95 % på eksamensdagen. Op til 5
nye genkaldsspørgsmål om dagen, og kun fra uger, der er markeret som læst. Typerne (genkald, eksamen, begreb, drill) blandes på skift, og
siden viser, hvor tit svaret sad, når man sagde "sikker", "usikker" eller "gætter". Sikkerheden gives som 0-100 % på en
skyder; under Tænk højt kan du skrive, hvordan du tænkte, og begge dele står kun i loggen.

## Selvstudie og USB-noter

**Selvstudie** sammenligner tiden pr. fag med kursusbeskrivelsens arbejdstimer (`arbejdsbyrde` i `fag.json`). Selvstudiet er
sessionerne i `sessioner.json`: stopuret (i Kompas' menu og på siden, også med Pomodoro), det, du selv tilføjer eller retter,
og forslag ud fra tidspunkterne på dine svar, som du gemmer eller afviser. Undervisningen kommer fra overbliks `liv.json`
(`studietid`) pr. kursuskode, uden de gange, du har markeret under Fremmøde i Ugeoverblik. Forventet til nu regnes for et fag
med kendt start og eksamen; et kursus over flere semestre kan have dette semesters del under `dette_semester`. Øverst står
dagsmålet fra Indstillinger på siden (ellers `studiemaal` i `fag.json`): fremskridt, dage i træk, medaljer, saldoen mod
dagsmålet, rytmen (ugedage og tidsrum) og en månedskalender. Eksporten regner det hele; siden viser det kun, undtagen
stopuret, der tæller sekunderne i den session, du selv har startet.

**USB-noter** viser fagnoterne i Word for et fag med `usb_noter` uge for uge, med antal ord og kodeblokke. Du giver en
uge en vurdering, og Studie-rutinen (se `RUTINE.md`, afsnit 6) skriver ugen om efter den med `RESET_WEEKS` i en
notes-fil; det, der står under I egne ord, flyttes med uændret.

## Nyt semester

Koden kender ingen fag; alt fagspecifikt står i semestermappens filer. Et semester er en mappe med `Scripts/fag.json`,
og `KOMPAS_SEMESTER` (eller symlinket `~/kompas/studie`) peger på det aktuelle. Alt under Studie viser det; de tidligere
står på Kompas → Studie → **Semestre** (periode, fag, selvstudie mod forventet, saldo og medaljer), regnet ud fra hvert
semesters egne filer, som mapper ved siden af det aktuelle. Semesterskiftet er `Scripts/nyt-semester.js`, kørt fra det
semester, der slutter:

1. `node Scripts/nyt-semester.js "2. sem" --navn "2. semester"` viser, hvad der bliver lavet (mappens navn først;
   `--navn` er navnet på siderne, `semester` i fag.json); med `--kør` laver det mappen ved siden af denne: `Scripts/` og
   `RUTINE.md`, `README.md`, `CLAUDE.md`, men ikke log- og statusfilerne (`genkald-log.jsonl`, `laest.json`,
   `deadlines-status.json`, `fravaer.json`, `fremmoede.json`, `sessioner.json`, `usb-vurdering.json`, `canvas-*`) eller
   fagnoternes backup. `studiemaal.json` (dine mål fra Indstillinger på Selvstudie) kommer med, så dagsmålet, dagene og
   medaljerne gælder fra første dag. CLAUDE.md mister rækkerne under "Vigtige datoer" og "Egen plan".
   `Scripts/fag.json` får kun de fag, der fortsætter: et kursus over to semestre får `dette_semester` med resten af
   kursusbeskrivelsens timer (hver post minus det, de tidligere semestre har haft, som står under `tidligere`) og
   `til: "eksamen"`, og dets `canvas` tømmes. Et fag, der er slut, kommer ikke med.
2. Udfyld den nye mappe: de nye fag i `Scripts/fag.json` (se `fag.example.json`), og tjek dem, der fortsætter (canvas,
   eksamenstraening, afleveringer); `Scripts/undervisningsdage.json` (semestrets periode starter ved den første dag);
   "Vigtige datoer" og "Egen plan" i `CLAUDE.md` (eksamensdagene læses herfra); tabellen "De tre fag trænes forskelligt"
   i `README.md`, så Fag-kolonnen matcher `readme` i `fag.json`.
3. `node Scripts/nyt-semester.js "2. sem" --skift` siger, hvad der stadig mangler; med `--skift --kør` peger det symlinket
   på den nye mappe, genstarter Studie-serveren og kører eksporten og testene dér. Sætter du `KOMPAS_SEMESTER` selv, så
   ret den også. Selvstudiet begynder forfra: stopuret laver `Scripts/sessioner.json` med dagens dato som `fra`, første
   gang det startes, og overblik beholder de tidligere ugers tal. Kalenderens undervisning tæller kun inden for semestrets
   periode, så et kursus over to semestre (samme kursuskode) ikke tæller dobbelt.
4. Fagnoternes eksempler (`notes_<id>.py`, se `Scripts/fagnoter/README.md`) bruges efter eksamensform, indtil de nye fag
   har deres egne.

Testene: `node tests/test_studie_semester.js && node tests/test_studie_fag.js && node tests/test_studie_sider.js`
og `node tests/test_studie_nyt_semester.js` (scriptet mod et opdigtet semester i en midlertidig mappe).
