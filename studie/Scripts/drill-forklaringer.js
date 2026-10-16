// Finder tjek(...) i kodefagets Drills/kap*.js (fx Gamma/vscode/Drills), der mangler en forklaring i forklaringer/<drill>.md,
// og viser for hvert: beskrivelsen (som den skal stå i "## "-overskriften), udtrykket og hvad
// JavaScript faktisk giver. Læser kun; skriver intet og viser aldrig dine gæt.
//
//   node Scripts/drill-forklaringer.js           → kun de manglende
//   node Scripts/drill-forklaringer.js --alle    → alle tjek

const fs = require("fs");
const path = require("path");
const Module = require("module");

const S = require("./semester");
// Kodefaget i fag.json har drillene i <mappe>/<kode>/Drills
const KODEFAG = S.fagMed("kode")[0];
if (!KODEFAG) { console.log("Intet fag har kode i fag.json, så der er ingen drills."); process.exit(0); }
const DRILLS = path.join(S.ROD, KODEFAG.mappe, KODEFAG.kode, "Drills");
const alle = process.argv.includes("--alle");
const noegle = (s) => s.replace(/\s*←.*$/, "").replace(/\s+/g, " ").trim();

function vis(v) {
  if (v === undefined) return "undefined";
  if (typeof v === "number" && !Number.isFinite(v)) return String(v);
  if (typeof v === "function") return "[funktion]";
  try { return JSON.stringify(v); } catch { return String(v); }
}

// Drill-filen køres med en tjek.js, der kun noterer udtryk og resultat
const fundet = [];
const ægte = require(path.join(DRILLS, "tjek.js"));
const load = Module._load;
Module._load = function (req, parent, ...r) {
  if (/(^|\/)tjek(\.js)?$/.test(req)) return {
    TOM: ægte.TOM, opsummer() {}, forvent() {},
    tjek(beskrivelse, udtryk) {
      let v;
      try { v = udtryk(); } catch (e) { v = `${e.constructor.name}: ${e.message}`; }
      fundet.push({ beskrivelse: noegle(beskrivelse), udtryk: udtryk.toString().replace(/^\(\)\s*=>\s*/, ""), js: vis(v) });
    },
  };
  return load.call(this, req, parent, ...r);
};

let mangler = 0;
for (const fil of fs.readdirSync(DRILLS).filter((n) => /^kap\d+.*\.js$/.test(n)).sort()) {
  const md = path.join(DRILLS, "forklaringer", fil.replace(/\.js$/, ".md"));
  const har = new Set(fs.existsSync(md)
    ? fs.readFileSync(md, "utf8").split(/^## /m).slice(1).map((a) => noegle(a.split("\n")[0])) : []);
  fundet.length = 0;
  const log = console.log; console.log = () => {};
  try { require(path.join(DRILLS, fil)); } catch (e) { console.log = log; console.log(`## ${fil}: kan ikke køres (${e.message})\n`); continue; }
  console.log = log;
  const vist = fundet.filter((t) => alle || !har.has(t.beskrivelse));
  mangler += fundet.filter((t) => !har.has(t.beskrivelse)).length;
  if (!vist.length) continue;
  console.log(`######## ${fil} → forklaringer/${path.basename(md)}${fs.existsSync(md) ? "" : " (findes ikke endnu)"}\n`);
  for (const t of vist) console.log(`## ${t.beskrivelse}\n${t.udtryk}\n=> ${t.js}\n`);
}
console.log(`${mangler} tjek mangler en forklaring.`);
