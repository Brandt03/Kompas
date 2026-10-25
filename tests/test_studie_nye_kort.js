// Nye genkaldsspørgsmål i Dagens kort og i Ekstra genkald (På farten) på et opdigtet semester med to genkaldsfag
// (Alfa og Gamma): ældste uge først, og inden for ugen på skift mellem fagene, så det fag, der er nået kortest i
// ugen, får det næste. Og de forfaldne: faget med den nærmeste eksamen først, fag uden kommende eksamen sidst.
// Drills bliver kun kort, når de er gættet forkert, eller du satte flueben i "gættede".
// Kører på en midlertidig semestermappe med egen port og egen eksportmappe; koden kører fra studie/Scripts med
// KOMPAS_SEMESTER sat til mappen.
//   node tests/test_studie_nye_kort.js
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const SCRIPTS = path.join(__dirname, "..", "studie", "Scripts");
const rod = fs.mkdtempSync(path.join(os.tmpdir(), "nye-kort-test-"));
const skriv = (f, t) => { fs.mkdirSync(path.dirname(path.join(rod, f)), { recursive: true }); fs.writeFileSync(path.join(rod, f), t); };
skriv("Scripts/fag.json", JSON.stringify({ semester: "Testsemester", fag: [
  { id: "alfa", kort: "Alfa", navn: "Alfa", mappe: "Alfa", readme: "Alfa", fagnoter_overskrift: "Alfa", genkald: true },
  { id: "gamma", kort: "Gamma", navn: "Gamma", mappe: "Gamma", readme: "Gamma", fagnoter_overskrift: "Gamma", genkald: true },
  { id: "beta", kort: "Beta", navn: "Beta", mappe: "Beta", readme: "Beta", fagnoter_overskrift: "Beta", kode: "kode" },
] }));
// Gammas eksamen er om 30 dage, Alfas var i går (overstået), Beta har ingen
process.env.KOMPAS_SEMESTER = rod;
const S = require(path.join(SCRIPTS, "semester.js")), dd = n => String(n).padStart(2, "0");
const eksLinje = (fag, dag) => `| ${S.isoUge(dag)} | ${fag} | **Eksamen: skriftlig** — ${dd(dag.getDate())}.${dd(dag.getMonth() + 1)}.${dag.getFullYear()} kl. 09:00-11:00 |`;
skriv("CLAUDE.md", `# Testsemester\n\n## Vigtige datoer\n\n| Uge | Fag | Hvad |\n|---|---|---|\n${eksLinje("Gamma", S.plusDage(new Date(), 30))}\n${eksLinje("Alfa", S.plusDage(new Date(), -1))}\n`);
skriv("README.md", "# Testsemester\n");
// Tre tjek med et gæt hver: rigtigt og sikkert, rigtigt men gættet, og forkert
// En lille tjek.js med samme udskrift som semestrets: "FEJL  <tjek>" og "du gættede …" ved et forkert gæt, og en opsummering
skriv("Beta/kode/Drills/tjek.js", `const TOM = Symbol("ikke udfyldt"); let ok = 0, fejl = 0, tomme = 0;
function tjek(navn, udtryk, gaet) {
  if (gaet === TOM) { tomme++; return; }
  const js = udtryk();
  if (JSON.stringify(js) === JSON.stringify(gaet)) { ok++; return; }
  fejl++; console.log("FEJL  " + navn); console.log("      du gættede   " + JSON.stringify(gaet)); console.log("      JavaScript:  " + JSON.stringify(js));
}
function opsummer() { console.log(ok + " rigtige · " + fejl + " forkerte · " + tomme + " ikke udfyldt (af " + (ok + fejl + tomme) + ")"); }
module.exports = { tjek, TOM, opsummer };
`);
skriv("Beta/kode/Drills/kap01-test.js", `// Beta kap. 1 — test
const { tjek, TOM, opsummer } = require("./tjek.js");
tjek("sikker", () => 1 + 1, 2);
tjek("gættede", () => 2 + 2, 4);
tjek("forkert", () => 3 + 3, 7);
opsummer();
`);
// mærker: { nr: "✓" } for spørgsmål, der er markeret i filen
const genkald = (fag, uge, n, mærker = {}) => skriv(`${fag}/Genkald/genkald-uge${uge}-${uge}.md`, `# ${fag} — genkaldelse, uge ${uge}\n\n---\n\n## Uge ${uge} — emne\n\n`
  + Array.from({ length: n }, (_, i) => `**${i + 1}.** ${mærker[i + 1] ? `[${mærker[i + 1]}] ` : ""}Spørgsmål ${i + 1}?\n`).join("\n"));
genkald("Alfa", 36, 2, { 1: "✓" });
genkald("Alfa", 37, 3);
genkald("Alfa", 38, 1);
genkald("Gamma", 36, 4);
genkald("Gamma", 37, 2);
// Uge 39 er ikke læst, men ét spørgsmål i hvert fag er taget for længe siden og er forfaldent; Alfas er ældst
genkald("Alfa", 39, 1);
genkald("Gamma", 39, 1);
// Uge 36-37 er læst i begge fag; Alfa uge 38 er ikke
skriv("Scripts/laest.json", JSON.stringify({ alfa: { 36: "2026-09-01", 37: "2026-09-01" }, gamma: { 36: "2026-09-01", 37: "2026-09-01" } }));
// Alfa uge 36 nr. 1 er taget i går (sad), så Alfa er ét spørgsmål foran i uge 36
const igår = new Date(Date.now() - 864e5).toISOString();
const dageSiden = n => new Date(Date.now() - n * 864e5).toISOString();
skriv("Scripts/genkald-log.jsonl", [
  { tid: dageSiden(40), type: "genkald", noegle: "alfa/genkald-uge39-39.md#1", mark: "sad", karakter: 3 },
  { tid: dageSiden(30), type: "genkald", noegle: "gamma/genkald-uge39-39.md#1", mark: "sad", karakter: 3 },
  { tid: igår, type: "genkald", noegle: "alfa/genkald-uge36-36.md#1", mark: "sad", karakter: 3 },
  // For ti dage siden: alle tre ville være forfaldne, hvis de var kort
  { tid: dageSiden(10), type: "drill", noegle: "drill/kap01-test.js#sikker", rigtig: true },
  { tid: dageSiden(10), type: "drill", noegle: "drill/kap01-test.js#gættede", rigtig: true, sikkerhed: "gaet" },
  { tid: dageSiden(10), type: "drill", noegle: "drill/kap01-test.js#forkert", rigtig: false },
].map(x => JSON.stringify(x)).join("\n") + "\n");

let fejl = 0;
const tjek = (navn, ok, detalje = "") => { if (!ok) { fejl++; console.log("FEJL", navn, detalje); } };
const vis = x => JSON.stringify(x);

const PORT = 19000 + (process.pid % 1000), ud = path.join(rod, "ud");
const server = spawn(process.execPath, [path.join(SCRIPTS, "kompas-server.js")],
  { env: { ...process.env, KOMPAS_SEMESTER: rod, STUDIE_PORT: String(PORT), STUDIE_EKSPORT_UD: ud }, stdio: ["ignore", "ignore", "pipe"] });
let log = ""; server.stderr.on("data", d => { log += d; });
const hent = async sti => (await fetch(`http://127.0.0.1:${PORT}/studie/api${sti}`)).json();

(async () => {
  let r = null;
  for (let i = 0; i < 40; i++) { try { r = await hent("/repetition"); break; } catch { await new Promise(x => setTimeout(x, 100)); } }
  const nye = (r?.kort || []).filter(k => k.ny).map(k => k.noegle);
  tjek("Dagens kort: på skift mellem fagene, så det fag, der er nået kortest i ugen, får det næste", vis(nye) === vis([
    "gamma/genkald-uge36-36.md#1", "alfa/genkald-uge36-36.md#2", "gamma/genkald-uge36-36.md#2",
    "gamma/genkald-uge36-36.md#3", "gamma/genkald-uge36-36.md#4",
  ]), vis(nye) + log);
  tjek("statistikken tæller de klar og de låste", r?.statistik.nye_klar === 10 && r?.statistik.nye_venter_paa_laesning === 1, vis(r?.statistik));
  tjek("ulæste uger pr. fag: Alfa uge 38 venter med ét spørgsmål", vis(r?.statistik.ulaeste_uger) === vis([{ fag: "alfa", navn: "Alfa", uger: [38], spoergsmaal: 1 }]), vis(r?.statistik.ulaeste_uger));

  const drills = (r?.kort || []).filter(k => k.type === "drill").map(k => k.noegle);
  tjek("drills: kun det forkerte og det gættede bliver kort", vis(drills.sort()) === vis(["drill/kap01-test.js#forkert", "drill/kap01-test.js#gættede"]), vis(drills));
  const forfaldne = (r?.kort || []).filter(k => !k.ny && k.type === "genkald").map(k => k.noegle);
  tjek("forfaldne: nærmeste eksamen først, overstået eksamen som ingen eksamen", vis(forfaldne) === vis([
    "gamma/genkald-uge39-39.md#1", "alfa/genkald-uge39-39.md#1",
  ]), vis(forfaldne));

  // Ekstra genkald: resten af de nye fra læste uger i samme orden, derefter de markerede
  const ekstra = (await hent("/pakke")).ekstra.map(k => k.noegle);
  tjek("Ekstra genkald: næste uge på skift mellem fagene, så de markerede, uden ulæste uger", vis(ekstra) === vis([
    "alfa/genkald-uge37-37.md#1", "gamma/genkald-uge37-37.md#1", "alfa/genkald-uge37-37.md#2",
    "gamma/genkald-uge37-37.md#2", "alfa/genkald-uge37-37.md#3", "alfa/genkald-uge36-36.md#1",
  ]), vis(ekstra));

  server.kill();
  fs.rmSync(rod, { recursive: true, force: true });
  if (fejl) { console.log(`${fejl} fejl`); process.exitCode = 1; } else console.log("nye kort: alt ok");
})().catch(e => { console.log("FEJL", e); server.kill(); process.exitCode = 1; });
