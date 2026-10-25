// Siderne i studie/Scripts/kompas/: ugen, Ugeoverblik og Fag åbner på (visUge i studie.js), og hvilken køreplan de viser i
// weekenden (koereplan), kapitlet Drills åbner på, og hvad På farten har med uden net. studie.js køres i en tom
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

// ── sidernes egne scripts kan læses (en fejl her tømmer hele siden) ──
for (const side of fs.readdirSync(SIDER).filter(n => n.endsWith(".html"))) {
  const js = [...fs.readFileSync(path.join(SIDER, side), "utf8").matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).join("\n;\n");
  try { new vm.Script(js, { filename: side }); } catch (e) { tjek(`${side} kan læses som JavaScript`, false, e.message); }
}

// ── weekenden: til næste uges køreplan er skrevet (søndag kl. 18), viser siderne sidste uges med et mærke ──
const koereplan = kontekst.koereplan;
const plan = (uge, fra) => ({ uge, fra });
const P42 = plan(42, "2026-10-12"), P43 = plan(43, "2026-10-19"), P44 = plan(44, "2026-10-26");
const kp = (navn, planer, uge, d, forventet, sidste) => {
  const k = koereplan(planer, uge, visUge(d));
  tjek(navn, k.plan === forventet && k.sidste === sidste, vis({ uge: k.plan?.uge, sidste: k.sidste }));
};
kp("lørdag uden uge 44: sidste uges (43) med mærket", [P42, P43], 44, new Date(2026, 9, 24, 12, 0), P43, true);
kp("søndag aften uden uge 44: stadig sidste uges", [P42, P43], 44, new Date(2026, 9, 25, 23, 30), P43, true);
kp("søndag, når uge 44 er skrevet: uge 44 uden mærke", [P42, P43, P44], 44, new Date(2026, 9, 25, 18, 30), P44, false);
kp("onsdag: næste uge uden køreplan låner ikke denne uges", [P42, P43], 44, new Date(2026, 9, 21, 12, 0), null, false);
kp("lørdag, Ugen før-knappen: uge 42 som den er", [P42, P43], 42, new Date(2026, 9, 24, 12, 0), P42, false);
kp("lørdag uden sidste uges køreplan: intet (heller ikke en ældre)", [P42], 44, new Date(2026, 9, 24, 12, 0), null, false);
const P53 = plan(53, "2026-12-28");
kp("årsskiftet: lørdag 2. jan. uden uge 1 låner uge 53", [P53], 1, new Date(2027, 0, 2, 12, 0), P53, true);
tjek("mærket siger, hvornår den nye kommer", /sidste uges køreplan · ny kommer søndag kl\. 18/.test(vm.runInContext("SIDSTE_UGES", kontekst)));
for (const side of ["index.html", "fag.html"]) {
  const tekst = fs.readFileSync(path.join(SIDER, side), "utf8");
  tjek(`${side} henter køreplanen gennem koereplan og viser mærket`, /koereplan\(/.test(tekst) && /SIDSTE_UGES/.test(tekst));
}
tjek("Fag kalder ikke eksportens aktuelle uge for denne uge", !/p\.uge === S\.aktuel_uge \? " · denne uge"/.test(fs.readFileSync(path.join(SIDER, "fag.html"), "utf8")));

// ── Træning → Drills åbner på første kapitel med ugættede, ikke på et husket ──
{
  const tekst = fs.readFileSync(path.join(SIDER, "genkald.html"), "utf8");
  const linje = tekst.match(/^const startKap = .*$/m);
  tjek("genkald.html har startKap", !!linje);
  if (linje) {
    const startKap = vm.runInNewContext(linje[0] + "; startKap");
    const kap = (...st) => ({ tjek: st.map(status => ({ status })) });
    tjek("kap. 1 gættet, kap. 4 ugættet: åbner på kap. 4", startKap([kap("rigtig", "forkert"), kap("rigtig"), kap("vscode"), kap("tom", "rigtig")]) === 3);
    tjek("alt gættet: åbner på det første", startKap([kap("rigtig"), kap("forkert")]) === 0);
  }
  tjek("Drills husker ikke kapitlet mellem visninger", !/dKap\s*[=}]/.test((tekst.match(/genkald-valg[^\n]*/g) || []).join("\n")) && !/\{ gFag, bFag, dKap \}/.test(tekst));
}

// ── På farten: USB-noter står på Overblik og kan åbnes uden net ──
{
  const mobil = fs.readFileSync(path.join(SIDER, "mobil.html"), "utf8"), sw = fs.readFileSync(path.join(SIDER, "mobil-sw.js"), "utf8");
  const overblik = mobil.slice(mobil.indexOf("const OVERBLIK"), mobil.indexOf("function renderOverblik"));
  tjek("Overblik har USB-noter", /\["\/studie\/usb\.html", "hard-drive", "USB-noter"/.test(overblik));
  const varm = mobil.slice(mobil.indexOf("function varm"), mobil.indexOf("function iKoe"));
  tjek("pakken henter USB-noter og vurderingerne med", varm.includes('"/studie/usb.html"') && varm.includes('"/studie/api/usb-vurdering"'));
  const liste = navn => vm.runInNewContext(sw.match(new RegExp(`const ${navn} = (\\[[\\s\\S]*?\\]);`))[1]);
  tjek("service workeren gemmer usb.html", liste("SIDER").includes("/studie/usb.html"));
  tjek("service workeren gemmer /studie/api/usb-vurdering som data", liste("DATA").includes("/studie/api/usb-vurdering"));
}

// ── På farten: en forelæsning eller øvelse, der er hentet én gang, åbner uden net ──
// mobil-sw.js køres med et lager i hukommelsen og et net, der kan slås fra (Mac'en sover).
async function pensumPaaTelefonen() {
  const lager = new Map(), lyt = {};
  let net = true, kald = 0;
  const c = { match: async p => lager.get(p), put: async (p, r) => { lager.set(p, r); }, add: async () => {} };
  vm.runInContext(fs.readFileSync(path.join(SIDER, "mobil-sw.js"), "utf8"), vm.createContext({
    self: { addEventListener: (t, f) => { lyt[t] = f; } }, caches: { open: async () => c }, location: { origin: "https://mac.ts.net" },
    URL, Response, Promise, setTimeout: () => 0,
    fetch: async p => { kald++; if (!net) throw new TypeError("Mac'en svarer ikke"); return new Response(`PDF ${p}`); } }));
  const aabn = sti => { let svar; lyt.fetch({ request: { method: "GET", url: "https://mac.ts.net" + sti }, respondWith: p => { svar = p; }, waitUntil() {} }); return svar; };
  const fil = "/studie/api/pensum/gamma/Forel%C3%A6sninger/20270315_FL5_Lorem%20ipsum.pdf";

  net = false; let r = await aabn(fil);
  tjek("ikke hentet og uden net: siden siger, at filen ikke er på telefonen", r.status === 503 && /ligger ikke på telefonen/.test(await r.text()), r.status);
  net = true; r = await aabn(fil);
  tjek("med net: filen hentes fra Mac'en", r.ok && (await r.text()) === `PDF ${fil}`);
  net = false; const foer = kald; r = await aabn(fil);
  tjek("uden net bagefter: filen åbner fra telefonen", r.ok && (await r.text()) === `PDF ${fil}`);
  net = true; await aabn(fil);
  tjek("en hentet fil hentes ikke igen", kald === foer, kald - foer);
}

pensumPaaTelefonen().catch(e => tjek("På farten: pensum", false, e.stack)).then(() => {
  if (fejl) { console.log(`${fejl} fejl`); process.exit(1); }
  console.log("siderne: alt ok");
});
