// Sprog: fælles kerne for serveren (server.js) og rutinens kommandoer (sprog.js).
//
// Data ligger i data/ (eller SPROG_DATA), uden for git; bin/backup-data.sh i Kompas tager en kopi hver dag.
//   sprog.json   de fire sprog: rolle (aktiv, vedligehold, studie), nye kort pr. dag, niveau. Findes den ikke, gælder STANDARD
//   kort.json    alle kort. Kun rutinen tilføjer kort (sprog.js tilfoej); serveren læser dem
//   log.jsonl    dine svar: karakteren 1-4 og det, du skrev. Repetitionen regnes herfra; der er ingen anden tilstand
//   tekster/     ugens tekst (<uge>.json, fx 2026-W43.json) med rutinens feedback på dit svar
//   regler.json  sprogreglerne (Regler), som kort kan pege på med `regel`; kun rutinen skriver dem (sprog.js regel)
//   sessioner.json  tiden på sprog: de forslag ud fra dine svar, du har godkendt, og dem, du har afvist (se Tid nedenfor)
// Eksamensdatoerne læses fra Studies eksport (~/.kompas/studie/studie.json, eller SPROG_STUDIE_JSON); kun læsning.
// Serveren skriver kun det, du selv taster eller klikker (log.jsonl og sessioner.json). Alt andet skriver rutinen gennem sprog.js.
// CommonJS, ingen afhængigheder, som Studie-serveren.
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");

const DATA = path.resolve(process.env.SPROG_DATA || path.join(__dirname, "data"));
const FIL = { sprog: path.join(DATA, "sprog.json"), kort: path.join(DATA, "kort.json"), log: path.join(DATA, "log.jsonl"), tekster: path.join(DATA, "tekster"),
  regler: path.join(DATA, "regler.json"), sessioner: path.join(DATA, "sessioner.json") };

// Rollerne: aktiv (bygges op: flest nye kort og ugens tekst), vedligehold (holdes ved lige: få nye kort),
// pause (ingen nye kort; kortene bliver liggende), studie (dansk og engelsk: kort af dine egne fejl og fagsprog).
// Standarden: spansk er aktivt, tysk holdes ved lige. sprog.js aktivt og rolle skifter, når brugeren beder om det.
// Niveauet sættes af rutinen ud fra niveautesten (sprog.js niveau), aldrig på forhånd.
const STANDARD = {
  aktivt: "es",
  sprog: {
    es: { navn: "Spansk", stemme: "es-ES", rolle: "aktiv", nye_pr_dag: 3, fokus: "rejse og hverdag", niveau: null, niveau_note: null, niveau_sat: null },
    de: { navn: "Tysk", stemme: "de-DE", rolle: "vedligehold", nye_pr_dag: 1, fokus: "rejse og hverdag", niveau: null, niveau_note: null, niveau_sat: null },
    da: { navn: "Dansk", stemme: "da-DK", rolle: "studie", nye_pr_dag: 1, fokus: "skriftlig præcision i studiet", niveau: null, niveau_note: null, niveau_sat: null },
    en: { navn: "Engelsk", stemme: "en-GB", rolle: "studie", nye_pr_dag: 1, fokus: "akademisk og fagligt engelsk", niveau: null, niveau_note: null, niveau_sat: null },
  },
};
// Rækkefølgen i Dagens kort: ét sprog ad gangen (ikke blandet), det aktive først. Spansk og tysk lige efter
// hinanden blander ordene sammen, så vedligeholdssproget kommer sidst, efter dansk og engelsk.
const ROLLE_ORDEN = { aktiv: 0, studie: 1, vedligehold: 2, pause: 3 };
const ROLLER = Object.keys(ROLLE_ORDEN);
// frase: dansk → sproget (du siger det selv). ret: ret en sætning (dine egne fejl). ord: brug et ord i en sætning.
// udfyld: en sætning med ___, hvor du sætter det manglende ord ind (øver en regel). test: niveautesten; besvares én
// gang og kommer ikke igen.
const TYPER = ["frase", "ret", "ord", "udfyld", "test"];
const NIVEAUER = ["A1", "A2", "B1", "B2", "C1", "C2"];
const DAG = 864e5;
// Højst så mange forfaldne kort om dagen (ca. 6-8 minutter); nye kort og niveautesten kommer oveni
const MAKS_FORFALDNE = 15;
// Et kort "sidder", når du med 90 % sandsynlighed stadig kan det om tre uger (samme grænse som Studie)
const LÆRT = 21;
// Eksamensperiode: fra 14 dage før en eksamen i Studie til og med eksamensdagen kommer der ingen nye sprogkort, kun
// gentagelse, så studiet får tiden
const EKSAMEN_DAGE_FØR = 14;
const STUDIE_JSON = process.env.SPROG_STUDIE_JSON || path.join(os.homedir(), ".kompas", "studie", "studie.json");

const læs = f => fs.readFileSync(f, "utf8");
// Atomisk: et unikt midlertidigt navn ved siden af filen, så serveren aldrig læser en halvt skrevet fil
function skriv(f, tekst) {
  fs.mkdirSync(path.dirname(f), { recursive: true });
  const tmp = path.join(path.dirname(f), `.${path.basename(f)}.${process.pid}.${crypto.randomBytes(6).toString("hex")}.tmp`);
  fs.writeFileSync(tmp, tekst, { flag: "wx" });
  fs.renameSync(tmp, f);
}
function læsJson(f, std) {
  let t;
  try { t = læs(f); } catch (e) { if (e.code === "ENOENT") return std; throw e; }
  try { return JSON.parse(t); } catch (e) { throw new Error(`${path.relative(DATA, f)} kan ikke læses: ${e.message}`); }
}
const skrivJson = (f, v) => skriv(f, JSON.stringify(v, null, 1) + "\n");

// ── datoer (Mac'ens lokaltid) ────────────────────────────────────────
const isoDato = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function isoUge(d = new Date()) {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  t.setUTCDate(t.getUTCDate() + 3 - (t.getUTCDay() + 6) % 7);   // torsdagen i ugen afgør året
  const år = t.getUTCFullYear(), uge = 1 + Math.floor((t - Date.UTC(år, 0, 1)) / DAG / 7);
  return `${år}-W${String(uge).padStart(2, "0")}`;
}
const dagStart = (d = new Date()) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x.getTime(); };
// Mandagen efter d (rutinen kører søndag aften og skriver til den kommende uge). Er d en mandag, er det d selv.
function næsteMandag(d = new Date()) { const x = new Date(d); x.setHours(12, 0, 0, 0); x.setDate(x.getDate() + (8 - x.getDay()) % 7); return x; }
const UGE = /^\d{4}-W\d{2}$/;

// ── sprog, kort, log ─────────────────────────────────────────────────
function sprogTilstand() {
  const s = læsJson(FIL.sprog, null);
  return s || JSON.parse(JSON.stringify(STANDARD));
}
const gemSprog = s => skrivJson(FIL.sprog, s);
const kortListe = () => læsJson(FIL.kort, { kort: [] }).kort || [];
const reglerListe = () => læsJson(FIL.regler, { regler: [] }).regler || [];
const gemRegler = regler => skrivJson(FIL.regler, { regler });
const gemKort = kort => skrivJson(FIL.kort, { kort });
// I tidsorden: svar fra telefonen kommer først i loggen, når de er sendt, men med det tidspunkt, du gav dem.
// En ødelagt linje springes over, så én dårlig skrivning ikke tager hele historikken med sig.
function logPoster() {
  let t;
  try { t = læs(FIL.log); } catch (e) { if (e.code === "ENOENT") return []; throw e; }
  return t.split("\n").filter(Boolean).map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean)
    .sort((a, b) => String(a.tid).localeCompare(String(b.tid)));
}
function log(post) { fs.mkdirSync(DATA, { recursive: true }); fs.appendFileSync(FIL.log, JSON.stringify({ tid: new Date().toISOString(), ...post }) + "\n"); }

// ── FSRS-6 ───────────────────────────────────────────────────────────
// Samme model og standardparametre som Studie-serveren (Scripts/kompas-server.js i semestermappen). Kopieret, ikke
// delt, så Sprog ikke afhænger af semestrets mappe; se README (Kendt dublering). Uden eksamensdage.
const W = [0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001, 1.8722, 0.1666, 0.796,
  1.4835, 0.0614, 0.2629, 1.6483, 0.6014, 1.8729, 0.5425, 0.0912, 0.0658, 0.1542];
const MÅL = 0.9;
const FALD = -W[20], FAKTOR = 0.9 ** (1 / FALD) - 1;
const klem = (x, a, b) => Math.min(b, Math.max(a, x));
const husker = (t, s) => (1 + FAKTOR * t / s) ** FALD;
const dageTil = (s, r) => s / FAKTOR * (r ** (1 / FALD) - 1);
const d0 = g => W[4] - Math.exp(W[5] * (g - 1)) + 1;
function fsrs(st, g, dage) {
  if (!st) return { s: klem(W[g - 1], 0.001, 36500), d: klem(d0(g), 1, 10) };
  const { s, d } = st;
  let ns;
  if (dage < 1) {
    let op = Math.exp(W[17] * (g - 3 + W[18])) * s ** -W[19];
    if (g >= 3) op = Math.max(op, 1);
    ns = s * op;
  } else {
    const r = husker(dage, s);
    ns = g === 1
      ? Math.min(W[11] * d ** -W[12] * ((s + 1) ** W[13] - 1) * Math.exp(W[14] * (1 - r)), s / Math.exp(W[17] * W[18]))
      : s * (1 + Math.exp(W[8]) * (11 - d) * s ** -W[9] * (Math.exp(W[10] * (1 - r)) - 1) * (g === 2 ? W[15] : 1) * (g === 4 ? W[16] : 1));
  }
  const nd = W[7] * d0(4) + (1 - W[7]) * (d - W[6] * (g - 3) * (10 - d) / 9);
  return { s: klem(ns, 0.001, 36500), d: klem(nd, 1, 10) };
}
// Genafspiller kortets svar gennem FSRS: { s, d, forfald, sidst } (tider i ms)
function planlæg(hs) {
  let st = null, forfald = null, sidst = null;
  for (const h of hs) {
    st = fsrs(st, h.g, sidst == null ? 0 : Math.floor((h.t - sidst) / DAG));
    sidst = h.t;
    forfald = h.t + Math.max(1, Math.round(dageTil(st.s, MÅL))) * DAG;
  }
  return { s: st?.s ?? null, d: st?.d ?? null, forfald, sidst };
}

// ── eksamensperiode ──────────────────────────────────────────────────
// Eksamener fra Studies frister (type eksamen, ikke markeret færdig), hvis dag ligger fra i dag til `dage` dage frem
// (14 for i dag; rapporten kigger 14 dage ud over den uge, teksten skrives til). En eksamen uden præcis dato gælder hele
// sin uge (fra-til). null: Studies eksport kan ikke læses; så er der ingen eksamensperiode, og rapporten siger det
// (eksamener_kendt).
function eksamener(nu = new Date(), dage = EKSAMEN_DAGE_FØR) {
  let d;
  try { d = JSON.parse(læs(STUDIE_JSON)); } catch { return null; }
  const idag = isoDato(nu), g = new Date(nu); g.setDate(g.getDate() + dage);
  const grænse = isoDato(g);
  return (d.deadlines || []).filter(x => x && x.type === "eksamen" && !x.faerdig).map(x => ({ fag: x.fag || "", fra: x.dato || x.fra, til: x.dato || x.til }))
    .filter(x => x.fra && x.til && x.fra <= grænse && x.til >= idag).sort((a, b) => a.fra.localeCompare(b.fra));
}
function eksamensperiode(nu = new Date()) {
  const e = eksamener(nu);
  return e && e.length ? { fag: e[0].fag, dato: e[0].fra, eksamener: e } : null;
}

// ── Dagens kort ──────────────────────────────────────────────────────
// Karakter efter et forsøg, som i Studie: 1 blankt, 2 halvt, 3 sad, 4 let
const KARAKTERER = [1, 2, 3, 4];
function standardOpgave(type, navn) {
  return { frase: `Sig det på ${navn.toLowerCase()}`, test: `Sig det på ${navn.toLowerCase()}`, ret: "Ret sætningen", ord: "Brug ordet i en sætning",
    udfyld: "Sæt det manglende ind" }[type];
}
// Et kort, som siderne får det: med sprogets navn og stemme, opgaven og reglen, det øver
function kortUd(k, S, { ny, s, forfald, sidst } = {}) {
  const sp = S.sprog[k.sprog];
  return { id: k.id, sprog: k.sprog, sprognavn: sp.navn, stemme: sp.stemme, type: k.type, situation: k.situation || null, niveau: k.niveau || null,
    opgave: k.opgave || standardOpgave(k.type, sp.navn), forside: k.forside, bagside: k.bagside, note: k.note || null, regel: k.regel || null, ny: !!ny,
    stabilitet: s != null ? +s.toFixed(1) : null, forfald: forfald ? new Date(forfald).toISOString() : null, sidst: sidst ? new Date(sidst).toISOString() : null };
}
function hændelser(poster) {
  const H = {};
  for (const p of poster) if (p.type === "svar" && KARAKTERER.includes(p.karakter)) (H[p.id] ||= []).push({ t: Date.parse(p.tid), g: p.karakter, svar: p.svar });
  return H;
}
// Alt, Dagens kort og oversigten bruger: køen til i dag og tal pr. sprog
function repetition(nu = new Date()) {
  const S = sprogTilstand(), alle = kortListe(), poster = logPoster(), H = hændelser(poster);
  const start = dagStart(nu), slut = start + DAG - 1, eks = eksamensperiode(nu);
  const orden = Object.keys(S.sprog).sort((a, b) => (ROLLE_ORDEN[S.sprog[a].rolle] ?? 9) - (ROLLE_ORDEN[S.sprog[b].rolle] ?? 9) || (a === S.aktivt ? -1 : b === S.aktivt ? 1 : 0));
  const pr = Object.fromEntries(orden.map(s => [s, { test: [], forfaldne: [], nye: [], nyeIdag: 0 }]));
  const stat = Object.fromEntries(orden.map(s => [s, { i_alt: 0, laert: 0, forfaldne: 0, nye_venter: 0, test_i_alt: 0, test_tilbage: 0 }]));
  let næste = null;
  for (const k of alle) {
    const P = pr[k.sprog], st = stat[k.sprog]; if (!P) continue;
    const hs = H[k.id] || [];
    if (k.type === "test") { st.test_i_alt++; if (!hs.length) { st.test_tilbage++; P.test.push({ k, ny: true }); } continue; }
    st.i_alt++;
    if (!hs.length) { st.nye_venter++; P.nye.push({ k, ny: true }); continue; }
    if (hs[0].t >= start) P.nyeIdag++;
    const p = planlæg(hs);
    if (p.s >= LÆRT) st.laert++;
    if (p.forfald <= slut) { st.forfaldne++; P.forfaldne.push({ k, ny: false, ...p }); }
    else if (næste == null || p.forfald < næste) næste = p.forfald;
  }
  // Forfaldne: det aktive sprog først, inden for sproget det ældste forfald først. Nye: kort til en regel først (så ugens
  // regel øves den uge, den kommer), ellers i den rækkefølge, rutinen skrev dem.
  let plads = MAKS_FORFALDNE;
  const kø = [];
  for (const s of orden) {
    const P = pr[s];
    P.forfaldne.sort((a, b) => a.forfald - b.forfald);
    P.nye.sort((a, b) => (b.k.regel ? 1 : 0) - (a.k.regel ? 1 : 0));
    const forfaldne = P.forfaldne.slice(0, Math.max(0, plads)); plads -= forfaldne.length;
    const nye = eks ? [] : P.nye.slice(0, Math.max(0, (S.sprog[s].nye_pr_dag ?? 0) - P.nyeIdag));
    stat[s].nye_i_dag = nye.length;
    kø.push(...P.test, ...forfaldne, ...nye);
  }
  const klaret = poster.filter(p => p.type === "svar" && Date.parse(p.tid) >= start).length;
  return {
    kort: kø.map(({ k, ...p }) => kortUd(k, S, p)),
    statistik: { klaret_i_dag: klaret, minutter: Math.max(1, Math.round(kø.length * 0.5)), naeste: næste ? new Date(næste).toISOString() : null, sprog: stat,
      eksamensperiode: eks ? { fag: eks.fag, dato: eks.dato } : null },
  };
}

// ── ugens tekst ──────────────────────────────────────────────────────
// Dit svar står i loggen (type tekst-svar); det seneste for ugen gælder
function tekster() {
  let navne = [];
  try { navne = fs.readdirSync(FIL.tekster).filter(n => /^\d{4}-W\d{2}\.json$/.test(n)); } catch (e) { if (e.code !== "ENOENT") throw e; }
  const svar = {};
  for (const p of logPoster()) if (p.type === "tekst-svar") svar[p.uge] = { tekst: p.tekst, tid: p.tid };
  return navne.sort().reverse().map(n => ({ ...læsJson(path.join(FIL.tekster, n), {}), svar: svar[n.slice(0, -5)] || null }));
}
const tekstFil = uge => path.join(FIL.tekster, `${uge}.json`);
// Rutinen skriver feedback på ugens tekst og den nye tekst i samme kørsel søndag aften. Så længe den nye tekst ikke er
// besvaret, står feedbacken på ugen før forrest på siderne (og I dag kan sige det). T: tekster(), nyeste først.
function nyFeedback(T = tekster()) {
  const [ny, før] = T;
  return ny && !ny.svar && før?.feedback ? { uge: før.uge, titel: før.titel, skrevet: før.feedback.skrevet } : null;
}

// ── skrivninger fra siderne (kun det, du selv taster eller klikker) ──
const kortFindes = id => kortListe().some(k => k.id === id);
function gemSvar({ id, karakter, svar }, meta = {}) {
  id = String(id || "");
  if (!kortFindes(id)) throw new Error("ukendt kort");
  karakter = +karakter;
  if (!KARAKTERER.includes(karakter)) throw new Error("ukendt karakter");
  svar = svar == null ? "" : String(svar).replace(/\r\n?/g, "\n").trim();
  if (svar.length > 2000) throw new Error("svaret er for langt");
  log({ ...meta, type: "svar", id, karakter, ...(svar ? { svar } : {}) });
  return { gemt: true };
}
function gemTekstSvar({ uge, tekst }, meta = {}) {
  uge = String(uge || "");
  if (!UGE.test(uge) || !fs.existsSync(tekstFil(uge))) throw new Error("ukendt uge");
  tekst = String(tekst ?? "").replace(/\r\n?/g, "\n").trim();
  if (!tekst) throw new Error("svaret er tomt");
  if (tekst.length > 4000) throw new Error("svaret er for langt");
  log({ ...meta, type: "tekst-svar", uge, tekst });
  return { gemt: true };
}

// ── På farten: pakke og sync ─────────────────────────────────────────
// Telefonen henter en pakke, mens Mac'en kan nås, og sender svarene bagefter. Pakken har bagsiden med, så du kan
// se svaret efter dit forsøg uden net (som Dagens kort i Studie).
// Reglerne og alle kort, der øver en regel, kommer også med, så Regler og "Øv reglen" virker uden net.
function pakke(nu = new Date()) {
  const r = repetition(nu), S = sprogTilstand(), H = hændelser(logPoster());
  const regelkort = kortListe().filter(k => k.regel && k.type !== "test" && S.sprog[k.sprog]).map(k => kortUd(k, S, { ny: !H[k.id] }));
  // Dit seneste svar på et sprogkort eller ugens tekst, til "Står stille" på I dag
  const sidst = logPoster().findLast(p => p.type === "svar" || p.type === "tekst-svar");
  const T = tekster();
  return { genereret: new Date().toISOString(), aktivt: S.aktivt, sprog: S.sprog, kort: r.kort, tekster: T.slice(0, 3), statistik: r.statistik,
    regler: reglerListe(), regelkort, sidst_svar: sidst?.tid || null, ny_feedback: nyFeedback(T) };
}
// Hver post fra telefonen har et id; er det allerede gemt (svaret nåede ikke tilbage sidst), gemmes det ikke igen
function sync({ poster }, nu = Date.now()) {
  if (!Array.isArray(poster) || poster.length > 500) throw new Error("ingen poster");
  const set = new Set(logPoster().filter(p => p.sync_id).map(p => p.sync_id)), ud = [];
  for (const p of [...poster].sort((a, b) => String(a?.tid).localeCompare(String(b?.tid)))) {
    const id = String(p?.id || "");
    if (!/^[\w-]{8,64}$/.test(id)) { ud.push({ id, ok: false, fejl: "posten mangler et id" }); continue; }
    if (set.has(id)) { ud.push({ id, ok: true, allerede: true }); continue; }
    // Tidspunktet, du svarede; et ugyldigt eller fremtidigt tidspunkt bliver til nu
    const t = Date.parse(p.tid), meta = { tid: new Date(t > 0 && t <= nu + 3e5 ? Math.min(t, nu) : nu).toISOString(), sync_id: id };
    try {
      const d = p.data || {};
      const r = p.type === "svar" ? gemSvar(d, meta) : p.type === "tekst-svar" ? gemTekstSvar(d, meta) : (() => { throw new Error("ukendt type"); })();
      set.add(id);
      ud.push({ id, ok: true, ...r });
    } catch (e) { ud.push({ id, ok: false, fejl: e.message }); }
  }
  return { resultater: ud };
}

// ── Tid ──────────────────────────────────────────────────────────────
// Tiden på sprog, foreslået ud fra tidspunkterne på dine svar på sprogkort (også fra telefonen) og gemt, når du godkender
// forslaget (på Studie → Selvstudie). Den tæller for sig, ikke i Studies dagsmål. Reglerne er de samme som Studies
// forslag (studie/Scripts/sessioner.js, kopieret, ikke delt; se README, Kendt dublering): svar med højst
// pause_min minutter imellem hører sammen, hvert svar får tiden siden det forrige og det første den mediane tid mellem
// svarene; tid, der allerede er gemt, trækkes fra; et forslag kommer, når der er gået pause_min minutter efter det sidste
// svar, og kun med mindst mindst_min minutter. Ugens tekst tæller ikke: ét svar siger intet om, hvor længe du skrev.
const FORSLAG = { pause_min: 10, mindst_min: 5, dage: 14 };
const sessionerLæs = () => { const d = læsJson(FIL.sessioner, {}); return { sessioner: d.sessioner || [], afviste: d.afviste || [] }; };
function forslag(svar, d, nu = Date.now()) {
  const pause = FORSLAG.pause_min * 6e4, afviste = new Set(d.afviste), fra = nu - FORSLAG.dage * DAG;
  const logget = d.sessioner.flatMap(s => s.stykker.map(([a, b]) => [Date.parse(a), Date.parse(b)]));
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
    const dele = new Map();
    g.forEach((x, i) => {
      let stykker = [[i ? g[i - 1].t : x.t - median, x.t]];
      for (const [a, b] of logget) stykker = stykker.flatMap(([c, e]) => b <= c || a >= e ? [[c, e]] : [[c, a], [b, e]].filter(([y, z]) => z > y));
      const del = dele.get(x.sprog) || dele.set(x.sprog, []).get(x.sprog);
      for (const st of stykker) if (del.length && del.at(-1)[1] === st[0]) del.at(-1)[1] = st[1]; else del.push([...st]);
    });
    const timer = st => st.reduce((a, [c, e]) => a + e - c, 0) / 36e5;
    const ds = [...dele].map(([sprog, st]) => ({ sprog, stykker: st, timer: timer(st) })).filter(x => x.stykker.length);
    if (ds.reduce((a, x) => a + x.timer, 0) * 60 < FORSLAG.mindst_min) continue;
    ud.push({ id, start: Math.min(...ds.map(x => x.stykker[0][0])), slut: Math.max(...ds.map(x => x.stykker.at(-1)[1])), svar: g.length, dele: ds });
  }
  return ud;
}
// Dine svar på sprogkort, med kortets sprog
function svarTider() {
  const sprog = new Map(kortListe().map(k => [k.id, k.sprog]));
  return logPoster().filter(p => p.type === "svar" && Date.parse(p.tid) > 0 && sprog.get(p.id)).map(p => ({ t: Date.parse(p.tid), sprog: sprog.get(p.id) }));
}
const r2 = x => Math.round(x * 100) / 100;
const iso = t => new Date(t).toISOString();
// Til Selvstudie og Oversigt: forslagene, denne uges tid (mandag til nu) og sessionerne de seneste 14 dage (nyeste først)
function tid(nu = Date.now()) {
  const d = sessionerLæs(), S = sprogTilstand(), navn = k => S.sprog[k]?.navn || k;
  const varighed = s => s.stykker.reduce((a, [x, y]) => a + Date.parse(y) - Date.parse(x), 0) / 36e5;
  const mandag = (() => { const x = new Date(nu); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - (x.getDay() + 6) % 7); return x.getTime(); })();
  const uge = d.sessioner.filter(s => Date.parse(s.stykker[0][0]) >= mandag);
  return { forslag_regler: FORSLAG,
    forslag: forslag(svarTider(), d, nu).map(f => ({ ...f, start: iso(f.start), slut: iso(f.slut),
      dele: f.dele.map(x => ({ sprog: x.sprog, navn: navn(x.sprog), timer: r2(x.timer), stykker: x.stykker.map(st => st.map(iso)) })) })),
    uge: { mandag: isoDato(new Date(mandag)), timer: r2(uge.reduce((a, s) => a + varighed(s), 0)), sessioner: uge.length },
    sessioner: d.sessioner.filter(s => Date.parse(s.stykker[0][0]) >= nu - FORSLAG.dage * DAG).sort((a, b) => Date.parse(b.stykker[0][0]) - Date.parse(a.stykker[0][0]))
      .map(s => ({ id: s.id, sprog: s.sprog, navn: navn(s.sprog), start: s.stykker[0][0], slut: s.stykker.at(-1)[1], timer: r2(varighed(s)) })) };
}
const gemSessioner = d => skrivJson(FIL.sessioner, { afviste: d.afviste.slice(-200), sessioner: d.sessioner });
// Et forslag godkendt (gem: én session pr. sprog) eller afvist (kommer ikke igen); forslaget regnes igen her
function gemForslag({ id, handling } = {}, nu = Date.now()) {
  const d = sessionerLæs(), f = forslag(svarTider(), d, nu).find(x => x.id === id);
  if (!f) throw new Error("forslaget findes ikke længere");
  if (handling === "gem") for (const x of f.dele) d.sessioner.push({ id: `s-${crypto.randomBytes(6).toString("hex")}`, sprog: x.sprog, stykker: x.stykker.map(st => st.map(iso)), kilde: "forslag" });
  else if (handling === "afvis") d.afviste.push(id);
  else throw new Error("ukendt handling");
  d.sessioner.sort((a, b) => Date.parse(a.stykker[0][0]) - Date.parse(b.stykker[0][0]));
  gemSessioner(d);
  return tid(nu);
}
function sletSession({ id } = {}, nu = Date.now()) {
  const d = sessionerLæs(), i = d.sessioner.findIndex(s => s.id === id);
  if (i < 0) throw new Error("sessionen findes ikke");
  d.sessioner.splice(i, 1);
  gemSessioner(d);
  return tid(nu);
}

module.exports = {
  DATA, FIL, STANDARD, TYPER, NIVEAUER, ROLLER, LÆRT, DAG, UGE, EKSAMEN_DAGE_FØR, eksamener, eksamensperiode, læs, skriv, læsJson, skrivJson, isoDato, isoUge, næsteMandag, dagStart,
  sprogTilstand, gemSprog, kortListe, gemKort, reglerListe, gemRegler, logPoster, hændelser, planlæg, standardOpgave, repetition, tekster, tekstFil, nyFeedback,
  gemSvar, gemTekstSvar, pakke, sync, FORSLAG, forslag, tid, gemForslag, sletSession,
};
