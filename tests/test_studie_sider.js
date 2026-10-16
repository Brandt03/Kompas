// Siderne i studie/Scripts/kompas/: ugen, Ugeoverblik og Fag åbner på (visUge i studie.js). studie.js køres i en tom
// browser-attrap på kompas.localhost, så den ikke registrerer telefonens service worker.
//   node tests/test_studie_sider.js
"use strict";
// Datoerne nedenfor er lokal tid i København, uanset hvor testen køres
process.env.TZ = "Europe/Copenhagen";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SIDER = path.join(__dirname, "..", "studie", "Scripts", "kompas");
const kontekst = vm.createContext({ location: { hostname: "kompas.localhost" }, Date });
vm.runInContext(fs.readFileSync(path.join(SIDER, "studie.js"), "utf8"), kontekst);
const visUge = kontekst.visUge;

let fejl = 0;
const tjek = (navn, ok, detalje = "") => { if (!ok) { fejl++; console.log("FEJL", navn, detalje); } };
const vis = x => JSON.stringify(x);
const uge = (d, mandag, nr, naeste) => { const v = visUge(d); tjek(`${d.toDateString()} viser uge ${nr}`, v.mandag === mandag && v.uge === nr && v.naeste === naeste, vis(v)); };

// ── weekenden hører til næste uge ──
uge(new Date(2026, 9, 5, 8, 0), "2026-10-05", 41, false);     // mandag
uge(new Date(2026, 9, 9, 23, 59), "2026-10-05", 41, false);   // fredag aften
uge(new Date(2026, 9, 10, 0, 30), "2026-10-12", 42, true);    // lørdag lige efter midnat (i UTC stadig fredag)
uge(new Date(2026, 9, 11, 23, 30), "2026-10-12", 42, true);   // søndag aften (i UTC allerede mandag)
uge(new Date(2026, 9, 12, 9, 0), "2026-10-12", 42, false);    // mandagen efter: samme uge som i weekenden
// ── årsskiftet og sommertid ──
uge(new Date(2026, 11, 26, 12, 0), "2026-12-28", 53, true);   // 2026 har uge 53
uge(new Date(2027, 0, 2, 12, 0), "2027-01-04", 1, true);
uge(new Date(2026, 2, 28, 12, 0), "2026-03-30", 14, true);    // lørdag før sommertid

// ── begge sider bruger den, og ingen har sin egen weekendregel ──
for (const side of ["index.html", "fag.html"]) {
  const tekst = fs.readFileSync(path.join(SIDER, side), "utf8");
  tjek(`${side} bruger visUge`, /visUge\(\)/.test(tekst));
  tjek(`${side} har ingen egen weekendregel`, !/\[0, 6\]\.includes|getDay\(\)\s*(===|==)\s*[06]/.test(tekst));
}
tjek("Fag åbner ikke på eksportens aktuelle uge", !/planUge = d\.aktuel_uge/.test(fs.readFileSync(path.join(SIDER, "fag.html"), "utf8")));

if (fejl) { console.log(`${fejl} fejl`); process.exit(1); }
console.log("siderne: alt ok");
