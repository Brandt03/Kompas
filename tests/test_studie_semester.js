// semester.js mod et opdigtet semester (Alfa, Beta, Gamma) i en midlertidig mappe: fagene fra fag.json,
// frister og eksamensdage fra CLAUDE.md og eksamensformerne fra README.md.
//   node tests/test_studie_semester.js
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");

const rod = fs.mkdtempSync(path.join(os.tmpdir(), "semester-test-"));
fs.mkdirSync(path.join(rod, "Scripts"));
fs.writeFileSync(path.join(rod, "Scripts", "fag.json"), JSON.stringify({
  semester: "Testsemester",
  fag: [
    { id: "alfa", kort: "Alfa", navn: "Alfa for begyndere", mappe: "Alfa", genkald: true, begreber: { ekstra_kolonne: null } },
    { id: "beta", kort: "Beta", navn: "Beta og kode", mappe: "Beta", kode: "kode",
      afleveringer: { mappe: "kode/A-opgaver", praefiks: "A", navn: "A-opgaver" } },
    { id: "gamma", kort: "Gamma", navn: "Gamma", mappe: "Gamma", farve: "#123456" },
  ],
}));
fs.writeFileSync(path.join(rod, "CLAUDE.md"), `# Testsemester

## Vigtige datoer

| Uge | Fag | Hvad |
|---|---|---|
| 41 | Beta | **A1** — onsdag 07.10 kl. 23:59 |
| 46-47 | Gamma | **Præsentation i øvelsestimen**, forudsætning for eksamen |
| 50 | Alfa | **Eksamen: skriftlig stedprøve** — torsdag 10.12.2026 kl. 09:00-11:00 |
| 1 | Gamma | **Eksamen: mundtlig** — torsdag 07.01.2027 |
| 51 | Beta | **Eksamen** (datoen er ikke kommet endnu) |

## Egen plan
`);
fs.writeFileSync(path.join(rod, "README.md"), `# Testsemester

## De tre fag trænes forskelligt

| Fag | Eksamen | Arbejdsform |
|---|---|---|
| Alfa | Skriftlig, 2 timer | Genkald |
| Beta | Kode, 4 timer | Drills |
`);
// Koden bliver liggende i studie/Scripts; KOMPAS_SEMESTER peger den på det opdigtede semester
process.env.KOMPAS_SEMESTER = rod;
const S = require(path.join(__dirname, "..", "studie", "Scripts", "semester.js"));

let fejl = 0;
const tjek = (navn, ok, detalje = "") => { if (!ok) { fejl++; console.log("FEJL", navn, detalje); } };
const vis = x => JSON.stringify(x);

// ── fagene ──
const fag = S.fag();
tjek("fagene i fag.json's rækkefølge", vis(fag.map(f => f.id)) === '["alfa","beta","gamma"]', vis(fag.map(f => f.id)));
tjek("farve efter rækkefølgen", fag[0].farve === "var(--c1)" && fag[1].farve === "var(--c2)", vis(fag.map(f => f.farve)));
tjek("et fags egen farve vinder", fag[2].farve === "#123456", fag[2].farve);
tjek("fag uden genkald har genkald false", fag[1].genkald === false && fag[2].genkald === false);
tjek("fagMed finder kun fagene med feltet", vis(S.fagMed("kode").map(f => f.id)) === '["beta"]' && vis(S.fagMed("genkald").map(f => f.id)) === '["alfa"]');
tjek("find med ukendt id giver null", S.find("delta") === null && S.find("beta").kort === "Beta");
tjek("fraKort er ligeglad med store bogstaver og mellemrum", S.fraKort(" alfa ")?.id === "alfa" && S.fraKort("—") === null);
tjek("semestrets navn fra fag.json", S.semester() === "Testsemester", S.semester());

// ── afleveringer ──
tjek("afleveringsNr finder præfikset fra fag.json", S.afleveringsNr("Husk A3 i aften") === "A3");
tjek("afleveringsNr kender ikke andre semestres præfiks", S.afleveringsNr("G1 (dart)") === null);
tjek("afleveringsNr kræver et helt ord", S.afleveringsNr("AA3 og A3x") === null);
tjek("afleveringsNr tillader ét mellemrum efter præfikset", S.afleveringsNr("se A 4 i aften") === "A 4");

// ── frister fra CLAUDE.md ──
const rækker = S.vigtigeDatoer();
tjek("Vigtige datoer har fem rækker", rækker.length === 5, String(rækker.length));
const d = r => S.deadline(r, 2026, 36);
const [a1, praes, alfaEks, gammaEks, betaEks] = rækker.map(d);
tjek("A1 er en aflevering, selvom ordet ikke står der", a1.type === "aflevering" && a1.fag === "Beta", vis(a1));
tjek("A1 får datoen fra teksten", a1.dato === "2026-10-07" && a1.tid === "23.59", vis([a1.dato, a1.tid]));
tjek("præsentation før eksamen er en præsentation", praes.type === "praesentation" && praes.fra === "2026-11-09" && praes.til === "2026-11-22", vis(praes));
tjek("Alfas eksamen", alfaEks.type === "eksamen" && alfaEks.dato === "2026-12-10" && alfaEks.tid === "09.00–11.00", vis(alfaEks));
tjek("en januar-eksamen i en efterårsplan ligger året efter", gammaEks.dato === "2027-01-07", vis(gammaEks));
tjek("en eksamen uden dato har kun ugen", betaEks.type === "eksamen" && betaEks.dato === null && betaEks.fra === "2026-12-14", vis(betaEks));

// ── eksamensdage ──
const nu = new Date(2026, 8, 1);
const eks = S.eksamensdatoer(nu);
tjek("eksamensdage for fagene med en dato", vis(Object.keys(eks).sort()) === '["alfa","gamma"]', vis(eks));
tjek("Alfas eksamensdag er lokal midnat", eks.alfa === new Date(2026, 11, 10).getTime(), String(new Date(eks.alfa)));
tjek("Gammas eksamensdag i januar", eks.gamma === new Date(2027, 0, 7).getTime(), String(new Date(eks.gamma)));

// ── eksamensformer fra README.md ──
const former = S.eksamensformer();
tjek("eksamensformerne fra README", vis(former.map(r => r.Fag)) === '["Alfa","Beta"]' && former[1].Eksamen === "Kode, 4 timer", vis(former));

// ── datoer ──
tjek("isoUge", S.isoUge(new Date(2026, 11, 10)) === 50 && S.isoUge(new Date(2027, 0, 1)) === 53);
tjek("mandagIUge", S.isoDato(S.mandagIUge(2026, 1)) === "2025-12-29" && S.isoDato(S.mandagIUge(2026, 50)) === "2026-12-07");

fs.rmSync(rod, { recursive: true, force: true });
if (fejl) { console.log(`${fejl} fejl`); process.exit(1); }
console.log("semester.js: alt ok");
