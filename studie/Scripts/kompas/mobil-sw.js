// Service worker til På farten (mobil.html) og Studie-siderne på telefonen. Registreres kun gennem Tailscale,
// aldrig på kompas.localhost. Holder siderne, designkittet og Studie-dataene på telefonen, så de åbner uden
// forbindelse til Mac'en. Dagens kort og køen af svar ligger i mobil.html's eget lager, ikke her.
//   sider og designkit: vises fra lageret med det samme og hentes på ny i baggrunden (ny udgave næste gang)
//   data (studie.json, fagnoter.json, kalender.json, læst/genkald): hentes frisk, når Mac'en svarer inden for
//     4 sekunder; ellers den sidst hentede udgave
//   billeder i fagnoterne: gemmes, når de er vist én gang med forbindelse
const CACHE = "paa-farten-2";
const SIDER = ["/studie/mobil.html", "/studie/mobil.webmanifest", "/studie/mobil-ikon-192.png", "/studie/mobil-ikon-512.png",
  "/studie/", "/studie/fag.html", "/studie/deadlines.html", "/studie/studie.js",
  "/kompas/assets/tokens.css", "/kompas/assets/page.css", "/kompas/assets/md.js", "/kompas/assets/icons.js",
  "/kompas/assets/liv.js", "/kompas/assets/Geist.woff2"];
const DATA = ["/studie/studie.json", "/studie/fagnoter.json", "/studie/kalender.json", "/studie/api/laest", "/studie/api/genkald"];
const noegle = p => p === "/studie/index.html" ? "/studie/" : p;

self.addEventListener("install", e => e.waitUntil(caches.open(CACHE)
  .then(c => Promise.all([...SIDER, ...DATA].map(p => c.add(p).catch(() => {}))))   // én fil, der mangler, må ikke stoppe resten
  .then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(caches.keys()
  .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));

const hent = (c, p) => fetch(p, { cache: "no-store" }).then(r => { if (r.ok) c.put(p, r.clone()); return r; });
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url), p = noegle(url.pathname);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (DATA.includes(p)) {
    e.respondWith(caches.open(CACHE).then(async c => {
      const frisk = hent(c, p);
      const svar = await Promise.race([frisk.catch(() => null), new Promise(r => setTimeout(() => r(null), 4000))]);
      return svar || await c.match(p) || frisk;
    }));
  } else if (SIDER.includes(p) || p.startsWith("/studie/fagnoter/")) {
    e.respondWith(caches.open(CACHE).then(async c => {
      const gemt = await c.match(p), frisk = hent(c, p);
      if (gemt) { e.waitUntil(frisk.catch(() => {})); return gemt; }
      return frisk;
    }));
  }
});
