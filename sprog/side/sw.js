// Service worker til Sprog på telefonen. Registreres kun gennem Tailscale, aldrig på kompas.localhost. Holder siden
// og designkittet på telefonen, så den åbner uden forbindelse til Mac'en. Dagens kort og køen af svar ligger i
// mobil.html's eget lager, ikke her. Siderne vises fra lageret med det samme og hentes på ny i baggrunden.
const CACHE = "sprog-2";
const SIDER = ["/sprog/mobil.html", "/sprog/regel.js", "/sprog/manifest.webmanifest", "/sprog/ikon-192.png", "/sprog/ikon-512.png",
  "/kompas/assets/tokens.css", "/kompas/assets/page.css", "/kompas/assets/md.js", "/kompas/assets/icons.js",
  "/kompas/assets/liv.js", "/kompas/assets/Geist.woff2"];

self.addEventListener("install", e => e.waitUntil(caches.open(CACHE)
  .then(c => Promise.all(SIDER.map(p => c.add(p).catch(() => {}))))   // én fil, der mangler, må ikke stoppe resten
  .then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(caches.keys()
  .then(ks => Promise.all(ks.filter(k => k.startsWith("sprog-") && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));

const hent = (c, p) => fetch(p, { cache: "no-store" }).then(r => { if (r.ok) c.put(p, r.clone()); return r; });
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url), p = url.pathname;
  if (e.request.method !== "GET" || url.origin !== location.origin || !SIDER.includes(p)) return;
  e.respondWith(caches.open(CACHE).then(async c => {
    const gemt = await c.match(p), frisk = hent(c, p);
    if (gemt) { e.waitUntil(frisk.catch(() => {})); return gemt; }
    return frisk;
  }));
});
