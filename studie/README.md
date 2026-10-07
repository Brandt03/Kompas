# Studie

Studie-delen af Kompas (`/studie/`): ugeoverblik, fag, genkald med spaced repetition, eksamenstræning, frister og
en offline-app til telefonen. Koden ligger i `Scripts/` inde i en semestermappe og læser de filer, man alligevel
arbejder i: ugeplaner, genkaldsspørgsmål, begreber, drills og eksamenssæt i markdown og JavaScript.

Kun koden er med her. Kursusmateriale, egne svar og forsøgsloggen hører til semestermappen og er ikke en del af
repoet. Demoen (`demo/projekter/studie.py`) laver opdigtede data i samme form.

## Filerne

| Fil | Hvad den gør |
|---|---|
| `Scripts/kompas-eksport.js` | Læser semestermappen og skriver `studie.json`, `fagnoter.json`, `kalender.json` og `kompas.json` til `~/.kompas/studie/`, plus en kopi af siderne. Læser kun; ændrer aldrig arbejdsfiler. |
| `Scripts/kompas-server.js` | Lille server på `127.0.0.1:8767` (Caddy sender `/studie/api/*` hertil). Læser genkald, begreber, drills og eksamenssæt og skriver kun det, brugeren selv taster: svar, markeringer, definitioner og gæt. Facit udleveres først efter et forsøg. |
| `Scripts/kompas/` | Siderne: Ugeoverblik (`index.html`), Fag, Genkald, Eksamen, Deadlines og På farten (`mobil.html` med service worker, manifest og ikoner). De bruger Kompas' designkit fra `/kompas/assets/`. |
| `Scripts/drill-forklaringer.js` | Viser de drill-tjek, der mangler en forklaring, med det JavaScript faktisk giver. Læser kun. |
| `Scripts/canvas-sortering.js` | Flytter Canvas-downloads fra `~/Downloads` ind i fagmapperne og giver dem ensartede navne (macOS; bruger `xattr`, `plutil` og evt. LibreOffice). Prøvekørsel uden `--kør`. |
| `Scripts/undervisningsdage.example.json` | Eksempel på skemaet, `canvas-sortering.js` bruger. Kopiér til `undervisningsdage.json`. |

Alt er CommonJS uden afhængigheder; Node 18 eller nyere. Eksporten bruger `unzip` til fagnoterne (Word).

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

## Semestermappen

```
<semestermappe>/
  CLAUDE.md                     tabellerne "## Vigtige datoer" og "## Egen plan" (| Uge | Fag | Hvad |)
  README.md                     tabellen "## De tre fag trænes forskelligt" (| Fag | Eksamen | Det der virker |)
  Uge_Overblik/
    Ugeplan_uge12_16-22mar_2027.md
  Alfa/  Beta/  Gamma/          ét fag pr. mappe (fagene står i FAG øverst i kompas-eksport.js)
    Fagnoter - Alfa.docx        Word; hver uge er en "Uge NN — …"-overskrift (Overskrift 2)
    Genkald/
      begreber.md
      genkald-uge10-11.md       spørgsmål  (+ genkald-uge10-11-svar.md med facit)
    Modeller/                   tegnede modeller (tælles)
    Eksamenstræning/
      <id>.md, <id>-svar.md     sæt og facit; besvarelser/ skrives af serveren
  Gamma/vscode/                 faget med kode: drills og nummererede afleveringer
    Drills/kap01-lorem.js       drills  (+ tjek.js og forklaringer/kap01-lorem.md)
    Opgaver/README.md           "## Status"-tabel (| Opgave | Uge | Afleveret | Godkendt | Hvad drillede |)
                                og fx "**4 af 6 skal godkendes**"; Opgave 1/, Opgave 2/ … er mapperne
    Bog/  Øvelser/  *.js        færdige og igangværende øvelser (tælles)
  Scripts/                      koden + datafiler, der skrives undervejs:
    genkald-log.jsonl           alle forsøg; Dagens kort regnes ud herfra
    laest.json                  uger markeret som læst
    deadlines-status.json       frister markeret som færdige
```

Formaterne, koden forventer:

- **Ugeplan**: `# Titel`, et `## <fagnavn>`-afsnit pr. fag med `**Hurtigt overblik**`, `**Kilder**`,
  `**Noter til pensum**`, `**Til rapporten**` og `**Video**`, og evt. øvelsesspørgsmål fra `*Øvelsesspørgsmål …*`
  til `*Svar …*`. Desuden `## Vigtigst i ugen`, `## Genkaldelse …` (med `*Svar*`) og `## Deadlines`
  (`| Uge | Fag | Aktivitet | Dato | Bemærkning |`). Planerne skrives af en planlagt Claude-opgave
  (køreplan-rutinen) eller i hånden; koden læser dem kun. En frist med "Opgave N" i teksten kobles til
  afleveringernes tabel, så den er færdig, når kolonnen Afleveret er udfyldt.
- **Genkald**: `## Uge 10 — emne` og spørgsmål som `**1.** …`. Markeringen står efter nummeret
  (`**1.** [✓] …`, `[~]`, `[✗]`), dit svar nederst som `> **Mit svar** (14.03): …`. `-svar.md` har samme numre.
- **Begreber**: `## Uge 10 — emne` og en tabel, hvis første kolonne hedder `Begreb`:
  `| Begreb | Min definition | Kilde |` (Beta har også `| Hvad det får dig til at se |`).
- **Drills**: `tjek("beskrivelse", () => udtryk, TOM);` under `// ── afsnit ──`-linjer. Gættet skrives i stedet
  for `TOM`. `tjek.js` (i drillmappen, ikke med her) eksporterer `tjek`, `TOM` og `opsummer` og skriver
  `FEJL  <beskrivelse>`, `du gættede …` og `JavaScript: …` ved fejl og til sidst `N rigtige · N forkerte · …`.
- **Eksamenssæt**: `# Titel`, en kursiv metalinje (`*2 timer · …*`), `---`, sektioner som
  `## Del A — Multiple choice (40 %)` og opgaver som `**1.** …` med `*Emne: … · uge 10*` til sidst.

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
| `/pakke` | På farten: dagens kort med facit, ekstra genkald, tomme begreber og ugættede drills |

| POST | Skriver |
|---|---|
| `/genkald` | svar og markering i `genkald-*.md` |
| `/begreb` | definition i `begreber.md` |
| `/drill` | gæt i stedet for `TOM`; filen køres, og går den ned, sættes den tilbage |
| `/repetition`, `/eksamen/resultat` | et forsøg i loggen (og i filen for genkald) |
| `/eksamen/afslut` | besvarelsen i `Eksamenstræning/besvarelser/` |
| `/laest`, `/deadline` | `laest.json`; færdig-markering i `deadlines-status.json` eller afleveringernes tabel |
| `/sync` | svar givet på telefonen uden net, med samme skrivninger som ovenfor |

## Dagens kort

Kortene regnes ud af `genkald-log.jsonl`; der er ingen anden tilstand. Et kort, der sad, kommer igen efter 3, 7,
21, 60 og 120 dage; halvt efter 2 dage, blankt eller forkert dagen efter. Op til 5 nye genkaldsspørgsmål om
dagen, og kun fra uger, der er markeret som læst. Typerne (genkald, eksamen, begreb, drill) blandes på skift, og
siden viser, hvor tit svaret sad, når man sagde "sikker", "usikker" eller "gætter".
