// Studie → Kompas (https://kompas.localhost)
//
// Læser semestermappen og skriver det, Kompas viser under "Studie", til ~/.kompas/studie/ (eller STUDIE_EKSPORT_UD):
//   studie.json      ugeplanerne (fra køreplan-rutinen), deadlines, eksamensformer og status pr. fag
//   fagnoter.json    ugeblokkene i Fagnoter-dokumenterne (Word) som html, billederne i fagnoter/<fag>/
//   kompas.json        hvilke sider projektet har (Kompas bygger menuen ud fra den)
//   *.html, *.js     siderne selv, kopieret fra Scripts/kompas/ (også På fartens manifest og ikoner)
//
// Scriptet LÆSER kun. Det ændrer aldrig arbejdsfiler (begreber, genkald, drills, afleveringer) og
// løser intet. Status tælles på samme måde som køreplanen gør det (afsnit 2, punkt 3 i rutinen).
//
// Kør:  node Scripts/kompas-eksport.js          (fra semestermappen, eller med fuld sti)
//       node Scripts/kompas-eksport.js --ud <mappe>
//
// Stier (env-variabler, alle valgfrie):
//   KOMPAS_SEMESTER     semestermappen; standard er mappen over Scripts/
//   STUDIE_EKSPORT_UD   hvor eksporten skriver; standard ~/.kompas/studie (--ud vinder)
//   LIV_SITE            mappen, overblik skriver liv.json i; standard ~/.garmin-coach/site
//
// Køres af Kompas-appen, når den åbner, og af køreplan-rutinen søndag efter en ny ugeplan.

const fs = require("fs");
const path = require("path");
const os = require("os");
const { execFileSync } = require("child_process");
const crypto = require("crypto");

const hjem = s => s.replace(/^~(?=$|\/)/, os.homedir());
const ROD = path.resolve(hjem(process.env.KOMPAS_SEMESTER || path.join(__dirname, "..")));
// Scriptenes egne datafiler (deadlines-status.json m.fl.) ligger i semestermappens Scripts/
const DATA = path.join(ROD, "Scripts");
const SIDER = path.join(__dirname, "kompas");
const argUd = process.argv.indexOf("--ud");
const UD = argUd > 0 ? path.resolve(process.argv[argUd + 1])
  : path.resolve(hjem(process.env.STUDIE_EKSPORT_UD || path.join(os.homedir(), ".kompas", "studie")));
const LIV_SITE = path.resolve(hjem(process.env.LIV_SITE || path.join(os.homedir(), ".garmin-coach", "site")));

// Fagene: id bruges i data og adresser, mappe er fagets mappe i semestermappen, readme er fagets navn i README.md's
// tabel over eksamensformer, og overskrift genkender fagets afsnit i ugeplanerne. Gamma har drills og afleveringer.
const FAG = [
  { id: "alfa", mappe: "Alfa", kort: "Alfa", navn: "Alfa – lorem ipsum", readme: "Alfa", overskrift: /^Alfa\b/ },
  { id: "beta", mappe: "Beta", kort: "Beta", navn: "Beta – dolor sit amet", readme: "Beta", overskrift: /^Beta\b/ },
  { id: "gamma", mappe: "Gamma", kort: "Gamma", navn: "Gamma – consectetur", readme: "Gamma", overskrift: /^Gamma\b/ },
];

// ── små hjælpere ─────────────────────────────────────────────────────

const læs = f => { try { return fs.readFileSync(f, "utf8"); } catch { return null; } };
const findes = f => { try { fs.accessSync(f); return true; } catch { return false; } };
const ls = d => { try { return fs.readdirSync(d).filter(n => !n.startsWith(".") && !n.startsWith("~$")); } catch { return []; } };
const mtime = f => { try { return fs.statSync(f).mtime; } catch { return null; } };
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

// ── markdown → html (det, planerne bruger: overskrifter, lister, tabeller, fed, kode) ──

// " escapes også: link-reglen og alt-teksterne sætter teksten ind i en attribut
const escHtml = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
function inline(s) {
  const koder = [];
  s = escHtml(s).replace(/`([^`]+)`/g, (_, c) => `\u0000${koder.push(c) - 1}\u0000`);
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
       .replace(/(^|[^*\w])\*(?!\s)(.+?)\*(?!\w)/g, "$1<em>$2</em>")
       // Kun webadresser bliver til links (ugens videoer); stier i mappen forbliver tekst
       .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, `<a href="$2" target="_blank" rel="noopener">$1</a>`)
       .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${koder[i]}</code>`).replace(/\u0001/g, "<br>");
}
function md(src) {
  const ud = [];
  const linjer = src.replace(/\r/g, "").split("\n");
  let para = [], liste = null;
  const lukPara = () => { if (para.length) { ud.push(`<p>${inline(para.join(" "))}</p>`); para = []; } };
  const lukListe = () => {
    if (!liste) return;
    ud.push(`<${liste.tag}>${liste.items.map(it => `<li>${inline(it.tekst)}${it.under.length ? `<ul>${it.under.map(u => `<li>${inline(u)}</li>`).join("")}</ul>` : ""}</li>`).join("")}</${liste.tag}>`);
    liste = null;
  };
  for (let i = 0; i < linjer.length; i++) {
    const l = linjer[i];
    if (/^```/.test(l)) {
      lukPara(); lukListe();
      const kode = [];
      while (++i < linjer.length && !/^```/.test(linjer[i])) kode.push(linjer[i]);
      ud.push(`<pre><code>${escHtml(kode.join("\n"))}</code></pre>`);
      continue;
    }
    if (!l.trim()) { lukPara(); if (liste && !/^\s+\S/.test(linjer[i + 1] || "") && !/^\s*([-*]|\d+\.)\s/.test(linjer[i + 1] || "")) lukListe(); continue; }
    if (/^---+\s*$/.test(l)) { lukPara(); lukListe(); ud.push("<hr>"); continue; }
    const h = l.match(/^(#{1,6})\s+(.*)$/);
    if (h) { lukPara(); lukListe(); ud.push(`<h${h[1].length <= 3 ? 3 : 4}>${inline(h[2])}</h${h[1].length <= 3 ? 3 : 4}>`); continue; }
    if (/^\s*\|/.test(l)) {
      lukPara(); lukListe();
      const rækker = [];
      while (i < linjer.length && /^\s*\|/.test(linjer[i])) rækker.push(linjer[i++]);
      i--;
      const celler = r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      const [hoved, , ...krop] = rækker;
      ud.push(`<table><thead><tr>${celler(hoved).map(c => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>${
        krop.map(r => `<tr>${celler(r).map(c => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
      continue;
    }
    const li = l.match(/^(\s*)([-*]|\d+\.)\s+(.*)$/);
    if (li) {
      lukPara();
      const tag = /\d/.test(li[2]) ? "ol" : "ul";
      if (li[1].length >= 2 && liste) { liste.items[liste.items.length - 1].under.push(li[3]); continue; }
      if (!liste || liste.tag !== tag) { lukListe(); liste = { tag, items: [] }; }
      liste.items.push({ tekst: li[3], under: [] });
      continue;
    }
    // Svarmuligheder ("   a) …") under et spørgsmål står på hver sin linje; anden indrykket tekst er ombrydning
    if (liste && /^\s+\S/.test(l)) { liste.items[liste.items.length - 1].tekst += (/^\s+[a-h]\)\s/.test(l) ? "\u0001" : " ") + l.trim(); continue; }
    lukListe();
    para.push(l.trim());
  }
  lukPara(); lukListe();
  return ud.join("\n");
}

function tabel(src) {
  const rækker = src.split("\n").filter(l => /^\s*\|/.test(l));
  if (rækker.length < 2) return [];
  const celler = r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
  const hoved = celler(rækker[0]);
  return rækker.slice(2).map(r => Object.fromEntries(celler(r).map((c, i) => [hoved[i] || `k${i}`, c])));
}

// ── ugeplaner fra køreplan-rutinen ───────────────────────────────────

const DELAFSNIT = ["Hurtigt overblik", "Kilder", "Noter til pensum", "Til rapporten", "Video"];

// Øvelsesspørgsmål i en plan: fra "*Øvelsesspørgsmål …*" eller "*Pensumspørgsmål:* …" til "*Svar …*" eller
// "*Disponeret … svar*". Spørgsmål og svar holdes adskilt, så Genkald-fanen kan vise svaret efter forsøget.
function splitOevelse(raa) {
  const l = raa.split("\n");
  const q = l.findIndex(x => /^\*(Øvelsesspørgsmål|Pensumspørgsmål)/.test(x.trim()));
  if (q < 0) return null;
  const a = l.findIndex((x, i) => i > q && /^\*(Svar|Disponeret)/.test(x.trim()));
  if (a < 0) return null;
  const ren = xs => { while (xs.length && /^(---+)?\s*$/.test(xs[xs.length - 1])) xs.pop(); return xs.join("\n"); };
  return { spoergsmaal: md(ren(l.slice(q, a))), svar: md(ren(l.slice(a + 1))) };
}

function læsPlan(fil) {
  const tekst = læs(path.join(ROD, "Uge_Overblik", fil));
  const m = fil.match(/^Ugeplan_uge(\d+)_.*?(\d{4})\.md$/);
  if (!tekst || !m) return null;
  const uge = +m[1], aar = +m[2];
  const mandag = mandagIUge(aar, uge);
  const titel = (tekst.match(/^# (.*)$/m) || [])[1] || `Uge ${uge}`;
  const afsnit = tekst.split(/^## /m).slice(1).map(a => {
    const nl = a.indexOf("\n");
    return { titel: a.slice(0, nl).trim(), krop: a.slice(nl + 1).trim() };
  });
  const plan = { uge, aar, fil: `Uge_Overblik/${fil}`, titel, fra: isoDato(mandag), til: isoDato(plusDage(mandag, 6)),
    ændret: mtime(path.join(ROD, "Uge_Overblik", fil))?.toISOString() ?? null, fag: {}, vigtigst: null, genkaldelse: null, deadlines: [], øvrigt: [] };
  for (const a of afsnit) {
    const fag = FAG.find(f => f.overskrift.test(a.titel));
    if (fag) {
      // Del kun på de faste underoverskrifter; noterne kan selv have fede linjer som mellemrubrikker
      const dele = {}; let nu = "intro"; const buf = { intro: [] };
      for (const l of a.krop.split("\n")) {
        // "**Noter til pensum** *(opslagsværk til USB'en)*" tæller også; resten af linjen bliver første linje.
        // Planerne før uge 39 bruger "### Hurtigt overblik" i stedet for fed tekst.
        const t = l.trim().replace(/^###\s+(.*)$/, "**$1**");
        const hit = DELAFSNIT.find(d => t.startsWith(`**${d}**`));
        if (hit) { nu = hit; buf[nu] = [t.slice(hit.length + 4).trim()]; continue; }
        buf[nu].push(l);
      }
      for (const [k, v] of Object.entries(buf)) if (v.join("").trim()) dele[k] = md(v.join("\n"));
      const oev = splitOevelse(Object.values(buf).map(v => v.join("\n")).join("\n"));
      plan.fag[fag.id] = { overskrift: a.titel, ...dele, ...(oev ? { oevelse: oev } : {}) };
      continue;
    }
    // Uge 38 har "### Vigtigst i ugen" inde under Deadlines-afsnittet
    const vUnder = a.krop.match(/^###\s+Vigtigst[^\n]*\n([\s\S]*?)(?=^###\s|(?![\s\S]))/m);
    if (vUnder && !plan.vigtigst) plan.vigtigst = md(vUnder[1]);
    if (/^Vigtigst/i.test(a.titel)) plan.vigtigst = md(a.krop);
    else if (/^Genkald/i.test(a.titel)) {
      const l = a.krop.split("\n"), sv = l.findIndex(x => /^\*Svar/.test(x.trim()));
      const ren = xs => { while (xs.length && /^(---+)?\s*$/.test(xs[xs.length - 1])) xs.pop(); return xs.join("\n"); };
      plan.genkaldelse = { titel: a.titel, html: md(a.krop),
        ...(sv > 0 ? { spoergsmaal: md(ren(l.slice(0, sv))), svar: md(ren(l.slice(sv + 1))) } : {}) };
    }
    else if (/^Deadlines/i.test(a.titel)) plan.deadlines = tabel(a.krop);
    else plan.øvrigt.push({ titel: a.titel, html: md(a.krop) });
  }
  return plan;
}

// ── deadlines og eksamener ───────────────────────────────────────────

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
  else if (/\bopgave \d+\b|aflever/i.test(ren)) type = "aflevering";
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
    uger: r.Uge || "", dato_tekst: r.Dato || null, fag: /^(—|–|-|alle)?$/i.test((r.Fag || "").trim()) ? "Alle" : r.Fag.trim(), hvad: inline(hvad), note: r.Bemærkning ? inline(r.Bemærkning) : null,
    type, fra: fra && isoDato(fra), til: til && isoDato(til), dato, tid,
  };
}

function eksamensformer() {
  const readme = læs(path.join(ROD, "README.md")) || "";
  const afsnit = readme.split(/^## /m).find(a => /trænes forskelligt/i.test(a)) || "";
  return tabel(afsnit);
}

// ── status pr. fag (samme optælling som køreplanen) ─────────────────

function begreber(fil) {
  const t = læs(fil);
  if (!t) return null;
  const uger = []; let nu = null, begrebTabel = false;
  const linjer = t.split("\n");
  linjer.forEach((l, i) => {
    const h = l.match(/^## (.*)$/);
    if (h) { nu = { uge: h[1].trim(), udfyldt: 0, i_alt: 0 }; uger.push(nu); return; }
    if (!nu || !/^\s*\|/.test(l) || /^\s*\|\s*-/.test(l)) return;
    const c = l.trim().replace(/^\||\|$/g, "").split("|").map(x => x.trim());
    // Kun tabeller med kolonnen "Begreb" tæller; andre skemaer i filen er andre øvelser
    if (/^\s*\|\s*-/.test(linjer[i + 1] || "")) { begrebTabel = /^Begreb$/i.test(c[0]); return; }
    if (!begrebTabel) return;
    nu.i_alt++; if (c[1]) nu.udfyldt++;
  });
  const u = uger.filter(x => x.i_alt);
  return { udfyldt: u.reduce((s, x) => s + x.udfyldt, 0), i_alt: u.reduce((s, x) => s + x.i_alt, 0), uger: u,
    ændret: mtime(fil)?.toISOString() ?? null };
}

function genkald(mappe) {
  return ls(mappe).filter(n => /^genkald-.*\.md$/.test(n) && !/-svar\.md$/.test(n)).sort().map(n => {
    const t = læs(path.join(mappe, n)) || "";
    const blokke = t.split(/^(?=\*\*\d+\.\*\*)/m).slice(1);
    const tæl = { sad: 0, halvt: 0, blankt: 0, umarkeret: 0 };
    for (const b of blokke) {
      const m = b.match(/\[(✓|~|✗)\]/);
      tæl[m ? { "✓": "sad", "~": "halvt", "✗": "blankt" }[m[1]] : "umarkeret"]++;
    }
    const u = n.match(/uge(\d+)-(\d+)/);
    return { fil: n, uger: u ? (u[1] === u[2] ? `uge ${u[1]}` : `uge ${u[1]}–${u[2]}`) : n,
      spoergsmaal: blokke.length, ...tæl, ændret: mtime(path.join(mappe, n))?.toISOString() ?? null };
  });
}

function drills(mappe) {
  return ls(mappe).filter(n => /^kap\d+.*\.js$/.test(n)).sort().map(n => {
    const t = læs(path.join(mappe, n)) || "";
    const titel = (t.match(/^\/\/\s*(.*)$/m) || [])[1] || n;
    const pladser = (t.match(/^tjek\(/gm) || []).length;
    const tomme = (t.match(/,\s*TOM\s*\)/g) || []).length;
    return { fil: n, titel, pladser, tomme, gættet: pladser - tomme,
      stubbe: (t.match(/DIN KODE HER/g) || []).length, ændret: mtime(path.join(mappe, n))?.toISOString() ?? null };
  });
}

// Afleveringernes statustabel (Gamma/vscode/Opgaver/README.md): Opgave | Uge | Afleveret | Godkendt | Hvad drillede
function afleveringer(fil) {
  const t = læs(fil);
  if (!t) return null;
  const status = t.split(/^## /m).find(a => /^Status/.test(a)) || "";
  const rækker = tabel(status);
  const ja = v => !!v && !/^(nej|-|—|–)$/i.test(v.trim());
  return {
    raekker: rækker.map(r => ({ opgave: r.Opgave, uge: r.Uge || null, afleveret: r.Afleveret || null,
      godkendt: r.Godkendt || null, drillede: r["Hvad drillede"] || null, mappe: findes(path.join(path.dirname(fil), r.Opgave || "_")) })),
    afleveret: rækker.filter(r => ja(r.Afleveret)).length,
    godkendt: rækker.filter(r => ja(r.Godkendt) && !/nej|ikke/i.test(r.Godkendt)).length,
    krav: +((t.match(/\*\*(\d+) af (\d+) skal godkendes\*\*/) || [])[1] || 0) || null,
    ud_af: +((t.match(/\*\*(\d+) af (\d+) skal godkendes\*\*/) || [])[2] || 0) || null,
  };
}

// Filer ændret de sidste 7 dage i fagets arbejdsdele (ikke kildemateriale)
function aktivitet(fagMappe) {
  const grænse = Date.now() - 7 * 864e5, fundet = [];
  const gå = (d, dybde) => {
    for (const n of ls(d)) {
      if (["Pensum", "Afleveringer", "node_modules"].includes(n)) continue;
      const f = path.join(d, n);
      let st; try { st = fs.statSync(f); } catch { continue; }
      if (st.isDirectory()) { if (dybde < 4) gå(f, dybde + 1); }
      else if (st.mtimeMs >= grænse && !/\.pdf$/i.test(n)) fundet.push({ fil: path.relative(ROD, f), ændret: st.mtime.toISOString() });
    }
  };
  gå(path.join(ROD, fagMappe), 0);
  return fundet.sort((a, b) => b.ændret.localeCompare(a.ændret)).slice(0, 12);
}

function fagStatus(f) {
  const d = path.join(ROD, f.mappe);
  const s = { aktivitet: aktivitet(f.mappe),
    eksamenssaet: ls(d).filter(n => /eksamen/i.test(n)),
    fagnoter: ls(d).filter(n => /^Fagnoter.*\.docx$/i.test(n)).map(n => ({ fil: n, ændret: mtime(path.join(d, n))?.toISOString() ?? null })) };
  if (findes(path.join(d, "Genkald"))) {
    s.begreber = begreber(path.join(d, "Genkald", "begreber.md"));
    s.genkald = genkald(path.join(d, "Genkald"));
  }
  if (findes(path.join(d, "Modeller"))) s.modeller = ls(path.join(d, "Modeller")).filter(n => !/^README/i.test(n)).length;
  if (f.id === "gamma") {
    const vs = path.join(d, "vscode");
    s.drills = drills(path.join(vs, "Drills"));
    s.oevelser_i_gang = ls(vs).filter(n => /\.js$/.test(n));
    s.oevelser_faerdige = [...ls(path.join(vs, "Bog")), ...ls(path.join(vs, "Øvelser"))].length;
    s.afleveringer = afleveringer(path.join(vs, "Opgaver", "README.md"));
  }
  return s;
}

// ── fagnoter (Word) ──────────────────────────────────────────────────
// Køreplan-rutinen udfylder en uge i Fagnoter-dokumentet, når ugen er slut og slides er lagt op (afsnit 6).
// Ugeblokkene ("Uge NN — …" som Overskrift 2) læses her som html til Fag-siden, og billederne kopieres til
// <UD>/fagnoter/<fag>/. Dokumentet læses kun (unzip -p). Kan det ikke læses, beholdes sidste eksport.

const ENT = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };
const afEnt = s => s.replace(/&(#x?[0-9a-f]+|\w+);/gi, (m, e) =>
  e[0] !== "#" ? ENT[e] ?? m : String.fromCodePoint(/^#x/i.test(e) ? parseInt(e.slice(2), 16) : +e.slice(1)));
// Lille XML-læser: nok til document.xml (elementer, attributter, tekst)
function xml(src) {
  const rod = { navn: "#rod", attr: {}, børn: [] }, stak = [rod];
  const re = /<(\/?)([\w:.-]+)((?:\s+[\w:.-]+\s*=\s*(?:"[^"]*"|'[^']*'))*)\s*(\/?)>|<[?!][^>]*>|([^<]+)/g;
  for (let m; (m = re.exec(src));) {
    if (m[5] != null) { stak[stak.length - 1].børn.push(afEnt(m[5])); continue; }
    if (!m[2]) continue;
    if (m[1]) { if (stak.length > 1) stak.pop(); continue; }
    const attr = {};
    for (const a of m[3].matchAll(/([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')/g)) attr[a[1]] = afEnt(a[2] ?? a[3]);
    const n = { navn: m[2], attr, børn: [] };
    stak[stak.length - 1].børn.push(n);
    if (!m[4]) stak.push(n);
  }
  return rod;
}
const elem = n => n.børn.filter(b => typeof b !== "string");
const barn = (n, navn) => n && elem(n).find(b => b.navn === navn);
const alle = (n, navn, ud = []) => { for (const b of elem(n)) { if (b.navn === navn) ud.push(b); alle(b, navn, ud); } return ud; };
const tændt = (rPr, navn) => { const b = barn(rPr, navn); return !!b && !/^(0|false|off)$/.test(b.attr["w:val"] || ""); };

// Label-afsnittene i skabelonen (samme liste som rutinens fill_fagnoter.py)
const FN_LABELS = ["Kilder", "Purpose", "Kernebegreber", "I egne ord", "Forbindelser", "Uafklaret", "Modeller",
  "Mønstre i gamle sæt", "Spørgsmålsformer", "Egne øvelsesspørgsmål", "Feedback fra tidligere afleveringer",
  "Syntaks og eksempler", "Typiske fejl"];

function wAfsnit(p, billede) {
  const pPr = barn(p, "w:pPr");
  const stil = barn(pPr, "w:pStyle")?.attr["w:val"] || "";
  const runs = elem(p).flatMap(b => b.navn === "w:r" ? [b] : ["w:hyperlink", "w:ins", "w:smartTag"].includes(b.navn) ? elem(b).filter(r => r.navn === "w:r") : []);
  let html = "", ren = "", førsteFed = null;
  for (const r of runs) {
    const rPr = barn(r, "w:rPr");
    const fed = tændt(rPr, "w:b"), kursiv = tændt(rPr, "w:i");
    const grå = barn(rPr, "w:color")?.attr["w:val"] === "595959" || +(barn(rPr, "w:sz")?.attr["w:val"] || 99) <= 18;
    for (const c of elem(r)) {
      let h = "";
      if (c.navn === "w:t") { const t = c.børn.join(""); ren += t; h = escHtml(t); if (førsteFed == null && t.trim()) førsteFed = fed; }
      else if (c.navn === "w:tab") { ren += " "; h = " "; }
      else if (c.navn === "w:br") h = "<br>";
      else if (c.navn === "w:drawing") {
        const src = billede(alle(c, "a:blip")[0]?.attr["r:embed"]);
        if (src) html += `<img src="${src}" alt="${escHtml(alle(c, "wp:docPr")[0]?.attr.descr || "")}" loading="lazy">`;
        continue;
      }
      if (!h) continue;
      if (fed) h = `<strong>${h}</strong>`;
      if (kursiv) h = `<em>${h}</em>`;
      if (grå) h = `<span class="fn-graa">${h}</span>`;
      html += h;
    }
  }
  return {
    stil, html, ren,
    liste: !!barn(pPr, "w:numPr"),
    kode: barn(pPr, "w:shd")?.attr["w:fill"] === "F2F2F2",
    midt: barn(pPr, "w:jc")?.attr["w:val"] === "center",
    label: førsteFed ? FN_LABELS.find(l => ren.trim().startsWith(l)) || null : null,
  };
}

// Afsnit → html; lister og kodelinjer samles
function wHtml(afsnit) {
  const ud = [];
  for (let i = 0; i < afsnit.length; i++) {
    const a = afsnit[i];
    if (a.tabel) { ud.push(a.tabel); continue; }
    if (a.kode) {
      const linjer = [];
      for (; i < afsnit.length && afsnit[i].kode; i++) linjer.push(escHtml(afsnit[i].ren));
      i--; ud.push(`<pre><code>${linjer.join("\n")}</code></pre>`); continue;
    }
    // Tomme afsnit og skabelonens "Kopiér blokken ovenfor …" vises ikke
    if (!a.ren.trim() && !a.html.includes("<img") || /^Kopiér blokken/.test(a.ren.trim())) continue;
    if (a.liste) {
      const pkt = [];
      for (; i < afsnit.length && afsnit[i].liste; i++) if (afsnit[i].ren.trim() || afsnit[i].html.includes("<img")) pkt.push(`<li>${afsnit[i].html}</li>`);
      i--; if (pkt.length) ud.push(`<ul>${pkt.join("")}</ul>`); continue;
    }
    if (a.label) { ud.push(`<h4 class="fn-label">${a.html}</h4>`); continue; }
    ud.push(`<p${a.midt ? ` class="fn-midt"` : ""}>${a.html}</p>`);
  }
  return ud.join("\n");
}

function wTabel(t, billede) {
  return `<table><tbody>${elem(t).filter(r => r.navn === "w:tr").map(r => `<tr>${elem(r).filter(c => c.navn === "w:tc").map(c =>
    `<td>${wHtml(elem(c).filter(p => p.navn === "w:p").map(p => wAfsnit(p, billede)))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function fagnoterUger(fil, fagId) {
  const unzip = indre => execFileSync("unzip", ["-p", fil, indre], { maxBuffer: 256 << 20 });
  const doc = xml(unzip("word/document.xml").toString("utf8"));
  const rels = {};
  for (const r of alle(xml(unzip("word/_rels/document.xml.rels").toString("utf8")), "Relationship")) rels[r.attr.Id] = r.attr.Target;
  const brugt = new Set();
  const billede = id => {
    const mål = rels[id];
    if (!mål || !/^media\/[^/]+$/.test(mål)) return null;
    brugt.add(mål);
    return `fagnoter/${fagId}/${mål.slice(6)}`;
  };
  const krop = barn(barn(doc, "w:document"), "w:body");
  const uger = {};
  let nu = null;
  for (const b of elem(krop)) {
    if (b.navn === "w:tbl") { if (nu) nu.afsnit.push({ tabel: wTabel(b, billede) }); continue; }
    if (b.navn !== "w:p") continue;
    const a = wAfsnit(b, billede);
    const niveau = +((a.stil.match(/^(?:Overskrift|Heading)\s*(\d)$/i) || [])[1] || 0);
    if (niveau) {
      const u = niveau === 2 && a.ren.trim().match(/^Uge\s+(\d+)\b/i);
      nu = u ? (uger[+u[1]] = { titel: a.ren.trim(), afsnit: [] }) : null;
      continue;
    }
    if (nu) nu.afsnit.push(a);
  }
  const ud = {};
  for (const [uge, u] of Object.entries(uger)) {
    // Rutinen regner en uge for udfyldt, når blokken har en "Modeller"-label (afsnit 6 i køreplan-rutinen)
    ud[uge] = { titel: u.titel, udfyldt: u.afsnit.some(a => a.label === "Modeller"),
      kun_bog: u.afsnit.some(a => /Slides til uge \d+ var ikke uploadet/i.test(a.ren || "")), html: wHtml(u.afsnit) };
  }
  return { uger: ud, billeder: [...brugt] };
}

// Billederne pakkes kun ud, når dokumentet er ændret siden sidst (stempel = ændringstid + størrelse)
function fagnoter(forrige) {
  const ud = {};
  for (const f of FAG) {
    const navn = ls(path.join(ROD, f.mappe)).find(n => /^Fagnoter.*\.docx$/i.test(n));
    if (!navn) continue;
    const fil = path.join(ROD, f.mappe, navn);
    try {
      const st = fs.statSync(fil), stempel = `${st.mtimeMs}:${st.size}`;
      const { uger, billeder } = fagnoterUger(fil, f.id);
      const dir = path.join(UD, "fagnoter", f.id);
      if (forrige?.[f.id]?.stempel !== stempel || !findes(dir)) {
        const tmp = `${dir}.${process.pid}.tmp`;   // to eksporter på én gang (opdater.sh og en gemning) deler ikke mappen
        fs.rmSync(tmp, { recursive: true, force: true });
        fs.mkdirSync(tmp, { recursive: true });
        for (const b of billeder) fs.writeFileSync(path.join(tmp, b.slice(6)), execFileSync("unzip", ["-p", fil, `word/${b}`], { maxBuffer: 256 << 20 }));
        fs.rmSync(dir, { recursive: true, force: true });
        fs.renameSync(tmp, dir);
      }
      ud[f.id] = { fil: `${f.mappe}/${navn}`, ændret: st.mtime.toISOString(), stempel, uger };
    } catch (e) {
      console.error(`Fagnoter ${f.kort}: ${e.message.split("\n")[0]}`);
      if (forrige?.[f.id]) ud[f.id] = forrige[f.id];
    }
  }
  return ud;
}

// ── saml og skriv ────────────────────────────────────────────────────

function main() {
  const nu = new Date();
  const planer = ls(path.join(ROD, "Uge_Overblik")).filter(n => /^Ugeplan_uge\d+_.*\.md$/.test(n))
    .map(læsPlan).filter(Boolean).sort((a, b) => a.aar - b.aar || a.uge - b.uge);
  const ugeNu = isoUge(nu);
  const aktuel = planer.find(p => p.uge === ugeNu) || [...planer].reverse().find(p => p.uge < ugeNu) || planer[0] || null;
  const nyeste = planer[planer.length - 1] || null;

  // Deadlines: tabellen i den nyeste plan flettet med CLAUDE.md's "Vigtige datoer". En række fra CLAUDE.md
  // med en præcis dato (fx eksamen fra Eksamener.pdf) erstatter planens række for samme fag, uge og type;
  // rækker planen ikke har, kommer med; resten af planens rækker står uændret.
  let deadlines = nyeste?.deadlines?.length ? nyeste.deadlines.map(r => deadline(r, nyeste.aar, nyeste.uge)) : [];
  const claude = læs(path.join(ROD, "CLAUDE.md")) || "";
  const vigtige = tabel(claude.split(/^## /m).find(a => /^Vigtige datoer/.test(a)) || "")
    .map(r => deadline(r, nyeste?.aar ?? nu.getFullYear(), nyeste?.uge ?? ugeNu));
  const samme = (a, b) => a.fag === b.fag && a.type === b.type && a.fra === b.fra;
  for (const v of vigtige) {
    const i = deadlines.findIndex(d => samme(d, v));
    if (i < 0) deadlines.push(v);
    else if (v.dato) deadlines[i] = { ...v, note: deadlines[i].note && !/verificer|tjek/i.test(deadlines[i].note) ? deadlines[i].note : null };
  }
  // Prøveeksamener er en egen plan, ikke frister fra uddannelsen: de står i CLAUDE.md's "Egen plan" og vises på
  // Eksamen-fanen. En prøveeksamen i ugeplanens tabel eller under Vigtige datoer flyttes også derover.
  const egenPlan = tabel(claude.split(/^## /m).find(a => /^Egen plan/.test(a)) || "")
    .map(r => deadline(r, nyeste?.aar ?? nu.getFullYear(), nyeste?.uge ?? ugeNu));
  const proeveplan = [...egenPlan, ...deadlines.filter(d => d.type === "proeve" && !egenPlan.some(e => e.fag === d.fag && e.fra === d.fra))]
    .map(({ uger, fag, hvad, fra, til }) => ({ uger, fag, hvad, fra, til }))
    .sort((a, b) => String(a.fra).localeCompare(String(b.fra)));
  deadlines = deadlines.filter(d => d.type !== "proeve");
  deadlines.sort((a, b) => String(a.dato || a.fra).localeCompare(String(b.dato || b.fra)));
  // Færdig-markering fra Kompas: nummererede afleveringer ("Opgave 3") i "Afleveret" i Opgaver/README.md, resten i
  // deadlines-status.json. Nøglen er "<fag>|Opgave 3" for dem og ellers "<fag>|<type>|<uge>", så den overlever, at
  // planens tekst ændrer sig.
  let status = {};
  try { status = JSON.parse(læs(path.join(DATA, "deadlines-status.json")) || "{}"); } catch { status = {}; }
  const aflRækker = afleveringer(path.join(ROD, "Gamma", "vscode", "Opgaver", "README.md"))?.raekker || [];
  for (const d of deadlines) {
    const nr = (d.hvad.replace(/<[^>]+>/g, "").match(/\bopgave (\d+)\b/i) || [])[1];
    const g = nr ? `Opgave ${nr}` : null;
    d.noegle = g ? `${d.fag}|${g}` : `${d.fag}|${d.type}|${(d.uger.match(/\d+/) || [""])[0]}`;
    const gr = g && aflRækker.find(r => r.opgave === g);
    const afl = gr?.afleveret && !/^(nej|-|—|–)$/i.test(gr.afleveret) ? gr.afleveret : null;
    d.faerdig = status[d.noegle]?.faerdig || afl || null;
  }
  const deadlineKilde = [nyeste?.deadlines?.length ? nyeste.fil : null, vigtige.length ? "CLAUDE.md" : null].filter(Boolean).join(" og ") || null;

  const former = eksamensformer();
  const fag = FAG.map(f => ({
    id: f.id, kort: f.kort, navn: f.navn,
    eksamen: former.find(r => (r.Fag || "").startsWith(f.readme)) || null,
    status: fagStatus(f),
  }));

  const data = {
    genereret: nu.toISOString(), uge_nu: ugeNu, aktuel_uge: aktuel?.uge ?? null,
    planer: planer.map(p => ({ ...p, deadlines: undefined })),
    deadlines, deadline_kilde: deadlineKilde, proeveplan, fag,
  };
  const manifest = {
    omraade: "Studie", ikon: "graduation-cap", raekkefoelge: 20,
    kilde: `${path.basename(ROD)} (Scripts/kompas-eksport.js) · ugeplaner fra køreplan-rutinen`,
    opdateret: nu.toISOString(),
    sider: [
      { titel: "Ugeoverblik", ikon: "calendar", sti: "/studie/" },
      { titel: "Fag", ikon: "book-open", sti: "/studie/fag.html" },
      { titel: "Genkald", ikon: "brain", sti: "/studie/genkald.html" },
      { titel: "Eksamen", ikon: "file-text", sti: "/studie/eksamen.html" },
      { titel: "Deadlines", ikon: "clipboard-check", sti: "/studie/deadlines.html" },
    ],
  };

  fs.mkdirSync(UD, { recursive: true });
  const skriv = (navn, indhold) => { const tmp = path.join(UD, `${navn}.${process.pid}.tmp`); fs.writeFileSync(tmp, indhold); fs.renameSync(tmp, path.join(UD, navn)); };
  for (const n of ls(SIDER).filter(n => /\.(html|js|css|webmanifest|png)$/.test(n))) skriv(n, fs.readFileSync(path.join(SIDER, n)));
  skriv("studie.json", JSON.stringify(data));
  // Kalenderen til Ugeoverblik på telefonen. På Mac'en læser siden overbliks liv.json (/form/liv.json), men den
  // har også søvn, træning, forbrug og ugereviews og kommer derfor ikke med på telefonen. Her er kun kalenderen.
  const liv = (() => { try { return JSON.parse(læs(path.join(LIV_SITE, "liv.json"))); } catch { return null; } })();
  if (liv) skriv("kalender.json", JSON.stringify({ genereret: liv.genereret, selvstudie_fra: liv.selvstudie_fra || null, kalender: liv.kalender || {},
    reviews: (liv.reviews || []).map(r => ({ mandag: r.mandag, kalender: r.kalender || null, kommende: r.kommende || null })) }));
  let forrige = null;
  try { forrige = JSON.parse(læs(path.join(UD, "fagnoter.json"))); } catch { forrige = null; }
  const fn = fagnoter(forrige);
  skriv("fagnoter.json", JSON.stringify(fn));
  const fnUger = Object.values(fn).reduce((n, f) => n + Object.values(f.uger).filter(u => u.udfyldt).length, 0);
  // "nyt" pr. side: en nøgle for sidens nyeste indhold. Skifter den, viser menuen i Kompas en prik, til siden
  // er åbnet. Ugeoverblik: en ny køreplan (søndag). Fag: ny køreplan eller nye udfyldte fagnoter.
  // Deadlines: en frist er kommet til eller flyttet (færdig-markeringer og omformuleringer tæller ikke).
  const nyesteUge = Math.max(0, ...planer.map(p => p.uge));
  const fristNøgle = deadlines.map(d => `${d.noegle}@${d.dato || d.uger}`).sort().join("\n");
  const nyt = {
    "/studie/": nyesteUge ? `uge ${nyesteUge}` : null,
    "/studie/fag.html": nyesteUge ? `uge ${nyesteUge} · ${fnUger} fagnote-uger` : null,
    "/studie/deadlines.html": deadlines.length ? crypto.createHash("sha1").update(fristNøgle).digest("hex").slice(0, 10) : null,
  };
  for (const side of manifest.sider) if (nyt[side.sti]) side.nyt = nyt[side.sti];
  skriv("kompas.json", JSON.stringify(manifest));
  console.log(`Studie → ${UD}: ${planer.length} ugeplaner (aktuel uge ${aktuel?.uge ?? "–"}), ${deadlines.length} deadlines, ${fag.length} fag, ${fnUger} udfyldte fagnote-uger`);
}

main();
