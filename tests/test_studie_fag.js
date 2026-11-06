// Serveren og eksporten på et opdigtet semester med andre fag end dette (Alfa med genkald og begreber, Beta med
// kode og eksamenssæt), så intet i Scripts/ må kende de rigtige fag. Kører i en midlertidig kopi med egen port
// og egen eksportmappe; koden kører fra studie/Scripts med KOMPAS_SEMESTER sat til kopien. Til sidst: ingen faste fag-id'er i Scripts/ og siderne.
//   node tests/test_studie_fag.js
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn, execFileSync } = require("child_process");

const SCRIPTS = path.join(__dirname, "..", "studie", "Scripts");
const rod = fs.mkdtempSync(path.join(os.tmpdir(), "fag-test-"));
const skriv = (f, t) => { fs.mkdirSync(path.dirname(path.join(rod, f)), { recursive: true }); fs.writeFileSync(path.join(rod, f), t); };
skriv("Scripts/fag.json", JSON.stringify({ semester: "Testsemester", studiemaal: { dag_timer: 2, medaljer: { bronze: 2, soelv: 3, guld: 4 } }, fag: [
  { id: "alfa", kort: "Alfa", navn: "Alfa for begyndere", mappe: "Alfa", readme: "Alfa", fagnoter_overskrift: "Alfa",
    kursuskode: "ALFA1", arbejdsbyrde: { kilde: "test", semestre: 1, poster: [{ navn: "Forelæsning", timer: 20, undervisning: true }, { navn: "Læsning", timer: 80, undervisning: false }] },
    genkald: true, begreber: { ekstra_kolonne: "Hvad det viser", ekstra_spoergsmaal: "og sig hvad det viser" },
    eksamenstraening: { form: "skriftlig", note: "Alfa-note" } },
  { id: "beta", kort: "Beta", navn: "Beta og kode", mappe: "Beta", readme: "Beta", fagnoter_overskrift: "Beta",
    kode: "kode", usb_noter: true, eksamenstraening: { form: "kode", note: "Beta-note" } },
] }));

// Alfas eksamen ligger 60 dage fremme, så den tæller med i "til eksamen"
process.env.KOMPAS_SEMESTER = rod;
const S = require(path.join(SCRIPTS, "semester.js"));
const eksDag = S.plusDage(new Date(), 60), dd = n => String(n).padStart(2, "0");
skriv("CLAUDE.md", `# Testsemester

## Vigtige datoer

| Uge | Fag | Hvad |
|---|---|---|
| ${S.isoUge(eksDag)} | Alfa | **Eksamen: skriftlig** — ${dd(eksDag.getDate())}.${dd(eksDag.getMonth() + 1)}.${eksDag.getFullYear()} kl. 09:00-11:00 |
`);
skriv("README.md", "# Testsemester\n");
skriv("Alfa/Genkald/genkald-uge36-37.md", `# Alfa — genkaldelse, uge 36 til 37

---

## Uge 36 — Første emne

**1.** Hvad er alfa?

**2.** Hvad er forskellen på alfa og beta?
`);
skriv("Alfa/Genkald/genkald-uge36-37-svar.md", "# Alfa — facit\n\n---\n\n**1.** Det første bogstav.\n\n**2.** Det ene kommer før det andet.\n");
// En genkaldsfil, der ikke kan læses (som en fil i en skymappe, der kun ligger i skyen), må ikke vælte de andre
skriv("Alfa/Genkald/genkald-uge38-38.md", "# Alfa — uge 38\n\n## Uge 38 — Tredje emne\n\n**1.** Ulæselig?\n");
fs.chmodSync(path.join(rod, "Alfa/Genkald/genkald-uge38-38.md"), 0o000);
skriv("Alfa/Genkald/genkald-uge37-37.md", "# Alfa — uge 37\n\n## Uge 37 — Andet emne\n\n**1.** Læselig, men facit er ikke?\n");
skriv("Alfa/Genkald/genkald-uge37-37-svar.md", "**1.** Skjult.\n");
fs.chmodSync(path.join(rod, "Alfa/Genkald/genkald-uge37-37-svar.md"), 0o000);
skriv("Alfa/Genkald/begreber.md", `# Alfa — begreber

## Introduktion (uge 36)

| Begreb | Din definition | Hvad det viser | Kilde |
|---|---|---|---|
| Alfa | | | s. 1 |
| Omega | Det sidste | Slutningen | s. 2 |
`);
skriv("Beta/Eksamenstræning/2025.md", `# Beta — eksamen 2025

*Varighed: 4 timer*

---

## Opgave 1 — Tæl (100 %)

**1.** Skriv en funktion, der tæller til tre.
`);
fs.mkdirSync(path.join(rod, "Beta", "kode", "Drills"), { recursive: true });
// Et gammelt sæt som fil ved siden af mappen Eksamenstræning, som ikke er et sæt
skriv("Beta/Beta_Eksamener.pdf", "%PDF-1.4\n");
// Pensum: en forelæsning som pdf og et øvelsessæt som markdown; en fil af en anden slags udleveres ikke
skriv("Beta/Pensum/Forelæsninger/20260105_FL1_Intro.pdf", "%PDF-1.4\n");
skriv("Beta/Pensum/Øvelser/20260105_Øvelsessæt 1_Intro.md", "# Øvelsessæt 1\n");
skriv("Beta/Pensum/Øvelser/20260105_noter.txt", "noter\n");

let fejl = 0;
const tjek = (navn, ok, detalje = "") => { if (!ok) { fejl++; console.log("FEJL", navn, detalje); } };
const vis = x => JSON.stringify(x);

// Serveren kører i en tidszone, hvor datoen lige nu er en anden end i UTC, så en UTC-dato (toISOString) bliver fanget:
// 12 timer efter UTC om formiddagen (UTC), 14 timer før om eftermiddagen. Ingen af dem har sommertid.
const timer = new Date().getUTCHours() < 12 ? -12 : 14, TZ = timer < 0 ? "Etc/GMT+12" : "Pacific/Kiritimati";
const serverDag = () => new Date(Date.now() + timer * 36e5).toISOString().slice(0, 10);
const PORT = 18000 + (process.pid % 1000), ud = path.join(rod, "ud");
const server = spawn(process.execPath, [path.join(SCRIPTS, "kompas-server.js")],
  { env: { ...process.env, TZ, KOMPAS_SEMESTER: rod, STUDIE_PORT: String(PORT), STUDIE_EKSPORT_UD: ud }, stdio: ["ignore", "ignore", "pipe"] });
let log = ""; server.stderr.on("data", d => { log += d; });
const kald = async (sti, krop) => {
  const r = await fetch(`http://127.0.0.1:${PORT}/studie/api${sti}`, krop ? { method: "POST", body: JSON.stringify(krop),
    headers: { "Content-Type": "application/json", Origin: "https://kompas.localhost" } } : {});
  return { status: r.status, data: await r.json().catch(() => null) };
};

(async () => {
  for (let i = 0; i < 40; i++) { try { await kald("/laest"); break; } catch { await new Promise(r => setTimeout(r, 100)); } }

  // Pensum: alle slags, Fag linker til, svarer; markdown som ren tekst
  const pensum = async (mappe, fil) => { const r = await fetch(`http://127.0.0.1:${PORT}/studie/api/pensum/beta/${encodeURIComponent(mappe)}/${encodeURIComponent(fil)}`);
    return [r.status, r.headers.get("content-type"), await r.text()]; };
  const [pdf, md, txt] = [await pensum("Forelæsninger", "20260105_FL1_Intro.pdf"), await pensum("Øvelser", "20260105_Øvelsessæt 1_Intro.md"), await pensum("Øvelser", "20260105_noter.txt")];
  tjek("pensum: pdf udleveres", pdf[0] === 200 && pdf[1] === "application/pdf", vis(pdf));
  tjek("pensum: et øvelsessæt i markdown udleveres som tekst", md[0] === 200 && /^text\/plain/.test(md[1]) && md[2] === "# Øvelsessæt 1\n", vis(md));
  tjek("pensum: andre filtyper udleveres ikke", txt[0] === 404, vis(txt));

  const g = (await kald("/genkald")).data;
  const facitSvar = await kald("/facit?fag=alfa&fil=genkald-uge37-37.md&nr=1");
  tjek("en ulæselig facitfil giver intet facit, ikke en fejl", facitSvar.status === 200 && facitSvar.data.facit === null, vis(facitSvar));
  tjek("en ulæselig genkaldsfil springes over og står i loggen", /genkald: alfa\/genkald-uge38-38\.md: EACCES kunne ikke læses og springes over/.test(log), log.slice(0, 300));
  tjek("genkald kommer fra Alfa", vis(g.map(f => [f.fag, f.fil, f.spoergsmaal.length, f.har_facit])) === '[["alfa","genkald-uge36-37.md",2,true],["alfa","genkald-uge37-37.md",1,true]]', vis(g));

  const b = (await kald("/begreber")).data;
  tjek("begreber kun for Alfa", vis(Object.keys(b)) === '["alfa"]', vis(Object.keys(b)));
  tjek("Alfas ekstra kolonne og spørgsmål fra fag.json", b.alfa.hoved_se === "Hvad det viser" && b.alfa.spoergsmaal_se === "og sig hvad det viser", vis(b.alfa));
  tjek("begreberne læses med ekstra kolonne", vis(b.alfa.begreber.map(x => [x.begreb, x.definition, x.se])) === '[["Alfa","",""],["Omega","Det sidste","Slutningen"]]', vis(b.alfa.begreber));

  const e = (await kald("/eksamen")).data;
  tjek("eksamenssæt for Beta", vis(e.map(x => [x.fag, x.id, x.varighed, x.antal])) === '[["beta","2025",240,1]]', vis(e));

  // Til eksamen pr. uge: Alfas temaer (MC delt ligeligt, en opgaves point delt mellem delopgaverne, "i alt" med
  // egne point), dine egne spørgsmål for sig, og Betas opgaver koblet til ugerne gennem kapitlerne
  skriv("Alfa/Eksamenstræning/2024-ordinaer.md", `# Alfa — eksamen 2024 (ordinær)

*Varighed: 2 timer*

---

## Del A — Multiple choice (6 point)

**1.** Hvad er et net? 99 point?

*Emne: Netværk — typer · uge 37*

**2.** Hvad er en ring?

*Emne: Netværk — topologier · uge 37*

**3.** Hvad er SQL?

*Emne: SQL · uge 38*

## Del B — Tegne- og modelleringsopgaver (10 point)

**4.** B.Q1. SQL (8 points) — a)

*Emne: SQL — SELECT · uge 38*

**5.** B.Q1. SQL — b)

*Emne: SQL — WHERE · uge 38*

**6.** *(B.Q2 — Context diagram, 2 point)*

*Emne: Diagrammer · uge 38*

## Del C — Kortsvarsopgaver (4 point)

**7.** *(C.1 — Net, 4 point i alt — delopgave 1, 3 point)*

*Emne: Netværk — topologier · uge 37*

**8.** *(C.1 — delopgave 2, 1 point)*

*Emne: Netværk · uge 37*
`);
  skriv("Alfa/Eksamenstræning/pensum.md", "# Alfa — egne spørgsmål\n\n---\n\n## Uge 37 — Net\n\n**1.** Forklar et net.\n\n*Emne: Egne net · uge 37*\n");
  skriv("Beta/Eksamenstræning/2024.md", `# Beta — eksamen 2024

*Varighed: 4 timer*

---

## Opgave 1 — Klasser (60 %)

**1.** *Delopgave 1.1 (20 %)*

*Emne: klasser · kap. 6 og 4*

**2.** *Delopgave 1.2 (40 %)*

*Emne: løkker over objekter · kap. 4 og 6*

## Opgave 2 — Fejl (40 %)

**3.** Find fejlen, der koster 50% af tiden.

*Emne: fejlfinding · kap. 8*
`);
  skriv("Scripts/undervisningsdage.json", JSON.stringify({ Beta: { Forelæsninger: [{ dato: "2027-10-25", kapitler: [6] }, { dato: "2027-10-04", kapitler: [4] }, { dato: "2027-11-01", kapitler: [8] }] } }));
  const eu = (await kald("/eksamen/uger")).data;
  const a37 = eu.alfa?.uger?.[37], a38 = eu.alfa?.uger?.[38];
  tjek("til eksamen: kun årstalssæt er gamle sæt", eu.alfa?.saet_i_alt === 1 && eu.beta?.saet_i_alt === 2, vis([eu.alfa?.saet_i_alt, eu.beta?.saet_i_alt]));
  tjek("til eksamen: samme tema samles på tværs af detaljer", vis(a37?.grupper.map(g => [g.navn, g.spoergsmaal.map(x => [x.nr, x.form, x.point])])) ===
    '[["Netværk",[[1,"MC",2],[2,"MC",2],[7,"kortsvar",3],[8,"kortsvar",1]]]]', vis(a37));
  const omtrent = (x, y) => Math.abs(x - y) < 1e-9;
  tjek("til eksamen: ugens andel af sættets point", omtrent(a37?.andel, 0.4) && omtrent(a38?.andel, 0.6) && a37?.saet_med === 1, vis([a37?.andel, a38?.andel]));
  tjek("til eksamen: en opgaves point deles mellem delopgaverne, flest point først", vis(a38?.grupper.map(g => [g.navn, g.point])) === '[["SQL",10],["Diagrammer",2]]', vis(a38?.grupper));
  tjek("til eksamen: egne spørgsmål står for sig", vis(a37?.egne.map(x => [x.saet, x.nr])) === '[["pensum",1]]', vis(a37?.egne));
  const b43 = eu.beta?.uger?.[43], b40 = eu.beta?.uger?.[40];
  tjek("til eksamen: kapitlerne kobler opgaver til ugen; første kapitel er hovedemnet", vis(b43?.grupper.map(g => [g.navn, g.hoved, g.spoergsmaal.map(x => [x.nr, x.hoved, x.point])])) ===
    '[["2024 · Opgave 1 — Klasser",true,[[1,true,20],[2,false,40]]]]' && omtrent(b43?.andel, 0.1) && omtrent(b40?.andel, 0.2), vis([b43, b40?.andel]));
  tjek("til eksamen: en enkelt opgave får sektionens vægt, også med procent i teksten", eu.beta?.uger?.[44]?.grupper[0]?.spoergsmaal[0]?.point === 40, vis(eu.beta?.uger?.[44]));
  for (const f of ["Alfa/Eksamenstræning", "Beta/Eksamenstræning/2024.md", "Scripts/undervisningsdage.json"]) fs.rmSync(path.join(rod, f), { recursive: true });

  const gem = await kald("/genkald", { fag: "alfa", fil: "genkald-uge36-37.md", nr: 1, svar: "Et bogstav", karakter: 3, sikkerhed: "sikker" });
  const fil = fs.readFileSync(path.join(rod, "Alfa", "Genkald", "genkald-uge36-37.md"), "utf8");
  tjek("et genkaldssvar gemmes i Alfas fil", gem.status === 200 && /\*\*1\.\*\* \[✓\] Hvad er alfa\?/.test(fil) && /> \*\*Mit svar\*\* \([^)]+\): Et bogstav/.test(fil), vis(gem) + fil);
  const fremmed = await kald("/genkald", { fag: "delta", fil: "genkald-uge36-37.md", nr: 1, svar: "x", karakter: 3 });
  tjek("et fag uden for fag.json afvises", fremmed.status >= 400 && fremmed.status < 500, vis(fremmed));
  const begreb = await kald("/begreb", { fag: "alfa", begreb: "Alfa", definition: "Det første", se: "Begyndelsen" });
  tjek("et begreb gemmes med ekstra kolonne", begreb.status === 200 &&
    fs.readFileSync(path.join(rod, "Alfa", "Genkald", "begreber.md"), "utf8").includes("| Alfa | Det første | Begyndelsen | s. 1 |"), vis(begreb));

  // I egne ord: én fil pr. fag med ugerne i rækkefølge. En linje, der ligner en ugeoverskrift, starter ikke en ny uge
  await kald("/egne-ord", { fag: "beta", uge: 38, tekst: "Tredje\n## Uge 40\nslut" });
  await kald("/egne-ord", { fag: "beta", uge: 37, tekst: "  Anden\r\n" });
  const eoFil = () => fs.readFileSync(path.join(rod, "Beta", "egne-ord.md"), "utf8");
  let eo = (await kald("/egne-ord")).data;
  tjek("egne ord læses pr. fag og uge", vis(eo) === vis({ alfa: {}, beta: { 37: "Anden", 38: "Tredje\n## Uge 40\nslut" } }), vis(eo));
  tjek("egne ord står i Betas fil i ugeorden", /^# Beta — I egne ord\n[\s\S]*\n## Uge 37\n\nAnden\n\n## Uge 38\n\nTredje\n\\## Uge 40\nslut\n$/.test(eoFil()), eoFil());
  fs.writeFileSync(path.join(rod, "Beta", "egne-ord.md"), eoFil().replace(/^# Beta — I egne ord/, "# Mine noter"));
  await kald("/egne-ord", { fag: "beta", uge: 37, tekst: "" });
  eo = (await kald("/egne-ord")).data;
  tjek("en tom tekst fjerner ugen, og indledningen beholdes", vis(eo.beta) === vis({ 38: "Tredje\n## Uge 40\nslut" }) && eoFil().startsWith("# Mine noter\n") && !/Uge 37/.test(eoFil()), eoFil());
  await kald("/egne-ord", { fag: "alfa", uge: 36, tekst: "  " });
  tjek("en tom tekst opretter ingen fil", !fs.existsSync(path.join(rod, "Alfa", "egne-ord.md")));
  const eoFremmed = await kald("/egne-ord", { fag: "delta", uge: 36, tekst: "x" }), eoUge = await kald("/egne-ord", { fag: "beta", uge: 54, tekst: "x" });
  tjek("egne ord afviser ukendt fag og uge", eoFremmed.status === 400 && eoUge.status === 400, vis([eoFremmed, eoUge]));

  // USB-noter: vurderingen af en uge eller et hovedafsnit; kun fag med usb_noter, kendte vurderinger og et kort navn
  const usbFil = () => JSON.parse(fs.readFileSync(path.join(rod, "Scripts", "usb-vurdering.json"), "utf8"));
  const usb = await kald("/usb-vurdering", { fag: "beta", del: "39", vurdering: "for_meget", kommentar: "  To ens kodeblokke \r\n" });
  tjek("usb-vurdering gemmes", usb.status === 200 && usb.data.vurdering === "for_meget" && usbFil().beta["39"].kommentar === "To ens kodeblokke", vis([usb, usbFil()]));
  await kald("/usb-vurdering", { fag: "beta", del: "Eksamen", vurdering: "brugbar", kommentar: "" });
  tjek("usb-vurdering: et hovedafsnit kan vurderes, og GET viser begge", vis(Object.keys((await kald("/usb-vurdering")).data.beta)) === '["39","Eksamen"]');
  const usbAfvist = await Promise.all([{ fag: "alfa", del: "39", vurdering: "brugbar" }, { fag: "beta", del: "../x", vurdering: "brugbar" },
    { fag: "beta", del: "39", vurdering: "god" }, { fag: "beta", del: "39", kommentar: "x".repeat(2001) }].map(k => kald("/usb-vurdering", k)));
  tjek("usb-vurdering afviser fag uden usb_noter, mærkelige afsnit, ukendte vurderinger og lange kommentarer",
    usbAfvist.every(x => x.status === 400) && usbFil().beta["39"].vurdering === "for_meget", vis(usbAfvist.map(x => x.status)));
  await kald("/usb-vurdering", { fag: "beta", del: "39", vurdering: null, kommentar: "" });
  tjek("usb-vurdering: tom vurdering og kommentar fjerner ugen", !("39" in usbFil().beta), vis(usbFil()));

  const r = (await kald("/repetition")).data;
  const eks = r.statistik.eksamen || {};
  tjek("Alfas eksamensdag fra CLAUDE.md", vis(Object.keys(eks)) === '["alfa"]' && eks.alfa.dato === S.isoDato(eksDag) && eks.alfa.kort === 1, vis(eks));

  const p = (await kald("/pakke")).data;
  tjek("pakken har fagene fra fag.json", vis(p.fag.map(f => [f.id, f.kort, !!f.genkald, f.kode])) === '[["alfa","Alfa",true,null],["beta","Beta",false,"kode"]]', vis(p.fag));
  tjek("pakken har ingen tomme begreber, når de er skrevet", vis(p.begreber.map(x => [x.fag, x.begreb])) === "[]", vis(p.begreber));
  tjek("pakken har egne ord og ugens emne fra genkald", vis(p.egne_ord.tekster.beta) === vis({ 38: "Tredje\n## Uge 40\nslut" })
    && p.egne_ord.emner.alfa?.[36] === "Første emne" && Array.isArray(p.egne_ord.uger), vis(p.egne_ord));

  // I egne ord fra telefonen: gemmes, hvis ugen ikke er skrevet om på Mac'en siden pakken; et gensendt svar er gemt
  const eoPost = (id, data) => ({ id, type: "egne-ord", tid: new Date().toISOString(), data });
  const s1 = (await kald("/sync", { poster: [eoPost("egne-ord-0001", { fag: "beta", uge: 38, tekst: "Fra telefonen", foer: "Tredje\n## Uge 40\nslut" })] })).data;
  const s2 = (await kald("/sync", { poster: [eoPost("egne-ord-0001", { fag: "beta", uge: 38, tekst: "Fra telefonen", foer: "Tredje\n## Uge 40\nslut" })] })).data;
  const s3 = (await kald("/sync", { poster: [eoPost("egne-ord-0002", { fag: "beta", uge: 38, tekst: "Gammel pakke", foer: "Noget helt andet" })] })).data;
  eo = (await kald("/egne-ord")).data;
  tjek("egne ord fra telefonen gemmes, gensendes uden fejl og afvises ved en ændring på Mac'en",
    s1.resultater[0].ok && s2.resultater[0].ok && !s3.resultater[0].ok && /ændret på Mac'en/.test(s3.resultater[0].fejl) && eo.beta[38] === "Fra telefonen", vis([s1, s2, s3, eo.beta]));

  // Datoer i serverens lokaltid, ikke UTC
  const læstUge = await kald("/laest", { fag: "alfa", uge: 36, laest: true });
  tjek("en læst uge får den lokale dato", læstUge.status === 200 && læstUge.data.laest === serverDag(), vis([læstUge, serverDag(), TZ]));
  const læstKode = await kald("/laest", { fag: "beta", uge: 38, laest: true }), læstUkendt = await kald("/laest", { fag: "gamma", uge: 38, laest: true });
  tjek("et fag uden genkald kan også markere en uge som læst (Styr på i Beta)", læstKode.status === 200 && læstKode.data.laest === serverDag()
    && læstUkendt.status === 400, vis([læstKode, læstUkendt]));
  const frist = await kald("/deadline", { noegle: "Alfa|andet|41", faerdig: true });
  const status = JSON.parse(fs.readFileSync(path.join(rod, "Scripts", "deadlines-status.json"), "utf8"));
  tjek("en færdig frist får den lokale dato", frist.data?.faerdig === serverDag() && status["Alfa|andet|41"]?.faerdig === serverDag(), vis([frist, status, serverDag()]));
  const proeve = await kald("/eksamen/afslut", { fag: "beta", id: "2025", svar: { 1: "x" }, marks: { 1: { mark: "sad" } }, tilstand: "proeve" });
  const proeveLog = fs.readFileSync(path.join(rod, "Scripts", "genkald-log.jsonl"), "utf8").split("\n").filter(Boolean).map(JSON.parse).find(x => x.proeve);
  tjek("en prøveeksamen får den lokale dato", proeve.data?.gemt === `Beta/Eksamenstræning/besvarelser/2025-${serverDag()}-proeve.md`
    && proeveLog?.proeve.startsWith(`${serverDag()}T`), vis([proeve, proeveLog, serverDag()]));
  // Loglinjerne har tidsstempel i lokal tid med serverens offset
  const offset = `${timer < 0 ? "-" : "+"}${String(Math.abs(timer)).padStart(2, "0")}:00`;
  tjek("loglinjerne begynder med lokal tid", new RegExp(`^${serverDag()}T\\d{2}:\\d{2}:\\d{2}\\${offset} Studie-API på`).test(log), vis([log.slice(0, 120), offset]));

  // Stopuret og sessionerne (Scripts/sessioner.json). Tiden går ikke i en test, så filen skrives om imellem, som om
  // stopuret var startet tidligere; serveren læser filen ved hvert kald.
  const sFil = path.join(rod, "Scripts", "sessioner.json"), sLæs = () => JSON.parse(fs.readFileSync(sFil, "utf8"));
  const tilbage = min => new Date(Date.now() - min * 6e4).toISOString();
  const flyt = stykker => { const d = sLæs(); d.igang.stykker = stykker; fs.writeFileSync(sFil, JSON.stringify(d)); };
  let su = (await kald("/stopur")).data;
  tjek("stopur: intet kører, fagene og Pomodoro 25/5", su.igang === null && vis(su.fag.map(f => f.id)) === '["alfa","beta"]'
    && vis(su.pomodoro) === '{"arbejde":25,"pause":5}' && su.maal === 2 && vis(su.sessioner) === "[]", vis(su));
  const ukendtFag = await kald("/stopur", { handling: "start", fag: "is" }), ikkeIGang = await kald("/stopur", { handling: "stop" });
  tjek("stopur: ukendt fag og stop uden stopur afvises", ukendtFag.status === 400 && ikkeIGang.status === 400, vis([ukendtFag, ikkeIGang]));
  su = (await kald("/stopur", { handling: "start", fag: "alfa" })).data;
  const toGange = await kald("/stopur", { handling: "start", fag: "beta" });
  tjek("stopur: kører med ét åbent stykke og kan ikke startes to gange", su.igang?.fag === "alfa" && su.igang.stykker.length === 1
    && su.igang.stykker[0][1] === null && su.igang.pomodoro === null && toGange.status === 400 && sLæs().fra === serverDag(), vis([su.igang, toGange, sLæs().fra]));
  flyt([[tilbage(50), null]]);
  su = (await kald("/stopur", { handling: "pause" })).data;
  const toPauser = await kald("/stopur", { handling: "pause" });
  flyt([[tilbage(50), tilbage(30)]]);
  su = (await kald("/stopur", { handling: "fortsaet" })).data;
  flyt([[tilbage(50), tilbage(30)], [tilbage(20), null]]);
  await kald("/stopur", { handling: "skift", fag: "beta" });
  su = (await kald("/stopur", { handling: "stop" })).data;
  const første = su.sessioner[0];
  tjek("stopur: pause, fortsæt, skift fag og stop giver én session, og pausen tæller ikke", toPauser.status === 400 && su.igang === null
    && su.sessioner.length === 1 && første.fag === "beta" && Math.abs(første.timer - 40 / 60) < 0.01 && første.pause_min === 10 && første.kilde === "stopur"
    && sLæs().sessioner[0].stykker.length === 2, vis([toPauser, su]));
  await kald("/stopur", { handling: "start", fag: "alfa" });
  su = (await kald("/stopur", { handling: "stop" })).data;
  tjek("stopur: under et minut gemmes ikke", su.sessioner.length === 1 && /intet er gemt/.test(su.besked), vis(su));
  await kald("/stopur", { handling: "start", fag: "alfa" });
  su = (await kald("/stopur", { handling: "annuller" })).data;
  tjek("stopur: kassér gemmer intet", su.igang === null && su.sessioner.length === 1, vis(su));
  // Pomodoro: et fokus slutter af sig selv efter 25 minutter, også når ingen trykker pause
  await kald("/stopur", { handling: "start", fag: "alfa", pomodoro: true });
  flyt([[tilbage(120), tilbage(95)], [tilbage(90), null]]);
  su = (await kald("/stopur", { handling: "fortsaet" })).data;
  const tredje = su.igang.stykker;
  su = (await kald("/stopur", { handling: "stop" })).data;
  const pomo = su.sessioner.find(x => x.pomodoro);
  tjek("pomodoro: et udløbet fokus lukkes efter 25 min, og det næste kan startes uden pause", tredje.length === 3
    && Math.abs(Date.parse(tredje[1][1]) - Date.parse(tredje[1][0]) - 25 * 6e4) < 2000 && pomo && Math.abs(pomo.timer - 50 / 60) < 0.01, vis([tredje, pomo]));
  // Pomodoro med dine egne valg: 45 min fokus, 10 min pause og 2 fokus; et tredje kan ikke startes
  const forkert = await kald("/stopur", { handling: "start", fag: "alfa", pomodoro: { arbejde: 2 } });
  su = (await kald("/stopur", { handling: "start", fag: "alfa", pomodoro: { arbejde: 45, pause: 10, antal: 2 } })).data;
  flyt([[tilbage(235), tilbage(190)], [tilbage(185), null]]);
  const tredjeFokus = await kald("/stopur", { handling: "fortsaet" });
  su = (await kald("/stopur", { handling: "stop" })).data;
  tjek("pomodoro: egen længde, pause og antal; efter det sidste fokus kan der ikke startes et nyt", forkert.status === 400
    && tredjeFokus.status === 400 && /færdige/.test(tredjeFokus.data.fejl) && Math.abs(su.sessioner.find(x => x.pomodoro && Math.abs(x.timer - 1.5) < 0.01)?.timer - 1.5) < 0.01,
    vis([forkert, tredjeFokus, su.sessioner]));
  for (const x of su.sessioner.filter(x => Math.abs(x.timer - 1.5) < 0.01)) await kald("/session", { id: x.id, slet: true });
  // Gem session: faget, starten, pausen, aktiviteten og noten rettet, når du stopper; en rettet pause lægges midt i
  await kald("/stopur", { handling: "start", fag: "alfa" });
  flyt([[tilbage(30 * 60 + 60), tilbage(30 * 60 + 40)], [tilbage(30 * 60 + 30), null]]);
  const gemSlut = new Date(Date.now() - 30 * 3600e3).toISOString();
  const iVejen = (await kald("/session", { fag: "alfa", start: tilbage(30 * 60 + 120), slut: tilbage(30 * 60 + 90) })).data.sessioner.find(x => x.kilde === "tilføjet");
  const overlapStop = await kald("/stopur", { handling: "stop", start: tilbage(30 * 60 + 100), slut: gemSlut, fag: "beta" });
  await kald("/session", { id: iVejen.id, slet: true });
  const lang = await kald("/stopur", { handling: "stop", slut: gemSlut, aktivitet: "x".repeat(61) });
  su = (await kald("/stopur", { handling: "stop", start: tilbage(30 * 60 + 50), slut: gemSlut, pause_min: 20, fag: "beta", aktivitet: " Øvelser ", note: "Opgave 3\r\nog 4" })).data;
  const gemt = su.sessioner.find(x => x.aktivitet === "Øvelser"), gemtFil = sLæs().sessioner.find(x => x.aktivitet === "Øvelser");
  tjek("gem session: start, pause, fag, aktivitet og note; pausen midt i, og et overlap eller en for lang tekst gemmer intet", overlapStop.status === 400
    && lang.status === 400 && gemt?.fag === "beta" && Math.abs(gemt.timer - 30 / 60) < 0.01 && gemt.pause_min === 20 && gemt.note === "Opgave 3\nog 4"
    && gemtFil.stykker.length === 2 && vis(su.aktiviteter) === '["Øvelser"]', vis([overlapStop, lang, gemt, gemtFil]));
  const retTekst = (await kald("/session", { id: gemt.id, fag: "beta", start: gemt.start, slut: gemt.slut, aktivitet: "", note: "kun note" })).data;
  const retUden = (await kald("/session", { id: gemt.id, fag: "alfa", start: gemt.start, slut: gemt.slut })).data;
  const efter = retUden.sessioner.find(x => x.id === gemt.id);
  tjek("ret session: tom aktivitet fjernes, og uden felterne bliver noten og pausen stående", !retTekst.sessioner.find(x => x.id === gemt.id).aktivitet
    && efter.note === "kun note" && efter.fag === "alfa" && efter.pause_min === 20, vis(efter));
  await kald("/session", { id: gemt.id, slet: true });
  // Glemte du at stoppe: kun tiden til det klokkeslæt, du skriver, tæller
  await kald("/stopur", { handling: "start", fag: "alfa" });
  flyt([[tilbage(300), null]]);
  const forTidligt = await kald("/stopur", { handling: "stop", slut: tilbage(400) });
  su = (await kald("/stopur", { handling: "stop", slut: tilbage(240) })).data;
  tjek("stopur: stop med et tidligere klokkeslæt gemmer kun tiden til da", forTidligt.status === 400
    && Math.abs(su.sessioner.find(x => Date.parse(x.start) < Date.now() - 290 * 6e4).timer - 1) < 0.01, vis([forTidligt, su.sessioner]));
  // Sessioner, du tilføjer, retter og sletter
  const tilføj = await kald("/session", { fag: "alfa", start: tilbage(30 * 60), slut: tilbage(29 * 60) });
  const overlap = await kald("/session", { fag: "beta", start: tilbage(29.5 * 60), slut: tilbage(28 * 60) });
  const fremtid = await kald("/session", { fag: "beta", start: tilbage(10), slut: tilbage(-60) });
  const tilføjet = tilføj.data?.sessioner.find(x => x.kilde === "tilføjet");
  tjek("session: tilføjes, men ikke oven i en anden eller ude i fremtiden", tilføj.status === 200 && tilføjet?.timer === 1
    && overlap.status === 400 && /overlapper med Alfa/.test(overlap.data.fejl) && fremtid.status === 400, vis([tilføj, overlap, fremtid]));
  const ret = await kald("/session", { id: første.id, fag: "alfa", start: new Date(Date.parse(første.start) - 5 * 6e4).toISOString(), slut: new Date(Date.parse(første.slut) + 5 * 6e4).toISOString() });
  const rettet = ret.data?.sessioner.find(x => x.id === første.id);
  tjek("session: rettes med fag, start og slut, og pausen bliver", ret.status === 200 && rettet.fag === "alfa" && Math.abs(rettet.timer - 50 / 60) < 0.01 && rettet.pause_min === 10,
    vis([ret.status, rettet]));
  const slet = await kald("/session", { id: tilføjet.id, slet: true }), sletIgen = await kald("/session", { id: tilføjet.id, slet: true });
  tjek("session: slettes én gang", slet.status === 200 && !slet.data.sessioner.some(x => x.id === tilføjet.id) && sletIgen.status === 400, vis([slet.status, sletIgen]));
  // Forslag ud fra svarene i loggen: Alfa (genkald) og Beta (drills, faget med kode) på skift, så fagenes stykker ligger
  // flettet; en færdig frist er ikke et svar
  fs.appendFileSync(path.join(rod, "Scripts", "genkald-log.jsonl"), [[200, "genkald", "alfa/genkald-uge36-37.md#1"], [198, "drill", "drill/kap01.js#y"],
    [197, "deadline", "Alfa|G1"], [196, "genkald", "alfa/genkald-uge36-37.md#1"], [194, "drill", "drill/kap01.js#x"], [190, "drill-rep", "drill/kap01.js#x"]]
    .map(([min, type, noegle]) => JSON.stringify({ tid: tilbage(min), type, noegle }) + "\n").join(""));
  su = (await kald("/stopur")).data;
  const fs1 = su.forslag.find(f => Math.abs(Date.parse(f.slut) - (Date.now() - 190 * 6e4)) < 6e4);
  tjek("forslag: én del pr. fag, det første svar får mediantiden, og en frist tæller ikke", fs1 && fs1.svar === 5
    && vis(fs1.dele.map(x => [x.fag, x.kort, Math.round(x.timer * 60)])) === '[["alfa","Alfa",4],["beta","Beta",8]]' && vis(fs1.typer) === '["Genkald","Drills"]', vis(su.forslag));
  const gemF = (await kald("/forslag", { id: fs1.id, handling: "gem" })).data, igenF = await kald("/forslag", { id: fs1.id, handling: "gem" });
  tjek("forslag: gemt som én session pr. fag og ikke foreslået igen", gemF.sessioner.filter(x => x.kilde === "forslag").length === 2
    && !gemF.forslag.some(f => f.id === fs1.id) && igenF.status === 400, vis([gemF.sessioner, igenF]));
  fs.appendFileSync(path.join(rod, "Scripts", "genkald-log.jsonl"), [180, 178, 170].map(min => JSON.stringify({ tid: tilbage(min), type: "genkald", noegle: "alfa/genkald-uge36-37.md#1" }) + "\n").join(""));
  const fs2 = (await kald("/stopur")).data.forslag.find(f => f.svar === 3);
  const afvis = (await kald("/forslag", { id: fs2?.id, handling: "afvis" })).data;
  tjek("forslag: et afvist forslag kommer ikke igen", fs2 && !afvis.forslag.some(f => f.id === fs2.id) && sLæs().afviste.includes(fs2.id), vis([fs2, afvis?.forslag]));
  // En session fra forslaget ligger i pauserne i den anden; den kan stadig få et andet fag
  const flettet = gemF.sessioner.find(x => x.kilde === "forslag" && x.fag === "alfa");
  const nytFag = await kald("/session", { id: flettet.id, fag: "beta", start: flettet.start, slut: flettet.slut });
  tjek("forslag: en flettet session kan rettes uden at overlappe sig selv med den anden", nytFag.status === 200, vis(nytFag));
  for (const x of gemF.sessioner.filter(x => x.kilde === "forslag")) await kald("/session", { id: x.id, slet: true });
  // Indstillinger: dine mål i studiemaal.json går forud for fag.json; forkerte værdier gemmer intet
  const maalFil = path.join(rod, "Scripts", "studiemaal.json");
  const udenDage = await kald("/studiemaal", { dag_timer: 3, dage: [], medaljer: { bronze: 2, soelv: 3, guld: 4 } });
  const forkertOrden = await kald("/studiemaal", { dag_timer: 3, dage: [0, 1], medaljer: { bronze: 3, soelv: 3, guld: 4 } });
  const maalOk = await kald("/studiemaal", { dag_timer: 2.5, dage: [4, 0, 0, 2], medaljer: { bronze: 2, soelv: 3, guld: 5 } });
  tjek("indstillinger: mål, dage og medaljer gemmes, og forkerte værdier afvises", udenDage.status === 400 && forkertOrden.status === 400
    && maalOk.status === 200 && maalOk.data.studiemaal.dag_timer === 2.5 && vis(maalOk.data.studiemaal.dage) === "[0,2,4]" && maalOk.data.studiemaal.medaljer.guld === 5,
    vis([udenDage, forkertOrden, maalOk]));
  fs.unlinkSync(maalFil);
  // Fremmøde: en gang markeres og fortrydes; en ukendt kursuskode afvises
  const fmUkendt = await kald("/fremmoede", { id: "XYZ999|2026-01-05T10:00", til_stede: false });
  const fmIkke = (await kald("/fremmoede", { id: "ALFA1|2026-01-05T10:00", til_stede: false })).data;
  const fmIgen = (await kald("/fremmoede", { id: "ALFA1|2026-01-05T10:00", til_stede: true })).data;
  tjek("fremmøde: markeres og fortrydes, og en ukendt gang afvises", fmUkendt.status === 400 && vis(fmIkke.ikke) === '["ALFA1|2026-01-05T10:00"]'
    && vis(fmIgen.ikke) === "[]" && vis((await kald("/fremmoede")).data.ikke) === "[]", vis([fmUkendt, fmIkke, fmIgen]));
  tjek("sessioner.json: én session pr. linje", sLæs().sessioner.length === 3 && fs.readFileSync(sFil, "utf8").split("\n").filter(l => /^  \{"id":"s-/.test(l)).length === 3,
    fs.readFileSync(sFil, "utf8"));

  // Sikkerhed i procent og Tænk højt: står i loggen (ikke i genkaldsfilen), ordet udledes, og kalibreringen tæller i procentspand
  {
    const logLinjer = () => fs.readFileSync(path.join(rod, "Scripts", "genkald-log.jsonl"), "utf8").split("\n").filter(Boolean).map(JSON.parse);
    const g1 = await kald("/genkald", { fag: "alfa", fil: "genkald-uge36-37.md", nr: 2, svar: "Rækkefølgen", karakter: 3, procent: 80, tanker: "  Jeg tænkte på\r\nalfabetet  " });
    const r1 = await kald("/repetition", { noegle: "genkald:alfa/genkald-uge36-37.md#2", karakter: 1, procent: 20 });
    const r2 = await kald("/repetition", { noegle: "genkald:alfa/genkald-uge36-37.md#2", karakter: 3, procent: 50, tanker: "" });
    const forkerte = [];
    for (const procent of [120, 33.5, -10, "80"]) forkerte.push(await kald("/repetition", { noegle: "genkald:alfa/genkald-uge36-37.md#2", karakter: 3, procent }));
    const nye = logLinjer().filter(x => x.noegle === "alfa/genkald-uge36-37.md#2").map(x => [x.procent, x.sikkerhed, x.tanker ?? null]);
    tjek("sikkerhed i procent gemmes med ordet, og Tænk højt renses", g1.status === 200 && r1.status === 200 && r2.status === 200
      && vis(nye) === vis([[80, "sikker", "Jeg tænkte på\nalfabetet"], [20, "gaet", null], [50, "usikker", null]]), vis([g1, r1, r2, nye]));
    tjek("sikkerhed uden for 0-100 % eller ikke et helt tal afvises", forkerte.every(x => x.status === 400), vis(forkerte));
    const genkaldFil = fs.readFileSync(path.join(rod, "Alfa", "Genkald", "genkald-uge36-37.md"), "utf8");
    tjek("Tænk højt står ikke i genkaldsfilen", !/alfabetet/.test(genkaldFil), genkaldFil);
    const sync = (await kald("/sync", { poster: [{ id: "repetition-tanker-1", type: "repetition", tid: new Date().toISOString(),
      data: { noegle: "genkald:alfa/genkald-uge36-37.md#1", karakter: 2, procent: 90, tanker: "Fra telefonen" } }] })).data;
    const fraTlf = logLinjer().find(x => x.sync_id === "repetition-tanker-1");
    tjek("sikkerhed og Tænk højt kommer med fra telefonen", sync.resultater[0].ok && fraTlf?.procent === 90 && fraTlf.tanker === "Fra telefonen", vis([sync, fraTlf]));
    const kal = (await kald("/repetition")).data.statistik;
    const spand = Object.fromEntries(kal.kalibrering_procent.map(x => [`${x.fra}-${x.til}`, [x.n, x.sad, x.halvt, x.blankt]]));
    tjek("kalibreringen i procentspand og grænserne for ordene", vis(spand) === vis({ "0-20": [1, 0, 0, 1], "30-40": [0, 0, 0, 0], "50-60": [1, 1, 0, 0], "70-80": [1, 1, 0, 0], "90-100": [1, 0, 1, 0] })
      && kal.sikker_fra === 70 && kal.usikker_fra === 30, vis([spand, kal.sikker_fra, kal.usikker_fra]));
  }

  server.kill();

  // Rytme: svar en bestemt dag; drills hører til faget med kode, en færdig-markeret frist er ikke et svar
  const dag = new Date(2026, 0, 5, 12).toISOString();
  fs.appendFileSync(path.join(rod, "Scripts", "genkald-log.jsonl"), [
    { tid: dag, type: "genkald", noegle: "alfa/genkald-uge36-37.md#1" }, { tid: dag, type: "genkald", noegle: "alfa/genkald-uge36-37.md#2" },
    { tid: dag, type: "drill", noegle: "drill/kap01.js#x" }, { tid: dag, type: "eksamen", noegle: "beta/2025-ordinaer#1" },
    { tid: dag, type: "deadline", noegle: "Alfa|Opgave 1" },
  ].map(p => JSON.stringify(p) + "\n").join(""));

  // Eksporten på samme semester: fagene og deres felter i studie.json
  // En liv.json med studietid i en midlertidig mappe (eksporten læser LIV_SITE/liv.json)
  // tidligt: en uge længe før semestrets første undervisningsdag (60 dage siden), som hører til et andet semester
  const livSite = path.join(rod, "liv"), m = S.isoDato(S.plusDage(new Date(), -7)), tidligt = S.isoDato(S.plusDage(new Date(), -200));
  fs.mkdirSync(livSite, { recursive: true });
  fs.writeFileSync(path.join(livSite, "liv.json"), JSON.stringify({ studietid: { fra: m, selvstudie_fra: m, til: S.isoDato(new Date()),
    undervisning: [{ kode: "ALFA1", navn: "Alfa", timer: 13, uger: { [m]: 8, [tidligt]: 5 }, former: [{ art: "Øvelse", form: "campus", timer: 11, uger: { [m]: 6, [tidligt]: 5 } },
      { art: "Forelæsning", form: "forudindspillet", timer: 2, uger: { [m]: 2 } }] }],
    studieblokke: [{ navn: "Alfa", timer: 3, planlagt_timer: 3, uger: { [m]: 1, [tidligt]: 2 } }] } }));
  // Selvstudiet fra sessionerne: i går to sessioner i Alfa (1,5 t med en halv times pause og 1 t), og én i Beta, der ikke
  // har arbejdsbyrde i fag.json. Logningen begyndte for 7 dage siden.
  const igår = (h, mi = 0) => { const d = S.plusDage(new Date(), -1); d.setHours(h, mi, 0, 0); return S.lokalTid(d); };
  fs.writeFileSync(sFil, JSON.stringify({ fra: m, igang: { id: "s-igang", fag: "alfa", pomodoro: null, stykker: [[igår(20), null]] }, sessioner: [
    { id: "s-1", fag: "alfa", stykker: [[igår(8), igår(9)], [igår(9, 30), igår(10)]], kilde: "stopur" },
    { id: "s-2", fag: "alfa", stykker: [[igår(13), igår(14)]], kilde: "tilføjet" },
    { id: "s-3", fag: "beta", stykker: [[igår(15), igår(16)]], kilde: "stopur" }] }));
  // Fravær i ugen med undervisning: den tæller ikke som brugt
  skriv("Scripts/fravaer.json", JSON.stringify({ ikke_til_stede: [{ uge: S.isoUge(S.plusDage(new Date(), -7)), fag: "Beta" }],
    bruges_ikke: [{ fag: "Alfa", art: "Forelæsning", form: "forudindspillet" }] }));
  skriv("Scripts/undervisningsdage.json", JSON.stringify({ Alfa: { Forelæsninger: [{ dato: S.isoDato(S.plusDage(new Date(), -60)) }] } }));
  const eksEnv = { ...process.env, KOMPAS_SEMESTER: rod, LIV_SITE: livSite };
  execFileSync(process.execPath, [path.join(SCRIPTS, "kompas-eksport.js"), "--ud", ud], { stdio: "pipe", env: eksEnv });
  const st = JSON.parse(fs.readFileSync(path.join(ud, "studie.json"), "utf8"));
  const ss = JSON.parse(fs.readFileSync(path.join(ud, "selvstudie.json"), "utf8")), alfa = ss.fag.find(f => f.id === "alfa");
  tjek("selvstudie: kun fag med arbejdsbyrde", vis(ss.fag.map(f => f.id)) === '["alfa"]', vis(ss.fag.map(f => f.id)));
  const tilLiv = JSON.parse(fs.readFileSync(path.join(ud, "sessioner.json"), "utf8"));
  tjek("sessioner.json til overblik: de afsluttede sessioner med kortnavn og stykker", tilLiv.fra === m
    && vis(tilLiv.sessioner.map(x => [x.id, x.kort, x.stykker.length])) === '[["s-1","Alfa",2],["s-2","Alfa",1],["s-3","Beta",1]]', vis(tilLiv));
  tjek("selvstudie: forventet fra kursusbeskrivelsen, undervisning fra liv.json og selvstudie fra sessionerne", vis([alfa.forventet.i_alt, alfa.forventet.undervisning, alfa.forventet.selvstudie]) === "[100,20,80]"
    && vis(alfa.brugt) === vis({ undervisning: 6, selvstudie: 2.5, studieblokke_forbi: 1, studieblokke_planlagt: 3, i_alt: 8.5 }) && ss.i_alt.brugt === 8.5, vis([alfa.forventet, alfa.brugt, ss.i_alt]));
  tjek("periode: undervisning og studieblokke før semestrets første undervisningsdag tæller ikke", ss.periode?.fra === S.isoDato(S.plusDage(new Date(), -60))
    && ss.periode.til === S.isoDato(eksDag) && !alfa.uger.some(u => u.mandag === tidligt) && alfa.undervisning_ikke_talt === 2, vis([ss.periode, alfa.uger, alfa.undervisning_ikke_talt]));
  // Første undervisningsdag for 60 dage siden og eksamen om 60 dage: halvdelen af kurset er gået (±1 efter tidspunktet på dagen)
  tjek("selvstudie: forventet til nu jævnt fordelt fra første undervisningsdag til eksamen", Math.abs(alfa.forventet_til_nu?.andel - 50) <= 1 && Math.abs(alfa.forventet_til_nu.i_alt - 50) <= 1, vis(alfa.forventet_til_nu));
  const mv = ss.motivation;
  // Logningen begyndte for 7 dage siden (8 dage med i dag); i går 2,5 t, i dag intet endnu
  tjek("motivation: dage i træk tæller fra i går, når i dag er tom", mv.i_traek === 1 && mv.i_traek_maal === 1 && mv.laengst_i_traek === 1, vis([mv.i_traek, mv.i_traek_maal, mv.laengst_i_traek]));
  tjek("motivation: medalje efter grænserne og saldo mod dagsmålet", mv.dage.at(-2).medalje === "bronze" && mv.dage.length === 8 && mv.saldo === -13.5
    && mv.i_dag.timer === 0 && mv.i_dag.maal === 2, vis([mv.dage.at(-2), mv.saldo, mv.i_dag]));
  tjek("motivation: måneder til i dag med sessioner, og målet tæller kun dage fra logningen", mv.maaneder.at(-1).maaned === S.isoDato(new Date()).slice(0, 7)
    && mv.maaneder.reduce((a, x) => a + x.sessioner, 0) === 2 && mv.maaneder.reduce((a, x) => a + x.maal, 0) === 2 * mv.maaneder.reduce((a, x) => a + x.dage.filter(d => d.dato >= mv.fra).length, 0)
    && mv.saldo_i_dag === -2, vis(mv.maaneder.map(x => [x.maaned, x.timer, x.maal, x.sessioner])));
  tjek("motivation: kalenderen er hele uger, og dage efter i dag er tomme", mv.kalender.every(u => u.dage.length === 7)
    && mv.kalender.at(-1).dage.filter(d => d.dato > S.isoDato(new Date())).every(d => d.timer === null), vis(mv.kalender.at(-1)));
  tjek("bruges ikke: den slags undervisning tæller ikke", alfa.ikke_talt.bruges_ikke === 2 && alfa.ikke_talt.fravaer === 0, vis(alfa.ikke_talt));
  tjek("fravær: kun det nævnte fags undervisning trækkes fra", alfa.brugt.undervisning === 6 && alfa.undervisning_ikke_talt === 2
    && vis(ss.fravaer) === vis([{ uge: S.isoUge(S.plusDage(new Date(), -7)), fag: "Beta" }]), vis([alfa.brugt, alfa.undervisning_ikke_talt, ss.fravaer]));
  fs.writeFileSync(path.join(rod, "Scripts", "fravaer.json"), JSON.stringify({ ikke_til_stede: [{ uge: S.isoUge(S.plusDage(new Date(), -7)) }] }));
  execFileSync(process.execPath, [path.join(SCRIPTS, "kompas-eksport.js"), "--ud", ud], { stdio: "pipe", env: eksEnv });
  const alfa2 = JSON.parse(fs.readFileSync(path.join(ud, "selvstudie.json"), "utf8")).fag.find(f => f.id === "alfa");
  tjek("fravær uden fag gælder alle fag: ugens undervisning tæller ikke", alfa2.brugt.undervisning === 0 && alfa2.undervisning_ikke_talt === 8 && alfa2.ikke_talt.fravaer === 8
    && alfa2.uger.find(u => u.mandag === m)?.fravaer === true, vis([alfa2.brugt, alfa2.undervisning_ikke_talt, alfa2.uger]));
  // Rytmen: i går 8-9, 9.30-10, 13-14 (Alfa) og 15-16 (Beta); stopuret, der kører, tæller ikke
  const ry = ss.rytme.alt, igårUd = (S.plusDage(new Date(), -1).getDay() + 6) % 7;
  tjek("rytme: timer pr. time, ugedag og tidsrum, og det største tidsrum er markeret", ry.i_alt === 3.5 && ry.timer[8] === 1 && ry.timer[9] === 0.5
    && ry.ugedage[igårUd] === 3.5 && vis(ry.tidsrum.map(x => [x.fra, x.timer, x.pct, !!x.stoerst])) === '[[2,0,0,false],[6,1.5,43,true],[10,1,29,false],[14,1,29,false],[18,0,0,false],[22,0,0,false]]',
    vis(ry));
  // Fridage: med en dag uden mål trækker den dag ikke saldoen ned, og dage i træk springer den over
  const fridag = (S.plusDage(new Date(), -2).getDay() + 6) % 7;
  fs.writeFileSync(path.join(rod, "Scripts", "studiemaal.json"), JSON.stringify({ dag_timer: 2, dage: [0, 1, 2, 3, 4, 5, 6].filter(x => x !== fridag), medaljer: { bronze: 2, soelv: 3, guld: 4 } }));
  execFileSync(process.execPath, [path.join(SCRIPTS, "kompas-eksport.js"), "--ud", ud], { stdio: "pipe", env: eksEnv });
  const mvf = JSON.parse(fs.readFileSync(path.join(ud, "selvstudie.json"), "utf8")).motivation, fri = mvf.dage.filter(d => d.fridag);
  tjek("fridage: målet er 0, saldoen trækkes ikke ned, og ugens mål er seks dage", fri.length >= 1 && fri.every(d => d.ugedag === fridag && d.maal_dag === 0 && d.naaet === null)
    && mvf.saldo === Math.round((mv.saldo + 2 * fri.length) * 100) / 100 && mvf.uge.maal === 12 && mvf.gaelder !== "alle dage", vis([fri, mvf.saldo, mv.saldo, mvf.uge, mvf.gaelder]));
  fs.unlinkSync(path.join(rod, "Scripts", "studiemaal.json"));
  // Et kursus over to semestre med dette semesters del: forventet er delen, til sidste undervisningsdag (datoer som tekst)
  const fj = JSON.parse(fs.readFileSync(path.join(rod, "Scripts", "fag.json"), "utf8"));
  Object.assign(fj.fag[0].arbejdsbyrde, { semestre: 2, dette_semester: { til: "sidste_undervisning", vurdering: "test",
    poster: [{ navn: "Forelæsning", timer: 10 }, { navn: "Læsning", timer: 30 }] } });
  fs.writeFileSync(path.join(rod, "Scripts", "fag.json"), JSON.stringify(fj));
  skriv("Scripts/undervisningsdage.json", JSON.stringify({ Alfa: { Forelæsninger: [{ dato: S.isoDato(S.plusDage(new Date(), -60)) }], Øvelser: [S.isoDato(S.plusDage(new Date(), 30))] } }));
  execFileSync(process.execPath, [path.join(SCRIPTS, "kompas-eksport.js"), "--ud", ud], { stdio: "pipe", env: eksEnv });
  const alfa3 = JSON.parse(fs.readFileSync(path.join(ud, "selvstudie.json"), "utf8")).fag.find(f => f.id === "alfa"), tn3 = alfa3.forventet_til_nu;
  tjek("dette semester: forventet er semestrets del, og til nu løber til sidste undervisningsdag", alfa3.forventet.i_alt === 40 && alfa3.forventet.hele_kurset === 100
    && alfa3.forventet.undervisning === 10 && tn3?.til_er === "sidste_undervisning" && tn3.til === S.isoDato(S.plusDage(new Date(), 30)) && Math.abs(tn3.andel - 67) <= 1
    && alfa3.forudsigelse?.eksamen === tn3.til, vis([alfa3.forventet, tn3, alfa3.forudsigelse]));
  // Semestre: et tidligere semester ved siden af dette med samme kursuskode (som et kursus over to semestre), regnet ud fra
  // sine egne filer til sin slutdato; kalenderens undervisning i dette semester tæller ikke dér
  const forrige = `${rod}-forrige`, fskriv = (f, t) => { fs.mkdirSync(path.dirname(path.join(forrige, f)), { recursive: true }); fs.writeFileSync(path.join(forrige, f), t); };
  fskriv("Scripts/fag.json", JSON.stringify({ semester: "Forrige", studiemaal: { dag_timer: 1, medaljer: { bronze: 1, soelv: 2, guld: 3 } }, fag: [
    { id: "alfa", kort: "Alfa", navn: "Alfa", mappe: "Alfa", kursuskode: "ALFA1", arbejdsbyrde: { kilde: "test", semestre: 1, poster: [{ navn: "Læsning", timer: 10, undervisning: false }] } }] }));
  fskriv("Scripts/undervisningsdage.json", JSON.stringify({ Alfa: { Forelæsninger: ["2025-09-01", "2025-11-24"] } }));
  fskriv("CLAUDE.md", "## Vigtige datoer\n\n| Uge | Fag | Hvad |\n|---|---|---|\n| 50 | Alfa | **Eksamen: skriftlig** — torsdag 11.12.2025 |\n");
  fskriv("Scripts/sessioner.json", JSON.stringify({ fra: "2025-09-29", sessioner: [{ id: "s-f", fag: "alfa", stykker: [["2025-10-01T10:00:00+02:00", "2025-10-01T12:00:00+02:00"]] }] }));
  execFileSync(process.execPath, [path.join(SCRIPTS, "kompas-eksport.js"), "--ud", ud], { stdio: "pipe", env: eksEnv });
  const sm = JSON.parse(fs.readFileSync(path.join(ud, "semestre.json"), "utf8")), smNu = sm.semestre.find(x => x.aktuel), fo = sm.semestre.find(x => x.mappe === path.basename(forrige));
  tjek("semestre: det aktuelle står først, og et tidligere ved siden af kommer med", sm.semestre[0] === smNu && smNu.navn === "Testsemester" && sm.aktuelt === "Testsemester"
    && fo?.navn === "Forrige" && !fo.aktuel, vis(sm.semestre.map(x => [x.navn, x.mappe, x.aktuel])));
  tjek("semestre: et tidligere semester regnes til sin slutdato ud fra sine egne filer", vis(fo?.periode) === '{"fra":"2025-09-01","til":"2025-12-11"}' && fo.regnet_til === "2025-12-11"
    && fo.i_alt.selvstudie === 2 && fo.fag[0].pct === 20 && fo.forventet.selvstudie === 10 && fo.sessioner === 1
    && fo.motivation.medaljer.soelv === 1 && fo.motivation.dage === 74 && fo.motivation.saldo === -72 && fo.motivation.dage_med_selvstudie === 1, vis(fo));
  tjek("semestre: samme kursuskode, men dette semesters undervisning tæller ikke i det tidligere", fo?.fag[0].brugt.undervisning === 0
    && vis(smNu.fag[0].brugt) === vis(JSON.parse(fs.readFileSync(path.join(ud, "selvstudie.json"), "utf8")).fag[0].brugt), vis([fo?.fag[0].brugt, smNu.fag[0].brugt]));
  tjek("semestre: alle semestre samlet", sm.i_alt.selvstudie === Math.round((smNu.i_alt.selvstudie + 2) * 10) / 10 && sm.i_alt.sessioner === smNu.sessioner + 1, vis(sm.i_alt));
  fs.rmSync(forrige, { recursive: true, force: true });
  tjek("selvstudie: logget tid i et fag uden arbejdsbyrde står for sig", vis(ss.ukendt) === '[{"navn":"Beta","timer":1}]' && ss.selvstudie_fra === m, vis(ss.ukendt));
  tjek("studie.json har Alfa og Beta", vis(st.fag.map(f => [f.id, f.kort, f.farve])) === '[["alfa","Alfa","var(--c1)"],["beta","Beta","var(--c2)"]]', vis(st.fag));
  tjek("studie.json har eksamensformen", st.fag[1].eksamenstraening?.form === "kode", vis(st.fag[1]));
  const sum = (xs, k) => xs.reduce((a, x) => a + x[k], 0);
  tjek("genkald og drills i alt fra eksporten", st.fag[0].status.genkald_i_alt.spoergsmaal === sum(st.fag[0].status.genkald, "spoergsmaal")
    && st.fag[0].status.genkald_i_alt.spoergsmaal > 0 && st.fag[1].status.drills_i_alt.pladser === sum(st.fag[1].status.drills, "pladser"),
    vis([st.fag[0].status.genkald_i_alt, st.fag[1].status.drills_i_alt]));
  tjek("rytme: svar pr. dag pr. fag", vis(st.fag.map(f => f.status.rytme.dage["2026-01-05"])) === "[2,2]" && st.fag[0].status.rytme.til === S.isoDato(new Date()),
    vis(st.fag.map(f => f.status.rytme)));
  // Sessionerne: i går 2,5 t i Alfa og 1 t i Beta (se Rytmen på Selvstudie nedenfor)
  const igårDag = S.isoDato(S.plusDage(new Date(), -1));
  tjek("rytme: selvstudie pr. dag pr. fag fra sessionerne", vis(st.fag.map(f => f.status.rytme.timer[igårDag])) === "[2.5,1]"
    && st.fag[0].status.rytme.timer_i_alt === 2.5 && st.fag[0].status.rytme.seneste >= igårDag, vis(st.fag.map(f => f.status.rytme)));
  tjek("gamle sæt er filerne, ikke mappen Eksamenstræning", vis(st.fag[1].status.eksamenssaet) === '["Beta_Eksamener.pdf"]'
    && vis(st.fag[0].status.eksamenssaet) === "[]", vis(st.fag.map(f => f.status.eksamenssaet)));

  // Fremmøde gang for gang: med gangene fra overblik tæller en markeret gang ikke, og de slags, du aldrig bruger, er ikke med
  {
    const liv2 = JSON.parse(fs.readFileSync(path.join(livSite, "liv.json"), "utf8"));
    const md = new Date(`${m}T12:00`), man = S.isoDato(S.plusDage(md, -((md.getDay() + 6) % 7)));
    liv2.studietid.undervisning[0].gange = [{ dato: man, start: "08:00", slut: "10:00", art: "Øvelse", form: "campus", timer: 2 },
      { dato: man, start: "12:00", slut: "13:00", art: "Øvelse", form: "campus", timer: 1 },
      { dato: man, start: "14:00", slut: "16:00", art: "Forelæsning", form: "forudindspillet", timer: 2 }];
    fs.writeFileSync(path.join(livSite, "liv.json"), JSON.stringify(liv2));
    fs.writeFileSync(path.join(rod, "Scripts", "fravaer.json"), JSON.stringify({ bruges_ikke: [{ fag: "Alfa", art: "Forelæsning", form: "forudindspillet" }] }));
    fs.writeFileSync(path.join(rod, "Scripts", "fremmoede.json"), JSON.stringify({ ikke: [`ALFA1|${man}T12:00`] }));
    execFileSync(process.execPath, [path.join(SCRIPTS, "kompas-eksport.js"), "--ud", ud], { stdio: "pipe", env: eksEnv });
    const a4 = JSON.parse(fs.readFileSync(path.join(ud, "selvstudie.json"), "utf8")).fag.find(f => f.id === "alfa");
    tjek("fremmøde: en markeret gang tæller ikke, og de slags, du aldrig bruger, er ikke blandt gangene", a4.brugt.undervisning === 2
      && a4.ikke_talt.fravaer === 1 && a4.ikke_talt.bruges_ikke === 2 && vis(a4.gange.map(g => [g.start, g.status])) === '[["08:00","talt"],["12:00","ikke"]]'
      && a4.gange[1].id === `ALFA1|${man}T12:00`, vis([a4.brugt, a4.ikke_talt, a4.gange]));
  }

  // Ingen faste fag-id'er i koden: fagene kommer fra fag.json
  const faste = [];
  for (const dir of [SCRIPTS, path.join(SCRIPTS, "kompas")]) for (const n of fs.readdirSync(dir).filter(n => /\.(js|html)$/.test(n))) {
    fs.readFileSync(path.join(dir, n), "utf8").split("\n").forEach((l, i) => {
      if (/^\s*\/\//.test(l)) return;
      if (/(["'`])(alfa|beta|gamma)\1|\bFAGNAVN\b|\bFAG_FARVE\b/.test(l)) faste.push(`${n}:${i + 1}: ${l.trim().slice(0, 100)}`);
    });
  }
  tjek("ingen faste fag-id'er i studie/Scripts/", !faste.length, "\n  " + faste.join("\n  "));
})().catch(e => { fejl++; console.log("FEJL", e.stack, log); }).finally(() => {
  server.kill();
  fs.rmSync(rod, { recursive: true, force: true });
  fs.rmSync(`${rod}-forrige`, { recursive: true, force: true });
  if (fejl) { console.log(`${fejl} fejl`); process.exitCode = 1; } else console.log("fag fra fag.json: alt ok");
});
