// Studies gentagelsesplan (intervaller ud fra loggen) og telefonens sync uden dubletter.
// Planen hentes direkte fra serveren; sync testes mod en server på en tom, midlertidig semestermappe.
//   node tests/test_studie_repetition.js
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const SERVER = path.join(__dirname, "..", "studie", "Scripts", "kompas-server.js");
const src = fs.readFileSync(SERVER, "utf8");
const kode = src.slice(src.indexOf("const INTERVAL ="), src.indexOf("async function repetitionsKort"));
const { planlæg, hændelser, INTERVAL, DAG } = new Function(`${kode}; return { planlæg, hændelser, INTERVAL, DAG };`)();
let fejl = 0;
const tjek = (navn, ok, detalje = "") => { if (!ok) { fejl++; console.log("FEJL", navn, detalje); } };

// ── planen ──
const t0 = Date.parse("2026-09-01T10:00:00Z");
const efter = (dage, res) => ({ t: t0 + dage * DAG, res });

// ✓ i træk giver 3, 7, 21, 60 og 120 dage, og derefter bliver det ved 120
let hs = [], dag = 0;
const forventet = [3, 7, 21, 60, 120, 120];
forventet.forEach((interval, i) => {
  hs.push(efter(dag, "sad"));
  const p = planlæg(hs);
  tjek(`✓ nr. ${i + 1}`, p.niveau === i + 1 && p.forfald === t0 + (dag + interval) * DAG, JSON.stringify(p));
  dag += interval;
});
tjek("intervallerne er dem, README'en lover", JSON.stringify(INTERVAL) === "[3,7,21,60,120]");

// ~ trækker ét niveau ned og giver 2 dage; ✗ starter forfra med 1 dag, og næste ✓ giver 3 dage igen
hs = [efter(0, "sad"), efter(3, "sad"), efter(10, "halvt")];
let p = planlæg(hs);
tjek("~ efter to ✓", p.niveau === 1 && p.forfald === t0 + 12 * DAG, JSON.stringify(p));
hs.push(efter(12, "blankt"));
p = planlæg(hs);
tjek("✗ nulstiller", p.niveau === 0 && p.forfald === t0 + 13 * DAG, JSON.stringify(p));
hs.push(efter(13, "sad"));
p = planlæg(hs);
tjek("✓ efter ✗ giver 3 dage", p.niveau === 1 && p.forfald === t0 + 16 * DAG, JSON.stringify(p));

// Et rigtigt drill-gæt lige efter et forkert er set i facit og tæller ikke som husket; et døgn senere tæller det
const iso = d => new Date(t0 + d * DAG).toISOString();
const H = hændelser([
  { tid: iso(0), type: "drill", noegle: "kap01.js#a", rigtig: false },
  { tid: iso(0.01), type: "drill", noegle: "kap01.js#a", rigtig: true },
  { tid: iso(2), type: "drill", noegle: "kap01.js#a", rigtig: true },
  { tid: iso(0), type: "genkald", noegle: "alfa/genkald-uge1.md#1", mark: "✓" },
  { tid: iso(1), type: "genkald", noegle: "alfa/genkald-uge1.md#1" },   // svar uden markering ændrer ikke planen
]);
tjek("rigtigt gæt lige efter forkert tæller ikke", JSON.stringify(H["drill:kap01.js#a"].map(h => h.res)) === '["blankt","sad"]',
  JSON.stringify(H["drill:kap01.js#a"]));
tjek("kun markerede genkald tæller", H["genkald:alfa/genkald-uge1.md#1"].length === 1);

// ── sync mod en midlertidig server ──
const PORT = 8790 + Math.floor(Math.random() * 9);
const rod = fs.mkdtempSync(path.join(os.tmpdir(), "studie-test-"));
fs.mkdirSync(path.join(rod, "Scripts"));
const server = spawn(process.execPath, [SERVER], { stdio: ["ignore", "ignore", "pipe"],
  env: { ...process.env, KOMPAS_SEMESTER: rod, STUDIE_PORT: String(PORT), STUDIE_EKSPORT_UD: path.join(rod, "ud") } });
let log = ""; server.stderr.on("data", d => { log += d; });

async function sync(poster) {
  const r = await fetch(`http://127.0.0.1:${PORT}/studie/api/sync`, { method: "POST", body: JSON.stringify({ poster }),
    headers: { Host: `127.0.0.1:${PORT}`, Origin: "https://kompas.localhost", "Content-Type": "application/json" } });
  return (await r.json()).resultater;
}
const post = (id, d) => ({ id, tid: iso(d), type: "repetition", data: { noegle: "drill:kap01.js#a", mark: "✓", sikkerhed: "sikker" } });

(async () => {
  try {
    for (let i = 0; i < 50 && !log.includes("Studie-API"); i++) await new Promise(r => setTimeout(r, 100));
    // Samme id to gange i én sending, og hele sendingen igen (svaret nåede ikke tilbage sidst)
    const første = await sync([post("svar-0001-aaaa", 1), post("svar-0001-aaaa", 1), post("svar-0002-bbbb", 2)]);
    const anden = await sync([post("svar-0001-aaaa", 1), post("svar-0002-bbbb", 2)]);
    const linjer = fs.readFileSync(path.join(rod, "Scripts", "genkald-log.jsonl"), "utf8").trim().split("\n").map(l => JSON.parse(l));
    tjek("to svar gemt én gang hver", linjer.length === 2, `${linjer.length} linjer`);
    tjek("dublet i samme sending", første[0].ok && !første[0].allerede && første[1].allerede === true, JSON.stringify(første));
    tjek("sendt igen", anden.every(r => r.ok && r.allerede), JSON.stringify(anden));
    tjek("tidspunktet er det, du svarede", linjer[0].tid === iso(1), linjer[0].tid);
    const ugyldig = await sync([{ tid: iso(1), type: "repetition", data: {} }]);
    tjek("post uden id afvises", ugyldig[0].ok === false, JSON.stringify(ugyldig));
  } catch (e) { fejl++; console.log("FEJL", e.message, log); }
  finally {
    server.kill();
    fs.rmSync(rod, { recursive: true, force: true });
  }
  if (fejl) { console.log(`${fejl} fejl`); process.exit(1); }
  console.log("Gentagelsesplanen og sync uden dubletter opførte sig rigtigt");
})();
