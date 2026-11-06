// Studie → Kompas (https://kompas.localhost)
//
// Læser semestermappen og skriver det, Kompas viser under "Studie", til ~/.kompas/studie/ (eller STUDIE_EKSPORT_UD):
//   studie.json      køreplanerne (fra Studie-rutinen), frister, eksamensformer og status pr. fag, også fagets
//                    rytme: dine svar pr. dag, talt i Scripts/genkald-log.jsonl (som Studie-serveren skriver), og
//                    selvstudiet pr. dag fra sessionerne
//   fagnoter.json    ugeblokkene i Fagnoter-dokumenterne (Word) som html med omfang (ord, kodeblokke), dokumentets
//                    øvrige hovedafsnit (fx Eksamen) og de vurderinger, rutinen har rettet efter; billederne i fagnoter/<fag>/
//   resumeer.json    kapitelresuméerne (resumeer i fag.json, fx Alfa/Resumeer/*.md) som html pr. fag og uge
//   kompas.json        hvilke sider projektet har (Kompas bygger menuen ud fra den)
//   selvstudie.json  siden Selvstudie: tid pr. fag, dagsmål og medaljer, regnet af sessionerne og overbliks undervisning
//   semestre.json    siden Semestre: hvert semester (mapperne med Scripts/fag.json ved siden af dette) regnet på samme måde
//                    ud fra sine egne filer
//   sessioner.json   de afsluttede sessioner fra Scripts/sessioner.json til overblik (ugetabellen, dagsplanen, I dag)
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
// Køres af Kompas-appen, når den åbner, og af Studie-rutinen søndag efter en ny køreplan.

const fs = require("fs");
const path = require("path");
const os = require("os");
const { execFileSync } = require("child_process");
const crypto = require("crypto");
const S = require("./semester");
const SS = require("./sessioner");
const { tabel, isoDato, isoUge, mandagIUge, plusDage } = S;

const ROD = S.ROD;
const SIDER = path.join(__dirname, "kompas");
const argUd = process.argv.indexOf("--ud");
const hjem = s => s.replace(/^~(?=$|\/)/, os.homedir());
const UD = argUd > 0 ? path.resolve(process.argv[argUd + 1])
  : path.resolve(hjem(process.env.STUDIE_EKSPORT_UD || path.join(os.homedir(), ".kompas", "studie")));
const LIV_SITE = path.resolve(hjem(process.env.LIV_SITE || path.join(os.homedir(), ".garmin-coach", "site")));

// ── små hjælpere ─────────────────────────────────────────────────────

const læs = f => { try { return fs.readFileSync(f, "utf8"); } catch { return null; } };
const findes = f => { try { fs.accessSync(f); return true; } catch { return false; } };
const ls = d => { try { return fs.readdirSync(d).filter(n => !n.startsWith(".") && !n.startsWith("~$")); } catch { return []; } };
const mtime = f => { try { return fs.statSync(f).mtime; } catch { return null; } };

// ── markdown → html (det, planerne bruger: overskrifter, lister, tabeller, fed, kode) ──

// " escapes også: link-reglen og alt-teksterne sætter teksten ind i en attribut
const escHtml = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
// Billeder (![tekst](billeder/fil.png)) vises kun i resuméerne, som sætter billedSti til, hvor eksporten lægger
// dem; alle andre steder bliver de til deres tekst
let billedSti = null;
function inline(s) {
  const koder = [];
  s = escHtml(s).replace(/`([^`]+)`/g, (_, c) => `\u0000${koder.push(c) - 1}\u0000`);
  s = s.replace(/!\[([^\]]*)\]\(billeder\/([\w.-]+\.(?:png|jpe?g|webp))\)/g, (_, alt, fil) => billedSti
    ? `<img class="model" src="${billedSti}/${fil}" alt="${alt}" loading="lazy">` : alt);
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

// ── køreplaner fra Studie-rutinen ───────────────────────────────────

// "Noter til pensum" står kun i planer fra før noterne blev samlet i fagnoterne, og når fagnote-dokumentet var åbent
const DELAFSNIT = ["Hurtigt overblik", "Kilder", "Noter til pensum", "Træning", "Til rapporten", "Video"];

// Øvelsesspørgsmål i en plan: fra "*Øvelsesspørgsmål …*" eller "*Pensumspørgsmål:* …" til "*Svar …*" eller
// "*Disponeret … svar*", og svaret til delafsnittets slutning. Øvelsen tages ud af delafsnittet (buf ændres), så
// Fag-siden kan vise den for sig med svaret skjult, til du har svaret selv.
function splitOevelse(buf) {
  const ren = xs => { while (xs.length && /^(---+)?\s*$/.test(xs[xs.length - 1])) xs.pop(); return xs.join("\n"); };
  for (const [k, l] of Object.entries(buf)) {
    const q = l.findIndex(x => /^\*(Øvelsesspørgsmål|Pensumspørgsmål)/.test(x.trim()));
    if (q < 0) continue;
    const a = l.findIndex((x, i) => i > q && /^\*(Svar|Disponeret)/.test(x.trim()));
    if (a < 0) return null;
    buf[k] = l.slice(0, q);
    return { spoergsmaal: md(ren(l.slice(q, a))), svar: md(ren(l.slice(a + 1))) };
  }
  return null;
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
    const fag = S.fag().find(f => a.titel.startsWith(f.fagnoter_overskrift));
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
      const oev = splitOevelse(buf);
      for (const [k, v] of Object.entries(buf)) if (v.join("").trim()) dele[k] = md(v.join("\n"));
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

// ── LeetCode pr. uge (leetcode i fag.json) ──────────────────────────────

// "## Uge N — emne", en valgfri note og én linje pr. opgave:
// "- [2634. Filter Elements from Array](https://leetcode.com/problems/filter-elements-from-array/) · Easy · hvorfor"
function leetcode() {
  const f = S.fagMed("leetcode")[0];
  const fil = f && path.join(ROD, f.mappe, f.leetcode), tekst = f && læs(fil);
  if (!tekst) return null;
  const uger = {};
  for (const a of tekst.split(/^## /m).slice(1)) {
    const m = a.match(/^Uge (\d+)\s*[—–-]?\s*(.*)\n([\s\S]*)$/);
    if (!m) continue;
    const opgaver = [], note = [];
    for (const l of m[3].split("\n")) {
      const o = l.match(/^- \[(\d+)\. (.+?)\]\((https:\/\/leetcode\.com\/problems\/[\w-]+\/)\) · (Easy|Medium|Hard)(?: · (.*))?$/);
      if (o) opgaver.push({ nr: +o[1], titel: o[2], url: o[3], niveau: o[4], hvorfor: o[5] ? inline(o[5]) : null });
      else note.push(l);
    }
    uger[m[1]] = { emne: m[2].trim(), note: note.join("").trim() ? md(note.join("\n")) : null, opgaver };
  }
  return { fag: f.id, fil: `${f.mappe}/${f.leetcode}`, uger };
}

// ── Studieguide pr. fag og uge (fx Alfa/studieguide.md) ───────────────

// Teksten før første "## Uge N — emne" er fagets generelle tilgang; hver uge er markdown med trin, videoer og
// "Kun én time?". Fag-siden viser ugen udfoldelig over køreplanen.
function studieguide() {
  const ud = {};
  for (const f of S.fagMed("studieguide")) {
    const tekst = læs(path.join(ROD, f.mappe, f.studieguide));
    if (!tekst) continue;
    const [hoved, ...afsnit] = tekst.split(/^## /m), uger = {};
    for (const a of afsnit) {
      const m = a.match(/^Uge (\d+)\s*[—–-]?\s*(.*)\n([\s\S]*)$/);
      if (!m) continue;
      const krop = m[3].replace(/\n---+\s*$/, "").trim();
      uger[m[1]] = { emne: m[2].trim(), html: md(krop), videoer: (krop.match(/https:\/\/(www\.)?(youtube\.com|youtu\.be)\//g) || []).length };
    }
    const intro = hoved.replace(/^# .*\n/, "").trim();
    ud[f.id] = { fil: `${f.mappe}/${f.studieguide}`, intro: intro ? md(intro) : null, uger };
  }
  return ud;
}

// ── Kapitelresuméer pr. fag og uge (fx Alfa/Resumeer/bog-kap05-netvaerk.md) ──

// Første linje "# Bog kap. 5 — Netværk … (uge 37)" giver titlen og ugen; "(uge 38-39)" og "(uge 36 og 37)" hører
// til flere uger. Et resumé uden uge i overskriften kommer ikke med. Modellerne (slides og figurer) ligger i
// <mappe>/billeder/ og kopieres af main til <UD>/resumeer/<fag>/.
function resumeer() {
  const ud = {};
  for (const f of S.fagMed("resumeer")) {
    const mappe = path.join(ROD, f.mappe, f.resumeer), uger = {};
    billedSti = `resumeer/${f.id}`;
    for (const n of ls(mappe).filter(n => n.endsWith(".md")).sort()) {
      const tekst = læs(path.join(mappe, n)) || "";
      const m = tekst.match(/^# (.+?)\s*\(uge ([\d\s,og–-]+)\)\s*\n([\s\S]*)$/);
      if (!m) continue;
      const nr = [];
      for (const del of m[2].split(/,|\bog\b/)) {
        const [a, b] = del.trim().split(/\s*[–-]\s*/).map(Number);
        if (a) for (let u = a; u <= (b || a); u++) nr.push(u);
      }
      const r = { titel: m[1], fil: `${f.mappe}/${f.resumeer}/${n}`, ord: m[3].split(/\s+/).filter(Boolean).length, html: md(m[3]) };
      for (const u of nr) (uger[u] ||= []).push(r);
    }
    ud[f.id] = { mappe: `${f.mappe}/${f.resumeer}`, uger };
  }
  billedSti = null;
  return ud;
}

// ── frister og eksamener ───────────────────────────────────────────

// En frist som html (selve tolkningen ligger i semester.js, så serveren bruger samme)
function deadline(r, aar, planUge) {
  const d = S.deadline(r, aar, planUge);
  return { ...d, hvad: inline(d.hvad), note: d.note ? inline(d.note) : null };
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

function afleveringsTabel(fil) {
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

// Selvstudiet pr. fag fra sessionerne (Scripts/sessioner.json): i alt, pr. ISO-uge (mandagens dato), pr. måned, pr. dag og
// antal sessioner pr. dag, alt under den dag, sessionen begyndte. Stopuret, der kører, tæller først, når det er stoppet.
function selvstudiePrFag(log) {
  const ud = {};
  for (const s of log?.sessioner || []) {
    const t = SS.timer(s), d = new Date(SS.start(s)), dag = isoDato(d), m = isoDato(plusDage(d, -((d.getDay() + 6) % 7)));
    const x = ud[s.fag] ||= { timer: 0, uger: {}, maaneder: {}, dage: {}, sessioner: {} };
    x.timer += t; x.uger[m] = (x.uger[m] || 0) + t; x.maaneder[dag.slice(0, 7)] = (x.maaneder[dag.slice(0, 7)] || 0) + t; x.dage[dag] = (x.dage[dag] || 0) + t; x.sessioner[dag] = (x.sessioner[dag] || 0) + 1;
  }
  return ud;
}

// Rytmen (siden Selvstudie, som Athenifys Weekdays og Time of day): hvornår du studerer, efter uret, ikke den dag,
// sessionen begyndte. Hvert stykke deles ved hver hele time, så en session fra 23.30 til 00.30 giver en halv time til
// hver dag. For denne uge (mandag til nu), denne måned og alt fra logningen begyndte: timer pr. ugedag (mandag først),
// pr. time på døgnet (0-23) og pr. tidsrum på fire timer (2-6, 6-10, …, 22-2) med andelen af periodens tid.
const TIDSRUM = [2, 6, 10, 14, 18, 22];
function rytmeFor(log, nu = new Date()) {
  if (!log) return null;
  const r2 = x => Math.round(x * 100) / 100;
  const mandag = new Date(nu.getFullYear(), nu.getMonth(), nu.getDate() - (nu.getDay() + 6) % 7).getTime();
  const perioder = { uge: mandag, maaned: new Date(nu.getFullYear(), nu.getMonth(), 1).getTime(), alt: -Infinity };
  const ud = Object.fromEntries(Object.keys(perioder).map(k => [k, { ugedage: Array(7).fill(0), timer: Array(24).fill(0) }]));
  for (const s of log.sessioner) for (const [a, b] of s.stykker) {
    for (let t = Date.parse(a), slut = Math.min(Date.parse(b), nu.getTime()); t < slut;) {
      const d = new Date(t), næste = Math.min(slut, new Date(d.getFullYear(), d.getMonth(), d.getDate(), d.getHours() + 1).getTime()), h = (næste - t) / 36e5;
      for (const [k, fra] of Object.entries(perioder)) if (t >= fra) { ud[k].ugedage[(d.getDay() + 6) % 7] += h; ud[k].timer[d.getHours()] += h; }
      t = næste;
    }
  }
  for (const x of Object.values(ud)) {
    const i_alt = x.timer.reduce((a, v) => a + v, 0);
    x.tidsrum = TIDSRUM.map(fra => { const t = [0, 1, 2, 3].reduce((a, i) => a + x.timer[(fra + i) % 24], 0);
      return { fra, til: (fra + 4) % 24, timer: r2(t), pct: i_alt ? Math.round(100 * t / i_alt) : 0 }; });
    const størst = Math.max(...x.tidsrum.map(t => t.timer));
    x.tidsrum.forEach(t => { if (størst > 0 && t.timer === størst) t.stoerst = true; });
    x.i_alt = r2(i_alt); x.ugedage = x.ugedage.map(r2); x.timer = x.timer.map(r2);
  }
  return ud;
}

// Siden Selvstudie: tid pr. fag mod kursusbeskrivelsens arbejdstimer (arbejdsbyrde i fag.json). Selvstudiet er sessionerne
// (log, se selvstudiePrFag). Undervisningen kommer fra overbliks liv.json (studietid) pr. kursuskode, når den er slut,
// og studieblokkene derfra. Forventet til nu regnes kun for et fag, der løber ét semester og har en
// eksamensdato: kursets timer jævnt fordelt fra første undervisningsdag til eksamen. Kurser over to semestre deler
// kursusbeskrivelsen ikke op, så dér er det null med grunden. Siden regner intet selv.
function selvstudie(liv, log, nu = new Date(), sem = S) {
  const st = liv?.studietid || null, prFag = selvstudiePrFag(log), eks = sem.eksamensdatoer(nu), r1 = x => Math.round(x * 10) / 10;
  let dage = {}; try { dage = JSON.parse(læs(path.join(sem.DATA, "undervisningsdage.json")) || "{}"); } catch {}
  const navne = f => [f.kort, ...(f.alias || []), f.id].map(x => String(x).toLowerCase());
  // Semestrets periode (første undervisningsdag til sidste eksamen, semester.js): kalenderens undervisning og studieblokke i
  // uger uden for den hører til et andet semester (et kursus over to semestre har samme kursuskode i begge). Uden kendt periode tæller alt.
  const per = sem.periode(), perFra = per && isoDato(plusDage(new Date(`${per.fra}T12:00`), -((new Date(`${per.fra}T12:00`).getDay() + 6) % 7)));
  const iPeriode = m => !per || (m >= perFra && m <= per.til);
  // Fravær (Scripts/fravaer.json): uger, hvor du ikke var til stede; kalenderens undervisning i dem tæller ikke som brugt
  // og slags undervisning, du aldrig bruger (bruges_ikke: fag, art og form som i kalenderen), som ikke tæller i nogen uge
  let fravær = [], brugesIkke = [];
  try { const fj = JSON.parse(læs(path.join(sem.DATA, "fravaer.json")) || "{}"); fravær = fj.ikke_til_stede || []; brugesIkke = fj.bruges_ikke || []; } catch {}
  // Fremmøde (Scripts/fremmoede.json, som du markerer på Selvstudie): de undervisningsgange, du ikke var til, som
  // "<kursuskode>|<dato>T<start>"
  let ikkeHer = new Set();
  try { ikkeHer = new Set(JSON.parse(læs(path.join(sem.DATA, "fremmoede.json")) || "{}").ikke || []); } catch {}
  const forFag = (f, x) => !x.fag || navne(f).includes(String(x.fag).toLowerCase());
  const fraværende = (f, mandag) => fravær.some(x => x.uge === isoUge(new Date(`${mandag}T12:00`)) && forFag(f, x));
  const ubrugt = (f, fo) => brugesIkke.some(x => forFag(f, x) && (x.art == null || x.art === fo.art) && (x.form == null || x.form === fo.form));
  const fag = sem.fag().filter(f => f.arbejdsbyrde?.poster?.length).map(f => {
    const ab = f.arbejdsbyrde, sum = xs => r1(xs.reduce((a, x) => a + x.timer, 0));
    // Et kursus over flere semestre med dette semesters del (dette_semester i fag.json, en vurdering, når kursusbeskrivelsen
    // ikke deler timerne op): posterne er semestrets, og om de er undervisning, står ved kursets poster med samme navn
    const ds = (ab.semestre || 1) > 1 && ab.dette_semester?.poster?.length ? ab.dette_semester : null;
    const poster = ds ? ds.poster.map(p => ({ ...p, undervisning: !!ab.poster.find(q => q.navn === p.navn)?.undervisning })) : ab.poster;
    const forventet = { i_alt: sum(poster), undervisning: sum(poster.filter(x => x.undervisning)),
      selvstudie: sum(poster.filter(x => !x.undervisning)), poster, kilde: ab.kilde, semestre: ab.semestre || 1,
      ...(ds ? { dette_semester: true, hele_kurset: sum(ab.poster), vurdering: ds.vurdering || null } : {}) };
    const u = (st?.undervisning || []).find(x => x.kode === f.kursuskode);
    const s = prFag[f.id];
    const b = (st?.studieblokke || []).find(x => navne(f).includes(String(x.navn).toLowerCase()));
    // Undervisningen pr. uge: kun de slags, du bruger, og ikke de gange, du ikke var til (fremmøde) eller uger med fravær.
    // Har overblik gangene enkeltvis, regnes der gang for gang, og de kommer med til Fremmøde på siden (uden de slags,
    // du aldrig bruger); ellers pr. slags og uge.
    const uUger = {}, gange = [];
    let ikkeTaltFravær = 0, ikkeBrugt = 0;
    if (u?.gange) for (const g of u.gange) {
      const d = new Date(`${g.dato}T12:00`), m = isoDato(plusDage(d, -((d.getDay() + 6) % 7)));
      if (!iPeriode(m)) continue;
      const id = `${f.kursuskode}|${g.dato}T${g.start}`;
      const status = ubrugt(f, g) ? "bruges_ikke" : ikkeHer.has(id) ? "ikke" : fraværende(f, m) ? "uge" : "talt";
      if (status === "bruges_ikke") ikkeBrugt += g.timer; else if (status === "talt") uUger[m] = (uUger[m] || 0) + g.timer; else ikkeTaltFravær += g.timer;
      if (status !== "bruges_ikke") gange.push({ id, dato: g.dato, start: g.start, slut: g.slut, art: g.art, form: g.form, timer: g.timer, status });
    } else for (const fo of u?.former || (u ? [{ art: "", form: "", uger: u.uger }] : [])) for (const [m, x] of Object.entries(fo.uger || {})) {
      if (!iPeriode(m)) continue;
      if (ubrugt(f, fo)) ikkeBrugt += x; else if (fraværende(f, m)) ikkeTaltFravær += x; else uUger[m] = (uUger[m] || 0) + x;
    }
    const ikkeTalt = r1(ikkeTaltFravær + ikkeBrugt);
    const brugt = { undervisning: r1(Object.values(uUger).reduce((a, x) => a + x, 0)), selvstudie: r1(s?.timer || 0), studieblokke_forbi: r1(per ? Object.entries(b?.uger || {}).filter(([m]) => iPeriode(m)).reduce((a, [, x]) => a + x, 0) : b?.timer || 0),
      studieblokke_planlagt: r1(b?.planlagt_timer || 0) };
    brugt.i_alt = r1(brugt.undervisning + brugt.selvstudie);
    const uger = [...new Set([...Object.keys(u?.uger || {}).filter(iPeriode), ...Object.keys(s?.uger || {})])].sort().map(m => ({
      mandag: m, uge: isoUge(new Date(`${m}T12:00`)), undervisning: r1(uUger[m] || 0), selvstudie: r1(s?.uger?.[m] || 0),
      ...(fraværende(f, m) ? { fravaer: true } : {}) }));
    // Forventet til nu: ét semester (eller dette semesters del) jævnt fordelt fra første undervisningsdag til eksamen, eller
    // til sidste undervisningsdag, når semestret ikke har en eksamen i faget (dette_semester.til). Undervisningsdagene står
    // som datoer eller som { dato }.
    const datoer = Object.values(dage[f.kort] || {}).flat().map(x => typeof x === "string" ? x : x?.dato).filter(Boolean).sort();
    const start = datoer[0] ? new Date(`${datoer[0]}T00:00`) : null;
    const slut = ds?.til === "sidste_undervisning" ? (datoer.length ? new Date(`${datoer.at(-1)}T23:59`) : null) : eks[f.id] ? new Date(eks[f.id]) : null;
    let til_nu = null, grund = null;
    if (forventet.semestre !== 1 && !ds) grund = `Kurset løber over ${forventet.semestre} semestre, og kursusbeskrivelsen deler ikke timerne op pr. semester.`;
    else if (!start || !slut) grund = !slut ? (ds?.til === "sidste_undervisning" ? "Sidste undervisningsdag kendes ikke (undervisningsdage.json)." : "Eksamensdatoen kendes ikke (Vigtige datoer i CLAUDE.md).")
      : "Første undervisningsdag kendes ikke (undervisningsdage.json).";
    else {
      const andel = Math.min(1, Math.max(0, (nu - start) / (slut - start)));
      til_nu = { i_alt: r1(forventet.i_alt * andel), undervisning: r1(forventet.undervisning * andel), selvstudie: r1(forventet.selvstudie * andel),
        andel: Math.round(andel * 100), fra: isoDato(start), til: isoDato(slut), til_er: ds?.til === "sidste_undervisning" ? "sidste_undervisning" : "eksamen" };
    }
    // Forudsigelse: kun med en slutdato forude og et kendt forventet for semestret: det selvstudie, der mangler, fordelt på ugerne dertil
    let forudsigelse = null;
    if ((forventet.semestre === 1 || ds) && slut && slut > nu) {
      const tilbage = Math.max(0, forventet.selvstudie - brugt.selvstudie), uger = (slut - nu) / (7 * 864e5);
      forudsigelse = { tilbage: r1(tilbage), uger_tilbage: r1(uger), pr_uge: r1(tilbage / uger), eksamen: isoDato(slut) };
    }
    const maaneder = Object.fromEntries(Object.entries(s?.maaneder || {}).sort().map(([k, v]) => [k, r1(v)]));
    return { id: f.id, kort: f.kort, navn: f.navn, farve: f.farve, kursuskode: f.kursuskode, forventet, brugt, forventet_til_nu: til_nu, grund, uger, maaneder,
      forudsigelse, undervisning_ikke_talt: ikkeTalt, ikke_talt: { fravaer: r1(ikkeTaltFravær), bruges_ikke: r1(ikkeBrugt) }, gange, _dage: s?.dage || {},
      _sessioner: s?.sessioner || {} };
  });
  const motivation = motivationFor(fag, log?.fra, nu, sem);
  fag.forEach(f => { delete f._dage; delete f._sessioner; });
  const sum = k => r1(fag.reduce((a, f) => a + f.brugt[k], 0));
  return { genereret: nu.toISOString(), periode: per, kalender_fra: st?.fra && per?.fra > st.fra ? per.fra : st?.fra || null, selvstudie_fra: log?.fra || null, til: st?.til || null, motivation, rytme: rytmeFor(log, nu),
    i_alt: { undervisning: sum("undervisning"), selvstudie: sum("selvstudie"), brugt: sum("i_alt") }, fag,
    // Logget selvstudie i et fag uden arbejdsbyrde i fag.json (eller et fag, der ikke længere står dér)
    ukendt: Object.entries(prFag).filter(([id]) => !fag.some(f => f.id === id)).map(([id, x]) => ({ navn: sem.find(id)?.kort || id, timer: r1(x.timer) })),
    fravaer: fravær.map(x => ({ uge: x.uge, fag: x.fag || null })),
    bruges_ikke: brugesIkke.map(x => ({ fag: x.fag || null, art: x.art ?? null, form: x.form ?? null, hvorfor: x.hvorfor || null })),
    mangler: !log ? "Scripts/sessioner.json kunne ikke læses (ligger den kun i skyen?)."
      : st ? null : "liv.json har ingen studietid (overblik eller træningsdelen mangler)." };
}

// Athenify-delen af Selvstudie, regnet ud fra det loggede selvstudie pr. dag og dine mål (studiemaal i fag.json):
// dagens, ugens og månedens fremskridt mod målet, dage i træk, medaljer, saldoen (den samlede forskel til dagsmålet,
// dag for dag fra logningen begyndte), de seneste 7 dage, en kalender og nedtællingen til eksamen. I dag er ikke slut:
// dage i træk tæller fra i går, når der ikke er logget noget i dag endnu. Uden mål eller data er den null.
function motivationFor(fag, start, nu = new Date(), sem = S) {
  const m = sem.studiemaal();
  if (!m?.dag_timer || !start) return null;
  // Til hundrededele af en time (36 sekunder), så en session fra stopuret står med de minutter, den varede
  const r1 = x => Math.round(x * 100) / 100, mål = m.dag_timer, med = m.medaljer || {};
  // Dagsmålet gælder på dine studiedage (dage i studiemaal); de andre er fridage: målet er 0 der, de trækker ikke saldoen
  // ned og bryder ikke dage i træk, men det, du alligevel studerer, tæller
  const studiedage = Array.isArray(m.dage) && m.dage.length ? [...new Set(m.dage)].filter(x => x >= 0 && x <= 6).sort() : [0, 1, 2, 3, 4, 5, 6];
  const ugedagAf = d => (d.getDay() + 6) % 7, målFor = d => studiedage.includes(ugedagAf(d)) ? mål : 0;
  const pct = (t, mm) => mm ? Math.round(100 * t / mm) : t > 0 ? 100 : 0;
  const medalje = t => t >= med.guld ? "guld" : t >= med.soelv ? "soelv" : t >= med.bronze ? "bronze" : null;
  const idag = isoDato(nu), dage = [];
  for (let d = new Date(`${start}T12:00`); isoDato(d) <= idag; d = plusDage(d, 1)) {
    const dato = isoDato(d), pr_fag = {}, maal_dag = målFor(d);
    for (const f of fag) if (f._dage[dato]) pr_fag[f.id] = r1(f._dage[dato]);
    const timer = r1(Object.values(pr_fag).reduce((a, x) => a + x, 0)), sessioner = fag.reduce((a, f) => a + (f._sessioner[dato] || 0), 0);
    dage.push({ dato, uge: isoUge(d), ugedag: ugedagAf(d), timer, pr_fag, sessioner, maal_dag, fridag: !maal_dag,
      naaet: maal_dag ? timer >= maal_dag : null, medalje: medalje(timer) });
  }
  let saldo = 0;
  for (const d of dage) { saldo += d.timer - d.maal_dag; d.saldo = r1(saldo); }
  // Dage i træk: fra i dag (eller i går, hvis intet er logget i dag endnu) og bagud. En fridag uden selvstudie springes over.
  const iTræk = krav => {
    let n = 0, i = dage.length - 1;
    if (i >= 0 && !krav(dage[i]) && !dage[i].fridag) i--;
    for (; i >= 0; i--) { if (krav(dage[i])) n++; else if (!dage[i].fridag) break; }
    return n;
  };
  let længst = 0, løb = 0; for (const d of dage) { løb = d.timer > 0 ? løb + 1 : d.fridag ? løb : 0; længst = Math.max(længst, løb); }
  // En periode: det loggede fra fra og målet for antal dage fra fra (også dage, der ikke er kommet endnu)
  const periode = (fra, antal) => { const ds = dage.filter(d => d.dato >= fra), timer = r1(ds.reduce((a, d) => a + d.timer, 0));
    let m2 = 0; for (let k = 0; k < antal; k++) m2 += målFor(plusDage(new Date(`${fra}T12:00`), k));
    return { timer, maal: r1(m2), pct: pct(timer, m2), medaljer: { guld: ds.filter(d => d.medalje === "guld").length,
      soelv: ds.filter(d => d.medalje === "soelv").length, bronze: ds.filter(d => d.medalje === "bronze").length } }; };
  const mandag = isoDato(plusDage(nu, -((nu.getDay() + 6) % 7))), første = `${idag.slice(0, 8)}01`;
  const dageIMåned = new Date(nu.getFullYear(), nu.getMonth() + 1, 0).getDate();
  // Kalenderen: hele uger (mandag til søndag) fra logningens første uge; dage efter i dag er tomme
  const kalender = []; const uge0 = plusDage(new Date(`${start}T12:00`), -((new Date(`${start}T12:00`).getDay() + 6) % 7));
  for (let w = uge0; isoDato(w) <= idag; w = plusDage(w, 7)) kalender.push({ uge: isoUge(w), mandag: isoDato(w),
    dage: [0, 1, 2, 3, 4, 5, 6].map(i => { const dato = isoDato(plusDage(w, i)), d = dage.find(x => x.dato === dato);
      return { dato, timer: d ? d.timer : null, niveau: d ? Math.min(1, d.timer / (med.guld || mål * 2)) : null, medalje: d?.medalje || null }; }) });
  // Månedskalenderen (som Athenifys): hver måned fra logningens første til denne, med studietid, mål (hele månedens dage
  // gange dagsmålet), sessioner og dagene; en dag før logningen eller efter i dag har timer null. trin 0–4: intet, under
  // bronze, bronze, sølv, guld (cellens farve). Målet tæller kun dagene fra logningen begyndte.
  const trin = t => t == null ? null : !t ? 0 : t >= med.guld ? 4 : t >= med.soelv ? 3 : t >= med.bronze ? 2 : 1;
  const MÅNEDER = ["januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober", "november", "december"];
  const maaneder = [];
  for (let mm = new Date(`${start.slice(0, 7)}-01T12:00`); isoDato(mm).slice(0, 7) <= idag.slice(0, 7); mm = new Date(mm.getFullYear(), mm.getMonth() + 1, 1, 12)) {
    const n = new Date(mm.getFullYear(), mm.getMonth() + 1, 0).getDate(), ds = [];
    for (let i = 1; i <= n; i++) { const dato = isoDato(new Date(mm.getFullYear(), mm.getMonth(), i, 12)), d = dage.find(x => x.dato === dato);
      ds.push({ dag: i, dato, timer: d ? d.timer : null, sessioner: d ? d.sessioner : null, medalje: d?.medalje || null, trin: trin(d ? d.timer : null) }); }
    const timer = r1(ds.reduce((a, d) => a + (d.timer || 0), 0));
    const maal = r1(ds.filter(d => d.dato >= start).reduce((a, d) => a + målFor(new Date(`${d.dato}T12:00`)), 0));  // fra logningen begyndte
    maaneder.push({ maaned: isoDato(mm).slice(0, 7), navn: `${MÅNEDER[mm.getMonth()]} ${mm.getFullYear()}`, forskyd: (mm.getDay() + 6) % 7,
      timer, maal, pct: pct(timer, maal), sessioner: ds.reduce((a, d) => a + (d.sessioner || 0), 0), dage: ds });
  }
  const eks = sem.eksamensdatoer(nu);
  const DAGE = ["man", "tir", "ons", "tor", "fre", "lør", "søn"];
  const gaelder = studiedage.length === 7 ? "alle dage" : studiedage.join() === "0,1,2,3,4" ? "man–fre" : studiedage.map(i => DAGE[i]).join(", ");
  return { maal: mål, maaneder, saldo_i_dag: r1((dage.at(-1)?.timer || 0) - (dage.at(-1)?.maal_dag || 0)), gaelder, studiedage, medaljer_graenser: med, fra: start,
    i_dag: { ...periode(idag, 1), medalje: dage.at(-1)?.medalje || null },
    uge: periode(mandag, 7), maaned: periode(første, dageIMåned), i_alt: periode(start, dage.length),
    i_traek: iTræk(d => d.timer > 0), i_traek_maal: iTræk(d => d.naaet), laengst_i_traek: længst,
    saldo: r1(saldo), seneste_7: dage.slice(-7), dage, kalender,
    eksamener: Object.entries(eks).filter(([, t]) => t >= new Date(idag).getTime() - 864e5).map(([id, t]) => {
      const f = sem.find(id); return { fag: f?.kort || id, dato: isoDato(new Date(t)), dage: Math.round((t - new Date(`${idag}T00:00`).getTime()) / 864e5) }; })
      .sort((a, b) => a.dato.localeCompare(b.dato)) };
}

// Siden Semestre: hvert semester (mapperne med Scripts/fag.json ved siden af dette, S.semestermapper) med periode, fag,
// selvstudiet pr. fag mod det forventede, saldo og medaljer, regnet af selvstudie() med det semesters egne filer (fag.json,
// sessioner.json, undervisningsdage.json, fravaer.json, studiemaal.json, CLAUDE.md) og overbliks undervisning. Et
// tidligere semester regnes til sin slutdato eller den sidste session, hvis den kom senere, så tallene er dem, Selvstudie
// viste, da semestret sluttede. Kun læsning. Det aktuelle semester står først, så de andre med det nyeste først.
function semestre(liv, nu = new Date()) {
  const r1 = x => Math.round(x * 10) / 10, liste = [];
  for (const rod of S.semestermapper()) {
    const aktuel = path.resolve(rod) === path.resolve(ROD), x = { navn: path.basename(rod), mappe: path.basename(rod), aktuel };
    try {
      if (læs(path.join(rod, "Scripts", "fag.json")) == null) throw new Error("Scripts/fag.json kunne ikke læses (ligger den kun i skyen?)");
      const sem = aktuel ? S : S.forMappe(rod), per = sem.periode(), log = SS.læs(path.join(rod, "Scripts", "sessioner.json"));
      let til = nu;
      if (!aktuel) {
        const sidste = Math.max(per ? Date.parse(`${per.til}T23:59`) : -Infinity, ...log.sessioner.map(s => Date.parse(SS.slut(s))).filter(Number.isFinite));
        if (Number.isFinite(sidste) && sidste < nu.getTime()) til = new Date(sidste);
      }
      const ss = selvstudie(liv, log, til, sem), mv = ss.motivation;
      Object.assign(x, { navn: sem.semester(), periode: per, regnet_til: isoDato(til), selvstudie_fra: log.fra, sessioner: log.sessioner.length,
        fag: ss.fag.map(f => ({ id: f.id, kort: f.kort, navn: f.navn, farve: f.farve, kursuskode: f.kursuskode, brugt: f.brugt, grund: f.grund,
          forventet: { i_alt: f.forventet.i_alt, undervisning: f.forventet.undervisning, selvstudie: f.forventet.selvstudie, semestre: f.forventet.semestre,
            ...(f.forventet.dette_semester ? { dette_semester: true, hele_kurset: f.forventet.hele_kurset } : {}) },
          forventet_til_nu: f.forventet_til_nu && { selvstudie: f.forventet_til_nu.selvstudie, undervisning: f.forventet_til_nu.undervisning, i_alt: f.forventet_til_nu.i_alt, andel: f.forventet_til_nu.andel },
          pct: f.forventet.selvstudie ? Math.round(100 * f.brugt.selvstudie / f.forventet.selvstudie) : null })),
        i_alt: ss.i_alt, ukendt: ss.ukendt,
        // Det forventede i semestret: selvstudiet (med andelen, du har logget) og den skemalagte undervisning
        forventet: (fv => ({ selvstudie: fv, pct: fv ? Math.round(100 * ss.i_alt.selvstudie / fv) : null,
          undervisning: r1(ss.fag.reduce((a, f) => a + f.forventet.undervisning, 0)) }))(r1(ss.fag.reduce((a, f) => a + f.forventet.selvstudie, 0))),
        motivation: mv && { maal: mv.maal, gaelder: mv.gaelder, saldo: mv.saldo, timer: mv.i_alt.timer, maal_i_alt: mv.i_alt.maal, pct: mv.i_alt.pct,
          medaljer: mv.i_alt.medaljer, laengst_i_traek: mv.laengst_i_traek, dage: mv.dage.length, dage_med_selvstudie: mv.dage.filter(d => d.timer > 0).length },
        mangler: ss.mangler });
    } catch (e) { x.mangler = e.message; }
    liste.push(x);
  }
  liste.sort((a, b) => b.aktuel - a.aktuel || String(b.periode?.fra || "").localeCompare(String(a.periode?.fra || "")));
  // Alle semestre samlet: selvstudie, undervisning, sessioner og medaljer
  const ok = liste.filter(x => x.i_alt), sum = f => r1(ok.reduce((a, x) => a + (f(x) || 0), 0));
  return { genereret: nu.toISOString(), aktuelt: liste.find(x => x.aktuel)?.navn || null, semestre: liste,
    i_alt: { semestre: liste.length, selvstudie: sum(x => x.i_alt.selvstudie), undervisning: sum(x => x.i_alt.undervisning), sessioner: sum(x => x.sessioner),
      medaljer: Object.fromEntries(["guld", "soelv", "bronze"].map(k => [k, sum(x => x.motivation?.medaljer?.[k])])) } };
}

// Forelæsninger og øvelser i <mappe>/Pensum/, som canvas-sortering.js har lagt der med undervisningsdagen
// forrest i navnet. Kun navnene; Studie-serveren udleverer selve filen (/studie/api/pensum/...).
// Er navnet bare "FL2", får det dagens emne fra undervisningsdage.json.
const PENSUM = { forelaesninger: "Forelæsninger", oevelser: "Øvelser" };
function pensum(f) {
  let dage = {}; try { dage = JSON.parse(læs(path.join(S.DATA, "undervisningsdage.json")) || "{}")[f.kort] || {}; } catch {}
  const ud = {};
  for (const [k, mappe] of Object.entries(PENSUM)) {
    ud[k] = ls(path.join(ROD, f.mappe, "Pensum", mappe)).filter(n => /^\d{8}[_ -]/.test(n)).sort().map(n => {
      const dato = `${n.slice(0, 4)}-${n.slice(4, 6)}-${n.slice(6, 8)}`;
      let titel = n.slice(9).replace(/\.[^.]+$/, "").replace(/^[\s_-]+/, "").replace(/_+/g, " ").replace(/\s+/g, " ").trim();
      const emne = (dage[mappe] || []).find(x => x.dato === dato)?.emne;
      if (emne && !/[a-zæøå]{3}/i.test(titel.replace(/^FL\s*\d+/i, ""))) titel = `${titel} · ${emne}`;
      return { fil: n, mappe, dato, uge: isoUge(new Date(`${dato}T12:00`)), titel };
    });
  }
  return ud;
}

// Rytme: dine svar pr. dag i faget, fra genkald-log.jsonl, og dit selvstudie pr. dag fra sessionerne (timer, under den
// dag, sessionen begyndte, som i selvstudiePrFag). Drills hører til faget med kode; genkald og eksamen til fagets id
// forrest i nøglen. En færdig-markeret frist er ikke et svar. fra er mandag i semestrets første køreplansuge, så siden
// kan vise dage uden noget som tomme.
let logLinjer = null;
function rytme(f, fra, ssDage = {}) {
  logLinjer ??= (læs(path.join(S.DATA, "genkald-log.jsonl")) || "").split("\n").filter(Boolean);
  const dage = {};
  for (const l of logLinjer) {
    let p; try { p = JSON.parse(l); } catch { continue; }
    if (!p?.tid || p.type === "deadline") continue;
    const hvem = /^drill/.test(p.type) ? (f.kode ? f.id : null) : String(p.noegle || "").split("/")[0];
    if (hvem !== f.id) continue;
    const dag = isoDato(new Date(p.tid));
    dage[dag] = (dage[dag] || 0) + 1;
  }
  const timer = Object.fromEntries(Object.entries(ssDage).map(([d, t]) => [d, Math.round(t * 10) / 10]).filter(([, t]) => t > 0));
  const n = Object.values(dage), t = Object.values(timer), datoer = [...new Set([...Object.keys(dage), ...Object.keys(timer)])].sort();
  return { fra: fra ? isoDato(fra) : datoer[0] || null, til: isoDato(new Date()), dage, timer,
    svar: n.reduce((a, x) => a + x, 0), timer_i_alt: Math.round(t.reduce((a, x) => a + x, 0) * 10) / 10, aktive_dage: datoer.length,
    flest: n.length ? Math.max(...n) : 0, flest_timer: t.length ? Math.max(...t) : 0, seneste: datoer.at(-1) || null };
}

// En øvelse (fil eller mappe) tæller som færdig, når der står din egen kode i en .js- eller .css-fil i den.
// Skabelonerne til kommende øvelsessæt har kun kommentarer, tomme blokke og overskrifter i konsollen.
function egenKode(p) {
  if (fs.statSync(p, { throwIfNoEntry: false })?.isDirectory()) return ls(p).some(n => egenKode(path.join(p, n)));
  if (!/\.(js|css)$/i.test(p)) return false;
  return (læs(p) || "").replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1")
    .split("\n").some(l => !/^\s*$|^\s*[{}();]+\s*$|^\s*console\.log\("\\n=== [^"]* ==="\);?\s*$/.test(l));
}

function fagStatus(f, fra, ssDage) {
  const d = path.join(ROD, f.mappe);
  const s = { aktivitet: aktivitet(f.mappe), pensum: pensum(f), rytme: rytme(f, fra, ssDage),
    // De gamle sæt er filer som Alfa_Eksamener.pdf; mappen Eksamenstræning er Kompas' opgaver ud fra dem
    eksamenssaet: ls(d).filter(n => /eksamen/i.test(n) && !/træning/i.test(n) && fs.statSync(path.join(d, n), { throwIfNoEntry: false })?.isFile()),
    fagnoter: ls(d).filter(n => /^Fagnoter.*\.docx$/i.test(n)).map(n => ({ fil: n, ændret: mtime(path.join(d, n))?.toISOString() ?? null })) };
  if (findes(path.join(d, "Genkald"))) {
    s.begreber = begreber(path.join(d, "Genkald", "begreber.md"));
    s.genkald = genkald(path.join(d, "Genkald"));
    // Fagets genkald i alt, så Fag-siden ikke lægger filerne sammen selv
    s.genkald_i_alt = s.genkald.reduce((a, x) => ({ spoergsmaal: a.spoergsmaal + x.spoergsmaal, forsoegt: a.forsoegt + x.sad + x.halvt + x.blankt,
      sad: a.sad + x.sad }), { spoergsmaal: 0, forsoegt: 0, sad: 0 });
  }
  if (findes(path.join(d, "Modeller"))) s.modeller = ls(path.join(d, "Modeller")).filter(n => !/^README/i.test(n)).length;
  if (f.kode) {
    const vs = path.join(d, f.kode);
    s.drills = drills(path.join(vs, "Drills"));
    s.drills_i_alt = s.drills.reduce((a, x) => ({ pladser: a.pladser + x.pladser, gaettet: a.gaettet + x.gættet, stubbe: a.stubbe + x.stubbe }),
      { pladser: 0, gaettet: 0, stubbe: 0 });
    s.oevelser_i_gang = ls(vs).filter(n => /\.js$/.test(n));
    s.oevelser_faerdige = [path.join(vs, "Bog"), path.join(vs, "Øvelser")].flatMap(m => ls(m).map(n => path.join(m, n))).filter(egenKode).length;
  }
  if (f.afleveringer) s.afleveringer = afleveringsTabel(path.join(d, f.afleveringer.mappe, "README.md"));
  return s;
}

// ── fagnoter (Word) ──────────────────────────────────────────────────
// Studie-rutinen skriver en uge i Fagnoter-dokumentet søndagen før ugen som foreløbig ("(foreløbig)" sidst i
// overskriften) og retter den søndagen efter, når slides og øvelser er lagt op (afsnit 6).
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

// Label-afsnittene i skabelonen fra Scripts/fagnoter/labels.json, som rutinens fill_fagnoter.py også bruger.
// Læses først, når et dokument læses, så en manglende fil kun rammer fagnoterne (sidste eksport beholdes)
let fnLabels = null;
const FN_LABELS = () => fnLabels ??= JSON.parse(fs.readFileSync(path.join(__dirname, "fagnoter", "labels.json"), "utf8")).labels;

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
    label: førsteFed ? FN_LABELS().find(l => ren.trim().startsWith(l)) || null : null,
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
  // Ugeblokkene under "Ugenoter" og dokumentets øvrige hovedafsnit (Overskrift 1, fx Eksamen) til siden USB-noter
  const uger = {}, dele = [];
  let nu = null;
  for (const b of elem(krop)) {
    if (b.navn === "w:tbl") { if (nu) nu.afsnit.push({ tabel: wTabel(b, billede) }); continue; }
    if (b.navn !== "w:p") continue;
    const a = wAfsnit(b, billede);
    const niveau = +((a.stil.match(/^(?:Overskrift|Heading)\s*(\d)$/i) || [])[1] || 0);
    if (niveau) {
      const u = niveau === 2 && a.ren.trim().match(/^Uge\s+(\d+)\b/i);
      const h1 = niveau === 1 && a.ren.trim() && !/^Ugenoter\b/i.test(a.ren.trim());
      nu = u ? (uger[+u[1]] = { titel: a.ren.trim(), afsnit: [] }) : h1 ? dele[dele.push({ titel: a.ren.trim(), afsnit: [] }) - 1] : null;
      continue;
    }
    if (nu) nu.afsnit.push(a);
  }
  // Ord og kodeblokke pr. blok, så USB-noter kan vise, hvor meget hver uge fylder
  const omfang = html => ({ ord: afEnt(html.replace(/<[^>]+>/g, " ")).split(/\s+/).filter(Boolean).length,
    kodeblokke: (html.match(/<pre>/g) || []).length });
  const ud = {};
  for (const [uge, u] of Object.entries(uger)) {
    // Rutinen regner en uge for udfyldt, når blokken har en "Modeller"-label (afsnit 6 i RUTINE.md)
    const html = wHtml(u.afsnit);
    ud[uge] = { titel: u.titel, udfyldt: u.afsnit.some(a => a.label === "Modeller"), foreloebig: /\(foreløbig\)\s*$/.test(u.titel),
      kun_bog: u.afsnit.some(a => /Slides til uge \d+ var ikke uploadet/i.test(a.ren || "")), html, ...omfang(html) };
  }
  const udDele = dele.map(d => { const html = wHtml(d.afsnit); return { titel: d.titel, html, ...omfang(html) }; }).filter(d => d.ord);
  return { uger: ud, dele: udDele, billeder: [...brugt] };
}

// Billederne pakkes kun ud, når dokumentet er ændret siden sidst (stempel = ændringstid + størrelse).
// handlet: de vurderinger fra USB-noter, Studie-rutinen har rettet ugen efter (Scripts/fagnoter/vurdering-handlet.json,
// { "<fag>": { "<uge eller afsnit>": "<vurderingens dato>" } }), så siden kan vise, at en vurdering er taget.
function fagnoter(forrige) {
  const ud = {};
  let handlet = {};
  try { handlet = JSON.parse(læs(path.join(S.DATA, "fagnoter", "vurdering-handlet.json")) || "{}"); } catch { handlet = {}; }
  for (const f of S.fag()) {
    const navn = ls(path.join(ROD, f.mappe)).find(n => /^Fagnoter.*\.docx$/i.test(n));
    if (!navn) continue;
    const fil = path.join(ROD, f.mappe, navn);
    try {
      const st = fs.statSync(fil), stempel = `${st.mtimeMs}:${st.size}`;
      const { uger, dele, billeder } = fagnoterUger(fil, f.id);
      const dir = path.join(UD, "fagnoter", f.id);
      if (forrige?.[f.id]?.stempel !== stempel || !findes(dir)) {
        const tmp = `${dir}.${process.pid}.tmp`;   // to eksporter på én gang (opdater.sh og en gemning) deler ikke mappen
        fs.rmSync(tmp, { recursive: true, force: true });
        fs.mkdirSync(tmp, { recursive: true });
        for (const b of billeder) fs.writeFileSync(path.join(tmp, b.slice(6)), execFileSync("unzip", ["-p", fil, `word/${b}`], { maxBuffer: 256 << 20 }));
        fs.rmSync(dir, { recursive: true, force: true });
        fs.renameSync(tmp, dir);
      }
      ud[f.id] = { fil: `${f.mappe}/${navn}`, ændret: st.mtime.toISOString(), stempel, uger, dele };
    } catch (e) {
      console.error(`Fagnoter ${f.kort}: ${e.message.split("\n")[0]}`);
      if (forrige?.[f.id]) ud[f.id] = forrige[f.id];
    }
    if (ud[f.id]) {
      ud[f.id].handlet = handlet[f.id] || {};
      // Hvor meget dokumentet fylder: de udfyldte og foreløbige uger og de øvrige hovedafsnit (det, USB-noter viser)
      ud[f.id].ord_i_alt = Object.values(ud[f.id].uger).filter(u => u.udfyldt || u.foreloebig).reduce((n, u) => n + (u.ord || 0), 0)
        + (ud[f.id].dele || []).reduce((n, d) => n + d.ord, 0);
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

  // Frister: tabellen (## Deadlines) i den nyeste plan flettet med CLAUDE.md's "Vigtige datoer". En række fra CLAUDE.md
  // med en præcis dato (fx eksamen fra Eksamener.pdf) erstatter planens række for samme fag, uge og type;
  // rækker planen ikke har, kommer med; resten af planens rækker står uændret.
  let deadlines = nyeste?.deadlines?.length ? nyeste.deadlines.map(r => deadline(r, nyeste.aar, nyeste.uge)) : [];
  const vigtige = S.vigtigeDatoer().map(r => deadline(r, nyeste?.aar ?? nu.getFullYear(), nyeste?.uge ?? ugeNu));
  const samme = (a, b) => a.fag === b.fag && a.type === b.type && a.fra === b.fra;
  for (const v of vigtige) {
    const i = deadlines.findIndex(d => samme(d, v));
    if (i < 0) deadlines.push(v);
    else if (v.dato) deadlines[i] = { ...v, note: deadlines[i].note && !/verificer|tjek/i.test(deadlines[i].note) ? deadlines[i].note : null };
  }
  // Prøveeksamener er en egen plan, ikke frister fra uddannelsen: de står i CLAUDE.md's "Egen plan" og vises på
  // Eksamen-siden. En prøveeksamen i køreplanens fristtabel eller under Vigtige datoer flyttes også derover.
  const egenPlan = S.egenPlan().map(r => deadline(r, nyeste?.aar ?? nu.getFullYear(), nyeste?.uge ?? ugeNu));
  const proeveplan = [...egenPlan, ...deadlines.filter(d => d.type === "proeve" && !egenPlan.some(e => e.fag === d.fag && e.fra === d.fra))]
    .map(({ uger, fag, hvad, fra, til }) => ({ uger, fag, hvad, fra, til }))
    .sort((a, b) => String(a.fra).localeCompare(String(b.fra)));
  deadlines = deadlines.filter(d => d.type !== "proeve");
  deadlines.sort((a, b) => String(a.dato || a.fra).localeCompare(String(b.dato || b.fra)));
  // Færdig-markering fra Kompas: afleveringer (fx Opgave 3) i "Afleveret" i fagets afleveringstabel, resten i
  // deadlines-status.json. Nøglen er "<fag>|Opgave 3" for afleveringer og ellers "<fag>|<type>|<uge>", så den overlever,
  // at planens tekst ændrer sig.
  let status = {};
  try { status = JSON.parse(læs(path.join(S.DATA, "deadlines-status.json")) || "{}"); } catch { status = {}; }
  const afleveringer = Object.fromEntries(S.fagMed("afleveringer").map(f =>
    [f.kort, afleveringsTabel(path.join(ROD, f.mappe, f.afleveringer.mappe, "README.md"))?.raekker || []]));
  for (const d of deadlines) {
    const g = S.afleveringsNr(d.hvad.replace(/<[^>]+>/g, ""));
    d.noegle = g ? `${d.fag}|${g}` : `${d.fag}|${d.type}|${(d.uger.match(/\d+/) || [""])[0]}`;
    const gr = g && (afleveringer[d.fag] || Object.values(afleveringer).flat()).find(r => r.opgave === g);
    const afl = gr?.afleveret && !/^(nej|-|—|–)$/i.test(gr.afleveret) ? gr.afleveret : null;
    d.faerdig = S.noegleVarianter(d.noegle).map(n => status[n]?.faerdig).find(Boolean) || afl || null;
  }
  const deadlineKilde = [nyeste?.deadlines?.length ? nyeste.fil : null, vigtige.length ? "CLAUDE.md" : null].filter(Boolean).join(" og ") || null;

  // Sessionerne fra stopuret (også til Rytme på Fag). Kan filen ikke læses, beholder overblik de sessioner, den fik sidst.
  const log = (() => { try { return SS.læs(); } catch (e) { console.error(`sessioner.json kunne ikke læses: ${e.message}`); return null; } })();
  const prFag = selvstudiePrFag(log);

  // Fagene med det, siderne skal vide om dem: farve og hvilke funktioner faget har (fra fag.json)
  const former = S.eksamensformer();
  const fag = S.fag().map(f => ({
    id: f.id, kort: f.kort, alias: f.alias || [], navn: f.navn, mappe: f.mappe, farve: f.farve, genkald: f.genkald,
    begreber: f.begreber, kode: f.kode, afleveringer: f.afleveringer, leetcode: !!f.leetcode, usb_noter: !!f.usb_noter,
    eksamenstraening: f.eksamenstraening, forudsaetning: f.forudsaetning,
    eksamen: former.find(r => (r.Fag || "").startsWith(f.readme)) || null,
    status: fagStatus(f, planer[0] ? mandagIUge(planer[0].aar, planer[0].uge) : null, prFag[f.id]?.dage),
  }));

  const data = {
    genereret: nu.toISOString(), uge_nu: ugeNu, aktuel_uge: aktuel?.uge ?? null,
    planer: planer.map(p => ({ ...p, deadlines: undefined })),
    deadlines, deadline_kilde: deadlineKilde, proeveplan, fag, leetcode: leetcode(), studieguide: studieguide(),
  };
  const manifest = {
    omraade: "Studie", ikon: "graduation-cap", raekkefoelge: 20,
    kilde: `${S.semester()} (Scripts/kompas-eksport.js) · køreplaner fra Studie-rutinen`,
    opdateret: nu.toISOString(),
    sider: [
      { titel: "Ugeoverblik", ikon: "calendar", sti: "/studie/" },
      // USB-noterne (fag med usb_noter i fag.json) ligger under Fag → faget; menuen markerer Fag, mens du er på dem
      { titel: "Fag", ikon: "book-open", sti: "/studie/fag.html", match: ["/studie/fag.html", "/studie/usb.html"] },
      { titel: "Træning", ikon: "brain", sti: "/studie/genkald.html" },
      { titel: "Eksamen", ikon: "file-text", sti: "/studie/eksamen.html" },
      // Tiden pr. fag mod kursusbeskrivelsens arbejdstimer (selvstudie.json)
      { titel: "Selvstudie", ikon: "pie-chart", sti: "/studie/selvstudie.html" },
      // Alle semestre samlet: periode, fag, selvstudie, saldo og medaljer (semestre.json)
      { titel: "Semestre", ikon: "calendar-range", sti: "/studie/semestre.html" },
      // Frister står øverst i menuen, under I dag og Forbindelser (`oeverst`), men er stadig Studies side
      { titel: "Frister", ikon: "clipboard-check", sti: "/studie/deadlines.html", oeverst: true },
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
  skriv("selvstudie.json", JSON.stringify(selvstudie(liv, log, nu)));
  skriv("semestre.json", JSON.stringify(semestre(liv, nu)));
  if (log) skriv("sessioner.json", JSON.stringify({ genereret: S.lokalTid(nu), fra: log.fra,
    sessioner: log.sessioner.map(s => ({ id: s.id, fag: s.fag, kort: S.find(s.fag)?.kort || s.fag, stykker: s.stykker })) }));
  let forrige = null;
  try { forrige = JSON.parse(læs(path.join(UD, "fagnoter.json"))); } catch { forrige = null; }
  const fn = fagnoter(forrige);
  skriv("fagnoter.json", JSON.stringify(fn));
  skriv("resumeer.json", JSON.stringify(resumeer()));
  for (const f of S.fagMed("resumeer")) {
    const fra = path.join(ROD, f.mappe, f.resumeer, "billeder"), til = path.join(UD, "resumeer", f.id);
    fs.rmSync(til, { recursive: true, force: true });
    const filer = ls(fra).filter(n => /\.(png|jpe?g|webp)$/i.test(n));
    if (filer.length) fs.mkdirSync(til, { recursive: true });
    for (const n of filer) fs.copyFileSync(path.join(fra, n), path.join(til, n));
  }
  const fnUger = Object.values(fn).reduce((n, f) => n + Object.values(f.uger).filter(u => u.udfyldt).length, 0);
  // "nyt" pr. side: en nøgle for sidens nyeste indhold. Skifter den, viser menuen i Kompas en prik, til siden
  // er åbnet. Ugeoverblik: en ny køreplan (søndag). Fag: ny køreplan eller nye udfyldte fagnoter.
  // Frister: en frist er kommet til eller flyttet (færdig-markeringer og omformuleringer tæller ikke).
  const nyesteUge = Math.max(0, ...planer.map(p => p.uge));
  const fristNøgle = deadlines.map(d => `${d.noegle}@${d.dato || d.uger}`).sort().join("\n");
  const nyt = {
    "/studie/": nyesteUge ? `uge ${nyesteUge}` : null,
    "/studie/fag.html": nyesteUge ? `uge ${nyesteUge} · ${fnUger} fagnote-uger` : null,
    "/studie/deadlines.html": deadlines.length ? crypto.createHash("sha1").update(fristNøgle).digest("hex").slice(0, 10) : null,
  };
  for (const side of manifest.sider) if (nyt[side.sti]) side.nyt = nyt[side.sti];
  skriv("kompas.json", JSON.stringify(manifest));
  console.log(`Studie → ${UD}: ${planer.length} køreplaner (aktuel uge ${aktuel?.uge ?? "–"}), ${deadlines.length} frister, ${fag.length} fag, ${fnUger} udfyldte fagnote-uger`);
}

main();
