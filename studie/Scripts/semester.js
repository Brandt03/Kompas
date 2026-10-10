// Semestret ét sted: fagene, datoerne og eksamensformerne. Alle scripts i Scripts/ spørger herfra i stedet for
// at have deres egne lister, så et nyt semester er en ny fag.json plus CLAUDE.md og README.md.
//   fag.json                     hvilke fag og hvad hvert fag har (genkald, kode, afleveringer, eksamenstræning …)
//   CLAUDE.md "Vigtige datoer"   frister og eksamensdatoer
//   README.md "… trænes forskelligt"   eksamens- og arbejdsform pr. fag
// fag.json ligger i semestermappens Scripts/ (se fag.example.json).
// CommonJS, ingen afhængigheder, som resten af Scripts/.

const fs = require("fs");
const path = require("path");
const os = require("os");

// Semestermappen er KOMPAS_SEMESTER, ellers mappen over Scripts/. Semestrets egne filer (fag.json, logs,
// læst-markeringer, færdige frister) ligger i dens Scripts/, også når koden ligger et andet sted.
const hjem = s => s.replace(/^~(?=$|\/)/, os.homedir());
const ROD = path.resolve(hjem(process.env.KOMPAS_SEMESTER || path.join(__dirname, "..")));
const DATA = path.join(ROD, "Scripts");
const læs = f => { try { return fs.readFileSync(f, "utf8"); } catch { return null; } };

// ── fagene ───────────────────────────────────────────────────────────

let cache = null;
function indhold() {
  if (!cache) cache = JSON.parse(læs(path.join(DATA, "fag.json")) || '{"fag": []}');
  return cache;
}
// Alle fag i fag.json's rækkefølge. Farven er --c1, --c2 … efter rækkefølgen, medmindre faget har sin egen.
function fag() {
  return indhold().fag.map((f, i) => ({ genkald: false, begreber: null, kode: null, afleveringer: null, leetcode: null,
    eksamenstraening: null, forudsaetning: null, canvas: [], oevelse_navn: null, ...f, farve: f.farve || `var(--c${i + 1})` }));
}
const fagMed = egenskab => fag().filter(f => f[egenskab]);
const find = id => fag().find(f => f.id === id) || null;
// Fag-kolonnen i ugeplaner og CLAUDE.md skriver kortnavnet ("Alfa")
const fraKort = kort => fag().find(f => f.kort.toLowerCase() === String(kort || "").trim().toLowerCase()) || null;
const semester = () => indhold().semester || path.basename(ROD);

// ── markdown-tabeller og afsnit ──────────────────────────────────────

function tabel(src) {
  const rækker = src.split("\n").filter(l => /^\s*\|/.test(l));
  if (rækker.length < 2) return [];
  const celler = r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
  const hoved = celler(rækker[0]);
  return rækker.slice(2).map(r => Object.fromEntries(celler(r).map((c, i) => [hoved[i] || `k${i}`, c])));
}
// Teksten under "## <titel>" i en markdown-fil i semestermappen
const afsnit = (fil, titel) => (læs(path.join(ROD, fil)) || "").split(/^## /m).find(a => titel.test(a)) || "";

// ── datoer ───────────────────────────────────────────────────────────

const isoDato = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function isoUge(d) {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7));
  return Math.ceil(((t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 864e5 + 1) / 7);
}
function mandagIUge(aar, uge) {
  const jan4 = new Date(aar, 0, 4);
  const m = new Date(jan4); m.setDate(jan4.getDate() - ((jan4.getDay() + 6) % 7) + (uge - 1) * 7);
  return m;
}
const plusDage = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };

// En frist fra en tabelrække (ugeplanens Deadlines eller CLAUDE.md). hvad og note er rå tekst; eksporten laver html.
// aar er planens år og planUge dens uge: en frist i uge 1-25 i en efterårsplan (fx en januar-eksamen)
// ligger i det følgende år
function deadline(r, aar, planUge = 40) {
  const uger = (r.Uge || "").match(/\d+/g)?.map(Number) || [];
  if (uger.length && uger[0] < 26 && planUge >= 26) aar += 1;
  const hvad = r.Aktivitet || r.Hvad || "";
  const ren = hvad.replace(/\*\*|`/g, "");
  let type = "andet";
  // Rækkefølgen betyder noget: "Præsentationen afleveres" er en aflevering, og
  // "præsentation … forudsætning for eksamen" er en præsentation, ikke en eksamen
  if (/prøveeksamen/i.test(ren)) type = "proeve";
  else if (afleveringsNr(ren) || /aflever/i.test(ren)) type = "aflevering";
  else if (/præsentation/i.test(ren)) type = "praesentation";
  else if (/stedprøve|eksamen|prøve\b/i.test(ren)) type = "eksamen";
  else if (/ferie/i.test(ren)) type = "ferie";
  let fra = uger.length ? mandagIUge(aar, uger[0]) : null;
  let til = uger.length ? plusDage(mandagIUge(aar, uger[uger.length - 1]), 6) : null;
  // En præcis dato (dd.mm) i Dato-kolonnen vinder over ugen, når den ligger i ugen.
  // Et interval ("28.09-04.10", "12.-18.10") er ingen frist, bare ugen igen.
  // Uden Dato-kolonne (CLAUDE.md's "Vigtige datoer") står datoen i teksten, fx "torsdag 10.12.2026 kl. 09:00-11:00"
  const kilde = r.Dato != null ? r.Dato : ren;
  const interval = r.Dato != null && /\d\.?\s*[-–]\s*\d/.test(r.Dato);
  const præcis = interval ? null : kilde.match(/(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?(?!\d)/);
  let dato = null;
  if (præcis && fra) {
    const d = new Date(præcis[3] ? +præcis[3] : aar, +præcis[2] - 1, +præcis[1]);
    if (d >= plusDage(fra, -1) && d <= plusDage(til, 1)) dato = isoDato(d);
  }
  const t = ren.match(/kl\.\s*(\d{1,2})[:.](\d{2})(?:\s*[-–]\s*(\d{1,2})[:.](\d{2}))?/);
  const tid = t ? `${t[1].padStart(2, "0")}.${t[2]}${t[3] ? `–${t[3].padStart(2, "0")}.${t[4]}` : ""}` : null;
  return {
    uger: r.Uge || "", dato_tekst: r.Dato || null, fag: /^(—|–|-|alle)?$/i.test((r.Fag || "").trim()) ? "Alle" : r.Fag.trim(), hvad, note: r.Bemærkning || null,
    type, fra: fra && isoDato(fra), til: til && isoDato(til), dato, tid,
  };
}

// Mønstret for en nummereret aflevering ud fra præfikserne i fag.json: "G" finder G1, "Opgave" finder Opgave 3
// (nummeret står lige efter præfikset eller efter ét mellemrum). null, når intet fag har afleveringer.
function afleveringsMoenster() {
  const p = fagMed("afleveringer").map(f => f.afleveringer.praefiks.trim()).filter(Boolean);
  return p.length ? `\\b(?:${p.map(x => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})\\s?\\d+\\b` : null;
}
// Afleveringen i en tekst ("G1", "Opgave 3"), eller null
function afleveringsNr(tekst) {
  const m = afleveringsMoenster();
  return m ? (String(tekst).match(new RegExp(m)) || [])[0] || null : null;
}

const vigtigeDatoer = () => tabel(afsnit("CLAUDE.md", /^Vigtige datoer/));
const egenPlan = () => tabel(afsnit("CLAUDE.md", /^Egen plan/));
const eksamensformer = () => tabel(afsnit("README.md", /trænes forskelligt/i));

// Eksamensdagen pr. fag-id (ms, lokal midnat) fra "Vigtige datoer". Et fag uden eksamen med dato er ikke med.
function eksamensdatoer(nu = new Date()) {
  const ud = {};
  for (const r of vigtigeDatoer()) {
    const d = deadline(r, nu.getFullYear(), isoUge(nu)), f = fraKort(d.fag);
    if (f && d.type === "eksamen" && d.dato && !(f.id in ud)) {
      const [y, m, dag] = d.dato.split("-").map(Number);
      ud[f.id] = new Date(y, m - 1, dag).getTime();
    }
  }
  return ud;
}

module.exports = { ROD, DATA, fag, fagMed, find, fraKort, semester, tabel, afsnit, isoDato, isoUge, mandagIUge, plusDage,
  deadline, afleveringsMoenster, afleveringsNr, vigtigeDatoer, egenPlan, eksamensformer, eksamensdatoer };
