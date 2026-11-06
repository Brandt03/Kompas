// Selvstudie: sessionerne fra stopuret på siden Selvstudie og dem, du selv har tilføjet eller rettet, i Scripts/sessioner.json.
// Studie-serveren skriver filen (kompas-server.js, /stopur og /session); eksporten læser den (kompas-eksport.js).
//
//   { fra: "ÅÅÅÅ-MM-DD",                       dagen, logningen begyndte (før den er selvstudiet ukendt, ikke 0)
//     igang: { id, fag, pomodoro, stykker } | null,   stopuret, mens det kører eller holder pause
//     sessioner: [{ id, fag, stykker: [[start, slut], …], kilde, pomodoro, aktivitet, note }],
//     afviste: ["f-…"] }                      forslag, du har afvist, så de ikke kommer igen
//
// En session er et fag og ét eller flere stykker: en pause står som mellemrummet mellem to stykker, og kun stykkerne
// tæller som selvstudie. Tiderne er lokal tid med offset (ÅÅÅÅ-MM-DDTtt:mm:ss+01:00). Et åbent stykke i igang har slut null.
// Med Pomodoro slutter et stykke af sig selv efter arbejde-minutterne, også når ingen trykker pause (slutFor).
// kilde: "stopur", "tilføjet" (skrevet ind bagefter), "forslag" (et forslag, du har godkendt) eller "caltask" (flyttet
// fra CalTask).
const fs = require("fs");
const path = require("path");
const { DATA } = require("./semester");

const FIL = path.join(DATA, "sessioner.json");
const POMODORO = { arbejde: 25, pause: 5 };  // minutter, som Athenify; studiemaal.pomodoro i fag.json overstyrer

// Filen, som den er. Mangler den, er der intet logget endnu. Kan den ikke læses (fx en fil, der kun ligger i
// skyen), kastes fejlen, så serveren aldrig skriver en tom log oven i den rigtige.
function læs(fil = FIL) {
  let tekst;
  try { tekst = fs.readFileSync(fil, "utf8"); } catch (e) { if (e.code === "ENOENT") return { fra: null, igang: null, sessioner: [], afviste: [] }; throw e; }
  const d = JSON.parse(tekst);
  return { ...d, fra: d.fra || null, igang: d.igang || null, sessioner: Array.isArray(d.sessioner) ? d.sessioner : [],
    afviste: Array.isArray(d.afviste) ? d.afviste : [] };
}

const ms = s => Date.parse(s);
// Hvor et åbent stykke slutter nu: med Pomodoro højst arbejde-minutter efter starten
const slutFor = (stykke, pomodoro, nu = Date.now()) => {
  if (stykke[1]) return ms(stykke[1]);
  return pomodoro ? Math.min(nu, ms(stykke[0]) + pomodoro.arbejde * 6e4) : nu;
};
// Timerne i en session (eller igang, med de åbne stykker til nu)
const timer = (s, nu = Date.now()) => s.stykker.reduce((a, st) => a + Math.max(0, slutFor(st, s.pomodoro, nu) - ms(st[0])), 0) / 36e5;
const start = s => s.stykker[0][0];
const slut = s => s.stykker.at(-1)[1];

// ── Forslag ─────────────────────────────────────────────────────────
// Selvstudie, du ikke har logget, foreslået ud fra tidspunkterne på dine svar (Dagens kort, Genkald, drills …), også dem
// fra telefonen. Intet gemmes, før du godkender. Svar med højst PAUSE minutter imellem hører sammen; hvert svar får tiden
// siden det forrige, og det første den mediane tid mellem svarene (den tid, du brugte på det første kort, kendes ikke).
// Den tid, der allerede er logget (sessionerne og stopuret), trækkes fra. Et forslag kommer først, når der er gået PAUSE
// minutter efter det sidste svar, og kun med mindst MINDST minutter. Svar i flere fag giver én del pr. fag.
// Sprog bruger samme regler (sprog/kerne.js, kopieret, ikke delt).
const FORSLAG = { pause_min: 10, mindst_min: 5, dage: 14 };
// svar: [{ t (ms), fag, type }]; d: loggen (sessioner, igang, afviste)
function forslag(svar, d, nu = Date.now()) {
  const pause = FORSLAG.pause_min * 6e4, afviste = new Set(d.afviste || []), fra = nu - FORSLAG.dage * 864e5;
  const logget = [...d.sessioner, ...(d.igang ? [d.igang] : [])].flatMap(s => s.stykker.map(st => [ms(st[0]), slutFor(st, s.pomodoro, nu)]));
  const grupper = [];
  for (const x of svar.filter(x => x.t >= fra && x.t <= nu).sort((a, b) => a.t - b.t)) {
    const g = grupper.at(-1);
    if (g && x.t - g.at(-1).t <= pause) g.push(x); else grupper.push([x]);
  }
  const ud = [];
  for (const g of grupper) {
    const id = `f-${new Date(g[0].t).toISOString()}`;
    if (g.length < 2 || nu - g.at(-1).t <= pause || afviste.has(id)) continue;
    const huller = g.slice(1).map((x, i) => x.t - g[i].t).sort((a, b) => a - b), median = huller[Math.floor((huller.length - 1) / 2)];
    // Hvert svars tid minus det, der er logget, og stykker i træk i samme fag sat sammen
    const dele = new Map();
    g.forEach((x, i) => {
      let stykker = [[i ? g[i - 1].t : x.t - median, x.t]];
      for (const [a, b] of logget) stykker = stykker.flatMap(([c, e]) => b <= c || a >= e ? [[c, e]] : [[c, a], [b, e]].filter(([y, z]) => z > y));
      const del = dele.get(x.fag) || dele.set(x.fag, []).get(x.fag);
      for (const st of stykker) if (del.length && del.at(-1)[1] === st[0]) del.at(-1)[1] = st[1]; else del.push([...st]);
    });
    const timer = st => st.reduce((a, [c, e]) => a + e - c, 0) / 36e5;
    const ds = [...dele].map(([fag, st]) => ({ fag, stykker: st, timer: timer(st) })).filter(x => x.stykker.length);
    if (ds.reduce((a, x) => a + x.timer, 0) * 60 < FORSLAG.mindst_min) continue;
    ud.push({ id, start: Math.min(...ds.map(x => x.stykker[0][0])), slut: Math.max(...ds.map(x => x.stykker.at(-1)[1])), svar: g.length,
      typer: [...new Set(g.map(x => x.type))], dele: ds });
  }
  return ud;
}

module.exports = { FIL, POMODORO, FORSLAG, læs, slutFor, timer, start, slut, forslag };
