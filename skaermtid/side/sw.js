// Service worker til Skærmtid på telefonen. Registreres kun gennem Tailscale (index.html), aldrig på kompas.localhost.
// Holder siden, designkittet og de sidst byggede tal på telefonen, så siden åbner uden forbindelse til Mac'en.
//   siden og designkittet: vises fra lageret med det samme og hentes på ny i baggrunden (ny udgave næste gang)
//   tallene (skaermtid.json): hentes frisk, når Mac'en svarer inden for 4 sekunder; ellers de sidst hentede. Siden
//     siger selv, hvornår de er bygget
//   dine valg (api/valg) går kun til Mac'en; uden forbindelse siger siden, at valget ikke er gemt
// Kopieres med resten af side/ til ~/.kompas/skaermtid af skaermtid.py byg.
const CACHE = "skaermtid-1", TAL = "/skaermtid/skaermtid.json";
const SIDER = ["/skaermtid/", "/kompas/assets/tokens.css", "/kompas/assets/page.css", "/kompas/assets/icons.js",
  "/kompas/assets/liv.js", "/kompas/assets/chart.js", "/kompas/assets/Geist.woff2"];
const noegle = p => p === "/skaermtid/index.html" ? "/skaermtid/" : p;
const ventTil = (ms, p) => Promise.race([p.catch(() => null), new Promise(r => setTimeout(() => r(null), ms))]);

self.addEventListener("install", e => e.waitUntil(caches.open(CACHE)
  .then(c => Promise.all([...SIDER, TAL].map(p => c.add(p).catch(() => {}))))   // én fil, der mangler, må ikke stoppe resten
  .then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(caches.keys()
  .then(ks => Promise.all(ks.filter(k => k.startsWith("skaermtid-") && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));

const hent = (c, p) => fetch(p, { cache: "no-store" }).then(r => { if (r.ok) c.put(p, r.clone()); return r; });
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url), p = noegle(url.pathname);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (p === TAL) {
    e.respondWith(caches.open(CACHE).then(async c => {
      const frisk = hent(c, p);
      return await ventTil(4000, frisk) || await c.match(p) || frisk;
    }));
  } else if (SIDER.includes(p)) {
    e.respondWith(caches.open(CACHE).then(async c => {
      const gemt = await c.match(p), frisk = hent(c, p);
      if (gemt) { e.waitUntil(frisk.catch(() => {})); return gemt; }
      return frisk;
    }));
  }
});
