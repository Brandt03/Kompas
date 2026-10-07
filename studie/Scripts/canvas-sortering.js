// Sorterer Canvas-downloads fra ~/Downloads ind i fag-mapperne.
//
//   node Scripts/canvas-sortering.js        prøvekørsel: viser kun, hvad der ville ske
//   node Scripts/canvas-sortering.js --kør  flytter filerne
//
// PowerPoint-filer konverteres til PDF (LibreOffice), og originalen går i papirkurven.
// Dubletter går også i papirkurven, ændrede versioner gemmes som _v2, _v3 osv.
//
// Fag og Canvas-fil-id aflæses fra macOS' "Hentet fra"-oplysning
// (kMDItemWhereFroms), som browseren sætter på hver download.
// Filer, der ikke kommer fra et kendt Canvas-kursus, røres ikke.
//
// Env-variabler (valgfrie):
//   KOMPAS_SEMESTER   semestermappen; standard er mappen over Scripts/
//   CANVAS_VAERT      Canvas-adressen, downloads kommer fra; standard canvas.instructure.com
// Undervisningsdagene står i Scripts/undervisningsdage.json (se undervisningsdage.example.json).

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const os = require("os");
const { execFileSync } = require("child_process");

const ROD = path.resolve((process.env.KOMPAS_SEMESTER || path.join(__dirname, "..")).replace(/^~(?=$|\/)/, os.homedir()));
const DATA = path.join(ROD, "Scripts");
const DOWNLOADS = path.join(os.homedir(), "Downloads");
const TILSTAND = path.join(DATA, "canvas-tilstand.json");
const LOG = path.join(DATA, "canvas-log.txt");
const CANVAS = (process.env.CANVAS_VAERT || "canvas.instructure.com").replace(/\./g, "\\.");
const INDBAKKE = path.join(ROD, "_Indbakke");
const KØR = process.argv.includes("--kør");

// Kursus-id -> fag og standardmappe, når filnavnet ikke afgør det.
// standard: null betyder, at usikre filer går i _Indbakke.
// Id'et står i kursets adresse på Canvas (…/courses/<id>). Tallene her er eksempler; skriv dine egne kurser.
const KURSER = {
  10001: { fag: "Gamma", standard: null },
  10002: { fag: "Beta", standard: "Forelæsninger" },
  10003: { fag: "Alfa", standard: "Forelæsninger" },
  10004: { fag: "Alfa", standard: "Øvelser" },
};

// Filnavn -> undermappe. Første regel, der passer, vinder.
const REGLER = [
  { mappe: "Studieteknik", mønster: /studieteknik|notatteknik/i },
  { mappe: "Afleveringer", mønster: /aflevering|assignment|godkendelsesopgave|\bopgave\s?\d+\b/i },
  { mappe: "Øvelser", mønster: /øvelse|exercise/i },
  { mappe: "Forelæsninger", mønster: /\bFL\s?\d|forelæsning|lecture/i },
];

function hentetFra(fil) {
  try {
    const hex = execFileSync("xattr", ["-px", "com.apple.metadata:kMDItemWhereFroms", fil], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
    const json = execFileSync("plutil", ["-convert", "json", "-o", "-", "-"], {
      input: Buffer.from(hex.replace(/\s/g, ""), "hex"),
      encoding: "utf8",
    });
    return JSON.parse(json);
  } catch {
    return [];
  }
}

function canvasKilde(fil) {
  for (const url of hentetFra(fil)) {
    const m = new RegExp(`${CANVAS}/courses/(\\d+)(?:/files/(\\d+))?`).exec(url);
    if (m) return { kursus: Number(m[1]), filId: m[2] || null };
  }
  return null;
}

function hash(fil) {
  return crypto.createHash("sha256").update(fs.readFileSync(fil)).digest("hex");
}

function datoPræfiks(fil) {
  const d = fs.statSync(fil).birthtime;
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}`;
}

// Undervisningsdagen filen hører til, fra Scripts/undervisningsdage.json.
//   1. Et nummer i navnet ("forelæsning 5", "FL5", "øvelsessæt 5", "Exercise 5") -> n'te dato.
//   2. "uge 40" i navnet -> datoen i den uge.
//   3. Ellers den første undervisningsdag på eller efter download (materiale lægges op før
//      undervisningen), højst 10 dage frem; ellers den seneste før.
// Returnerer { dato: "ÅÅÅÅMMDD", sikker } eller null, hvis faget/mappen ikke står i tabellen.
const UNDERVISNING = (() => {
  try { return JSON.parse(fs.readFileSync(path.join(DATA, "undervisningsdage.json"), "utf8")); }
  catch { return {}; }
})();

function isoUge(d) {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dag = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - dag);
  return Math.ceil(((t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 864e5 + 1) / 7);
}

function undervisningsdato(navn, fag, mappe, fil) {
  const liste = ((UNDERVISNING[fag] || {})[mappe] || []).map((x) => (typeof x === "string" ? { dato: x } : x));
  if (!liste.length) return null;
  const svar = (i, sikker) => ({ dato: liste[i].dato.replace(/-/g, ""), nr: i + 1, emne: sikker ? liste[i].emne || null : null, sikker });
  const nr = /(?:^|[^a-zæøå])(?:forelæsning|FL|lecture|øvelsessæt|exercise|øvelse)\s*_?0?(\d{1,2})(?!\d)/i.exec(navn);
  if (nr && liste[Number(nr[1]) - 1]) return svar(Number(nr[1]) - 1, true);
  const nrFør = /(?:^|[^\d])0?(\d{1,2})[_\s-]+(?:forelæsning|lecture|øvelsessæt|exercise|øvelse)/i.exec(navn.replace(/^\d{8}_/, ""));
  if (nrFør && liste[Number(nrFør[1]) - 1]) return svar(Number(nrFør[1]) - 1, true);
  const uge = /(?:^|[^a-zæøå])uge\s*_?(\d{1,2})(?!\d)/i.exec(navn);
  if (uge) {
    const i = liste.findIndex((x) => isoUge(new Date(x.dato)) === Number(uge[1]));
    if (i >= 0) return svar(i, true);
  }
  const hentet = fs.statSync(fil).birthtime;
  const dag = new Date(hentet.getFullYear(), hentet.getMonth(), hentet.getDate());
  const tid = (x) => new Date(x.dato + "T00:00");
  let i = liste.findIndex((x) => tid(x) >= dag && tid(x) - dag <= 10 * 864e5);
  if (i < 0) for (let k = liste.length - 1; k >= 0; k--) if (tid(liste[k]) <= dag) { i = k; break; }
  return i >= 0 ? svar(i, false) : null;
}

// Ensartet navn, når nummer og emne er kendt: 20261005_FL5_Lorem ipsum.pdf,
// 20261005_Øvelsessæt 5_Lorem ipsum.pdf, 20260911_Exercise 1_Dolor sit.pdf (Gamma har øvelsessæt, de andre exercises).
// Ellers: dato + Canvas-navnet.
function ensartetNavn(uv, fag, mappe, navn) {
  const ext = path.extname(rensNavn(navn));
  if (!uv) return null;
  if (!uv.emne) return `${uv.dato}_${rensNavn(navn).replace(/^\d{8}_/, "")}`;
  const emne = uv.emne.replace(/[\/:]/g, "-");
  const type = mappe === "Forelæsninger" ? `FL${uv.nr}` : fag === "Gamma" ? `Øvelsessæt ${uv.nr}` : `Exercise ${uv.nr}`;
  const løsning = /solution|løsning|facit/i.test(navn) ? " (løsning)" : "";
  return `${uv.dato}_${type}_${emne}${løsning}${ext}`;
}

// "slides (1).pdf" -> "slides.pdf"
function rensNavn(navn) {
  const ext = path.extname(navn);
  return path.basename(navn, ext).replace(/\s*\(\d+\)$/, "") + ext;
}

function nytNavn(navn, mappe) {
  const rent = rensNavn(navn);
  if (mappe === "Afleveringer" || mappe === "Studieteknik") return rent;
  return null; // dato sættes af kalderen
}

function alleFagFiler(fag) {
  const ud = [];
  const gå = (dir) => {
    if (!fs.existsSync(dir)) return;
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) gå(p);
      else if (!e.name.startsWith(".")) ud.push(p);
    }
  };
  gå(path.join(ROD, fag, "Pensum"));
  gå(path.join(ROD, fag, "Afleveringer"));
  gå(INDBAKKE);
  return ud;
}

// Leder efter en fil med præcis samme indhold. Størrelsen tjekkes først,
// så OneDrive ikke skal hente alle filer ned for at hashe dem.
function findDublet(fil, fag) {
  const str = fs.statSync(fil).size;
  const kandidater = alleFagFiler(fag).filter((p) => fs.statSync(p).size === str);
  if (kandidater.length === 0) return null;
  const h = hash(fil);
  return kandidater.find((p) => hash(p) === h) || null;
}

// PowerPoint-filer konverteres til PDF med LibreOffice. Originalen går i papirkurven.
const KONVERTER = /\.(pptx?|ppsx?)$/i;

function somPdf(navn) {
  return navn.replace(KONVERTER, ".pdf");
}

// Er slides allerede konverteret i hånden? PDF'en har så et andet indhold,
// så her sammenlignes på navnet uden datopræfiks.
function findPdfMedSammeNavn(navn, fag) {
  const ønsket = somPdf(rensNavn(navn)).toLowerCase();
  return alleFagFiler(fag).find((p) =>
    path.basename(p).replace(/^\d{8}_/, "").replace(/^[A-Za-z]+_\d{8}_/, "").toLowerCase() === ønsket) || null;
}

function konverterTilPdf(fil) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "canvas-"));
  try {
    execFileSync("soffice", [
      `-env:UserInstallation=file://${tmp}/profil`, // virker også, mens LibreOffice er åben
      "--headless", "--convert-to", "pdf", "--outdir", tmp, fil,
    ], { stdio: "ignore", timeout: 180000, env: { ...process.env, PATH: `/opt/homebrew/bin:/usr/local/bin:${process.env.PATH}` } });
    const pdf = path.join(tmp, somPdf(path.basename(fil)));
    return fs.existsSync(pdf) ? pdf : null;
  } catch {
    return null;
  }
}

function ledigSti(sti) {
  if (!fs.existsSync(sti)) return sti;
  const ext = path.extname(sti);
  const base = sti.slice(0, -ext.length);
  for (let i = 2; ; i++) {
    const kandidat = `${base}_v${i}${ext}`;
    if (!fs.existsSync(kandidat)) return kandidat;
  }
}

function tilPapirkurv(fil) {
  const mål = ledigSti(path.join(os.homedir(), ".Trash", path.basename(fil)));
  fs.renameSync(fil, mål);
}

function flyt(fra, til) {
  fs.mkdirSync(path.dirname(til), { recursive: true });
  try {
    fs.renameSync(fra, til);
  } catch (e) {
    if (e.code !== "EXDEV") throw e;
    fs.copyFileSync(fra, til);
    fs.unlinkSync(fra);
  }
}

function log(linje) {
  console.log(linje);
  if (KØR) fs.appendFileSync(LOG, `${new Date().toISOString().slice(0, 16)}  ${linje}\n`);
}

function main() {
  const tilstand = fs.existsSync(TILSTAND) ? JSON.parse(fs.readFileSync(TILSTAND, "utf8")) : {};
  let noget = false;

  for (const navn of fs.readdirSync(DOWNLOADS)) {
    const fil = path.join(DOWNLOADS, navn);
    if (navn.startsWith(".") || /\.(crdownload|download|part)$/.test(navn)) continue;
    const st = fs.statSync(fil);
    if (!st.isFile() || Date.now() - st.mtimeMs < 5000) continue; // stadig ved at blive hentet

    const kilde = canvasKilde(fil);
    if (!kilde || !KURSER[kilde.kursus]) continue;
    noget = true;
    const { fag, standard } = KURSER[kilde.kursus];
    const rel = (p) => path.relative(ROD, p);

    const h = hash(fil);
    const kendt = kilde.filId && tilstand[kilde.filId];
    const erSlides = KONVERTER.test(navn);
    const dublet = (kendt && kendt.hash === h && path.join(ROD, kendt.sti))
      || findDublet(fil, fag)
      || (erSlides && findPdfMedSammeNavn(navn, fag));
    if (dublet) {
      log(`DUBLET     ${navn}  (findes allerede som ${rel(dublet)}) -> papirkurv`);
      if (KØR) tilPapirkurv(fil);
      continue;
    }

    let mål;
    if (kendt && fs.existsSync(path.join(ROD, kendt.sti))) {
      // Samme Canvas-fil, men nyt indhold: underviseren har lagt en ny version op.
      mål = ledigSti(path.join(ROD, kendt.sti.replace(/_v\d+(\.[^.]+)$/, "$1")));
      log(`NY VERSION ${navn}  -> ${rel(mål)}  (gammel version bevaret)`);
    } else {
      const regel = REGLER.find((r) => r.mønster.test(navn));
      const mappe = regel ? regel.mappe : standard;
      const dir = mappe === null ? INDBAKKE
        : mappe === "Afleveringer" || mappe === "Studieteknik" ? path.join(ROD, fag, mappe)
        : path.join(ROD, fag, "Pensum", mappe);
      const uv = mappe && !["Afleveringer", "Studieteknik"].includes(mappe) ? undervisningsdato(navn, fag, mappe, fil) : null;
      let filnavn = nytNavn(navn, mappe) || ensartetNavn(uv, fag, mappe, navn) || `${datoPræfiks(fil)}_${rensNavn(navn)}`;
      if (erSlides) filnavn = somPdf(filnavn);
      mål = ledigSti(path.join(dir, mappe === null ? `${fag}_${filnavn}` : filnavn));
      const datoNote = nytNavn(navn, mappe) ? "" : !uv ? "  (dato = download, ingen undervisningsdag fundet)"
        : uv.sikker ? "" : "  (dato = nærmeste undervisningsdag, tjek)";
      log(`${mappe === null ? "INDBAKKE  " : "SORTERET  "} ${navn}  -> ${rel(mål)}${erSlides ? "  (konverteret til PDF)" : ""}${datoNote}`);
    }

    if (KØR) {
      if (erSlides) {
        const pdf = konverterTilPdf(fil);
        if (!pdf) {
          const ind = ledigSti(path.join(INDBAKKE, `${fag}_${rensNavn(navn)}`));
          log(`FEJL       ${navn}  kunne ikke konverteres -> ${rel(ind)}`);
          flyt(fil, ind);
          continue;
        }
        flyt(pdf, mål);
        fs.rmSync(path.dirname(pdf), { recursive: true, force: true });
        tilPapirkurv(fil);
      } else {
        flyt(fil, mål);
      }
      if (kilde.filId) tilstand[kilde.filId] = { sti: rel(mål), hash: h };
    }
  }

  if (KØR) fs.writeFileSync(TILSTAND, JSON.stringify(tilstand, null, 2) + "\n");
  if (!noget) console.log("Ingen nye Canvas-filer i Downloads.");
  else if (!KØR) console.log("\nPrøvekørsel. Kør med --kør for at flytte filerne.");
}

if (require.main === module) main();
module.exports = { undervisningsdato, ensartetNavn };
