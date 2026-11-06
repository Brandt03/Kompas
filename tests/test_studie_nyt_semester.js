// nyt-semester.js mod et opdigtet semester (Gammel med Alfa, Beta, Gamma og Delta) i en midlertidig mappe: prøvekørslen laver
// intet, --kør laver den nye mappe uden log- og statusfiler og med resten af timerne for kurser, der fortsætter, CLAUDE.md
// mister det gamle semesters datoer, og --skift peger et test-symlink om og kører eksporten til en testmappe. De rigtige
// filer og ~/kompas/studie røres ikke.
//   node tests/test_studie_nyt_semester.js
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const SCRIPTS = path.join(__dirname, "..", "studie", "Scripts");
const top = fs.mkdtempSync(path.join(os.tmpdir(), "nyt-semester-test-")), gammel = path.join(top, "Gammel"), ny = path.join(top, "Ny");
const link = path.join(top, "studie"), ud = path.join(top, "ud"), hjem = path.join(top, "hjem");
const skriv = (f, t) => { fs.mkdirSync(path.dirname(path.join(gammel, f)), { recursive: true }); fs.writeFileSync(path.join(gammel, f), t); };
for (const f of ["semester.js", "sessioner.js", "nyt-semester.js", "kompas-eksport.js"]) skriv(`Scripts/${f}`, fs.readFileSync(path.join(SCRIPTS, f)));
const post = (navn, timer, undervisning = false) => ({ navn, timer, undervisning });
skriv("Scripts/fag.json", JSON.stringify({ _forklaring: "Testfag.", semester: "Gammel", studiemaal: { dag_timer: 2 }, fag: [
  { id: "alfa", kort: "Alfa", navn: "Alfa", mappe: "Alfa", readme: "Alfa", arbejdsbyrde: { kilde: "test", semestre: 1, poster: [post("Læsning", 50)] } },
  { id: "beta", kort: "Beta", navn: "Beta", mappe: "Beta", readme: "Beta", canvas: [{ kursus: 1 }], arbejdsbyrde: { kilde: "test", semestre: 2,
    poster: [post("Forelæsning", 40, true), post("Læsning", 60), post("Projekt", 100)],
    dette_semester: { til: "sidste_undervisning", vurdering: "test", poster: [post("Forelæsning", 20), post("Læsning", 30)] } } },
  { id: "gamma", kort: "Gamma", navn: "Gamma", mappe: "Gamma", arbejdsbyrde: { kilde: "test", semestre: 2, poster: [post("Læsning", 80)] } },
  { id: "delta", kort: "Delta", navn: "Delta", mappe: "Delta", arbejdsbyrde: { kilde: "test", semestre: 2, poster: [post("Læsning", 40)],
    dette_semester: { til: "eksamen", poster: [post("Læsning", 25)], tidligere: [post("Læsning", 15)] } } },
] }));
skriv("Scripts/undervisningsdage.json", JSON.stringify({ _forklaring: "Undervisningsdagene.", Alfa: { Forelæsninger: ["2025-09-01", "2025-11-24"] } }));
skriv("Scripts/studiemaal.json", JSON.stringify({ dag_timer: 3 }));
for (const f of ["sessioner.json", "genkald-log.jsonl", "laest.json", "fravaer.json", "deadlines-status.json", "canvas-set.json", "canvas-log.txt", "fagnoter/backup/a.docx"])
  skriv(`Scripts/${f}`, "{}");
skriv("Scripts/canvas-sortering.js", "// test\n");
skriv("CLAUDE.md", "# Gammel\n\n## Hvad mappen er\n\nGammel.\n\n## Vigtige datoer\n\n| Uge | Fag | Hvad |\n|---|---|---|\n| 50 | Alfa | **Eksamen** — torsdag 11.12.2025 |\n\n**Skemaændring** i Alfa.\n\n## Egen plan: prøveeksamener\n\nIkke fra uddannelsen.\n\n| Uge | Fag | Hvad |\n|---|---|---|\n| 49 | Alfa | Prøveeksamen 1 |\n\n## Til sidst\n\nBliver.\n");
skriv("README.md", "# Gammel\n\n## De fag trænes forskelligt\n\n| Fag | Eksamen |\n|---|---|\n| Beta | mundtlig |\n");
skriv("RUTINE.md", "# Rutine\n");
fs.symlinkSync(gammel, link);
fs.mkdirSync(path.join(hjem, ".garmin-coach", "site"), { recursive: true });

let fejl = 0;
const tjek = (navn, ok, detalje = "") => { if (!ok) { fejl++; console.log("FEJL", navn, detalje); } };
const vis = x => JSON.stringify(x);
const kør = (...args) => spawnSync(process.execPath, [path.join(gammel, "Scripts", "nyt-semester.js"), ...args],
  { encoding: "utf8", env: { ...process.env, HOME: hjem, KOMPAS_SEMESTER: "", LIV_SITE: "", KOMPAS_STUDIE_LINK: link, STUDIE_EKSPORT_UD: ud } });
const læsJson = f => JSON.parse(fs.readFileSync(f, "utf8"));

try {
  const prøve = kør("Ny");
  tjek("prøvekørsel: laver intet og siger, hvad der fortsætter", prøve.status === 0 && !fs.existsSync(ny) && /Beta fortsætter med resten: 150 t/.test(prøve.stdout)
    && /Alfa er slut/.test(prøve.stdout) && /Delta er slut \(ingen timer tilbage\)/.test(prøve.stdout), prøve.stdout + prøve.stderr);

  const lav = kør("--navn", "Det nye semester", "Ny", "--kør");
  tjek("--kør laver mappen", lav.status === 0 && fs.existsSync(path.join(ny, "Scripts", "fag.json")), lav.stdout + lav.stderr);
  const fj = læsJson(path.join(ny, "Scripts", "fag.json")), beta = fj.fag.find(f => f.id === "beta"), gamma = fj.fag.find(f => f.id === "gamma");
  tjek("fag.json: kun fag, der fortsætter, og semestrets navn", fj.semester === "Det nye semester" && vis(fj.fag.map(f => f.id)) === '["beta","gamma"]' && fj.studiemaal.dag_timer === 2, vis(fj));
  tjek("fag.json: resten af timerne efter det, tidligere semestre har haft", vis(beta.arbejdsbyrde.dette_semester.poster) === vis([post("Forelæsning", 20), post("Læsning", 30), post("Projekt", 100)].map(({ navn, timer }) => ({ navn, timer })))
    && beta.arbejdsbyrde.dette_semester.til === "eksamen" && vis(beta.arbejdsbyrde.dette_semester.tidligere) === '[{"navn":"Forelæsning","timer":20},{"navn":"Læsning","timer":30}]'
    && beta.arbejdsbyrde.poster.length === 3 && vis(beta.canvas) === "[]", vis(beta));
  tjek("fag.json: et kursus uden dette_semester fortsætter uden at gætte fordelingen", gamma && !gamma.arbejdsbyrde.dette_semester && /skriv dette_semester selv/.test(lav.stdout), vis(gamma));
  const filer = fs.readdirSync(path.join(ny, "Scripts")).sort();
  tjek("Scripts/: koden og studiemaal.json, ikke log- og statusfilerne", vis(filer) === vis(["canvas-sortering.js", "fag.json", "fagnoter", "kompas-eksport.js", "nyt-semester.js", "semester.js", "sessioner.js", "studiemaal.json", "undervisningsdage.json"])
    && !fs.existsSync(path.join(ny, "Scripts", "fagnoter", "backup")), vis(filer));
  tjek("undervisningsdage.json: kun forklaringen", vis(læsJson(path.join(ny, "Scripts", "undervisningsdage.json"))) === '{"_forklaring":"Undervisningsdagene."}');
  const md = fs.readFileSync(path.join(ny, "CLAUDE.md"), "utf8");
  tjek("CLAUDE.md: uden det gamle semesters datoer og prøveeksamener, resten bliver", !/11\.12\.2025|Skemaændring|Prøveeksamen 1/.test(md) && /## Vigtige datoer\n\nUdfyldes for Ny/.test(md)
    && /\| Uge \| Fag \| Hvad \|\n\|---\|---\|---\|\n\n## Egen plan/.test(md) && /## Til sidst\n\nBliver\./.test(md) && /Gammel\./.test(md), md);
  tjek("mapperne: Bøger, Uge_Overblik og fagene, der fortsætter", ["Bøger", "Uge_Overblik", "Beta", "Gamma", "RUTINE.md", "README.md"].every(n => fs.existsSync(path.join(ny, n)))
    && !fs.existsSync(path.join(ny, "Alfa")), vis(fs.readdirSync(ny)));
  tjek("det gamle semester er urørt", fs.existsSync(path.join(gammel, "Scripts", "sessioner.json")) && læsJson(path.join(gammel, "Scripts", "fag.json")).fag.length === 4);
  const igen = kør("Ny", "--kør");
  tjek("--kør igen: mappen findes allerede", igen.status === 1 && /findes allerede/.test(igen.stderr), igen.stdout + igen.stderr);

  const tjekSkift = kør("Ny", "--skift");
  tjek("--skift som prøvekørsel: siger, hvad der mangler, og peger ikke linket om", tjekSkift.status === 0 && fs.realpathSync(link) === fs.realpathSync(gammel)
    && /Beta har ingen undervisningsdage/.test(tjekSkift.stdout) && /Gamma: README.md's tabel/.test(tjekSkift.stdout) && /"Hvad mappen er" er den samme/.test(tjekSkift.stdout), tjekSkift.stdout + tjekSkift.stderr);
  const ingen = kør("Findes ikke", "--skift");
  tjek("--skift til en mappe, der ikke findes: intet sker", ingen.status === 1 && /ingen Scripts\/fag.json/.test(ingen.stdout) && fs.realpathSync(link) === fs.realpathSync(gammel), ingen.stdout);

  // Skiftet: linket peger om, og eksporten kører til testmappen. Testene ligger ikke i den opdigtede mappe, så de fejler.
  const sk = kør("Ny", "--skift", "--kør");
  tjek("--skift --kør: linket peger på den nye mappe, og eksporten har kørt", fs.realpathSync(link) === fs.realpathSync(ny) && fs.existsSync(path.join(ud, "semestre.json"))
    && /test fejlede; linket peger stadig på Ny/.test(sk.stdout) && sk.status === 1, sk.stdout + sk.stderr);
  const sm = læsJson(path.join(ud, "semestre.json"));
  tjek("semestre.json efter skiftet: Ny er det aktuelle med sit visningsnavn, Gammel står ved siden af", sm.aktuelt === "Det nye semester"
    && sm.semestre[0].navn === "Det nye semester" && sm.semestre[0].mappe === "Ny"
    && sm.semestre.some(s => s.navn === "Gammel" && !s.aktuel), vis(sm.semestre.map(s => [s.navn, s.aktuel, s.mangler])));
  const tilbage = kør("Ny", "--skift");
  tjek("--skift, når linket allerede peger på mappen: intet sker", tilbage.status === 1 && /peger allerede på Ny/.test(tilbage.stdout), tilbage.stdout);
} catch (e) { fejl++; console.log("FEJL", e.stack); }
fs.rmSync(top, { recursive: true, force: true });
if (fejl) { console.log(`${fejl} fejl`); process.exitCode = 1; } else console.log("nyt semester: alt ok");
