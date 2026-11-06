// Nyt semester i ét trin (README.md, "Nyt semester"). Kør fra det semester, der slutter (KOMPAS_SEMESTER eller ~/kompas/studie):
//   node Scripts/nyt-semester.js "<navn>"                 prøvekørsel: viser, hvad der bliver lavet
//   node Scripts/nyt-semester.js "<navn>" --kør           laver mappen ved siden af denne
//        --navn "<visningsnavn>"                          semestrets navn på siderne (semester i fag.json, fx
//                                                         "2. semester"); uden står mappens navn dér
//   node Scripts/nyt-semester.js "<navn>" --skift         prøvekørsel af skiftet: hvad der mangler i den nye mappe
//   node Scripts/nyt-semester.js "<navn>" --skift --kør   peger ~/kompas/studie på den nye mappe, genstarter Studie-serveren
//                                                         og kører eksporten og testene dér
//
// Den nye mappe får Scripts/ (koden, siderne, testene og studiemaal.json, men ikke log- og statusfilerne), RUTINE.md,
// README.md, CLAUDE.md (uden rækkerne under "Vigtige datoer" og "Egen plan"), .gitignore, .vscode/settings.json og
// .claude/settings.json, tomme Bøger/ og Uge_Overblik/ og en mappe pr. fag, der fortsætter. fag.json får kun de fag, der
// fortsætter: et kursus over flere semestre med timer tilbage, med dette_semester = kursusbeskrivelsens poster minus det, de
// tidligere semestre har haft (dette_semester og dets tidligere). De nye fag skriver du ind fra kursusbeskrivelserne.
// Scriptet opfinder ingen fag, datoer eller timer, rører ikke git og ændrer intet i det gamle semester.
//
// Test mod en kopi: KOMPAS_STUDIE_LINK=<et andet symlink> og STUDIE_EKSPORT_UD=<mappe>. Med et andet link end
// ~/kompas/studie genstartes serveren ikke.

const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");
const S = require("./semester");

const args = process.argv.slice(2), iNavn = args.indexOf("--navn"), visningsnavn = iNavn >= 0 ? args[iNavn + 1] : null;
const navn = args.find((a, i) => !a.startsWith("--") && (iNavn < 0 || i !== iNavn + 1)), kør = args.includes("--kør"), skift = args.includes("--skift");
const STD_LINK = path.join(os.homedir(), "kompas", "studie");
const LINK = process.env.KOMPAS_STUDIE_LINK ? path.resolve(process.env.KOMPAS_STUDIE_LINK) : STD_LINK;
const UD = process.env.STUDIE_EKSPORT_UD ? path.resolve(process.env.STUDIE_EKSPORT_UD) : null;

const læs = f => { try { return fs.readFileSync(f, "utf8"); } catch { return null; } };
const stop = tekst => { console.error(tekst); process.exit(1); };
if (!navn || /[/\\]/.test(navn) || (iNavn >= 0 && !visningsnavn))
  stop('Brug: node Scripts/nyt-semester.js "<navn>" [--navn "<visningsnavn>"] [--kør] [--skift]   (navnet er mappens navn, fx "2. sem")');

const NY = path.join(path.dirname(S.ROD), navn);
// Det semester, der slutter: mappen, scriptet ligger i, når den nye laves; ved skiftet det, linket peger på nu (også når
// scriptet køres fra den nye mappe)
const GAMMEL = skift ? (() => { try { return fs.realpathSync(LINK); } catch { return S.ROD; } })() : S.ROD;

// ── den nye mappe ────────────────────────────────────────────────────

// Log- og statusfiler, der hører til det gamle semester (README, "Nyt semester"), og filer, scriptet selv skriver
// (canvas-*: Canvas-scripternes log og hvad de har hentet; kun selve scripterne kommer med)
const UDEN = new Set(["genkald-log.jsonl", "laest.json", "deadlines-status.json", "fravaer.json", "fremmoede.json", "sessioner.json", "usb-vurdering.json",
  "fag.json", "undervisningsdage.json", ".DS_Store", "__pycache__", "node_modules"]);
const UDEN_STIER = ["fagnoter/backup", "fagnoter/vurdering-handlet.json"];
const udelad = (n, rel) => UDEN.has(n) || UDEN_STIER.includes(rel) || (/^canvas-/.test(n) && !n.endsWith(".js"));

// Et kursus over flere semestre, der fortsætter: kursusbeskrivelsens poster minus det, semestrene indtil nu har haft. null,
// når faget ikke fortsætter (ét semester, eller ingen timer tilbage).
function fortsaetter(f) {
  const ab = f.arbejdsbyrde;
  if (!ab?.poster?.length || (ab.semestre || 1) < 2) return null;
  const ds = ab.dette_semester;
  if (!ds?.poster?.length) return { fag: f, ukendt: true };
  const haft = {};
  for (const p of [...(ds.tidligere || []), ...ds.poster]) haft[p.navn] = (haft[p.navn] || 0) + p.timer;
  const r2 = x => Math.round(x * 100) / 100;
  const poster = ab.poster.map(p => ({ navn: p.navn, timer: r2(p.timer - (haft[p.navn] || 0)) })).filter(p => p.timer > 0);
  if (!poster.length) return null;
  return { fag: f, poster, tidligere: Object.entries(haft).map(([navn, timer]) => ({ navn, timer: r2(timer) })) };
}

function nyFagJson() {
  const gl = JSON.parse(læs(path.join(GAMMEL, "Scripts", "fag.json")));
  const forrige = gl.semester || path.basename(GAMMEL), idag = S.isoDato(new Date());
  const videre = gl.fag.map(fortsaetter).filter(Boolean);
  const fag = videre.map(v => {
    const { arbejdsbyrde: ab, ...f } = v.fag;
    const { dette_semester, ...kursus } = ab;
    return { ...f, canvas: [],
      arbejdsbyrde: v.ukendt ? kursus : { ...kursus, dette_semester: { til: "eksamen",
        vurdering: `Resten af kursusbeskrivelsens timer efter ${forrige}: hver post minus det, de tidligere semestre har haft (tidligere). Regnet af nyt-semester.js ${idag}. Slutter semestret ikke med eksamen i faget, så ret til til sidste_undervisning.`,
        poster: v.poster, tidligere: v.tidligere } } };
  });
  const forklaring = String(gl._forklaring || "") + (/tidligere/.test(gl._forklaring || "") ? "" :
    " dette_semester.tidligere: de tidligere semestres del af posterne, som nyt-semester.js har trukket fra kursets poster.");
  return { json: { ...gl, _forklaring: forklaring, semester: visningsnavn || navn, fag }, videre, slut: gl.fag.filter(f => !videre.some(v => v.fag.id === f.id)) };
}

// CLAUDE.md uden rækkerne under "Vigtige datoer" og "Egen plan", så det gamle semesters frister og eksamensdage ikke følger med
function tømAfsnit(md, titel, tekst) {
  return md.split(/^(?=## )/m).map(a => {
    if (!a.startsWith("## ") || !titel.test(a.slice(3))) return a;
    const linjer = a.split("\n"), tabel = linjer.filter(l => /^\s*\|/.test(l)).slice(0, 2);
    return `${linjer[0]}\n\n${tekst}\n\n${tabel.join("\n")}\n\n`;
  }).join("");
}

function kopierScripts(fra, til, rel = "") {
  for (const n of fs.readdirSync(fra)) {
    const r = rel ? `${rel}/${n}` : n;
    if (udelad(n, r)) continue;
    const f = path.join(fra, n), st = fs.statSync(f);
    if (st.isDirectory()) { fs.mkdirSync(path.join(til, n), { recursive: true }); kopierScripts(f, path.join(til, n), r); }
    else fs.copyFileSync(f, path.join(til, n));
  }
}

function lav() {
  if (fs.existsSync(NY)) stop(`${NY} findes allerede. Vælg et andet navn, eller kør med --skift, når mappen er udfyldt.`);
  const { json, videre, slut } = nyFagJson();
  const mapper = ["Scripts", "Bøger", "Uge_Overblik", ...videre.map(v => v.fag.mappe).filter(Boolean)];
  console.log(`${kør ? "Laver" : "Prøvekørsel: ville lave"} ${NY}\n  ud fra ${GAMMEL}\n`);
  console.log(`Mapper: ${mapper.join(", ")}`);
  console.log(`Kopieres: Scripts/ (uden ${[...UDEN].filter(n => /\./.test(n) && !n.startsWith(".") && !["fag.json", "undervisningsdage.json"].includes(n)).join(", ")}, canvas-*-filerne, ${UDEN_STIER.join(", ")}),`);
  console.log("  RUTINE.md, README.md, CLAUDE.md (uden Vigtige datoer og Egen plan), .gitignore, .vscode/settings.json, .claude/settings.json");
  console.log("Skrives nye: Scripts/fag.json (nedenfor) og Scripts/undervisningsdage.json (kun forklaringen)");
  console.log(`\nfag.json (${visningsnavn || navn}):`);
  for (const v of videre) console.log(v.ukendt
    ? `  ${v.fag.kort} fortsætter, men ${path.basename(GAMMEL)} har ingen dette_semester, så restens fordeling kendes ikke: skriv dette_semester selv`
    : `  ${v.fag.kort} fortsætter med resten: ${v.poster.reduce((a, p) => a + p.timer, 0)} t (${v.poster.map(p => `${p.navn} ${p.timer}`).join("; ")})`);
  for (const f of slut) console.log(`  ${f.kort} er slut (${(f.arbejdsbyrde?.semestre || 1) > 1 ? "ingen timer tilbage" : "ét semester"}) og kommer ikke med`);
  if (!kør) { console.log("\nIntet er lavet. Kør igen med --kør."); return; }

  fs.mkdirSync(NY);
  for (const m of mapper) fs.mkdirSync(path.join(NY, m), { recursive: true });
  kopierScripts(path.join(GAMMEL, "Scripts"), path.join(NY, "Scripts"));
  fs.writeFileSync(path.join(NY, "Scripts", "fag.json"), JSON.stringify(json, null, 2) + "\n");
  const ud = JSON.parse(læs(path.join(GAMMEL, "Scripts", "undervisningsdage.json")) || "{}");
  fs.writeFileSync(path.join(NY, "Scripts", "undervisningsdage.json"),
    JSON.stringify(Object.fromEntries(Object.entries(ud).filter(([k]) => k.startsWith("_"))), null, 2) + "\n");
  for (const f of ["RUTINE.md", "README.md", ".gitignore", ".vscode/settings.json", ".claude/settings.json"]) {
    if (!fs.existsSync(path.join(GAMMEL, f))) continue;
    fs.mkdirSync(path.dirname(path.join(NY, f)), { recursive: true });
    fs.copyFileSync(path.join(GAMMEL, f), path.join(NY, f));
  }
  let md = læs(path.join(GAMMEL, "CLAUDE.md"));
  if (md) {
    md = tømAfsnit(md, /^Vigtige datoer/, `Udfyldes for ${navn}: frister og eksamensdatoer. Eksamensdatoerne læses herfra (kilden er uddannelsens eksamensplan).`);
    md = tømAfsnit(md, /^Egen plan/, `Din egen plan for prøveeksamener i ${navn} (ikke fra uddannelsen). Den står på siden Eksamen, ikke under Frister.`);
    fs.writeFileSync(path.join(NY, "CLAUDE.md"), md);
  }
  console.log(`\nLavet. Tilbage, før du skifter (README, "Nyt semester"):
  1. Scripts/fag.json: de nye fag fra kursusbeskrivelserne.${videre.length ? ` Tjek også ${videre.map(v => v.fag.kort).join(" og ")}: canvas (tømt), eksamenstraening, afleveringer, forudsaetning, usb_noter, leetcode, studieguide og resumeer.`: ""}
  2. Scripts/undervisningsdage.json: undervisningsdagene pr. fag (semestrets periode starter ved den første).
  3. CLAUDE.md: "Hvad mappen er", bøgerne under "Konventioner", "Materiale der mangler" og "Vigtige datoer".
  4. README.md: tabellen "… trænes forskelligt", så Fag-kolonnen matcher readme i fag.json.
  5. Bøger og kildemateriale i fagmapperne.
  Så: node Scripts/nyt-semester.js "${navn}" --skift`);
}

// ── skiftet ──────────────────────────────────────────────────────────

function tjekNy() {
  const fejl = [], adv = [];
  if (!fs.existsSync(path.join(NY, "Scripts", "fag.json"))) { fejl.push(`${NY} har ingen Scripts/fag.json. Lav mappen først (uden --skift).`); return { fejl, adv }; }
  let sem;
  try { sem = S.forMappe(NY); sem.fag(); } catch (e) { fejl.push(`Scripts/fag.json kan ikke læses: ${e.message}`); return { fejl, adv }; }
  const fag = sem.fag();
  if (!fag.length) fejl.push("Scripts/fag.json har ingen fag.");
  if (path.resolve(NY) === path.resolve(GAMMEL)) fejl.push(`${LINK} peger allerede på ${navn}.`);
  for (const f of fag.filter(f => !f.arbejdsbyrde?.poster?.length)) adv.push(`${f.kort} har ingen arbejdsbyrde i fag.json (Selvstudie og Semestre viser ikke faget).`);
  let dage = {};
  try { dage = JSON.parse(læs(path.join(NY, "Scripts", "undervisningsdage.json")) || "{}"); } catch { adv.push("Scripts/undervisningsdage.json kan ikke læses."); }
  for (const f of fag.filter(f => !Object.values(dage[f.kort] || {}).flat().length)) adv.push(`${f.kort} har ingen undervisningsdage i undervisningsdage.json.`);
  const per = sem.periode();
  if (!per) adv.push("Semestrets periode kendes ikke (ingen undervisningsdage), så Selvstudie tæller al undervisning med samme kursuskode.");
  const eks = per ? sem.eksamensdatoer(new Date(`${per.fra}T12:00`)) : {};
  for (const f of fag.filter(f => !(f.id in eks))) adv.push(`${f.kort} har ingen eksamensdato under "Vigtige datoer" i CLAUDE.md.`);
  const former = sem.eksamensformer();
  for (const f of fag.filter(f => !former.some(r => (r.Fag || "").startsWith(f.readme || "\u0000")))) adv.push(`${f.kort}: README.md's tabel "… trænes forskelligt" har ingen række for "${f.readme || "?"}".`);
  const gl = S.forMappe(GAMMEL), afsnit = (s, t) => s.afsnit("CLAUDE.md", t).trim();
  if (afsnit(sem, /^Hvad mappen er/) && afsnit(sem, /^Hvad mappen er/) === afsnit(gl, /^Hvad mappen er/)) adv.push(`CLAUDE.md's "Hvad mappen er" er den samme som i ${path.basename(GAMMEL)}.`);
  // Steder, der nævner den gamle mappe direkte i stedet for ~/kompas/studie
  const la = path.join(os.homedir(), "Library", "LaunchAgents");
  for (const n of (() => { try { return fs.readdirSync(la); } catch { return []; } })())
    if ((læs(path.join(la, n)) || "").includes(GAMMEL)) adv.push(`${path.join(la, n)} nævner ${GAMMEL} direkte.`);
  return { fejl, adv, per };
}

function skiftNu() {
  const { fejl, adv, per } = tjekNy();
  console.log(`${kør ? "Skifter" : "Prøvekørsel af skiftet"}: ${LINK}\n  fra ${GAMMEL}\n  til ${NY}${per ? ` (periode ${per.fra} – ${per.til})` : ""}\n`);
  for (const a of adv) console.log(`  ! ${a}`);
  for (const f of fejl) console.log(`  ✗ ${f}`);
  if (fejl.length) stop("\nSkiftet er ikke sket.");
  let st = null;
  try { st = fs.lstatSync(LINK); } catch { st = null; }
  if (st && !st.isSymbolicLink()) stop(`\n${LINK} er ikke et symlink. Skiftet er ikke sket.`);
  const genstart = path.resolve(LINK) === STD_LINK;
  if (!kør) {
    console.log(`\n${adv.length ? "Ret det, der mangler, eller skift alligevel" : "Klar"}: kør igen med --skift --kør. Det peger linket om${genstart ? ", genstarter Studie-serveren" : ""} og kører eksporten${UD ? ` (til ${UD})` : ""} og testene.`);
    return;
  }
  // Som ln -sfn, men atomisk: det nye link ved siden af, så omdøbt oven i det gamle
  const tmp = `${LINK}.ny-${process.pid}`;
  fs.symlinkSync(NY, tmp);
  fs.renameSync(tmp, LINK);
  console.log(`\n${LINK} → ${NY}`);
  if (genstart) execFileSync("launchctl", ["kickstart", "-k", `gui/${process.getuid()}/local.kompas.studie`], { stdio: "inherit" });
  // Koden ligger i den nye mappe, hvis Scripts/ er kopieret med, ellers ved siden af dette script; KOMPAS_SEMESTER peger den på mappen
  const kode = fs.existsSync(path.join(NY, "Scripts", "kompas-eksport.js")) ? path.join(NY, "Scripts") : __dirname;
  const env = { ...process.env, KOMPAS_SEMESTER: NY };
  execFileSync(process.execPath, [path.join(kode, "kompas-eksport.js"), ...(UD ? ["--ud", UD] : [])], { stdio: "inherit", cwd: NY, env });
  let fejlede = 0;
  for (const t of ["test_studie_semester.js", "test_studie_fag.js", "test_studie_sider.js"]) {
    try { execFileSync(process.execPath, [path.join(__dirname, "..", "..", "tests", t)], { stdio: "inherit", cwd: NY, env }); } catch { fejlede++; }
  }
  console.log(fejlede ? `\n${fejlede} test fejlede; linket peger stadig på ${navn}.` : `\nSkiftet: Studie viser nu ${navn}. ${path.basename(GAMMEL)} står under Studie → Semestre.`);
  if (fejlede) process.exitCode = 1;
}

skift ? skiftNu() : lav();
