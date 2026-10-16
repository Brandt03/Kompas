#!/usr/bin/env node
// Sprog: rutinens kommandoer (Kompas · Sprog, se RUTINE.md). Rutinen skriver kun gennem dem, så kort.json,
// sprog.json og tekster/ altid er gyldige, og serveren aldrig læser en halv fil.
//
//   node sprog.js rapport [--dage 7]          JSON til rutinen: sprogene, tal, ugens svar, niveautest, tekster
//   node sprog.js tilfoej <kort.json>         nye kort (en liste); dubletter springes over
//   node sprog.js tekst <tekst.json> [--uge 2026-W43] [--erstat]
//                                             ugens tekst; uden --uge den kommende uge (mandagen efter i dag)
//   node sprog.js feedback <uge> <fil.md>     rutinens feedback på dit svar på ugens tekst
//   node sprog.js regel <regel.json> [--erstat]
//                                             en sprogregel (Regler); kort peger på den med "regel": "<sprog>-<id>"
//   node sprog.js niveau <sprog> <A1-C2> <begrundelse …>
//   node sprog.js aktivt <sprog>              skift det aktive sprog (kun når brugeren beder om det)
//   node sprog.js rolle <sprog> <vedligehold|pause>
//                                             tysk eller spansk, når det ikke er aktivt (kun når brugeren beder om det)
//
// Data: data/ eller SPROG_DATA (se kerne.js).
"use strict";
const fs = require("fs");
const path = require("path");
const K = require("./kerne");

// Semestermappen, som i Studie: KOMPAS_SEMESTER, ellers ~/kompas/studie
const STUDIE = process.env.KOMPAS_SEMESTER || path.join(process.env.HOME || "", "kompas", "studie");

function fejl(t) { console.error(`sprog: ${t}`); process.exit(1); }
const ud = v => console.log(JSON.stringify(v, null, 1));
const læsFil = f => { try { return K.læs(path.resolve(f)); } catch (e) { fejl(`kan ikke læse ${f}: ${e.message}`); } };
const læsJsonFil = f => { try { return JSON.parse(læsFil(f)); } catch (e) { fejl(`${f} er ikke gyldig JSON: ${e.message}`); } };
function flag(args, navn) { const i = args.indexOf(navn); if (i < 0) return null; const v = args[i + 1]; args.splice(i, 2); return v ?? ""; }
function kunFlag(args, navn) { const i = args.indexOf(navn); if (i < 0) return false; args.splice(i, 1); return true; }
const tekstFelt = (v, navn, maks, kræv = true) => {
  if (v == null || v === "") { if (kræv) throw new Error(`${navn} mangler`); return null; }
  if (typeof v !== "string") throw new Error(`${navn} skal være tekst`);
  const t = v.trim(); if (t.length > maks) throw new Error(`${navn} er over ${maks} tegn`);
  return t;
};
// Til dubletter: samme sprog og samme forside, uanset store bogstaver, tegnsætning og mellemrum
const renForside = s => s.toLowerCase().normalize("NFC").replace(/[\s.,;:!?¡¿"'«»“”‘’()–—-]+/g, " ").trim();

// Dansk og engelsk: rutinen laver kort af det, du selv har skrevet i Studie (kun læsning). Stierne og hvornår de
// sidst er ændret, så rutinen kan se, hvad der er nyt siden sidst.
function egneTekster() {
  const ud = [];
  let fag = [];
  try { fag = fs.readdirSync(STUDIE, { withFileTypes: true }).filter(d => d.isDirectory() && !/^[._]/.test(d.name)).map(d => d.name); } catch { return ud; }
  for (const f of fag) for (const rel of ["egne-ord.md", path.join("Genkald", "begreber.md")]) {
    const fil = path.join(STUDIE, f, rel);
    try { ud.push({ fil, aendret: fs.statSync(fil).mtime.toISOString() }); } catch { /* findes ikke for faget */ }
  }
  return ud;
}

function rapport(args) {
  const dage = +(flag(args, "--dage") || 7);
  const nu = new Date(), fra = nu.getTime() - dage * K.DAG;
  const S = K.sprogTilstand(), kort = K.kortListe(), byId = new Map(kort.map(k => [k.id, k])), poster = K.logPoster();
  const r = K.repetition(nu);
  // Dine svar i perioden med kortet, så rutinen kan se, hvad du faktisk skrev, og hvad der driller
  const svar = poster.filter(p => p.type === "svar" && Date.parse(p.tid) >= fra && byId.has(p.id)).map(p => {
    const k = byId.get(p.id);
    return { tid: p.tid, id: p.id, sprog: k.sprog, type: k.type, situation: k.situation || null, forside: k.forside, bagside: k.bagside, karakter: p.karakter, svar: p.svar || null };
  });
  const H = K.hændelser(poster);
  // Kort, der bliver ved med at drille: mindst to blanke eller halve svar i alt
  const svære = kort.filter(k => k.type !== "test" && (H[k.id] || []).filter(h => h.g <= 2).length >= 2)
    .map(k => ({ id: k.id, sprog: k.sprog, forside: k.forside, bagside: k.bagside, forsoeg: (H[k.id] || []).map(h => h.g) }));
  // Niveautesten pr. sprog: alle svar, også de gamle, for testen besvares kun én gang
  const test = {};
  for (const k of kort.filter(k => k.type === "test")) {
    const t = (test[k.sprog] ||= { kort: 0, besvaret: 0, svar: [] }), hs = H[k.id] || [];
    t.kort++;
    if (hs.length) { t.besvaret++; t.svar.push({ id: k.id, niveau: k.niveau || null, forside: k.forside, bagside: k.bagside, karakter: hs[0].g, svar: hs[0].svar || null }); }
  }
  const næsteUge = K.isoUge(K.næsteMandag(nu)), eks = K.eksamener(nu);
  ud({
    i_dag: K.isoDato(nu), uge_nu: K.isoUge(nu), ny_tekst_til_uge: næsteUge, dage,
    aktivt: S.aktivt, sprog: S.sprog, statistik: r.statistik.sprog,
    kort_i_alt: kort.length, situationer: [...new Set(kort.filter(k => k.situation).map(k => `${k.sprog}: ${k.situation}`))].sort(),
    ugens_svar: svar, svaere_kort: svære, niveautest: test,
    tekster: K.tekster().slice(0, 3).map(t => ({ uge: t.uge, sprog: t.sprog, titel: t.titel, svar: t.svar, feedback: t.feedback ? "skrevet" : null })),
    tekst_til_ny_uge_findes: fs.existsSync(K.tekstFil(næsteUge)),
    // Reglerne, der findes, med antal kort og hvor mange af dem du har haft blankt eller halvt i perioden
    regler: K.reglerListe().map(g => ({ id: g.id, sprog: g.sprog, titel: g.titel, niveau: g.niveau || null, oprettet: g.oprettet,
      kort: kort.filter(k => k.regel === g.id).length, svaere_svar: svar.filter(s => byId.get(s.id).regel === g.id && s.karakter <= 2).length })),
    // Eksamener i Studie fra i dag til 14 dage frem. Er listen ikke tom, er det eksamensperiode (se RUTINE.md)
    eksamener_kendt: eks !== null, eksamener_inden_for_14_dage: eks || [],
    egne_tekster: egneTekster(),
  });
}

function tilfoej(args) {
  const f = args[0]; if (!f) fejl("brug: sprog.js tilfoej <kort.json>");
  const ind = læsJsonFil(f), liste = Array.isArray(ind) ? ind : ind?.kort;
  if (!Array.isArray(liste) || !liste.length) fejl("filen skal være en liste af kort");
  if (liste.length > 60) fejl("højst 60 kort ad gangen");
  const S = K.sprogTilstand(), kort = K.kortListe(), set = new Set(kort.map(k => `${k.sprog}|${renForside(k.forside)}`));
  const regler = new Map(K.reglerListe().map(g => [g.id, g]));
  const nr = {};
  for (const k of kort) { const m = k.id.match(/^(\w+)-(\d+)$/); if (m) nr[m[1]] = Math.max(nr[m[1]] || 0, +m[2]); }
  const tilfoejet = [], sprunget = [], nu = new Date().toISOString();
  // Først tjekkes alle; er ét kort ugyldigt, gemmes intet, så rutinen kan rette filen og prøve igen
  const nye = liste.map((k, i) => {
    try {
      if (!k || typeof k !== "object") throw new Error("ikke et kort");
      if (!S.sprog[k.sprog]) throw new Error(`ukendt sprog: ${k.sprog} (${Object.keys(S.sprog).join(", ")})`);
      if (!K.TYPER.includes(k.type)) throw new Error(`ukendt type: ${k.type} (${K.TYPER.join(", ")})`);
      if (k.niveau != null && !K.NIVEAUER.includes(k.niveau)) throw new Error(`ukendt niveau: ${k.niveau}`);
      if (k.regel != null && regler.get(k.regel)?.sprog !== k.sprog) throw new Error(`ukendt regel for ${k.sprog}: ${k.regel} (gem reglen først med sprog.js regel)`);
      if (k.type === "udfyld" && !String(k.forside || "").includes("___")) throw new Error("et udfyld-kort skal have ___ i forsiden");
      return { sprog: k.sprog, type: k.type, forside: tekstFelt(k.forside, "forside", 400), bagside: tekstFelt(k.bagside, "bagside", 400),
        opgave: tekstFelt(k.opgave, "opgave", 120, false), situation: tekstFelt(k.situation, "situation", 40, false), note: tekstFelt(k.note, "note", 400, false),
        niveau: k.niveau || null, regel: k.regel || null, kilde: tekstFelt(k.kilde, "kilde", 200) };
    } catch (e) { fejl(`kort ${i + 1}: ${e.message}`); }
  });
  for (const k of nye) {
    const n = `${k.sprog}|${renForside(k.forside)}`;
    if (set.has(n)) { sprunget.push({ forside: k.forside, grund: "findes allerede" }); continue; }
    set.add(n);
    nr[k.sprog] = (nr[k.sprog] || 0) + 1;
    const id = `${k.sprog}-${String(nr[k.sprog]).padStart(4, "0")}`;
    kort.push(Object.fromEntries(Object.entries({ id, ...k, oprettet: nu }).filter(([, v]) => v != null)));
    tilfoejet.push(id);
  }
  if (tilfoejet.length) K.gemKort(kort);
  ud({ tilfoejet, sprunget_over: sprunget });
}

function tekst(args) {
  const uge = flag(args, "--uge") || K.isoUge(K.næsteMandag()), erstat = kunFlag(args, "--erstat");
  const f = args[0]; if (!f) fejl("brug: sprog.js tekst <tekst.json> [--uge 2026-W43] [--erstat]");
  if (!K.UGE.test(uge)) fejl(`ugyldig uge: ${uge}`);
  const S = K.sprogTilstand(), t = læsJsonFil(f);
  if (fs.existsSync(K.tekstFil(uge)) && !erstat) fejl(`der er allerede en tekst til ${uge} (brug --erstat)`);
  let ny;
  try {
    if (!S.sprog[t.sprog]) throw new Error(`ukendt sprog: ${t.sprog}`);
    if (!Array.isArray(t.spoergsmaal) || !t.spoergsmaal.length || t.spoergsmaal.length > 5) throw new Error("spoergsmaal skal være 1-5 spørgsmål");
    if (t.ord != null && (!Array.isArray(t.ord) || t.ord.length > 15)) throw new Error("ord skal være en liste (højst 15)");
    if (t.niveau != null && !K.NIVEAUER.includes(t.niveau)) throw new Error(`ukendt niveau: ${t.niveau}`);
    ny = { uge, sprog: t.sprog, niveau: t.niveau || null, titel: tekstFelt(t.titel, "titel", 120), tekst: tekstFelt(t.tekst, "tekst", 3000),
      ord: (t.ord || []).map((o, i) => ({ ord: tekstFelt(o?.ord, `ord ${i + 1}`, 60), betydning: tekstFelt(o?.betydning, `betydning ${i + 1}`, 120) })),
      spoergsmaal: t.spoergsmaal.map((q, i) => tekstFelt(q, `spørgsmål ${i + 1}`, 300)),
      opgave: tekstFelt(t.opgave, "opgave", 300, false) || `Svar på spørgsmålene i tre til fem sætninger på ${S.sprog[t.sprog].navn.toLowerCase()}.`,
      skrevet: new Date().toISOString(), feedback: null };
  } catch (e) { fejl(e.message); }
  K.skrivJson(K.tekstFil(uge), ny);
  ud({ gemt: K.tekstFil(uge), uge });
}

function feedback(args) {
  const [uge, f] = args; if (!uge || !f) fejl("brug: sprog.js feedback <uge> <fil.md>");
  if (!K.UGE.test(uge) || !fs.existsSync(K.tekstFil(uge))) fejl(`ingen tekst til ${uge}`);
  const t = K.læsJson(K.tekstFil(uge), null), svar = K.tekster().find(x => x.uge === uge)?.svar;
  if (!svar) fejl(`der er intet svar på teksten til ${uge}; feedback gives kun på et svar`);
  let tekst;
  try { tekst = tekstFelt(læsFil(f), "feedback", 4000); } catch (e) { fejl(e.message); }
  t.feedback = { tekst, skrevet: new Date().toISOString(), til_svar: svar.tid };
  K.skrivJson(K.tekstFil(uge), t);
  ud({ gemt: K.tekstFil(uge) });
}

// En regel: kort forklaring på dansk, eksempler og typiske fejl (gerne brugerens egne). id'et er <sprog>-<id>, fx es-ser-estar.
function regel(args) {
  const erstat = kunFlag(args, "--erstat"), f = args[0];
  if (!f) fejl("brug: sprog.js regel <regel.json> [--erstat]");
  const S = K.sprogTilstand(), g = læsJsonFil(f), regler = K.reglerListe();
  let ny;
  try {
    if (!S.sprog[g.sprog]) throw new Error(`ukendt sprog: ${g.sprog}`);
    if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(g.id || "") || g.id.length > 40) throw new Error("id skal være små bogstaver, tal og bindestreger (højst 40), fx ser-estar");
    if (g.niveau != null && !K.NIVEAUER.includes(g.niveau)) throw new Error(`ukendt niveau: ${g.niveau}`);
    if (!Array.isArray(g.eksempler) || !g.eksempler.length || g.eksempler.length > 6) throw new Error("eksempler skal være 1-6");
    if (g.fejl != null && (!Array.isArray(g.fejl) || g.fejl.length > 5)) throw new Error("fejl skal være en liste (højst 5)");
    ny = { id: `${g.sprog}-${g.id}`, sprog: g.sprog, niveau: g.niveau || null, titel: tekstFelt(g.titel, "titel", 80), forklaring: tekstFelt(g.forklaring, "forklaring", 1500),
      eksempler: g.eksempler.map((e, i) => ({ tekst: tekstFelt(e?.tekst, `eksempel ${i + 1}`, 200), oversaettelse: tekstFelt(e?.oversaettelse, `oversættelse ${i + 1}`, 200, false) })),
      fejl: (g.fejl || []).map((x, i) => ({ fejl: tekstFelt(x?.fejl, `fejl ${i + 1}`, 200), rettet: tekstFelt(x?.rettet, `rettet ${i + 1}`, 200), hvorfor: tekstFelt(x?.hvorfor, `hvorfor ${i + 1}`, 200, false) })),
      kilde: tekstFelt(g.kilde, "kilde", 200) };
  } catch (e) { fejl(e.message); }
  const i = regler.findIndex(x => x.id === ny.id), nu = new Date().toISOString();
  if (i >= 0 && !erstat) fejl(`reglen ${ny.id} findes allerede (brug --erstat)`);
  if (i >= 0) regler[i] = { ...ny, oprettet: regler[i].oprettet, opdateret: nu }; else regler.push({ ...ny, oprettet: nu });
  K.gemRegler(regler);
  ud({ gemt: ny.id });
}

function niveau(args) {
  const [sprog, niv, ...begr] = args, S = K.sprogTilstand();
  if (!S.sprog[sprog]) fejl(`ukendt sprog: ${sprog}`);
  if (!K.NIVEAUER.includes(niv)) fejl(`niveauet skal være ${K.NIVEAUER.join(", ")}`);
  if (!begr.join(" ").trim()) fejl("skriv en begrundelse (hvad niveauet bygger på)");
  Object.assign(S.sprog[sprog], { niveau: niv, niveau_note: begr.join(" ").trim(), niveau_sat: K.isoDato() });
  K.gemSprog(S);
  ud({ sprog, niveau: niv });
}

function aktivt(args) {
  const [sprog] = args, S = K.sprogTilstand();
  if (!S.sprog[sprog] || !["aktiv", "vedligehold", "pause"].includes(S.sprog[sprog].rolle)) fejl("kun spansk og tysk kan være det aktive sprog");
  if (S.aktivt === sprog) return ud({ aktivt: sprog, uaendret: true });
  // Det gamle aktive sprog holdes ved lige med ét nyt kort om dagen; det nye får tre
  Object.assign(S.sprog[S.aktivt], { rolle: "vedligehold", nye_pr_dag: 1 });
  Object.assign(S.sprog[sprog], { rolle: "aktiv", nye_pr_dag: 3 });
  S.aktivt = sprog;
  K.gemSprog(S);
  ud({ aktivt: sprog });
}

// Det fremmedsprog, der ikke er aktivt, holdes ved lige (ét nyt kort om dagen) eller står på pause (ingen nye).
// Gentagelsen af de kort, du allerede har haft, fortsætter i begge tilfælde.
function rolle(args) {
  const [sprog, ny] = args, S = K.sprogTilstand();
  if (!S.sprog[sprog] || !["vedligehold", "pause"].includes(S.sprog[sprog].rolle)) fejl("kun det fremmedsprog, der ikke er aktivt, kan holdes ved lige eller sættes på pause");
  if (!["vedligehold", "pause"].includes(ny)) fejl("rollen skal være vedligehold eller pause");
  Object.assign(S.sprog[sprog], { rolle: ny, nye_pr_dag: ny === "pause" ? 0 : 1 });
  K.gemSprog(S);
  ud({ sprog, rolle: ny });
}

const [cmd, ...args] = process.argv.slice(2);
const KOMMANDOER = { rapport, tilfoej, tekst, feedback, regel, niveau, aktivt, rolle };
if (!KOMMANDOER[cmd]) fejl(`ukendt kommando${cmd ? `: ${cmd}` : ""}. Brug: ${Object.keys(KOMMANDOER).join(", ")} (se toppen af sprog.js)`);
try { KOMMANDOER[cmd](args); } catch (e) { fejl(e.message); }
