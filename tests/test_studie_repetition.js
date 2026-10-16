// Studies gentagelsesplan (FSRS ud fra loggen) og telefonens sync uden dubletter.
// Planen hentes direkte fra serveren; sync testes mod en server på en tom, midlertidig semestermappe.
//   node tests/test_studie_repetition.js
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const SERVER = path.join(__dirname, "..", "studie", "Scripts", "kompas-server.js");
const src = fs.readFileSync(SERVER, "utf8");
const t0 = Date.parse("2026-09-01T10:00:00Z");
// Planen hentes fra serveren. Eksamensdagene læser serveren fra CLAUDE.md; her erstattes opslaget, så `eksamen`
// giver "alfa" en eksamensdag
const EKS_KODE = /let eksamenCache = [\s\S]*?\nfunction eksamensdage\(\) \{[\s\S]*?\n\}\n/;
if (!EKS_KODE.test(src)) throw new Error("fandt ikke eksamensdage() i serveren");
const lav = (eksamen = null) => new Function(`${src.slice(src.indexOf("const NYE_PR_DAG ="), src.indexOf("async function repetitionsKort"))
  .replace(EKS_KODE, `function eksamensdage() { return ${eksamen ? `{ alfa: ${eksamen} }` : "{}"}; }\n`)};
  return { planlæg, hændelser, husker, dageTil, W, DAG, MÅL, MÅL_EKSAMEN };`)();
const { planlæg, hændelser, husker, dageTil, W, DAG, MÅL, MÅL_EKSAMEN } = lav();
let fejl = 0;
const tjek = (navn, ok, detalje = "") => { if (!ok) { fejl++; console.log("FEJL", navn, detalje); } };

// ── planen ──
const efter = (dage, g) => ({ t: t0 + dage * DAG, res: ["blankt", "halvt", "sad", "sad"][g - 1], g });
const dageTilForfald = p => (p.forfald - p.sidst) / DAG;

// FSRS' definition: stabiliteten er antallet af dage, til du kan kortet med 90 % sandsynlighed
tjek("husker(s, s) er 90 %", Math.abs(husker(7, 7) - 0.9) < 1e-12 && Math.abs(husker(30, 30) - 0.9) < 1e-12);

// Første gennemgang: stabiliteten er standardparameteren for karakteren, og intervallet er den, rundet (mindst 1 dag)
for (const [g, dage] of [[1, 1], [2, 1], [3, 2], [4, 8]]) {
  const p = planlæg([efter(0, g)]);
  tjek(`første gang, karakter ${g}`, p.s === W[g - 1] && dageTilForfald(p) === dage, JSON.stringify(p));
}

// Til tiden: sad igen og igen giver stadig længere intervaller
let hs = [efter(0, 3)], forrige = 0, voksende = true;
for (let i = 0; i < 5; i++) {
  const p = planlæg(hs), d = dageTilForfald(p);
  if (d <= forrige) voksende = false;
  forrige = d;
  hs.push(efter((hs.at(-1).t - t0) / DAG + d, 3));
}
tjek("sad til tiden giver voksende intervaller", voksende, String(forrige));

// Efter samme historik: let > sad > halvt > blankt, og blankt sænker stabiliteten
const basis = [efter(0, 3), efter(2, 3)];
const efterKarakter = g => planlæg([...basis, efter(12, g)]);
const [b, h, sd, l] = [1, 2, 3, 4].map(efterKarakter);
tjek("let > sad > halvt > blankt", dageTilForfald(l) > dageTilForfald(sd) && dageTilForfald(sd) > dageTilForfald(h) &&
  dageTilForfald(h) >= dageTilForfald(b), JSON.stringify([b, h, sd, l].map(dageTilForfald)));
tjek("blankt sænker stabiliteten", b.s < planlæg(basis).s, JSON.stringify([b.s, planlæg(basis).s]));

// Eksamen mellem kortets 95 %- og 90 %-punkt: kortet kommer, når det falder til 95 %, så det sidder på eksamensdagen.
// Et fag uden eksamen følger 90 %.
const lang = [efter(0, 4), efter(8, 4)], uden = planlæg(lang);
const d95 = Math.round(dageTil(uden.s, MÅL_EKSAMEN)), d90 = Math.round(dageTil(uden.s, MÅL));
const eksDag = uden.sidst + Math.floor((d95 + d90) / 2) * DAG;
const medEks = lav(eksDag).planlæg(lang, "alfa"), udenEks = lav(eksDag).planlæg(lang, "beta");
tjek("eksamen lige efter 95 %-punktet", d95 < d90, JSON.stringify([d95, d90]));
tjek("med eksamen kommer kortet ved 95 %", dageTilForfald(medEks) === d95 && medEks.forfald <= eksDag, JSON.stringify([dageTilForfald(medEks), d95]));
tjek("uden eksamen følger kortet 90 %", dageTilForfald(udenEks) === d90, JSON.stringify([dageTilForfald(udenEks), d90]));

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
  console.log("FSRS-planen og sync uden dubletter opførte sig rigtigt");
})();
