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
  const livSite = path.join(rod, "liv"), m = S.isoDato(S.plusDage(new Date(), -7));
  fs.mkdirSync(livSite, { recursive: true });
  fs.writeFileSync(path.join(livSite, "liv.json"), JSON.stringify({ studietid: { fra: m, selvstudie_fra: m, til: S.isoDato(new Date()),
    undervisning: [{ kode: "ALFA1", navn: "Alfa", timer: 8, uger: { [m]: 8 }, former: [{ art: "Øvelse", form: "campus", timer: 6, uger: { [m]: 6 } },
      { art: "Forelæsning", form: "forudindspillet", timer: 2, uger: { [m]: 2 } }] }], selvstudie: [{ navn: "Alfa", timer: 2.5, uger: { [m]: 2.5 }, dage: { [S.isoDato(S.plusDage(new Date(), -1))]: 2.5 }, sessioner: { [S.isoDato(S.plusDage(new Date(), -1))]: 2 } }, { navn: "Ukendt fag", timer: 1, uger: {} }],
    studieblokke: [{ navn: "Alfa", timer: 1, planlagt_timer: 3, uger: {} }] } }));
  // Fravær i ugen med undervisning: den tæller ikke som brugt
  skriv("Scripts/fravaer.json", JSON.stringify({ ikke_til_stede: [{ uge: S.isoUge(S.plusDage(new Date(), -7)), fag: "Beta" }],
    bruges_ikke: [{ fag: "Alfa", art: "Forelæsning", form: "forudindspillet" }] }));
  skriv("Scripts/undervisningsdage.json", JSON.stringify({ Alfa: { Forelæsninger: [{ dato: S.isoDato(S.plusDage(new Date(), -60)) }] } }));
  const eksEnv = { ...process.env, KOMPAS_SEMESTER: rod, LIV_SITE: livSite };
  execFileSync(process.execPath, [path.join(SCRIPTS, "kompas-eksport.js"), "--ud", ud], { stdio: "pipe", env: eksEnv });
  const st = JSON.parse(fs.readFileSync(path.join(ud, "studie.json"), "utf8"));
  const ss = JSON.parse(fs.readFileSync(path.join(ud, "selvstudie.json"), "utf8")), alfa = ss.fag.find(f => f.id === "alfa");
  tjek("selvstudie: kun fag med arbejdsbyrde", vis(ss.fag.map(f => f.id)) === '["alfa"]', vis(ss.fag.map(f => f.id)));
  tjek("selvstudie: forventet fra kursusbeskrivelsen og brugt fra liv.json", vis([alfa.forventet.i_alt, alfa.forventet.undervisning, alfa.forventet.selvstudie]) === "[100,20,80]"
    && vis(alfa.brugt) === vis({ undervisning: 6, selvstudie: 2.5, studieblokke_forbi: 1, studieblokke_planlagt: 3, i_alt: 8.5 }) && ss.i_alt.brugt === 8.5, vis([alfa.forventet, alfa.brugt, ss.i_alt]));
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
  tjek("selvstudie: logget tid uden fag står for sig", vis(ss.ukendt) === '[{"navn":"Ukendt fag","timer":1}]', vis(ss.ukendt));
  tjek("studie.json har Alfa og Beta", vis(st.fag.map(f => [f.id, f.kort, f.farve])) === '[["alfa","Alfa","var(--c1)"],["beta","Beta","var(--c2)"]]', vis(st.fag));
  tjek("studie.json har eksamensformen", st.fag[1].eksamenstraening?.form === "kode", vis(st.fag[1]));
  const sum = (xs, k) => xs.reduce((a, x) => a + x[k], 0);
  tjek("genkald og drills i alt fra eksporten", st.fag[0].status.genkald_i_alt.spoergsmaal === sum(st.fag[0].status.genkald, "spoergsmaal")
    && st.fag[0].status.genkald_i_alt.spoergsmaal > 0 && st.fag[1].status.drills_i_alt.pladser === sum(st.fag[1].status.drills, "pladser"),
    vis([st.fag[0].status.genkald_i_alt, st.fag[1].status.drills_i_alt]));
  tjek("rytme: svar pr. dag pr. fag", vis(st.fag.map(f => f.status.rytme.dage["2026-01-05"])) === "[2,2]" && st.fag[0].status.rytme.til === S.isoDato(new Date()),
    vis(st.fag.map(f => f.status.rytme)));
  tjek("gamle sæt er filerne, ikke mappen Eksamenstræning", vis(st.fag[1].status.eksamenssaet) === '["Beta_Eksamener.pdf"]'
    && vis(st.fag[0].status.eksamenssaet) === "[]", vis(st.fag.map(f => f.status.eksamenssaet)));

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
  if (fejl) { console.log(`${fejl} fejl`); process.exitCode = 1; } else console.log("fag fra fag.json: alt ok");
});
