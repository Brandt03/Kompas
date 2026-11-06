// Service worker til Sprog på telefonen. Registreres kun gennem Tailscale (mobil.html), aldrig på kompas.localhost.
// Holder siderne og designkittet på telefonen, så de åbner uden forbindelse til Mac'en. Dagens kort og køen af svar
// ligger i mobil.html's eget lager, ikke her.
//   sider (Dagens kort, Sprogoversigt, Regler) og designkit: vises fra lageret med det samme og hentes på ny i
//     baggrunden (ny udgave næste gang). Alle hentes, når service workeren installeres
//   pakken (/sprog/api/pakke): hentes frisk, når Mac'en svarer inden for 4 sekunder; ellers viser Sprogoversigt og Regler
//     den sidst hentede udgave. Dagens kort får aldrig en gemt pakke herfra: den har sin egen og ved selv, når Mac'en
//     ikke svarer
const CACHE = "sprog-3", PAKKE = "/sprog/api/pakke";
const SIDER = ["/sprog/mobil.html", "/sprog/", "/sprog/regler.html", "/sprog/regel.js", "/sprog/manifest.webmanifest",
  "/sprog/ikon-192.png", "/sprog/ikon-512.png",
  "/kompas/assets/tokens.css", "/kompas/assets/page.css", "/kompas/assets/md.js", "/kompas/assets/icons.js",
  "/kompas/assets/liv.js", "/kompas/assets/Geist.woff2"];
const noegle = p => p === "/sprog/index.html" ? "/sprog/" : p;
const ventTil = (ms, p) => Promise.race([p.catch(() => null), new Promise(r => setTimeout(() => r(null), ms))]);

self.addEventListener("install", e => e.waitUntil(caches.open(CACHE)
  .then(c => Promise.all([...SIDER, PAKKE].map(p => c.add(p).catch(() => {}))))   // én fil, der mangler, må ikke stoppe resten
  .then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(caches.keys()
  .then(ks => Promise.all(ks.filter(k => k.startsWith("sprog-") && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));

const hent = (c, p) => fetch(p, { cache: "no-store" }).then(r => { if (r.ok) c.put(p, r.clone()); return r; });
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url), p = noegle(url.pathname);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (p === PAKKE) {
    const fraDagensKort = /\/sprog\/mobil\.html$/.test(new URL(e.request.referrer || "about:blank", location.origin).pathname);
    e.respondWith(caches.open(CACHE).then(async c => {
      const frisk = hent(c, p);
      if (fraDagensKort) return frisk;   // fejler, som uden service worker, så Dagens kort bruger sin egen pakke
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
