// Studie → Kompas: Genkald-fanen (https://kompas.localhost/studie/genkald.html)
//
// En lille lokal server, der lader siden læse og skrive DIT arbejde i semestermappen. Den kan kun:
//   - skrive dit svar og din markering [✓]/[~]/[✗] ind under et spørgsmål i */Genkald/genkald-*.md
//   - skrive din definition (og for Beta: "Hvad det får dig til at se") i */Genkald/begreber.md
//   - erstatte TOM med DIT gæt i en tjek(...)-linje i Gamma/vscode/Drills/kap*.js og køre filen
// På farten (mobil.html) henter en pakke med dagens kort, så du kan svare uden net, og sender svarene
// tilbage med /sync, når Mac'en er vågen. Det er de samme skrivninger som ovenfor, bare senere.
// Alt, der skrives, er tekst du selv har tastet. Serveren finder aldrig på et svar, og facit
// udleveres kun ét spørgsmål ad gangen, når siden beder om det efter dit forsøg (se CLAUDE.md).
//
// Kør:  node Scripts/kompas-server.js      (lytter på 127.0.0.1:8767; Caddy sender /studie/api/* hertil)
// Kører altid i baggrunden som LaunchAgent local.kompas.studie (~/Library/LaunchAgents); log i ~/.kompas/studie-server.log.
// CommonJS, ingen afhængigheder, som resten af Scripts/.
//
// Env-variabler (alle valgfrie):
//   KOMPAS_SEMESTER     semestermappen; standard er mappen over Scripts/
//   STUDIE_PORT         port på 127.0.0.1; standard 8767
//   STUDIE_ORIGINS      ekstra adresser, der må skrive (kommasepareret), fx telefonens Tailscale-adresse
//   STUDIE_EKSPORT_UD   sendes videre til kompas-eksport.js som --ud (skal sættes på en testserver)

const http = require("http");
const fs = require("fs");
const path = require("path");
const os = require("os");
const { execFile } = require("child_process");

const hjem = s => s.replace(/^~(?=$|\/)/, os.homedir());
const ROD = path.resolve(hjem(process.env.KOMPAS_SEMESTER || path.join(__dirname, "..")));
// Serverens egne datafiler (forsøgslog, læst-markeringer, færdige frister) ligger i semestermappens Scripts/
const DATA = path.join(ROD, "Scripts");
const PORT = +(process.env.STUDIE_PORT || 8767);
const ORIGIN = "https://kompas.localhost";
// Telefonen kommer ind gennem Tailscale med sin egen adresse (https://<mac>.<tailnet>.ts.net), sat i LaunchAgent'en
const ORIGINS = [ORIGIN, ...String(process.env.STUDIE_ORIGINS || "").split(",").map(s => s.trim()).filter(Boolean)];
// Kun de navne, Kompas selv bruger: kompas.localhost, telefonens Tailscale-navn og de lokale porte. Ellers kan en
// fremmed side, der peger sit eget domæne på 127.0.0.1 (DNS rebinding), læse svarene, fordi browseren tror, det er
// dens egen side. 8768 er Caddys blok til telefonen. Afviste navne logges.
const VAERTER = new Set(["kompas.localhost", `127.0.0.1:${PORT}`, `localhost:${PORT}`, "127.0.0.1:8768", "localhost:8768",
  ...ORIGINS.map(o => { try { return new URL(o).host; } catch { return null; } }).filter(Boolean)]);
const LOG = path.join(DATA, "genkald-log.jsonl");
// Fagene (id → mappe). Alfa og Beta har genkald og begreber; Gamma har drills og afleveringer.
const FAG = { alfa: "Alfa", beta: "Beta", gamma: "Gamma" };
const MARK = { sad: "✓", halvt: "~", blankt: "✗" };
const DRILLS = path.join(ROD, FAG.gamma, "vscode", "Drills");

const læs = f => fs.readFileSync(f, "utf8");
function skriv(f, tekst) { const tmp = f + ".tmp"; fs.writeFileSync(tmp, tekst); fs.renameSync(tmp, f); }
const idag = (d = new Date()) => { return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}`; };
function logFoersoeg(post) { fs.appendFileSync(LOG, JSON.stringify({ tid: new Date().toISOString(), ...post }) + "\n"); eksporterSnart(); }
// Efter en gemning køres Kompas-eksporten, så Fag-siden og I dag viser de nye tal. Flere gemninger
// lige efter hinanden giver kun én kørsel. En testserver på en kopi af mappen skal sætte STUDIE_EKSPORT_UD,
// ellers skriver kopien sine data ud i de rigtige Studie-sider (~/.kompas/studie).
let eksportTimer = null;
const EKSPORT_UD = process.env.STUDIE_EKSPORT_UD ? ["--ud", process.env.STUDIE_EKSPORT_UD] : [];
function eksporterSnart() {
  clearTimeout(eksportTimer);
  eksportTimer = setTimeout(() => execFile(process.execPath, [path.join(__dirname, "kompas-eksport.js"), ...EKSPORT_UD], { timeout: 60000 },
    err => { if (err) console.error(`eksporten fejlede: ${err.message}`); }), 2000);
}
function sidst() {
  const ud = {};
  try { for (const l of læs(LOG).split("\n")) { if (!l) continue; const p = JSON.parse(l); ud[p.noegle] = p; } } catch { /* ingen log endnu */ }
  return ud;
}

// Stier: kun præcis de filer, fanen må skrive i
function genkaldFil(fag, fil) {
  if (!FAG[fag] || fag === "gamma" || !/^genkald-[\w-]+\.md$/.test(fil) || /-svar\.md$/.test(fil)) throw new Error("ukendt genkaldsfil");
  const f = path.join(ROD, FAG[fag], "Genkald", fil);
  if (!fs.existsSync(f)) throw new Error("filen findes ikke");
  return f;
}
function begrebFil(fag) {
  if (fag !== "alfa" && fag !== "beta") throw new Error("ukendt fag");
  return path.join(ROD, FAG[fag], "Genkald", "begreber.md");
}
function drillFil(fil) {
  if (!/^kap\d+[\w-]*\.js$/.test(fil)) throw new Error("ukendt drill");
  const f = path.join(DRILLS, fil);
  if (!fs.existsSync(f)) throw new Error("filen findes ikke");
  return f;
}

// ── genkald ──────────────────────────────────────────────────────────
// Et spørgsmål er blokken fra "**N.**" til næste "**M.**", "---" eller "## ".
// Markeringen står lige efter nummeret ("**3.** [~] ..."), så eksporten og køreplanen tæller den som før.
// Dit svar står som citatblok i bunden af blokken: "> **Mit svar** (28.09): ...".
function blokke(tekst) {
  const linjer = tekst.split("\n"), ud = [];
  let afsnit = "", cur = null;
  const luk = i => { if (cur) { cur.slut = i; ud.push(cur); cur = null; } };
  linjer.forEach((l, i) => {
    if (/^## /.test(l)) { luk(i); afsnit = l.slice(3).trim(); return; }
    if (/^---\s*$/.test(l)) { luk(i); return; }
    const m = l.match(/^\*\*(\d+)\.\*\*\s*/);
    if (m) { luk(i); cur = { nr: +m[1], start: i, afsnit }; }
  });
  luk(linjer.length);
  return { linjer, blokke: ud };
}
function parseBlok(linjer, b) {
  const krop = linjer.slice(b.start, b.slut);
  while (krop.length && !krop[krop.length - 1].trim()) krop.pop();
  const svarStart = krop.findIndex(l => /^> \*\*Mit svar\*\*/.test(l));
  const spm = (svarStart >= 0 ? krop.slice(0, svarStart) : krop).join("\n").trim();
  const mark = (spm.match(/^\*\*\d+\.\*\*\s*\[(✓|~|✗)\]/) || [])[1] || null;
  const tekst = spm.replace(/^\*\*\d+\.\*\*\s*(\[(✓|~|✗)\]\s*)?/, "");
  let svar = null, dato = null;
  if (svarStart >= 0) {
    const s = krop.slice(svarStart).map(l => l.replace(/^> ?/, ""));
    const m = s[0].match(/^\*\*Mit svar\*\*\s*(?:\(([^)]*)\))?:?\s*(.*)$/);
    dato = m?.[1] || null;
    svar = [m?.[2] || "", ...s.slice(1)].join("\n").trim();
  }
  return { nr: b.nr, afsnit: b.afsnit, tekst, mark, svar, dato };
}

function genkaldListe() {
  const log = sidst(), ud = [];
  for (const fag of ["alfa", "beta"]) {
    const dir = path.join(ROD, FAG[fag], "Genkald");
    let filer = [];
    try { filer = fs.readdirSync(dir).filter(n => /^genkald-.*\.md$/.test(n) && !/-svar\.md$/.test(n)).sort(); } catch { continue; }
    for (const fil of filer) {
      const tekst = læs(path.join(dir, fil));
      const { linjer, blokke: bs } = blokke(tekst);
      const titel = (tekst.match(/^# (.*)$/m) || [])[1] || fil;
      const u = fil.match(/uge(\d+)-(\d+)/);
      ud.push({ fag, fil, titel, uger: u ? (u[1] === u[2] ? `uge ${u[1]}` : `uge ${u[1]}–${u[2]}`) : fil,
        har_facit: fs.existsSync(path.join(dir, fil.replace(/\.md$/, "-svar.md"))),
        spoergsmaal: bs.map(b => { const p = parseBlok(linjer, b); return { ...p, uge: ugeFor(p.afsnit, fil), sidst: log[`${fag}/${fil}#${p.nr}`]?.tid || null }; }) });
    }
  }
  return ud;
}

// Facit for ét spørgsmål fra -svar.md (samme "**N.**"-opbygning)
function facit(fag, fil, nr) {
  const f = genkaldFil(fag, fil).replace(/\.md$/, "-svar.md");
  if (!fs.existsSync(f)) return null;
  const { linjer, blokke: bs } = blokke(læs(f));
  const b = bs.find(x => x.nr === nr);
  return b ? linjer.slice(b.start, b.slut).join("\n").trim().replace(/^\*\*\d+\.\*\*\s*/, "") : null;
}

const SIKKERHED = ["sikker", "usikker", "gaet"];
// meta: { tid, sync_id } for svar, der er givet på telefonen og sendes senere (se /sync)
function gemGenkald({ fag, fil, nr, svar, mark, sikkerhed }, meta = {}) {
  const f = genkaldFil(fag, fil);
  if (mark != null && !MARK[mark]) throw new Error("ukendt markering");
  const { linjer, blokke: bs } = blokke(læs(f));
  const b = bs.find(x => x.nr === +nr);
  if (!b) throw new Error(`spørgsmål ${nr} findes ikke i ${fil}`);
  let krop = linjer.slice(b.start, b.slut);
  let bag = [];
  while (krop.length && !krop[krop.length - 1].trim()) bag.unshift(krop.pop());
  const s = krop.findIndex(l => /^> \*\*Mit svar\*\*/.test(l));
  if (s >= 0) { krop = krop.slice(0, s); while (krop.length && !krop[krop.length - 1].trim()) krop.pop(); }
  if (mark) krop[0] = krop[0].replace(/^(\*\*\d+\.\*\*)\s*(\[(✓|~|✗)\]\s*)?/, `$1 [${MARK[mark]}] `);
  const tekst = String(svar || "").replace(/\r/g, "").trim();
  if (tekst) {
    const [første, ...rest] = tekst.split("\n");
    krop.push("", `> **Mit svar** (${idag(meta.tid ? new Date(meta.tid) : undefined)}): ${første}`, ...rest.map(l => `> ${l}`));
  }
  if (!bag.length) bag = [""];
  const ny = [...linjer.slice(0, b.start), ...krop, ...bag, ...linjer.slice(b.slut)];
  skriv(f, ny.join("\n"));
  logFoersoeg({ ...meta, type: "genkald", noegle: `${fag}/${fil}#${nr}`, mark: mark || null,
    ...(SIKKERHED.includes(sikkerhed) ? { sikkerhed } : {}) });
  return { gemt: true };
}

// ── begreber ─────────────────────────────────────────────────────────
const celler = l => l.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
// Skriv en tabelrække i samme form som filerne selv: "| a | b | | |" (tomme celler med ét mellemrum)
const række = c => `|${c.map(x => x ? ` ${x} ` : " ").join("|")}|`;
function begreberListe() {
  const log = sidst(), ud = {};
  for (const fag of ["alfa", "beta"]) {
    let tekst; try { tekst = læs(begrebFil(fag)); } catch { continue; }
    const linjer = tekst.split("\n"), rows = [];
    let afsnit = "", under = "", hoved = null;
    linjer.forEach((l, i) => {
      if (/^## /.test(l)) { afsnit = l.slice(3).trim(); under = ""; return; }
      if (/^### /.test(l)) { under = l.slice(4).trim(); return; }
      if (!/^\s*\|/.test(l)) { hoved = null; return; }
      if (/^\s*\|\s*-/.test(l)) return;
      if (/^\s*\|\s*-/.test(linjer[i + 1] || "")) { hoved = celler(l); return; }
      if (!hoved || !/^Begreb$/i.test(hoved[0])) return;
      const c = celler(l);
      rows.push({ begreb: c[0], definition: c[1] || "", se: hoved[2] && /se/i.test(hoved[2]) ? (c[2] || "") : null,
        kilde: c[c.length - 1] || "", afsnit: under ? `${afsnit} · ${under}` : afsnit, sidst: log[`${fag}/begreb/${c[0]}`]?.tid || null });
    });
    ud[fag] = { hoved_se: fag === "beta" ? "Hvad det får dig til at se" : null, begreber: rows };
  }
  return ud;
}
// foer: definitionen, som den så ud, da du begyndte (fra telefonen). Er den ændret siden, gemmes intet.
function gemBegreb({ fag, begreb, definition, se, foer }, meta = {}) {
  const f = begrebFil(fag);
  const ren = s => String(s || "").replace(/\r?\n+/g, " ").replace(/\|/g, "/").trim();
  const linjer = læs(f).split("\n");
  const idx = linjer.map((l, i) => [l, i]).filter(([l]) => /^\s*\|/.test(l) && celler(l)[0] === begreb).map(([, i]) => i);
  if (idx.length !== 1) throw new Error(idx.length ? `"${begreb}" står flere gange i begreber.md` : `"${begreb}" findes ikke`);
  const c = celler(linjer[idx[0]]);
  if (foer != null && c[1] !== ren(foer)) throw new Error(`"${begreb}" er ændret, siden du hentede pakken`);
  c[1] = ren(definition);
  if (se != null && c.length >= 4) c[2] = ren(se);
  linjer[idx[0]] = række(c);
  skriv(f, linjer.join("\n"));
  logFoersoeg({ ...meta, type: "begreb", noegle: `${fag}/begreb/${begreb}` });
  return { gemt: true };
}

// ── drills ───────────────────────────────────────────────────────────
// Et tjek-kald: tjek("beskrivelse", () => UDTRYK, GÆT);  — GÆT er TOM, indtil du har gættet.
// Kaldet kan strække sig over flere linjer, og udtrykket kan selv indeholde kommaer, så filen skannes
// med styr på parenteser, strenge og kommentarer.
function skanTil(s, i, stop) {
  let dybde = 0;
  for (; i < s.length; i++) {
    const c = s[i];
    if (c === '"' || c === "'" || c === "`") { const q = c; for (i++; i < s.length && s[i] !== q; i++) if (s[i] === "\\") i++; continue; }
    if (c === "/" && s[i + 1] === "/") { while (i < s.length && s[i] !== "\n") i++; continue; }
    if (c === "/" && s[i + 1] === "*") { i = s.indexOf("*/", i + 2); if (i < 0) return -1; i++; continue; }
    if ("([{".includes(c)) dybde++;
    else if (")]}".includes(c)) { if (dybde === 0) return i; dybde--; }
    else if (c === stop && dybde === 0) return i;
  }
  return -1;
}
function tjekKald(tekst) {
  const ud = [], re = /^tjek\(\s*/gm;
  let m;
  while ((m = re.exec(tekst))) {
    const linje = tekst.slice(0, m.index).split("\n").length;
    let i = m.index + m[0].length;
    if (tekst[i] !== '"') { ud.push({ linje, fejl: true }); continue; }
    let j = i + 1; while (j < tekst.length && tekst[j] !== '"') { if (tekst[j] === "\\") j++; j++; }
    let desc; try { desc = JSON.parse(tekst.slice(i, j + 1)); } catch { ud.push({ linje, fejl: true }); continue; }
    const komma = skanTil(tekst, j + 1, ",");
    const slutUdtryk = komma < 0 ? -1 : skanTil(tekst, komma + 1, ",");
    const slutKald = slutUdtryk < 0 ? -1 : skanTil(tekst, slutUdtryk + 1, ")");
    if (slutKald < 0) { ud.push({ linje, desc, fejl: true }); continue; }
    ud.push({ linje, desc, udtryk: tekst.slice(komma + 1, slutUdtryk).trim(), gaet: tekst.slice(slutUdtryk + 1, slutKald).trim(),
      gaetStart: slutUdtryk + 1, gaetSlut: slutKald });
  }
  return ud;
}
// Koden fra filen, et udtryk bruger: de funktioner, konstanter og variabler (øverst i filen), det nævner, og dem
// de selv nævner. Bruger det en variabel med let/var, kommer de tidligere tjek med, der også rører den, fordi de
// har ændret værdien, før det her tjek køres. Uden det kan "vejr('sol')" ikke gættes på en side, der ikke viser filen.
const NAVNE = /(?<![.\w$])[A-Za-z_$][\w$]*/g;
function definitioner(tekst) {
  const ud = [], re = /^(?:async\s+)?(function)\s+(\w+)|^(class)\s+(\w+)|^(const|let|var)\s+(\w+)\s*=/gm;
  let m;
  while ((m = re.exec(tekst))) {
    const fn = !!(m[1] || m[3]), navn = m[2] || m[4] || m[6], start = m.index;
    let d = 0, åbnet = false, i = start + m[0].length;
    for (; i < tekst.length; i++) {
      const c = tekst[i];
      if (c === '"' || c === "'" || c === "`") { const q = c; for (i++; i < tekst.length && tekst[i] !== q; i++) if (tekst[i] === "\\") i++; continue; }
      if (c === "/" && tekst[i + 1] === "/") { while (i < tekst.length && tekst[i + 1] !== "\n") i++; continue; }
      if ("([{".includes(c)) { d++; if (c === "{") åbnet = true; } else if (")]}".includes(c)) d--;   // en funktion slutter med sin krop, ikke parameterlisten
      if (fn && åbnet && d === 0) { i++; break; }
      if (!fn && d === 0 && c === ";") { i++; break; }
      if (!fn && d === 0 && c === "\n" && /^\S/.test(tekst[i + 1] || "")) break;
    }
    ud.push({ navn, start, slut: i, foranderlig: m[5] === "let" || m[5] === "var", kode: tekst.slice(start, i).trim() });
  }
  return ud;
}
function kontekst(udtryk, linje, defs, alleTjek) {
  const navne = s => new Set(s.match(NAVNE) || []);
  const valgt = new Set(), kø = [...navne(udtryk)];
  while (kø.length) {
    const n = kø.pop();
    for (const d of defs) if (d.navn === n && !valgt.has(d)) { valgt.add(d); kø.push(...navne(d.kode)); }
  }
  if (!valgt.size) return null;
  const ds = [...valgt].sort((a, b) => a.start - b.start), rørt = new Set(ds.map(d => d.navn));
  const før = ds.some(d => d.foranderlig)
    ? alleTjek.filter(t => !t.fejl && t.linje < linje && [...navne(t.udtryk)].some(n => rørt.has(n))).map(t => `${t.udtryk};`) : [];
  return [...ds.map(d => d.kode), ...(før.length ? [`// kørt før i filen:\n${før.join("\n")}`] : [])].join("\n\n");
}
function koerDrill(f) {
  return new Promise(res => execFile(process.execPath, [f], { cwd: path.dirname(f), timeout: 5000 }, (err, stdout, stderr) => {
    const fejl = {};
    const l = String(stdout).split("\n");
    for (let i = 0; i < l.length; i++) {
      const m = l[i].match(/^FEJL  (.*)$/);
      if (m && /du gættede/.test(l[i + 1] || "")) {
        fejl[m[1]] = { dit: l[i + 1].replace(/^\s*du gættede\s*/, ""), js: (l[i + 2] || "").replace(/^\s*JavaScript:\s*/, "") };
      }
    }
    const opsum = l.find(x => /rigtige · /.test(x)) || null;
    res({ fejl, opsum, crash: err && !opsum ? String(stderr).split("\n").slice(0, 6).join("\n") : null });
  }));
}
// Korte forklaringer i Drills/forklaringer/<drill>.md, én "## beskrivelse" pr. tjek (uden "← …"-noten).
// Sendes kun med for tjek, du har gættet på, så de ikke afslører noget på forhånd.
const forklaringNoegle = s => s.replace(/\s*←.*$/, "").replace(/\s+/g, " ").trim();
function forklaringer(fil) {
  const ud = {};
  try {
    for (const afsnit of læs(path.join(DRILLS, "forklaringer", fil.replace(/\.js$/, ".md"))).split(/^## /m).slice(1)) {
      const [overskrift, ...tekst] = afsnit.split("\n");
      ud[forklaringNoegle(overskrift)] = tekst.join("\n").trim();
    }
  } catch {}
  return ud;
}
let drillCache = null;
async function drillsCachet() {
  if (!drillCache || Date.now() - drillCache.tid > 60000) drillCache = { tid: Date.now(), data: await drillsListe() };
  return drillCache.data;
}
async function drillsListe() {
  const ud = [];
  const filer = fs.readdirSync(DRILLS).filter(n => /^kap\d+.*\.js$/.test(n)).sort();
  for (const fil of filer) {
    const f = path.join(DRILLS, fil), tekst = læs(f), linjer = tekst.split("\n");
    const titel = ((linjer[0] || "").match(/^\/\/\s*(.*)$/) || [])[1] || fil;
    const kørsel = await koerDrill(f), hvorfor = forklaringer(fil);
    // Afsnittet et kald står i: nærmeste "// ── navn ──"-linje over det
    const afsnitVed = n => { for (let k = n - 1; k >= 0; k--) { const a = linjer[k].match(/^\/\/ ── (.*?) ─/); if (a) return a[1]; } return ""; };
    const kald = tjekKald(tekst), defs = definitioner(tekst);
    const tjek = kald.map(t => {
      if (t.fejl) return { linje: t.linje, afsnit: afsnitVed(t.linje), beskrivelse: t.desc || linjer[t.linje - 1].slice(0, 80), udtryk: null, gaet: null, status: "vscode" };
      const tom = t.gaet === "TOM";
      return { linje: t.linje, afsnit: afsnitVed(t.linje), beskrivelse: t.desc, udtryk: t.udtryk, kontekst: kontekst(t.udtryk, t.linje, defs, kald), gaet: tom ? null : t.gaet,
        status: tom ? "tom" : kørsel.fejl[t.desc] ? "forkert" : kørsel.crash ? "ukendt" : "rigtig", javascript: kørsel.fejl[t.desc]?.js ?? null,
        forklaring: tom ? null : hvorfor[forklaringNoegle(t.desc)] || null };
    });
    const stubbe = [];
    linjer.forEach((l, i) => {
      if (/DIN KODE HER/.test(l)) {
        let j = i; while (j > 0 && !/^function |^const \w+ = /.test(linjer[j])) j--;
        stubbe.push({ linje: i + 1, navn: (linjer[j].match(/^(?:function\s+|const\s+)(\w+)/) || [])[1] || "stub" });
      }
    });
    ud.push({ fil, titel, sti: f, tjek, stubbe, opsum: kørsel.opsum, crash: kørsel.crash });
  }
  return ud;
}
// ── drill-gæt: kun værdier, aldrig kode ──────────────────────────────
// Et gæt er en JavaScript-værdi: tal (også NaN, Infinity og -0), tekst i "…", '…' eller `…` (uden ${…}),
// true/false/null/undefined og lister og objekter af dem. Gættet læses her og skrives ind i drill-filen i
// serverens egen form (skrivVærdi), så filen, Node kører, aldrig indeholder brugerens rå tekst. Gættet blev
// før prøvekørt med vm, men vm er ikke en sandkasse: et "gæt" kunne nå process og køre kode i serveren.
const ORD = { undefined: undefined, null: null, true: true, false: false, NaN: NaN, Infinity: Infinity };
function læsVærdi(tekst) {
  let i = 0, dybde = 0;
  const fejl = besked => { throw new Error(besked); };
  const mellemrum = () => { while (i < tekst.length && /\s/.test(tekst[i])) i++; };
  if (tekst.length > 2000) fejl("gættet er for langt");
  function værdi() {
    mellemrum();
    if (++dybde > 20) fejl("for mange lister i lister");
    const c = tekst[i];
    const v = c === '"' || c === "'" || c === "`" ? streng(c) : c === "[" ? liste() : c === "{" ? objekt() : talEllerOrd();
    dybde--;
    return v;
  }
  function streng(q) {
    let ud = "";
    for (i++; i < tekst.length && tekst[i] !== q; ) {
      let c = tekst[i++];
      if (q === "`" && c === "$" && tekst[i] === "{") fejl("${…} er kode, ikke en værdi");
      if (c === "\\") {
        const e = tekst[i++];
        const hex = n => {
          const h = tekst.slice(i, i + n);
          if (!new RegExp(`^[0-9a-fA-F]{${n}}$`).test(h)) fejl("ugyldig escape");
          i += n;
          return String.fromCharCode(parseInt(h, 16));
        };
        c = e === undefined ? fejl("teksten slutter midt i en \\") : e === "u" ? hex(4) : e === "x" ? hex(2)
          : { n: "\n", t: "\t", r: "\r", b: "\b", f: "\f", v: "\v", 0: "\0" }[e] ?? e;
      }
      ud += c;
    }
    if (tekst[i] !== q) fejl(`teksten mangler sit afsluttende ${q}`);
    i++;
    return ud;
  }
  function liste() {
    const ud = [];
    for (i++, mellemrum(); tekst[i] !== "]"; ) {
      if (i >= tekst.length) fejl("listen mangler sit ]");
      ud.push(værdi()); mellemrum();
      if (tekst[i] === ",") { i++; mellemrum(); } else if (tekst[i] !== "]") fejl("mangler , eller ] i listen");
    }
    i++;
    return ud;
  }
  function objekt() {
    const ud = {};
    for (i++, mellemrum(); tekst[i] !== "}"; ) {
      if (i >= tekst.length) fejl("objektet mangler sit }");
      let nøgle;
      if (tekst[i] === '"' || tekst[i] === "'") nøgle = streng(tekst[i]);
      else {
        const m = /^(?:[A-Za-z_$][\w$]*|\d+)/.exec(tekst.slice(i));
        if (!m) fejl("ugyldig nøgle i objektet");
        nøgle = m[0]; i += nøgle.length;
      }
      if (nøgle === "__proto__") fejl("__proto__ kan ikke bruges som nøgle");
      mellemrum(); if (tekst[i] !== ":") fejl("mangler : efter en nøgle"); i++;
      ud[nøgle] = værdi(); mellemrum();
      if (tekst[i] === ",") { i++; mellemrum(); } else if (tekst[i] !== "}") fejl("mangler , eller } i objektet");
    }
    i++;
    return ud;
  }
  function talEllerOrd() {
    const tal = /^[+-]?(?:Infinity|(?:\d[\d_]*(?:\.[\d_]*)?|\.\d[\d_]*)(?:[eE][+-]?\d+)?)/.exec(tekst.slice(i));
    if (tal) { i += tal[0].length; return Number(tal[0].replace(/_/g, "")); }
    const ord = /^[A-Za-z_$][\w$]*/.exec(tekst.slice(i));
    if (ord && Object.prototype.hasOwnProperty.call(ORD, ord[0])) { i += ord[0].length; return ORD[ord[0]]; }
    fejl(ord ? `${ord[0]} er ikke en værdi` : `uventet tegn ${JSON.stringify(tekst[i] ?? "")}`);
  }
  const v = værdi(); mellemrum();
  if (i < tekst.length) fejl("der står mere end én værdi");
  return v;
}
function skrivVærdi(v) {
  if (v === undefined) return "undefined";
  if (typeof v === "number") return Object.is(v, -0) ? "-0" : String(v);   // NaN, Infinity og -Infinity skrives som sig selv
  if (typeof v === "string") return JSON.stringify(v);
  if (v === null || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return `[${v.map(skrivVærdi).join(", ")}]`;
  const par = Object.keys(v).map(k => `${/^[A-Za-z_$][\w$]*$/.test(k) ? k : JSON.stringify(k)}: ${skrivVærdi(v[k])}`);
  return par.length ? `{ ${par.join(", ")} }` : "{}";
}

async function gemDrill({ fil, linje, beskrivelse, gaet }, meta = {}) {
  const f = drillFil(fil);
  gaet = String(gaet || "").trim();
  if (!gaet || /[\r\n]/.test(gaet)) throw new Error("skriv dit gæt på én linje");
  if (gaet === "TOM") throw new Error("det er jo ikke et gæt");
  // En fejltype uden anførselstegn (ReferenceError) er ment som tekst
  if (/^[A-Z]\w*Error$/.test(gaet)) gaet = `"${gaet}"`;
  try { gaet = skrivVærdi(læsVærdi(gaet)); } catch (e) {
    const hint = /er ikke en værdi/.test(e.message) ? ` Tekst skal stå i anførselstegn: "${gaet}".` : ` Tekst skal stå i anførselstegn, fx "number".`;
    throw new Error(`gættet kan ikke læses som en værdi (${e.message}).${hint}`);
  }
  const tekst = læs(f);
  // Er linjen flyttet (fx efter en rettelse i VS Code), findes tjekket på beskrivelsen, hvis den er entydig
  const alle = tjekKald(tekst), samme = alle.filter(x => !x.fejl && x.desc === beskrivelse);
  let t = alle.find(x => x.linje === +linje);
  if ((!t || t.fejl || t.desc !== beskrivelse) && samme.length === 1) t = samme[0];
  if (!t || t.fejl || t.desc !== beskrivelse) throw new Error("linjen har ændret sig; genindlæs siden");
  skriv(f, `${tekst.slice(0, t.gaetStart)} ${gaet}${tekst.slice(t.gaetSlut)}`);
  const k = await koerDrill(f);
  drillCache = null;
  // Går filen ned efter gættet, sættes den tilbage, så drillen altid kan køres
  if (k.crash) { skriv(f, tekst); return { status: "ukendt", fejl: `Filen kunne ikke køres med det gæt, så det er ikke gemt.\n${k.crash}` }; }
  logFoersoeg({ ...meta, type: "drill", noegle: `drill/${fil}#${beskrivelse}`, rigtig: !k.fejl[beskrivelse] });
  const forklaring = forklaringer(fil)[forklaringNoegle(beskrivelse)] || null;
  return k.fejl[beskrivelse] ? { status: "forkert", javascript: k.fejl[beskrivelse].js, forklaring } : { status: "rigtig", javascript: gaet, forklaring };
}

// ── eksamen (gamle sæt, tjeklister og pensumspørgsmål) ──────────────
// <Fag>/Eksamenstræning/<id>.md + <id>-svar.md. Opbygning: "# titel", en kursiv metalinje, "---",
// sektioner "## Del A …"/"## Opgave 1 …"/"## Uge 36 …" med evt. fælles tekst, og opgaver "**N.**".
// Hver opgave slutter med "*Emne: … · uge NN*" eller "· kap. N".
const EKS_FAG = { alfa: "Alfa", gamma: "Gamma", beta: "Beta" };
const eksDir = fag => path.join(ROD, EKS_FAG[fag], "Eksamenstræning");
function eksFil(fag, id, svar = false) {
  if (!EKS_FAG[fag] || !/^[\w-]{1,40}$/.test(id) || /-svar$/.test(id)) throw new Error("ukendt sæt");
  const f = path.join(eksDir(fag), `${id}${svar ? "-svar" : ""}.md`);
  if (!fs.existsSync(f)) throw new Error("sættet findes ikke");
  return f;
}
function parseEksamen(tekst) {
  const linjer = tekst.split("\n");
  const titel = (tekst.match(/^# (.*)$/m) || [])[1] || "";
  const meta = (linjer.find(l => /^\*[^*].*\*\s*$/.test(l.trim())) || "").trim().replace(/^\*|\*$/g, "");
  const t = meta.match(/(\d+)\s*time/i), m = meta.match(/(\d+)\s*min/i);
  const varighed = t ? +t[1] * 60 : m ? +m[1] : null;
  const skille = linjer.findIndex(l => /^---\s*$/.test(l));
  const intro = linjer.slice(0, Math.max(0, skille)).filter(l => !/^# /.test(l) && l.trim() !== `*${meta}*`).join("\n").trim();
  const sektioner = []; let sek = null, q = null;
  const lukQ = () => { if (q && sek) { const tx = q.linjer.join("\n").trim(); const e = tx.match(/\n?\*Emne:\s*([^*]+)\*\s*$/);
    const emne = e ? e[1].trim() : null; sek.spoergsmaal.push({ nr: q.nr, tekst: e ? tx.slice(0, e.index).trim() : tx, emne,
      uge: +((emne || "").match(/uge\s+(\d+)/i) || [])[1] || null, kap: +((emne || "").match(/kap\.?\s*(\d+)/i) || [])[1] || null }); } q = null; };
  for (const l of linjer.slice(skille + 1)) {
    const h = l.match(/^## (.*)$/);
    if (h) { lukQ(); const v = h[1].match(/\((\d+)\s*(?:%|point)\)/i); sek = { titel: h[1].replace(/\s*\(\d+\s*(?:%|point)\)\s*$/i, "").trim(), vaegt: v ? +v[1] : null, intro: [], spoergsmaal: [] }; sektioner.push(sek); continue; }
    if (/^---\s*$/.test(l)) { lukQ(); continue; }
    const n = l.match(/^\*\*(\d+)\.\*\*\s*(.*)$/);
    if (n && sek) { lukQ(); q = { nr: +n[1], linjer: [n[2]] }; continue; }
    if (q) q.linjer.push(l); else if (sek) sek.intro.push(l);
  }
  lukQ();
  sektioner.forEach(x => x.intro = x.intro.join("\n").trim());
  return { titel, meta, varighed, intro, sektioner };
}
function eksamensLog() {
  const ud = {};
  for (const p of logPoster()) if (p.type === "eksamen" && p.mark) (ud[p.noegle.split("#")[0]] ||= []).push(p);
  return ud;
}
function eksamenListe() {
  const log = eksamensLog(), ud = [];
  for (const fag of Object.keys(EKS_FAG)) {
    let filer = []; try { filer = fs.readdirSync(eksDir(fag)).filter(n => /\.md$/.test(n) && !/-svar\.md$/.test(n) && !/^README/i.test(n)).sort().reverse(); } catch { continue; }
    for (const n of filer) {
      const id = n.replace(/\.md$/, ""), e = parseEksamen(læs(path.join(eksDir(fag), n)));
      const ps = log[`${fag}/${id}`] || [], sidste = {};
      for (const p of ps) sidste[p.noegle] = p;
      const res = Object.values(sidste).reduce((a, p) => (a[RES[p.mark]]++, a), { sad: 0, halvt: 0, blankt: 0 });
      const prøver = [...new Set(ps.filter(p => p.proeve).map(p => p.proeve))];
      ud.push({ fag, id, titel: e.titel, meta: e.meta, varighed: e.varighed, antal: e.sektioner.reduce((a, x) => a + x.spoergsmaal.length, 0),
        sektioner: e.sektioner.map(x => ({ titel: x.titel, vaegt: x.vaegt, antal: x.spoergsmaal.length })),
        har_facit: fs.existsSync(path.join(eksDir(fag), `${id}-svar.md`)), resultat: res, proever: prøver.sort() });
    }
  }
  return ud;
}
function eksFacitAlle(fag, id) {
  const f = path.join(eksDir(fag), `${id}-svar.md`);
  if (!fs.existsSync(f)) return {};
  const { linjer, blokke: bs } = blokke(læs(f));
  return Object.fromEntries(bs.map(b => [b.nr, linjer.slice(b.start, b.slut).join("\n").trim().replace(/^\*\*\d+\.\*\*\s*/, "")]));
}
// Besvarelsen gemmes som din egen fil, så du kan se den igen (og rette den mod facit)
function afslutEksamen({ fag, id, svar, marks, start, slut, tilstand }) {
  eksFil(fag, id);
  const e = parseEksamen(læs(eksFil(fag, id))), dato = new Date().toISOString().slice(0, 10);
  const proeve = tilstand === "proeve" ? `${dato}T${new Date().toTimeString().slice(0, 5)}` : null;
  const dir = path.join(eksDir(fag), "besvarelser"); fs.mkdirSync(dir, { recursive: true });
  const min = start && slut ? Math.round((Date.parse(slut) - Date.parse(start)) / 60000) : null;
  const ud = [`# Min besvarelse — ${e.titel}`, "", `*${tilstand === "proeve" ? "Prøveeksamen" : "Øvelse"} ${dato}${min != null ? ` · ${min} min brugt` : ""}${e.varighed ? ` af ${e.varighed}` : ""}*`, "", "---", ""];
  for (const sek of e.sektioner) {
    ud.push(`## ${sek.titel}`, "");
    for (const q of sek.spoergsmaal) {
      const m = marks?.[q.nr], tx = String(svar?.[q.nr] ?? "").replace(/\r/g, "").trim();
      ud.push(`**${q.nr}.** ${m?.mark ? `[${MARK[RES[m.mark]] || ""}] ` : ""}${tx ? "" : "*(ikke besvaret)*"}`);
      if (tx) ud.push("", ...(sek.titel.startsWith("Opgave") || fag === "gamma" ? ["```js", tx, "```"] : tx.split("\n").map(l => `> ${l}`)));
      ud.push("");
    }
  }
  const fil = path.join(dir, `${id}-${dato}${tilstand === "proeve" ? "-proeve" : ""}.md`);
  skriv(fil, ud.join("\n"));
  for (const [nr, m] of Object.entries(marks || {})) {
    if (!RES[m?.mark]) continue;
    const p = { tid: new Date().toISOString(), type: "eksamen", noegle: `${fag}/${id}#${nr}`, mark: RES[m.mark], ...(SIKKERHED.includes(m.sikkerhed) ? { sikkerhed: m.sikkerhed } : {}), ...(proeve ? { proeve } : {}) };
    fs.appendFileSync(LOG, JSON.stringify(p) + "\n");
  }
  eksporterSnart();
  return { gemt: path.relative(ROD, fil) };
}
function gemEksamenResultat({ fag, id, nr, mark, sikkerhed }, meta = {}) {
  eksFil(fag, id);
  if (!RES[mark]) throw new Error("ukendt markering");
  logFoersoeg({ ...meta, type: "eksamen", noegle: `${fag}/${id}#${+nr}`, mark: RES[mark], ...(SIKKERHED.includes(sikkerhed) ? { sikkerhed } : {}) });
  return { gemt: true };
}

// ── indhentet / læst pr. uge ─────────────────────────────────────────
// Scripts/laest.json: { "alfa": { "36": "2026-10-01" }, "beta": { ... } }. Nye genkaldsspørgsmål kommer kun
// i Dagens kort fra uger, der er markeret her; ellers ville man "genkalde" stof, man ikke har læst.
const LAEST = path.join(DATA, "laest.json");
function læst() { try { return JSON.parse(læs(LAEST)); } catch { return {}; } }
function gemLæst({ fag, uge, laest }) {
  if (fag !== "alfa" && fag !== "beta") throw new Error("ukendt fag");
  uge = String(+uge);
  if (!(+uge >= 1 && +uge <= 53)) throw new Error("ukendt uge");
  const l = læst();
  l[fag] ||= {};
  if (laest) l[fag][uge] = new Date().toISOString().slice(0, 10); else delete l[fag][uge];
  skriv(LAEST, JSON.stringify(l, null, 1) + "\n");
  return { fag, uge: +uge, laest: l[fag][uge] || null };
}
// Ugen et genkaldsspørgsmål hører til: "Uge 36 — …" i afsnittet, ellers første uge i filnavnet
const ugeFor = (afsnit, fil) => +((afsnit || "").match(/Uge\s+(\d+)/i) || fil.match(/uge(\d+)/) || [])[1] || null;

// ── repetition (spaced repetition + kalibrering) ─────────────────────
// Alt regnes ud fra genkald-log.jsonl; der er ingen separat tilstand. Tre slags kort:
//   genkald  alle spørgsmål i genkald-*.md (nye kommer med nogle få ad gangen)
//   begreb   definitioner, du selv har skrevet i begreber.md (overhøres)
//   drill    tjek-opgaver, du har gættet forkert mindst én gang
// Interval efter et forsøg: ✓ → 3, 7, 21, 60, 120 dage (stiger for hver ✓ i træk), ~ → 2 dage, ✗ → 1 dag.
const INTERVAL = [3, 7, 21, 60, 120], NYE_PR_DAG = 5, MAKS_KORT = 25, DAG = 864e5;
const RES = { sad: "sad", halvt: "halvt", blankt: "blankt", "✓": "sad", "~": "halvt", "✗": "blankt" };

// I tidsorden: svar fra telefonen kommer først i loggen, når de er sendt, men med det tidspunkt, du gav dem
function logPoster() {
  try { return læs(LOG).split("\n").filter(Boolean).map(l => JSON.parse(l)).sort((a, b) => String(a.tid).localeCompare(String(b.tid))); } catch { return []; }
}
// Hændelser pr. kort i tidsorden: { tid, res, sikkerhed }
function hændelser(poster) {
  const ud = {};
  const put = (k, h) => (ud[k] ||= []).push(h);
  const sidsteDrillFejl = {};
  for (const p of poster) {
    const t = Date.parse(p.tid);
    if (p.type === "genkald" && p.mark) put(`genkald:${p.noegle}`, { t, res: RES[p.mark], sikkerhed: p.sikkerhed });
    else if (p.type === "begreb") put(`begreb:${p.noegle}`, { t, res: "ny" });
    else if (p.type === "overhoer") put(`begreb:${p.noegle}`, { t, res: RES[p.mark], sikkerhed: p.sikkerhed });
    else if (p.type === "drill") {
      // Et rigtigt gæt lige efter et forkert er set i facit, ikke husket; det tæller ikke
      if (!p.rigtig) { sidsteDrillFejl[p.noegle] = t; put(`drill:${p.noegle}`, { t, res: "blankt" }); }
      else if (!(sidsteDrillFejl[p.noegle] && t - sidsteDrillFejl[p.noegle] < DAG)) put(`drill:${p.noegle}`, { t, res: "sad", foerste: true });
    } else if (p.type === "drill-rep") put(`drill:${p.noegle}`, { t, res: RES[p.mark], sikkerhed: p.sikkerhed });
    else if (p.type === "eksamen" && p.mark) put(`eksamen:${p.noegle}`, { t, res: RES[p.mark], sikkerhed: p.sikkerhed });
  }
  return ud;
}
function planlæg(hs) {
  let niveau = 0, forfald = null, sidst = null;
  for (const h of hs) {
    sidst = h;
    if (h.res === "sad") { niveau++; forfald = h.t + INTERVAL[Math.min(niveau, INTERVAL.length) - 1] * DAG; }
    else if (h.res === "halvt") { niveau = Math.max(0, niveau - 1); forfald = h.t + 2 * DAG; }
    else { niveau = 0; forfald = h.t + DAG; }   // blankt, eller nyskrevet definition
  }
  return { niveau, forfald, sidst: sidst?.t ?? null };
}

async function repetitionsKort() {
  const poster = logPoster(), H = hændelser(poster), nu = Date.now(), L = læst();
  const dagSlut = new Date(); dagSlut.setHours(23, 59, 59, 999);
  const idagStart = new Date(); idagStart.setHours(0, 0, 0, 0);
  const alle = [];
  for (const f of genkaldListe()) for (const q of f.spoergsmaal) {
    const noegle = `${f.fag}/${f.fil}#${q.nr}`, hs = H[`genkald:${noegle}`] || [];
    // Markeret i filen, men ikke i loggen (fx i VS Code): forfalden nu
    const p = hs.length ? planlæg(hs) : q.mark ? { niveau: 0, forfald: 0, sidst: null } : null;
    const uge = ugeFor(q.afsnit, f.fil);
    alle.push({ type: "genkald", noegle, fag: f.fag, uge, laest: !!L[f.fag]?.[uge], kicker: `${FAG[f.fag]} · ${f.uger} · ${q.afsnit}`, titel: `Spørgsmål ${q.nr}`,
      spoergsmaal: q.tekst, ny: !p, ...(p || {}) });
  }
  const B = begreberListe();
  for (const fag of Object.keys(B)) for (const b of B[fag].begreber) {
    if (!b.definition) continue;
    const noegle = `${fag}/begreb/${b.begreb}`, hs = H[`begreb:${noegle}`] || [];
    const p = hs.length ? planlæg(hs) : { niveau: 0, forfald: 0, sidst: null };
    alle.push({ type: "begreb", noegle, fag, kicker: `${FAG[fag]} · begreb · ${b.afsnit}`, titel: b.begreb,
      spoergsmaal: `Forklar **${b.begreb}** med dine egne ord${B[fag].hoved_se ? ", og sig hvad det får dig til at se i en organisation" : ""}.`, ...p });
  }
  for (const k of await drillsCachet()) for (const t of k.tjek) {
    if (!t.udtryk) continue;
    const noegle = `drill/${k.fil}#${t.beskrivelse}`, hs = H[`drill:${noegle}`] || [];
    if (!hs.some(h => h.res === "blankt")) continue;   // kun dem, du har taget fejl af
    alle.push({ type: "drill", noegle, fag: "gamma", kicker: `${FAG.gamma} · drill · ${k.titel}`, titel: t.beskrivelse.replace(/\s+←.*$/, ""),
      spoergsmaal: "Hvad giver udtrykket?", udtryk: t.udtryk, kontekst: t.kontekst, ...planlæg(hs) });
  }

  // Eksamensopgaver, du ikke havde helt rigtigt, repeteres som kort
  for (const k of Object.keys(H).filter(k => k.startsWith("eksamen:"))) {
    const hs = H[k]; if (!hs.some(h => h.res !== "sad")) continue;
    const [, fag, id, nr] = k.match(/^eksamen:(\w+)\/([\w-]+)#(\d+)$/) || [];
    let q = null, titel = id;
    try { const e = parseEksamen(læs(eksFil(fag, id))); titel = e.titel; for (const sek of e.sektioner) q ||= sek.spoergsmaal.find(x => x.nr === +nr) && { ...sek.spoergsmaal.find(x => x.nr === +nr), sek: sek.titel, intro: sek.intro }; } catch { continue; }
    if (!q) continue;
    alle.push({ type: "eksamen", noegle: k.slice(8), fag, kicker: `${EKS_FAG[fag]} · eksamen · ${titel.replace(/^\w+ — /, "")} · ${q.sek}`, titel: `Opgave ${nr}`,
      spoergsmaal: (fag === "gamma" && q.intro ? q.intro + "\n\n" : "") + q.tekst, ...planlæg(hs) });
  }
  const forfaldne = alle.filter(k => !k.ny && k.forfald <= dagSlut.getTime()).sort((a, b) => a.forfald - b.forfald);
  const nyeIdag = new Set(poster.filter(p => p.type === "genkald" && p.mark && Date.parse(p.tid) >= idagStart.getTime()).map(p => p.noegle));
  const førsteGang = poster.reduce((m, p) => (p.type === "genkald" && p.mark && !m.has(p.noegle) ? m.set(p.noegle, Date.parse(p.tid)) : m), new Map());
  const nyeTaget = [...førsteGang.values()].filter(t => t >= idagStart.getTime()).length;
  const nye = alle.filter(k => k.ny && k.laest).slice(0, Math.max(0, NYE_PR_DAG - nyeTaget));
  const venter = alle.filter(k => k.ny && !k.laest);
  // Nye spørgsmål kommer altid med; typerne blandes (genkald, begreb, drill på skift), fordi blandet
  // øvelse (interleaving) husker bedre end blokke af det samme
  const valgt = [...forfaldne.slice(0, Math.max(0, MAKS_KORT - nye.length)), ...nye];
  const spor = ["genkald", "eksamen", "begreb", "drill"].map(t => valgt.filter(k => k.type === t));
  const kø = [];
  while (spor.some(x => x.length)) for (const x of spor) if (x.length) kø.push(x.shift());

  // Kalibrering: hvor tit sad det, når du sagde "sikker" / "usikker" / "gætter"?
  const kal = Object.fromEntries(SIKKERHED.map(s => [s, { n: 0, sad: 0, halvt: 0, blankt: 0 }]));
  for (const hs of Object.values(H)) for (const h of hs) if (h.sikkerhed && kal[h.sikkerhed] && RES[h.res]) { kal[h.sikkerhed].n++; kal[h.sikkerhed][h.res]++; }
  const klaretIdag = poster.filter(p => ["genkald", "overhoer", "drill-rep"].includes(p.type) && p.mark && Date.parse(p.tid) >= idagStart.getTime()).length;
  const næste = alle.filter(k => !k.ny && k.forfald > dagSlut.getTime()).sort((a, b) => a.forfald - b.forfald)[0];

  return {
    kort: kø.map(({ forfald, sidst, ...k }) => ({ ...k, id: `${k.type}:${k.noegle}`, forfald: forfald ? new Date(forfald).toISOString() : null, sidst: sidst ? new Date(sidst).toISOString() : null })),
    statistik: { forfaldne: forfaldne.length, nye: nye.length, nye_venter_paa_laesning: venter.length,
      nye_klar: alle.filter(k => k.ny && k.laest).length, klaret_i_dag: klaretIdag, i_alt: alle.length,
      laert: alle.filter(k => !k.ny && k.niveau >= 2).length, naeste: næste ? new Date(næste.forfald).toISOString() : null,
      kalibrering: kal, minutter: Math.max(1, Math.round(kø.length * 0.75)) },
  };
}
async function repetitionSvar(noegle) {
  const [type, rest] = [noegle.split(":")[0], noegle.slice(noegle.indexOf(":") + 1)];
  if (type === "genkald") {
    const m = rest.match(/^(alfa|beta)\/(genkald-[\w-]+\.md)#(\d+)$/);
    if (!m) throw new Error("ukendt kort");
    return { svar: facit(m[1], m[2], +m[3]), form: "md" };
  }
  if (type === "begreb") {
    const [fag, , ...navn] = rest.split("/"), b = (begreberListe()[fag]?.begreber || []).find(x => x.begreb === navn.join("/"));
    if (!b) throw new Error("ukendt begreb");
    return { svar: b.definition, se: b.se || null, form: "tekst" };
  }
  if (type === "eksamen") {
    const m = rest.match(/^(\w+)\/([\w-]+)#(\d+)$/);
    if (!m) throw new Error("ukendt kort");
    eksFil(m[1], m[2]);
    return { svar: eksFacitAlle(m[1], m[2])[+m[3]] || null, form: "md" };
  }
  if (type === "drill") {
    const m = rest.match(/^drill\/(kap\d+[\w-]*\.js)#(.*)$/);
    const t = m && (await drillsCachet()).find(k => k.fil === m[1])?.tjek.find(x => x.beskrivelse === m[2]);
    if (!t) throw new Error("ukendt drill");
    return { svar: t.status === "forkert" ? t.javascript : t.gaet, form: "kode", forklaring: forklaringer(m[1])[forklaringNoegle(t.beskrivelse)] || null };
  }
  throw new Error("ukendt kort");
}
function gemRepetition({ noegle, mark, sikkerhed, svar }, meta = {}) {
  noegle = String(noegle || "");
  if (!RES[mark]) throw new Error("ukendt markering");
  if (sikkerhed != null && !SIKKERHED.includes(sikkerhed)) throw new Error("ukendt sikkerhed");
  const type = noegle.split(":")[0], rest = noegle.slice(noegle.indexOf(":") + 1);
  if (type === "genkald") {
    const m = rest.match(/^(alfa|beta)\/(genkald-[\w-]+\.md)#(\d+)$/);
    if (!m) throw new Error("ukendt kort");
    return gemGenkald({ fag: m[1], fil: m[2], nr: +m[3], svar, mark: RES[mark], sikkerhed }, meta);
  }
  if (type === "eksamen") {
    const m = rest.match(/^(\w+)\/([\w-]+)#(\d+)$/);
    if (!m) throw new Error("ukendt kort");
    return gemEksamenResultat({ fag: m[1], id: m[2], nr: +m[3], mark, sikkerhed }, meta);
  }
  if (type !== "begreb" && type !== "drill") throw new Error("ukendt kort");
  logFoersoeg({ ...meta, type: type === "begreb" ? "overhoer" : "drill-rep", noegle: rest, mark: RES[mark], ...(sikkerhed ? { sikkerhed } : {}) });
  return { gemt: true };
}

// ── på farten (mobil.html) ───────────────────────────────────────────
// Telefonen er ofte uden forbindelse til Mac'en (den sover i tasken). Den henter derfor en pakke, mens
// der er forbindelse, og sender svarene med /sync bagefter. Pakken har facit med til dagens kort og de
// ekstra genkaldsspørgsmål, så siden kan vise det efter dit forsøg uden net. Ugættede drills og tomme
// begreber kommer uden facit: drills rettes af JavaScript på Mac'en, når de er sendt.
const EKSTRA_GENKALD = 20;
async function pakke() {
  const r = await repetitionsKort(), L = læst(), log = sidst();
  const kort = [];
  for (const k of r.kort) { let svar = null; try { svar = await repetitionSvar(k.id); } catch { /* kortet er væk siden */ } kort.push({ ...k, facit: svar }); }
  // Ekstra genkald: ikke i dagens kort; først nye fra læste uger i filens orden, så ✗, ~ og ✓ med ældste forsøg først
  const iDag = new Set(kort.map(k => k.id)), vægt = { "✗": 1, "~": 2, "✓": 3 }, kand = [];
  for (const f of genkaldListe()) for (const q of f.spoergsmaal) {
    const noegle = `${f.fag}/${f.fil}#${q.nr}`;
    if (iDag.has(`genkald:${noegle}`) || (!q.mark && !L[f.fag]?.[q.uge])) continue;
    kand.push({ f, q, noegle, v: q.mark ? vægt[q.mark] : 0, t: log[noegle]?.tid || "" });
  }
  kand.sort((a, b) => a.v - b.v || (a.v ? a.t.localeCompare(b.t) : 0));
  const ekstra = kand.slice(0, EKSTRA_GENKALD).map(({ f, q, noegle }) => ({ id: `genkald:${noegle}`, type: "genkald", noegle, fag: f.fag,
    kicker: `${FAG[f.fag]} · ${f.uger} · ${q.afsnit}`, titel: `Spørgsmål ${q.nr}`, spoergsmaal: q.tekst, ny: !q.mark, mark: q.mark,
    facit: { svar: facit(f.fag, f.fil, q.nr), form: "md" } }));
  const B = begreberListe(), begreber = [];
  for (const fag of Object.keys(B)) for (const b of B[fag].begreber) if (!b.definition)
    begreber.push({ fag, begreb: b.begreb, afsnit: b.afsnit, kilde: b.kilde, se: B[fag].hoved_se ? "" : null });
  const drills = [];
  for (const k of await drillsCachet()) for (const t of k.tjek) if (t.status === "tom" && t.udtryk)
    drills.push({ fil: k.fil, titel: k.titel, linje: t.linje, afsnit: t.afsnit, beskrivelse: t.beskrivelse, udtryk: t.udtryk, kontekst: t.kontekst });
  const { klaret_i_dag, laert, i_alt, naeste, kalibrering } = r.statistik;
  return { genereret: new Date().toISOString(), kort, ekstra, begreber, drills, statistik: { klaret_i_dag, laert, i_alt, naeste, kalibrering } };
}

// Hver post fra telefonen har et id; er det allerede gemt (svaret nåede ikke tilbage sidst), gemmes den ikke igen
async function sync({ poster }) {
  if (!Array.isArray(poster) || poster.length > 500) throw new Error("ingen poster");
  const set = new Map(logPoster().filter(p => p.sync_id).map(p => [p.sync_id, p])), nu = Date.now(), ud = [];
  for (const p of [...poster].sort((a, b) => String(a.tid).localeCompare(String(b.tid)))) {
    const id = String(p?.id || "");
    if (!/^[\w-]{8,64}$/.test(id)) { ud.push({ id, ok: false, fejl: "posten mangler et id" }); continue; }
    if (set.has(id)) { const g = set.get(id); ud.push({ id, ok: true, allerede: true, ...(g.type === "drill" ? { status: g.rigtig ? "rigtig" : "forkert" } : {}) }); continue; }
    // Tidspunktet, du svarede; et ugyldigt eller fremtidigt tidspunkt bliver til nu
    const t = Date.parse(p.tid), meta = { tid: new Date(t > 0 && t <= nu + 3e5 ? Math.min(t, nu) : nu).toISOString(), sync_id: id };
    try {
      const d = p.data || {};
      const r = p.type === "repetition" ? gemRepetition(d, meta) : p.type === "begreb" ? gemBegreb(d, meta)
        : p.type === "drill" ? await gemDrill(d, meta) : (() => { throw new Error("ukendt type"); })();
      ud.push(r.status === "ukendt" ? { id, ok: false, fejl: r.fejl } : { id, ok: true, ...r });
    } catch (e) { ud.push({ id, ok: false, fejl: e.message }); }
  }
  return { resultater: ud };
}

// ── deadlines ────────────────────────────────────────────────────────
// Færdig-markering fra Deadlines-siden. Nummererede afleveringer ("Opgave 3") skrives i kolonnen "Afleveret" i
// Gamma/vscode/Opgaver/README.md
// (der hvor køreplanen også læser dem); andre frister i Scripts/deadlines-status.json.
const STATUS = path.join(DATA, "deadlines-status.json");
function gemDeadline({ noegle, faerdig }) {
  noegle = String(noegle || "");
  if (!/^[\wÆØÅæøå]{1,12}\|(Opgave \d{1,2}|[a-z]+\|\d{0,2})$/.test(noegle)) throw new Error("ukendt frist");
  const dato = new Date(), iso = dato.toISOString().slice(0, 10);
  const g = (noegle.match(/\|(Opgave \d{1,2})$/) || [])[1];
  if (g) {
    const f = path.join(ROD, FAG.gamma, "vscode", "Opgaver", "README.md");
    const linjer = læs(f).split("\n");
    const hovedIdx = linjer.findIndex((l, i) => /^\s*\|\s*Opgave\s*\|/i.test(l) && /^\s*\|\s*-/.test(linjer[i + 1] || ""));
    if (hovedIdx < 0) throw new Error("fandt ikke statustabellen i Opgaver/README.md");
    const kol = celler(linjer[hovedIdx]).findIndex(c => /^Afleveret$/i.test(c));
    const i = linjer.findIndex((l, j) => j > hovedIdx && celler(l)[0] === g);
    if (kol < 0 || i < 0) throw new Error(`${g} står ikke i statustabellen`);
    const c = celler(linjer[i]);
    c[kol] = faerdig ? idag() : "";
    linjer[i] = række(c);
    skriv(f, linjer.join("\n"));
  } else {
    let st = {}; try { st = JSON.parse(læs(STATUS)); } catch { /* ny fil */ }
    if (faerdig) st[noegle] = { faerdig: iso }; else delete st[noegle];
    skriv(STATUS, JSON.stringify(st, null, 1) + "\n");
  }
  logFoersoeg({ type: "deadline", noegle, faerdig: !!faerdig });
  return { noegle, faerdig: faerdig ? (g ? idag() : iso) : null };
}

// ── http ─────────────────────────────────────────────────────────────
function send(res, kode, obj) {
  const b = Buffer.from(JSON.stringify(obj));
  res.writeHead(kode, { "Content-Type": "application/json; charset=utf-8", "Content-Length": b.length, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" });
  res.end(b);
}
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://x"), sti = url.pathname.replace(/^\/studie\/api/, "");
  const vaert = String(req.headers.host || "").toLowerCase().replace(/:(?:443|80)$/, "");
  if (!VAERTER.has(vaert)) { console.error(`afvist vært: ${vaert.slice(0, 80)} (${req.method} ${sti.slice(0, 40)})`); return send(res, 403, { fejl: "ukendt vært" }); }
  try {
    if (req.method === "GET") {
      if (sti === "/genkald") return send(res, 200, genkaldListe());
      if (sti === "/facit") return send(res, 200, { facit: facit(url.searchParams.get("fag"), url.searchParams.get("fil"), +url.searchParams.get("nr")) });
      if (sti === "/begreber") return send(res, 200, begreberListe());
      if (sti === "/drills") { drillCache = null; return send(res, 200, await drillsCachet()); }
      if (sti === "/repetition") return send(res, 200, await repetitionsKort());
      if (sti === "/laest") return send(res, 200, læst());
      if (sti === "/eksamen") return send(res, 200, eksamenListe());
      if (sti === "/eksamen/saet") { const f = eksFil(url.searchParams.get("fag"), url.searchParams.get("id")); return send(res, 200, parseEksamen(læs(f))); }
      // Facit kun på opfordring: ét nummer under øvelse, alle efter en afleveret prøveeksamen
      if (sti === "/eksamen/facit") { const fag = url.searchParams.get("fag"), id = url.searchParams.get("id"), nr = url.searchParams.get("nr"); eksFil(fag, id);
        const alle = eksFacitAlle(fag, id); return send(res, 200, nr ? { facit: alle[+nr] || null } : { facit: alle }); }
      if (sti === "/pakke") return send(res, 200, await pakke());
      if (sti === "/repetition/svar") return send(res, 200, await repetitionSvar(url.searchParams.get("noegle") || ""));
      return send(res, 404, { fejl: "ikke fundet" });
    }
    if (req.method !== "POST") return send(res, 405, { fejl: "kun GET og POST" });
    // Kun Kompas må skrive: en fremmed side kan ikke sende JSON på tværs af origins uden en CORS-preflight,
    // som serveren aldrig godkender, og Origin-tjekket fanger resten
    if (!ORIGINS.includes(req.headers.origin) || !String(req.headers["content-type"] || "").startsWith("application/json")) return send(res, 403, { fejl: "kun fra Kompas" });
    let krop = "";
    for await (const c of req) { krop += c; if (krop.length > 500000) return send(res, 413, { fejl: "for stort" }); }
    const d = JSON.parse(krop || "{}");
    if (sti === "/genkald") return send(res, 200, gemGenkald(d));
    if (sti === "/repetition") return send(res, 200, gemRepetition(d));
    if (sti === "/laest") return send(res, 200, gemLæst(d));
    if (sti === "/eksamen/resultat") return send(res, 200, gemEksamenResultat(d));
    if (sti === "/eksamen/afslut") return send(res, 200, afslutEksamen(d));
    if (sti === "/begreb") return send(res, 200, gemBegreb(d));
    if (sti === "/drill") return send(res, 200, await gemDrill(d));
    if (sti === "/sync") return send(res, 200, await sync(d));
    if (sti === "/deadline") return send(res, 200, gemDeadline(d));
    return send(res, 404, { fejl: "ikke fundet" });
  } catch (e) {
    return send(res, 400, { fejl: e.message });
  }
});
server.listen(PORT, "127.0.0.1", () => console.error(`Studie-API på http://127.0.0.1:${PORT} (Caddy: https://kompas.localhost/studie/api/)`));
