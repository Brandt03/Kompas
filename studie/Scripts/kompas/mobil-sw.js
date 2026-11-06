// Service worker til På farten (mobil.html) og alle Studie-siderne på telefonen. Registreres kun gennem Tailscale,
// aldrig på kompas.localhost. Holder siderne, designkittet og Studie-dataene på telefonen, så de åbner uden
// forbindelse til Mac'en, og henter nyt, så snart Mac'en svarer. Dagens kort og køen af svar ligger i mobil.html's eget
// lager, ikke her.
//   sider og designkit (/studie/…, /kompas/assets/…): vises fra lageret med det samme og hentes på ny i baggrunden (ny
//     udgave næste gang). Alle Studie-sider hentes, når service workeren installeres, så de åbner uden net, også før
//     du har åbnet dem
//   data (*.json og læsekald til /studie/api/): hentes frisk, når Mac'en svarer inden for 4 sekunder; ellers den sidst
//     hentede udgave. Pakken (/studie/api/pakke) røres ikke: På farten gemmer sin egen
//   billeder i fagnoterne: gemmes, når de er vist én gang med forbindelse
//   forelæsninger og øvelser (/studie/api/pensum/...): hentes én gang og åbnes derefter fra telefonen, også uden net.
//     Denne og næste uges hentes med pakken (varm i mobil.html), andre, når de er åbnet én gang med forbindelse
//   markeringer uden net: en læst uge (/api/laest), en færdig frist (/api/deadline) og din vurdering af USB-noterne
//     (/api/usb-vurdering) lægges i kø, når Mac'en ikke svarer, og sendes gennem /api/sync med tidspunktet, du satte dem,
//     når den svarer igen (ved næste kald, der lykkes, og med Background Sync, hvor telefonen har det). Siden får svaret
//     med det samme, og de gemte data rettes, så markeringen også står der, næste gang siden åbnes. Andre skrivninger
//     (svar på genkald, drills og I egne ord på Fag) får et svar, der siger, at de kan gives i På farten, som har sin
//     egen kø; en prøveeksamen gemmes kun, mens Mac'en er vågen
const CACHE = "paa-farten-4", KOE_CACHE = "studie-koe", KOE = "/studie/__koe__";
const SIDER = ["/studie/mobil.html", "/studie/mobil.webmanifest", "/studie/mobil-ikon-192.png", "/studie/mobil-ikon-512.png",
  "/studie/", "/studie/fag.html", "/studie/deadlines.html", "/studie/usb.html", "/studie/genkald.html", "/studie/eksamen.html",
  "/studie/selvstudie.html", "/studie/semestre.html", "/studie/studie.js",
  "/kompas/assets/tokens.css", "/kompas/assets/page.css", "/kompas/assets/md.js", "/kompas/assets/icons.js",
  "/kompas/assets/liv.js", "/kompas/assets/chart.js", "/kompas/assets/Geist.woff2"];
const DATA = ["/studie/studie.json", "/studie/fagnoter.json", "/studie/resumeer.json", "/studie/kalender.json", "/studie/selvstudie.json", "/studie/semestre.json",
  "/studie/api/laest", "/studie/api/genkald", "/studie/api/usb-vurdering", "/studie/api/egne-ord", "/studie/api/begreber",
  "/studie/api/drills", "/studie/api/repetition", "/studie/api/eksamen", "/studie/api/eksamen/niveauer"];
// Skrivninger, der kan vente: de sætter en tilstand, og /api/sync tager dem med deres tidspunkt
const KAN_VENTE = { "/studie/api/laest": "laest", "/studie/api/deadline": "deadline", "/studie/api/usb-vurdering": "usb-vurdering" };
const noegle = p => p === "/studie/index.html" ? "/studie/" : p;
const json = (d, status = 200) => new Response(JSON.stringify(d), { status, headers: { "Content-Type": "application/json; charset=utf-8" } });
const isoDag = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const ventTil = (ms, p) => Promise.race([p.catch(() => null), new Promise(r => setTimeout(() => r(null), ms))]);

self.addEventListener("install", e => e.waitUntil(caches.open(CACHE)
  .then(c => Promise.all([...SIDER, ...DATA].map(p => c.add(p).catch(() => {}))))   // én fil, der mangler, må ikke stoppe resten
  .then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(caches.keys()
  .then(ks => Promise.all(ks.filter(k => k.startsWith("paa-farten-") && k !== CACHE).map(k => caches.delete(k))))
  .then(() => self.clients.claim()).then(() => sendKoe())));

// Svarer Mac'en, sendes køen af markeringer med det samme (e: hændelsen, der holder service workeren vågen imens)
const hent = (c, p, e) => fetch(p, { cache: "no-store" }).then(r => { if (r.ok) { c.put(p, r.clone()); e?.waitUntil(sendKoe()); } return r; });
const ikkeGemt = () => new Response(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Ikke på telefonen</title>
<style>body{font:15px system-ui;margin:15vh auto;max-width:34em;padding:0 16px;color:#737373;background:#f7f7f7}h1{color:#171717;font-size:21px;font-weight:600}a{color:#171717}
@media (prefers-color-scheme:dark){body{background:#0b0b0b;color:#a3a3a3}h1,a{color:#f5f5f5}}</style>
<h1>Filen ligger ikke på telefonen</h1><p>Mac'en svarer ikke, og filen er ikke hentet før. Denne og næste uges forelæsninger og øvelser hentes,
når På farten henter en pakke; andre ligger på telefonen, når du har åbnet dem én gang med forbindelse.</p>
<p><a href="/studie/fag.html" onclick="history.back();return false">‹ Fag</a></p>`, { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } });

// ── køen af markeringer, der venter på Mac'en ──
// Ligger i sit eget Cache-lager (overlever, at browseren lukkes, og en ny udgave af service workeren). Én ændring ad gangen.
let laas = Promise.resolve();
const medLaas = fn => { const r = laas.then(fn, fn); laas = r.catch(() => {}); return r; };
const læsKoe = async () => { const r = await (await caches.open(KOE_CACHE)).match(KOE); return r ? r.json() : []; };
const gemKoe = async k => (await caches.open(KOE_CACHE)).put(KOE, json(k));
let sender = null;
function sendKoe() {
  return sender ||= medLaas(async () => {
    const k = await læsKoe();
    if (!k.length) return;
    let r;
    try { r = await fetch("/studie/api/sync", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ poster: k }), cache: "no-store" }); }
    catch { return; }                              // Mac'en svarer stadig ikke: prøv igen næste gang
    if (!r.ok) return;                             // serveren kører ikke, eller svaret kom ikke igennem: prøv igen
    // Gemt eller afvist (fx en frist, der ikke findes mere): ud af køen begge veje. Det, der er lagt i kø imens, bliver
    const sendt = new Set(k.map(p => p.id));
    await gemKoe((await læsKoe()).filter(p => !sendt.has(p.id)));
  }).finally(() => { sender = null; });
}
self.addEventListener("sync", e => { if (e.tag === "studie-koe") e.waitUntil(sendKoe()); });

// Svaret, siden ville have fået af Mac'en, og de gemte data rettet, så markeringen står der næste gang
async function iKoe(sti, d) {
  const nu = new Date(), dag = isoDag(nu), id = `${KAN_VENTE[sti]}-${nu.getTime().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  await medLaas(async () => gemKoe([...(await læsKoe()), { id, type: KAN_VENTE[sti], tid: nu.toISOString(), data: d }]));
  try { await self.registration.sync?.register("studie-koe"); } catch { /* ikke på alle telefoner; køen sendes ved næste kald */ }
  const c = await caches.open(CACHE), ret = async (p, f) => { const r = await c.match(p); if (r) await c.put(p, json(f(await r.json()))); };
  if (sti === "/studie/api/laest") {
    const uge = String(+d.uge);
    await ret("/studie/api/laest", l => { const f = (l[d.fag] ||= {}); if (d.laest) f[uge] = dag; else delete f[uge]; return l; });
    return json({ fag: d.fag, uge: +uge, laest: d.laest ? dag : null, koe: true });
  }
  if (sti === "/studie/api/deadline") {
    // Afleveringer (fx Gamma|Opgave 3) står som dd.mm i afleveringstabellen, andre frister som en dato
    const andet = /^[^|]+\|[a-z]+\|\d{0,2}$/.test(d.noegle || ""), faerdig = d.faerdig ? (andet ? dag : `${dag.slice(8)}.${dag.slice(5, 7)}`) : null;
    await ret("/studie/studie.json", s => { (s.deadlines || []).forEach(x => { if (x.noegle === d.noegle) x.faerdig = faerdig; }); return s; });
    return json({ noegle: d.noegle, faerdig, koe: true });
  }
  const kommentar = String(d.kommentar ?? "").trim(), v = d.vurdering || kommentar ? { vurdering: d.vurdering || null, kommentar, dato: dag } : null;
  await ret("/studie/api/usb-vurdering", u => { const f = (u[d.fag] ||= {}); if (v) f[d.del] = v; else delete f[d.del]; return u; });
  return json({ fag: d.fag, del: d.del, ...(v || { vurdering: null, kommentar: "", dato: null }), koe: true });
}

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url), p = noegle(url.pathname);
  if (url.origin !== location.origin) return;
  if (e.request.method === "POST" && p.startsWith("/studie/api/") && p !== "/studie/api/sync") {
    // Skrivninger går direkte til Mac'en; kun hvis den ikke svarer, lægges markeringerne i kø
    e.respondWith((async () => {
      const krop = await e.request.clone().text();
      let r = null;
      try { r = await fetch(e.request); } catch { /* Mac'en svarer ikke */ }
      if (r && r.status < 500) { e.waitUntil(sendKoe()); return r; }
      if (KAN_VENTE[p]) { let d; try { d = JSON.parse(krop || "{}"); } catch { return json({ fejl: "ugyldig krop" }, 400); } return iKoe(p, d); }
      return r || json({ fejl: p.startsWith("/studie/api/eksamen/") ? "Mac'en svarer ikke. En prøveeksamen gemmes kun, mens Mac'en er vågen."
        : "Mac'en svarer ikke. Svar på genkald, drills og I egne ord kan gives i På farten uden net; de sendes, når Mac'en svarer." }, 503);
    })());
    return;
  }
  // Pakken går altid direkte til Mac'en: På farten har sin egen og skal kunne se, at Mac'en ikke svarer
  if (e.request.method !== "GET" || p === "/studie/api/pakke") return;
  if (DATA.includes(p) || (p.startsWith("/studie/api/") && !p.startsWith("/studie/api/pensum/")) || (p.startsWith("/studie/") && p.endsWith(".json"))) {
    const k = p + url.search;   // fx /api/facit?fag=…&nr=… gemmes for sig
    e.respondWith(caches.open(CACHE).then(async c => {
      const frisk = hent(c, k, e);
      return await ventTil(4000, frisk) || await c.match(k) || frisk;
    }));
  } else if (p.startsWith("/studie/api/pensum/")) {
    // Filerne skifter ikke indhold (navnet har undervisningsdagen), så den gemte udgave vises uden at spørge Mac'en
    e.respondWith(caches.open(CACHE).then(async c => await c.match(p) || await ventTil(8000, hent(c, p)) || ikkeGemt()));
  } else if (p.startsWith("/studie/") || p.startsWith("/kompas/assets/")) {
    e.respondWith(caches.open(CACHE).then(async c => {
      const gemt = await c.match(p), frisk = hent(c, p, e);
      if (gemt) { e.waitUntil(frisk.catch(() => {})); return gemt; }
      return frisk;
    }));
  }
});
