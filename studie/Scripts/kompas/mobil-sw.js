// Service worker til På farten (mobil.html) og Studie-siderne på telefonen. Registreres kun gennem Tailscale,
// aldrig på kompas.localhost. Holder siderne, designkittet og Studie-dataene på telefonen, så de åbner uden
// forbindelse til Mac'en. Dagens kort og køen af svar ligger i mobil.html's eget lager, ikke her.
//   sider og designkit: vises fra lageret med det samme og hentes på ny i baggrunden (ny udgave næste gang)
//   data (studie.json, fagnoter.json, kalender.json, læst/genkald/usb-vurdering): hentes frisk, når Mac'en svarer inden for
//     4 sekunder; ellers den sidst hentede udgave
//   billeder i fagnoterne: gemmes, når de er vist én gang med forbindelse
//   forelæsninger og øvelser (/studie/api/pensum/...): hentes én gang og åbnes derefter fra telefonen, også uden net.
//     Denne og næste uges hentes med pakken (varm i mobil.html), andre, når de er åbnet én gang med forbindelse
const CACHE = "paa-farten-3";
const SIDER = ["/studie/mobil.html", "/studie/mobil.webmanifest", "/studie/mobil-ikon-192.png", "/studie/mobil-ikon-512.png",
  "/studie/", "/studie/fag.html", "/studie/deadlines.html", "/studie/usb.html", "/studie/studie.js",
  "/kompas/assets/tokens.css", "/kompas/assets/page.css", "/kompas/assets/md.js", "/kompas/assets/icons.js",
  "/kompas/assets/liv.js", "/kompas/assets/Geist.woff2"];
const DATA = ["/studie/studie.json", "/studie/fagnoter.json", "/studie/kalender.json", "/studie/api/laest", "/studie/api/genkald",
  "/studie/api/usb-vurdering"];
const noegle = p => p === "/studie/index.html" ? "/studie/" : p;

self.addEventListener("install", e => e.waitUntil(caches.open(CACHE)
  .then(c => Promise.all([...SIDER, ...DATA].map(p => c.add(p).catch(() => {}))))   // én fil, der mangler, må ikke stoppe resten
  .then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(caches.keys()
  .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));

const hent = (c, p) => fetch(p, { cache: "no-store" }).then(r => { if (r.ok) c.put(p, r.clone()); return r; });
const ikkeGemt = () => new Response(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Ikke på telefonen</title>
<style>body{font:15px system-ui;margin:15vh auto;max-width:34em;padding:0 16px;color:#737373;background:#f7f7f7}h1{color:#171717;font-size:21px;font-weight:600}a{color:#171717}
@media (prefers-color-scheme:dark){body{background:#0b0b0b;color:#a3a3a3}h1,a{color:#f5f5f5}}</style>
<h1>Filen ligger ikke på telefonen</h1><p>Mac'en svarer ikke, og filen er ikke hentet før. Denne og næste uges forelæsninger og øvelser hentes,
når På farten henter en pakke; andre ligger på telefonen, når du har åbnet dem én gang med forbindelse.</p>
<p><a href="/studie/fag.html" onclick="history.back();return false">‹ Fag</a></p>`, { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } });
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url), p = noegle(url.pathname);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (DATA.includes(p)) {
    e.respondWith(caches.open(CACHE).then(async c => {
      const frisk = hent(c, p);
      const svar = await Promise.race([frisk.catch(() => null), new Promise(r => setTimeout(() => r(null), 4000))]);
      return svar || await c.match(p) || frisk;
    }));
  } else if (p.startsWith("/studie/api/pensum/")) {
    // Filerne skifter ikke indhold (navnet har undervisningsdagen), så den gemte udgave vises uden at spørge Mac'en
    e.respondWith(caches.open(CACHE).then(async c => {
      const gemt = await c.match(p); if (gemt) return gemt;
      return await Promise.race([hent(c, p).catch(() => null), new Promise(r => setTimeout(() => r(null), 8000))]) || ikkeGemt();
    }));
  } else if (SIDER.includes(p) || p.startsWith("/studie/fagnoter/")) {
    e.respondWith(caches.open(CACHE).then(async c => {
      const gemt = await c.match(p), frisk = hent(c, p);
      if (gemt) { e.waitUntil(frisk.catch(() => {})); return gemt; }
      return frisk;
    }));
  }
});
