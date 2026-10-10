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
skriv("Scripts/fag.json", JSON.stringify({ semester: "Testsemester", fag: [
  { id: "alfa", kort: "Alfa", navn: "Alfa for begyndere", mappe: "Alfa", readme: "Alfa", fagnoter_overskrift: "Alfa",
    genkald: true, begreber: { ekstra_kolonne: "Hvad det viser", ekstra_spoergsmaal: "og sig hvad det viser" },
    eksamenstraening: { form: "skriftlig", note: "Alfa-note" } },
  { id: "beta", kort: "Beta", navn: "Beta og kode", mappe: "Beta", readme: "Beta", fagnoter_overskrift: "Beta",
    kode: "kode", eksamenstraening: { form: "kode", note: "Beta-note" } },
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

let fejl = 0;
const tjek = (navn, ok, detalje = "") => { if (!ok) { fejl++; console.log("FEJL", navn, detalje); } };
const vis = x => JSON.stringify(x);

const PORT = 18000 + (process.pid % 1000), ud = path.join(rod, "ud");
const server = spawn(process.execPath, [path.join(SCRIPTS, "kompas-server.js")],
  { env: { ...process.env, KOMPAS_SEMESTER: rod, STUDIE_PORT: String(PORT), STUDIE_EKSPORT_UD: ud }, stdio: ["ignore", "ignore", "pipe"] });
let log = ""; server.stderr.on("data", d => { log += d; });
const kald = async (sti, krop) => {
  const r = await fetch(`http://127.0.0.1:${PORT}/studie/api${sti}`, krop ? { method: "POST", body: JSON.stringify(krop),
    headers: { "Content-Type": "application/json", Origin: "https://kompas.localhost" } } : {});
  return { status: r.status, data: await r.json().catch(() => null) };
};

(async () => {
  for (let i = 0; i < 40; i++) { try { await kald("/laest"); break; } catch { await new Promise(r => setTimeout(r, 100)); } }

  const g = (await kald("/genkald")).data;
  tjek("genkald kommer fra Alfa", vis(g.map(f => [f.fag, f.fil, f.spoergsmaal.length, f.har_facit])) === '[["alfa","genkald-uge36-37.md",2,true]]', vis(g));

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

  const r = (await kald("/repetition")).data;
  const eks = r.statistik.eksamen || {};
  tjek("Alfas eksamensdag fra CLAUDE.md", vis(Object.keys(eks)) === '["alfa"]' && eks.alfa.dato === S.isoDato(eksDag) && eks.alfa.kort === 1, vis(eks));

  const p = (await kald("/pakke")).data;
  tjek("pakken har fagene fra fag.json", vis(p.fag.map(f => [f.id, f.kort, !!f.genkald, f.kode])) === '[["alfa","Alfa",true,null],["beta","Beta",false,"kode"]]', vis(p.fag));
  tjek("pakken har ingen tomme begreber, når de er skrevet", vis(p.begreber.map(x => [x.fag, x.begreb])) === "[]", vis(p.begreber));

  server.kill();

  // Eksporten på samme semester: fagene og deres felter i studie.json
  execFileSync(process.execPath, [path.join(SCRIPTS, "kompas-eksport.js"), "--ud", ud], { stdio: "pipe", env: { ...process.env, KOMPAS_SEMESTER: rod } });
  const st = JSON.parse(fs.readFileSync(path.join(ud, "studie.json"), "utf8"));
  tjek("studie.json har Alfa og Beta", vis(st.fag.map(f => [f.id, f.kort, f.farve])) === '[["alfa","Alfa","var(--c1)"],["beta","Beta","var(--c2)"]]', vis(st.fag));
  tjek("studie.json har eksamensformen", st.fag[1].eksamenstraening?.form === "kode", vis(st.fag[1]));

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
