// Sprog → Kompas (https://kompas.localhost/sprog/)
//
// En lille lokal server, der viser Sprog-siderne og lader dem gemme DINE svar. Den kan kun skrive:
//   - din karakter (1-4) og det, du skrev, på et kort i data/log.jsonl
//   - dit svar på ugens tekst, også i data/log.jsonl
// Kortene, ugens tekst og feedbacken skriver rutinen (Kompas · Sprog) gennem sprog.js; serveren finder aldrig på noget.
// På farten (mobil.html) henter en pakke med dagens kort, så du kan svare uden net, og sender svarene med /sync,
// når Mac'en er vågen. Samme mønster som Studie-serverens På farten.
//
// Kør:  node server.js      (lytter på 127.0.0.1:8769; Caddy sender /sprog/* hertil)
// Kører altid i baggrunden som LaunchAgent local.kompas.sprog (~/Library/LaunchAgents); log i ~/.kompas/sprog-server.log.
// Testserver: SPROG_PORT og SPROG_DATA (en kopi af data/), så de rigtige svar aldrig røres.
"use strict";
const http = require("http");
const fs = require("fs");
const path = require("path");
const util = require("util");
const K = require("./kerne");

// Hver loglinje begynder med tidspunktet i lokal tid, fx 2026-10-12T22:31:05
for (const k of ["log", "warn", "error"]) {
  const ud = console[k].bind(console);
  console[k] = (...a) => { const t = new Date(Date.now() - new Date().getTimezoneOffset() * 6e4).toISOString().slice(0, 19); ud(util.format(...a).split("\n").map(l => `${t} ${l}`).join("\n")); };
}
const PORT = +(process.env.SPROG_PORT || 8769);
const ORIGIN = "https://kompas.localhost";
// Telefonen kommer ind gennem Tailscale med sin egen adresse (https://<mac>.<tailnet>.ts.net), sat i LaunchAgent'en
// af bin/tailscale-mobil.sh i Kompas
const ORIGINS = [ORIGIN, ...String(process.env.SPROG_ORIGINS || "").split(",").map(s => s.trim()).filter(Boolean)];
// Kun de navne, Kompas selv bruger (mod DNS rebinding, som Studie-serveren). 8768 er Caddys blok til telefonen.
const VAERTER = new Set(["kompas.localhost", `127.0.0.1:${PORT}`, `localhost:${PORT}`, "127.0.0.1:8768", "localhost:8768",
  ...ORIGINS.map(o => { try { return new URL(o).host; } catch { return null; } }).filter(Boolean)]);
const SIDE = path.join(__dirname, "side");
const TYPER = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml", ".png": "image/png", ".webmanifest": "application/manifest+json" };

// Kompas bygger menuen ud fra denne. "nyt" er den nyeste tekst eller feedback, så menuen viser en prik ved Oversigt.
function manifest() {
  const t = K.tekster()[0], nyt = t ? `${t.uge}${t.feedback ? "-feedback" : ""}` : null;
  const r = K.reglerListe().map(g => g.opdateret || g.oprettet).sort().pop();
  return { omraade: "Sprog", ikon: "languages", raekkefoelge: 25, kilde: "~/kompas/sprog/server.js (live, port 8769)", opdateret: new Date().toISOString(),
    sider: [
      { titel: "Oversigt", ikon: "languages", sti: "/sprog/", praecis: true, ...(nyt ? { nyt } : {}) },
      { titel: "Dagens kort", ikon: "check", sti: "/sprog/mobil.html" },
      { titel: "Regler", ikon: "book-open", sti: "/sprog/regler.html", ...(r ? { nyt: r } : {}) },
    ] };
}

function send(res, kode, obj) {
  const b = Buffer.from(JSON.stringify(obj));
  res.writeHead(kode, { "Content-Type": "application/json; charset=utf-8", "Content-Length": b.length, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" });
  res.end(b);
}
function sendFil(res, navn) {
  // Kun filer direkte i side/, aldrig undermapper eller skjulte filer
  if (!/^[\w-]+\.(html|js|css|svg|png|webmanifest)$/.test(navn)) return send(res, 404, { fejl: "ikke fundet" });
  let b;
  try { b = fs.readFileSync(path.join(SIDE, navn)); } catch { return send(res, 404, { fejl: "ikke fundet" }); }
  res.writeHead(200, { "Content-Type": TYPER[path.extname(navn)], "Content-Length": b.length, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" });
  res.end(b);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://x"), sti = url.pathname.replace(/^\/sprog(?=\/|$)/, "") || "/";
  const vaert = String(req.headers.host || "").toLowerCase().replace(/:(?:443|80)$/, "");
  if (!VAERTER.has(vaert)) { console.error(`afvist vært: ${vaert.slice(0, 80)} (${req.method} ${sti.slice(0, 40)})`); return send(res, 403, { fejl: "ukendt vært" }); }
  try {
    if (req.method === "GET") {
      if (sti === "/") return sendFil(res, "index.html");
      if (sti === "/kompas.json") return send(res, 200, manifest());
      if (sti === "/api/pakke") return send(res, 200, K.pakke());
      if (sti === "/api/tekster") return send(res, 200, K.tekster());
      if (sti === "/api/regler") return send(res, 200, K.reglerListe());
      if (sti.startsWith("/api/")) return send(res, 404, { fejl: "ikke fundet" });
      return sendFil(res, sti.slice(1));
    }
    if (req.method !== "POST") return send(res, 405, { fejl: "kun GET og POST" });
    // Kun Kompas må skrive: en fremmed side kan ikke sende JSON på tværs af origins uden en CORS-preflight,
    // som serveren aldrig godkender, og Origin-tjekket fanger resten
    if (!ORIGINS.includes(req.headers.origin) || !String(req.headers["content-type"] || "").startsWith("application/json")) return send(res, 403, { fejl: "kun fra Kompas" });
    let krop = "";
    for await (const c of req) { krop += c; if (krop.length > 500000) return send(res, 413, { fejl: "for stort" }); }
    const d = JSON.parse(krop || "{}");
    if (sti === "/api/svar") return send(res, 200, K.gemSvar(d));
    if (sti === "/api/tekst-svar") return send(res, 200, K.gemTekstSvar(d));
    if (sti === "/api/sync") return send(res, 200, K.sync(d));
    return send(res, 404, { fejl: "ikke fundet" });
  } catch (e) {
    return send(res, 400, { fejl: e.message });
  }
});
server.listen(PORT, "127.0.0.1", () => console.log(`Sprog-serveren lytter på 127.0.0.1:${PORT} (data: ${K.DATA})`));
