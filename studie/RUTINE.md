# Køreplan-rutinen: instruktioner

Instruktionerne til rutinen Studie (`studie-koereplan`) i Claude-appen. Rutinen selv peger kun hertil, så
rutinen ændres her og versioneres med projektet.

Lav min køreplan for den kommende uge.

Mappen: semestermappen (`$KOMPAS_SEMESTER`, fx `~/kompas/studie`).
Brug absolutte stier. Alle stier nedenfor er relative til den mappe.

## 0. FØR ALT ANDET

a) Læs `CLAUDE.md` i roden. Dens regler gælder også for denne kørsel, og den har
   bøgernes konventioner, "Materiale der mangler" og "Vigtige datoer". Læs også
   `Scripts/fag.json` (semestrets fag) og tabellen "… trænes forskelligt" i `README.md`
   (eksamensform pr. fag). Rutinen går fagene igennem i fag.json's rækkefølge, og `<mappe>`
   nedenfor er fagets `mappe`. Felterne siger, hvad faget har: `genkald`, `begreber`,
   `kode` (mappen med drills og øvelser), `afleveringer` (mappe og præfiks som G i G1)
   og `eksamenstraening.form` (skriftlig, kode eller mundtlig). Vigtigst i CLAUDE.md:
   - **Mine arbejdsfiler** (`*/Genkald/begreber.md`, eksisterende `genkald-*.md`,
     alt i `<mappe>/<kode>/` for et kodefag) læser du kun. Du redigerer ALDRIG i dem.
   - **Mine opgaver** (drills, øvelsessæt, afleveringer, obligatoriske opgaver): til dem
     skriver du stof og spørgsmål, ALDRIG facit, heller ikke som kodeeksempel.
   - Du opretter kun NYE filer, der er nævnt i denne fil. To undtagelser må
     udvides: Fagnoter-dokumenterne (KUN efter afsnit 6) og
     `<mappe>/<kode>/Drills/forklaringer/*.md` (KUN efter afsnit 6b).

a2) SORTÉR CANVAS-DOWNLOADS. Kør altid, også når køreplanen springes over i c):
   `node Scripts/canvas-sortering.js --kør` (fra semestermappen).
   Scriptet flytter Canvas-filer fra ~/Downloads ind i `<mappe>/Pensum/...` og
   `<mappe>/Afleveringer/`, konverterer PPTX til PDF og lægger dubletter i
   papirkurven. Ret ikke i scriptet, og flyt ikke filer i hånden. Filer i
   `_Indbakke/` kunne scriptet ikke placere. Lad dem ligge, men nævn dem i
   slutsvaret. Fejler kørslen, så skriv én linje om det og fortsæt.
   Scriptet navngiver selv filerne efter undervisningsdagen og emnet fra
   `Scripts/undervisningsdage.json` (fx `20270315_FL5_Lorem ipsum.pdf`).
   Linjer markeret "(tjek)" eller "(dato = download …)" er gættede datoer: nævn dem
   i slutsvaret, så brugeren kan rette dem.

b) Find ugen. Kørslen er planlagt søndag kl. 18, men kan komme for sent, hvis
   appen var lukket.
   - Søndag → planlæg ugen, der starter i morgen (ISO-uge + 1).
   - Mandag-tirsdag → kørslen er forsinket: planlæg den INDEVÆRENDE uge, og skriv
     øverst i filen, at planen er forsinket, og hvornår den er kørt.
   - Onsdag-lørdag → planlæg næste uge.
   Skriv ugenummer og datoer (mandag-søndag) i overskriften.

c) Findes der allerede en `Uge_Overblik/Ugeplan_ugeNN_*.md` for den uge, så spring
   køreplanen (afsnit 1-5) over, og skriv ikke noget over. Fortsæt med afsnit 6, 6b
   og 7, og sig i slutsvaret, at planen fandtes.

## 1. MATERIALET — HVOR DET LIGGER

| Hvad | Sti |
|---|---|
| Ugeplaner (dine tidligere output) | `Uge_Overblik/Ugeplan_uge*.md` |
| Lektionsplan, kursusbeskrivelse, kursusplan | `<mappe>/` (filerne pr. fag står i CLAUDE.md under "Hvad mappen er") |
| Obligatoriske opgaver | `<mappe>/Afleveringer/` |
| Gamle eksamenssæt | søg hele mappen efter `*Eksamen*` |
| Slides | `<mappe>/Pensum/Forelæsninger/ÅÅÅÅMMDD_*.pdf` |
| Øvelsessæt | `<mappe>/Pensum/Øvelser/ÅÅÅÅMMDD_*.pdf` |
| Opgavetekster (afleveringer m.m.) | `<mappe>/Afleveringer/` — deres frister har FORRANG for kursusplanens uge |
| Lærebøger | `Bøger/` |

HVILKEN UGE EN FIL HØRER TIL (bruges overalt, hvor filen siger "dato i ugen"):
Står der et ugenummer i filnavnet efter datopræfikset (`Uge 12`, `uge 12`, `uge12`,
`Uge 12(2)`, `uge11A`), hører filen til den uge, også når datopræfikset ligger i en
anden uge. Ellers afgør datopræfikset `ÅÅÅÅMMDD`. Eksempel: `20270314_Lorem_Uge 12(2)_Ipsum.pdf`
er dateret søndag i uge 11, men hører til uge 12. Omdøb ikke filen. Nævn uoverensstemmelsen i slutsvaret, så brugeren kan rette
datoen.

Mangler et fags kursusplan eller eksamenssættene, så brug de tidligere ugeplaner i
`Uge_Overblik/` som kilde til afleveringsuger og emner, og skriv under "Huller" at
filen mangler i mappen. Opfind aldrig datoer.

## 2. FREMGANGSMÅDE

1. Slå ugen op i lektionsplanerne og kursusplanerne. Et fag kan have flere
   selvstudier eller øvelsesgange i samme uge. Tag dem alle.

2. SLIDES OG ØVELSESSÆT. Se efter filer i `<mappe>/Pensum/Forelæsninger/` og
   `<mappe>/Pensum/Øvelser/`, der hører til den planlagte uge (se "Hvilken uge en
   fil hører til" i afsnit 1). Findes de, så
   læs dem, og byg noteafsnittet på slides + bog (slides viser, hvad underviseren
   vægter). Findes de ikke, så skriv "slides til uge NN ikke uploadet endnu" i
   Hurtigt overblik, og byg på bog + lektionsplan. Læs også den seneste uges
   slides, hvis de ikke var med i forrige ugeplan.

3. MIN STATUS — læs den direkte fra mappen.
   Datér alt med filernes ændringsdato (`stat -f '%Sm' -t '%d.%m' fil`).
   Fremstil det aldrig som mere end det, filerne viser.
   - Drills (fag med `kode`): for hver `<mappe>/<kode>/Drills/kap*.js`: antal `TOM`
     tilbage (`grep -cw TOM`) og antal `DIN KODE HER` tilbage (mine arbejdsfiler).
     Du må køre `node` på dem for at tælle bestået/fejlet.
   - Øvelser i gang: `.js`-filer direkte i `<mappe>/<kode>/`. Færdige: filer i
     `<mappe>/<kode>/Bog/` og `<mappe>/<kode>/Øvelser/`.
   - Afleveringer (fag med `afleveringer`): statustabellen i
     `<mappe>/<afleveringer.mappe>/README.md` og eventuelle mapper med præfikset.
   - Begreber (fag med `begreber`): i `<mappe>/Genkald/begreber.md`, antal
     tabelrækker hvor definitionskolonnen er udfyldt, ud af det samlede antal.
   - Genkald (fag med `genkald`): i `<mappe>/Genkald/genkald-*.md` (ikke `-svar.md`),
     antal `[✓]`, `[~]`, `[✗]` og antal spørgsmål uden markering.
   - Aktivitet: filer ændret de sidste 7 dage i fagenes mapper
     (`find ... -mtime -7`), inkl. Fagnoter-dokumenterne.
   Brug status til at målrette rådene: fx er en drill ikke begyndt, og en
   aflevering er denne uge, så sig det. Er noget umuligt at aflæse, så skriv det.

4. Læs ugens pensum i lærebøgerne, før du skriver noteafsnittet. Skriv ud fra
   bogen, ikke ud fra hvad du husker om emnet.

5. Læs de tidligere ugeplaner i `Uge_Overblik/`, så du ikke gentager dig selv
   og kan hente genkaldsstof.

## 3. OM BØGERNE

- Bøgerne, deres udgaver, filnavne og hvordan de læses (sidetal, OCR, omregning
  mellem udgaver) står i CLAUDE.md under "Konventioner". Følg dem, og angiv altid
  sidetal i min udgave.
- Står noget fra "Materiale der mangler" i CLAUDE.md på pensum, og finder du det
  ikke i mappen: skriv afsnittet som forberedelsesnote, marker det tydeligt, og
  opfind aldrig sidetal eller struktur.
- Er ugen ferie eller uden undervisning i et fag, så skriv det kort og gå videre.

## 4. FORMAT — én sektion per fag

Én `## <navn>`-sektion per fag i fag.json's rækkefølge, med fagets `navn` fra fag.json
som overskrift (Kompas finder sektionen ud fra den). Hver sektion har:

**Hurtigt overblik** — punktform, maks otte linjer
- Ugens emne og formål
- Undervisning: dag, dato, tidspunkt, underviser, format
- Læsning: bog, kapitel, sider i min udgave
- Slides/øvelsessæt: uploadet eller ej
- Skal være klar inden: øvelsessvar, problemformulering, prototype, case
- Min status fra mappen, med dato
- Huller eller uoverensstemmelser i planen

**Kilder** — ét punkt per kilde med præcis henvisning: lektionsplan (uge og
række), bog (kapitel, afsnitsoverskrift, sider i min udgave), slides
(filnavn, slidenummer), status-filer (sti og dato).

**Noter til pensum** — 400-600 ord. FORMEN AFHÆNGER AF FAGETS EKSAMEN: formen står i
`eksamenstraening.form` i fag.json, og eksamenens detaljer (varighed, hjælpemidler,
opgavetyper) i fagets række i README's "… trænes forskelligt".

  · **kode** — skriftlig prøve i kode. Er noter tilladt, så skriv et opslagsværk,
    ikke forståelsesprosa. Syntaks, kaldsignatur og et minimaleksempel, der viser
    hvad det returnerer, for hvert nyt konstrukt. De to-tre typiske fejl,
    formuleret så jeg kan genkende dem i en fejlmeddelelse. Brug egne
    eksempler, aldrig facit til mine opgaver.

  · **skriftlig** — prosa, der forklarer sammenhængen. Slut ALTID med 5-8
    øvelsesspørgsmål i eksamensformatet fra README: fx multiple choice med plausible
    distraktorer, en model eller tabel fra faget at udfylde, mindst ét essayspørgsmål.
    Svarene til sidst, adskilt. Findes der eksamenssæt i mappen, så kalibrér formatet
    efter dem.

  · **mundtlig** — prosa med bogens fagtermer. Slut med ét realistisk
    pensumspørgsmål og et disponeret svar på fem minutter: tre-fire hovedpunkter
    i rækkefølge med de begreber, der skal nævnes i hvert.

  Fælles: bogens egne termer på bogens sprog. Knyt stoffet til læringsmålet i
  kursusbeskrivelsen.

**Til rapporten** — én til tre linjer. Hvilke begreber kan operationaliseres i
fagets rapport, projekt eller obligatoriske opgave (se `<mappe>/Afleveringer/` og
kursusbeskrivelsen)? Ingen kobling er et gyldigt svar. Har faget ingen rapport eller
opgave, så udelad afsnittet.

**Video** — højst én YouTube-video pr. fag, kun når en virkelig god findes.
Udelad afsnittet helt for et fag, hvis ingen video passer. Det er bedre end en
middelmådig video. Det gælder også uger uden undervisning.
- Kvalitet: kanaler som Veritasium, TED/TED-Ed, Kurzgesagt, Computerphile,
  3Blue1Brown, CrashCourse, Fireship, Fun Fun Function, tutor2u eller en
  anerkendt fagperson. Undgå kursussælgere og autogenererede videoer. En
  ukendt kanal kræver mange visninger og en tydelig grund.
- Længde 5-50 minutter. Normalt 5-20. Over 20 minutter kun, når videoen
  rammer ugens tema præcist eller giver stor værdi, som en gennemført
  dokumentar eller et foredrag, der dækker hele emnet. Sig så i sætningen,
  hvorfor den er længden værd. Rammer en video kun ugens stof i et kort
  afsnit, så angiv tidsstemplet.
- Prioritér det, der er svært i ugen, eller det, eksamen spørger om, fx
  critical path, normalisering, closures eller rekursion. Find ikke en video
  bare for at have en.
- Gentag aldrig en video fra en tidligere ugeplan (`grep -h "youtube.com"
  Uge_Overblik/*.md`).
- Find den med WebSearch og VERIFICÉR hver video, før den skrives ind. Titel,
  kanal, længde, visninger og år hentes direkte fra YouTube:
  `curl -s -A "Mozilla/5.0" -H "Accept-Language: en" "https://www.youtube.com/watch?v=ID"`
  og grep efter `<meta name="title"`, `"ownerChannelName"`, `"lengthSeconds"`,
  `"viewCount"`, `"publishDate"` og `"shortDescription"`. Finder du ikke
  titel og længde, så brug ikke videoen. Opfind aldrig et link eller et
  video-id.
- CS50 som ekstra: ud over videoen må hvert fag få ÉN CS50-forelæsning, når
  en del af den passer godt til ugens emne. Det gælder typisk de tekniske fag
  (databaser, SQL, netværk, programmering) og næsten aldrig organisations- og
  samfundsfag. 50-minutters-grænsen gælder
  ikke her, men link til den relevante del med `&t=<sekunder>s`, og angiv
  start-slut og omtrentlig længde. Tidsstemplerne skal komme fra kapitlerne
  i videoens beskrivelse (`"shortDescription"`), aldrig fra et gæt.
  Kilder: CS50x (nyeste år, links på `https://cs50.harvard.edu/x/weeks/N/`),
  CS50 SQL (`https://cs50.harvard.edu/sql/weeks/N/`), CS50 Web og CS50's
  Understanding Technology. Brug den engelske udgave, ikke en
  spansk/portugisisk dublet. CS50x underviser i C og Python, så sig, hvad der
  overføres til kodefagets sprog, og hvad der kan springes over. Gentag ikke en
  del, der er brugt før (`grep -h "CS50:" Uge_Overblik/*.md`). Form:
  `- CS50: [Titel](https://www.youtube.com/watch?v=ID&t=Ns) (Kursus år, m:ss-m:ss, ca. N min.). <1-3 sætninger>`
  som ekstra punkt under samme **Video**-overskrift.
- Form (Kompas viser afsnittet med klikbart link):
  `- [Titel](https://www.youtube.com/watch?v=ID) (Kanal, m:ss). <1-3 sætninger>`
  Sætningerne siger, hvad videoen dækker, ud fra titel og beskrivelse, og
  aldrig mere end det. De siger, hvor den afviger fra bogen (notation,
  begreber, sprog, alder), og hvornår den skal ses (før forelæsningen,
  efter læsningen, efter en aflevering). Er en videos ramme en anden end
  fagets, så gør koblingen til bogens begreber til en lille opgave.

EFTER FAGSEKTIONERNE

**Genkaldelse** — tre spørgsmål fra stof to til fire uger tilbage.
Spørgsmål, ikke resumé. Prioritér faget med den nærmeste eksamen ("Vigtige datoer" i
CLAUDE.md). Svarene til sidst, adskilt.
Prioritér stof, hvor min status viser `[~]`/`[✗]` eller tomme begreber.

**Deadlines** — tabel over obligatoriske aktiviteter og eksamener inden for
fire uger, inkl. de frister under "Vigtige datoer" i CLAUDE.md, der falder i perioden.
Tabellen skal have kolonnerne `| Uge | Dato | Fag | Aktivitet | Bemærkning |` (Kompas læser den),
med fagets `kort` fra fag.json i Fag-kolonnen.
Kendes en præcis frist (opgavetekst i `<mappe>/Afleveringer/`, Canvas, eksamensplanen eller "Vigtige datoer" i CLAUDE.md), så skriv den
som `dd.mm kl. tt:mm` i Dato-kolonnen og sæt Uge til fristens uge, ikke kursusplanens.

**Vigtigst i ugen** — maks tre linjer.

## 5. FRISTER OG KOMPAS

Kompas (https://kompas.localhost) er overblikket over frister; de føres kun i ugeplanen og dér.

1. Frister, jeg har markeret som færdige på Kompas, står i `Scripts/deadlines-status.json`
   (`{"<fag>|<type>|<uge>": {"faerdig": "ÅÅÅÅ-MM-DD"}}`). Afleveringer (fag med
   `afleveringer`) markeres i stedet i kolonnen "Afleveret" i
   `<mappe>/<afleveringer.mappe>/README.md`. Læs begge.
2. En færdig frist står stadig i Deadlines-tabellen, men med "✓ færdig" først i
   Bemærkning, og den nævnes ikke i Vigtigst i ugen eller som noget, der skal nås.
3. Ret aldrig i `deadlines-status.json` eller i README-tabellen. Det gør jeg selv på Kompas.

## 6. FAGNOTER — UDFYLD UGEN, DER NETOP ER SLUT

Ud over køreplanen for den kommende uge skal du udfylde fagnoterne for den uge,
der netop er slut (den uge, hvis søndag er i dag, eller ved en forsinket kørsel
den seneste afsluttede uge). Det gælder alle fag i fag.json. Er et fag uden
undervisning den uge (fx efterårsferie), så spring det over.

Dokumenter: fagets Word-dokument `<mappe>/Fagnoter - *.docx`.

Værktøjet, der skriver noterne ind i Word-dokumentet (python-docx), er ikke med i repoet. Det skal kunne:
indsætte en uges noter i samme form som de godkendte eksempler (felter, længde, sprog, sidetalsform,
billedtekster; ét eksempel pr. fag, eller et fra et fag med samme eksamensform), og for fag med `kode` køre
alle `// →`-resultater i kodeblokkene gennem node. Kør den kontrol altid, og ret alle fejl.

Fremgangsmåde per fag:
1. Hvilke uger: den netop afsluttede uge PLUS tidligere uger, der endnu ikke er
   udfyldt (indhentning). En uge er udfyldt, hvis dens blok har en "Modeller"-label.
   Slides-reglen: mangler forelæsningsslides for en uge (ingen fil i
   `<mappe>/Pensum/Forelæsninger/`, der hører til ugen efter reglen i afsnit 1), så vent. Spring ugen over nu, så
   den tages ved en senere kørsel, og skriv det i rapporten. Er ugen mere end 14
   dage gammel og mangler slides stadig, så udfyld den ud fra bog og lektionsplan
   og skriv under Uafklaret: "[?] Slides til uge NN var ikke uploadet — noterne
   bygger kun på bogen." Uger uden undervisning i faget springes altid over.
2. Findes der en Word-låsefil (`~$*.docx`) i fagmappen, er dokumentet åbent. Så
   spring faget over og skriv det i rapporten.
3. Læs ugens slides og øvelsessæt først (de er forelæserens sammenfatning), og slå
   derefter definitioner og sidetal op i bogen med målrettede `pdftotext`-opslag.
   Læs ikke hele kapitler, når slides dækker indholdet. Verificér hvert sidetal.
   Brug ikke subagenter.
4. Skriv noterne i samme form som de godkendte eksempler. Billeder:
   render slides med `pdftoppm -r 110 -singlefile`, gem som JPEG i scratch, kig på
   dem før brug, og gentag ikke figurer, som brugeren eller tidligere uger allerede har.
5. Tag backup af dokumentet, før du skriver i det.
6. Prøvekør mod en kopi i scratch, og tjek bagefter, at alle ikke-tomme afsnit fra
   backuppen findes i samme rækkefølge i kopien. Først derefter kører du mod det
   rigtige dokument og tjekker det samme igen.

Regler: "I egne ord" og alt, brugeren selv har skrevet, røres aldrig. Ingen facit til
mine opgaver. Mangler en kilde, så skriv at den mangler, og opfind aldrig indhold eller sidetal.

GENKALD — HVER UGE, KUN FAG MED `genkald` I FAG.JSON
Når et fags fagnoter er gjort færdige (eller faget blev sprunget over pga. låsefil),
laver du genkaldsfiler for samme fag ud fra det samme materiale, du lige har læst.
Kompas viser dem under Genkald og Dagens kort, så snart brugeren har markeret ugen
som læst under Fag → Indhentning.
1. Hvilke uger: hver uge til og med den netop afsluttede uge, hvor faget havde
   undervisning, og som ingen genkaldsfil dækker endnu (en fil
   `<mappe>/Genkald/genkald-ugeAA-BB.md` dækker uge AA til BB). Slides-reglen ovenfor
   gælder også her: venter en uge på slides, så venter dens genkald også (de andre
   uger laves alligevel). Låsefil-reglen gælder ikke, for genkald rører ikke
   Word-dokumentet.
2. Én fil pr. uge: `<mappe>/Genkald/genkald-ugeNN-NN.md` (kun spørgsmål) og
   `<mappe>/Genkald/genkald-ugeNN-NN-svar.md` (facit med kapitel og sidetal i min
   udgave, og slidenummer). Overskriv aldrig en eksisterende fil.
3. Kopiér formatet fra fagets nyeste `genkald-ugeNN-NN.md` og `-svar.md` (har faget
   ingen endnu, så fra et andet genkaldsfag): samme indledning om at
   svare fra hukommelsen og markere `[✓]`/`[~]`/`[✗]`, én `## Uge NN — <forelæsning>`-
   overskrift (Kompas læser ugen derfra), nummererede `**N.**`-spørgsmål med samme numre
   i facit. 5-7 spørgsmål, der kræver produktion, ikke genkendelse. Dæk både
   forelæsningen og ugens øvelsessæt. Mangler øvelsessættet, så skriv det i
   indledningen.
4. Genkald er spørgsmål til stof: ingen spørgsmål, hvis svar er facit til en af mine opgaver.

## 6b. DRILL-FORKLARINGER — KUN DE MANGLENDE

Kompas og `tjek.js` viser en kort forklaring, når brugeren har gættet på et
`tjek(...)` i kodefagets `<mappe>/<kode>/Drills/kap*.js`. Forklaringerne ligger i
`<mappe>/<kode>/Drills/forklaringer/<drill>.md` (samme navn som drill-filen).

1. Kør `node Scripts/drill-forklaringer.js` (fra semestermappen). Det viser hvert
   tjek, der mangler en forklaring: overskriften, udtrykket og `=> det JavaScript
   giver`. Siger det "0 tjek mangler", eller har intet fag `kode`, så er du færdig
   med dette afsnit.
2. Skriv en forklaring til hvert manglende tjek, der forklarer, HVORFOR
   JavaScript giver præcis det resultat, scriptet viser. Byg på resultatet fra
   scriptet, aldrig på hvad du tror udtrykket giver. Ser resultatet forkert ud,
   så skriv ingen forklaring til det tjek, men nævn det i slutsvaret.
3. Form: kopiér stilen fra de eksisterende filer. `## <overskrift præcis som
   scriptet skriver den>`, derunder 1-2 korte sætninger på dansk med fagtermer på
   engelsk (`undefined`, closure, scope). Kode i backticks. Brug kodefagets
   lærebogs begreber.
4. Føj de nye afsnit til enden af den rigtige fil. Findes filen ikke, så opret
   den med samme indledning som den første fil i `forklaringer/` (kapitlets titel
   fra første linje i drill-filen). Ret, flyt eller slet ALDRIG eksisterende afsnit.
5. Kør scriptet igen og tjek, at det nu siger "0 tjek mangler".

Regler: Rør aldrig drill-filerne selv eller `tjek.js`. Skriv aldrig forklaringer
til `forvent(...)`/`// DIN KODE HER`-opgaver (det ville være løsningen), og lad
ikke en forklaring afsløre facit til en stub eller en af mine opgaver.

## 7. LEVERING

Skriv på dansk. Gem køreplanen som
`Uge_Overblik/Ugeplan_ugeNN_DD-DDmmm_ÅÅÅÅ.md` (fx `Ugeplan_uge12_16-22mar_2027.md`).

Til sidst, også når køreplanen blev sprunget over i 0c, opdaterer du Kompas-siden
(https://kompas.localhost/studie/), som viser ugeplanen, fagnoterne, deadlines og status pr. fag:
`node Scripts/kompas-eksport.js` (fra semestermappen). Scriptet læser kun
og retter intet. Fejler det, så skriv én linje om det og fortsæt.

Afslut med et kort svar, én linje pr. punkt (udelad et punkt uden indhold):
- Canvas: antal flyttede filer, hvad der ligger i `_Indbakke/`, og gættede datoer ("(tjek)")
- Køreplanens filnavn, eller at den fandtes i forvejen (0c)
- Andre oprettede filer, inkl. genkaldsfiler
- Fagnoter- og genkald-uger udfyldt eller sprunget over, og hvorfor
- Antal drill-forklaringer (afsnit 6b), og tjek hvis resultat så forkert ud
- Fag med video og CS50-forelæsning
- Slides til ugen uploadet eller ej, og de vigtigste huller
- Filer hvis datopræfiks ikke passer til ugenummeret i navnet (afsnit 1)
