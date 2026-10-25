// Shared by the study project's pages (served at /studie/): loads studie.json from Scripts/kompas-eksport.js.
async function loadStudie() {
  const r = await fetch("/studie/studie.json", { cache: "no-store" });
  if (!r.ok) throw new Error(`studie.json svarede ${r.status}`);
  const d = await r.json();
  saetFag(d.fag);
  return d;
}
// The semester's courses from Scripts/fag.json (via studie.json or the phone's package): id, kort, navn, farve and
// which features each has (genkald, begreber, kode, eksamenstraening …). Pages ask here instead of keeping lists.
let FAG = [];
const saetFag = fag => { if (Array.isArray(fag) && fag.length) FAG = fag; };
const fagInfo = id => FAG.find(f => f.id === id) || null;
const fagKort = id => fagInfo(id)?.kort || id;
const fagFarve = id => fagInfo(id)?.farve || "var(--gray-400)";
const fagMed = egenskab => FAG.filter(f => f[egenskab]);
// Deadlines and CLAUDE.md name the course by its short name ("Alfa"), older files maybe by an alias
const fagFraKort = k => FAG.find(f => [f.kort, ...(f.alias || [])].some(n => n.toLowerCase() === String(k).trim().toLowerCase())) || null;
// Ugen, Ugeoverblik og Fag åbner på: mandag-fredag denne uge, lørdag og søndag næste uge (ugens undervisning er
// overstået, og køreplanen for næste uge skrives søndag). { mandag: "2026-10-12", uge: 42, naeste: true }
function visUge(nu = new Date()) {
  const naeste = [0, 6].includes(nu.getDay());
  const m = new Date(nu.getFullYear(), nu.getMonth(), nu.getDate() - (nu.getDay() + 6) % 7 + (naeste ? 7 : 0));
  const to = n => String(n).padStart(2, "0");
  const tor = new Date(Date.UTC(m.getFullYear(), m.getMonth(), m.getDate() + 3));   // ISO-ugen er torsdagens uge
  return { mandag: `${m.getFullYear()}-${to(m.getMonth() + 1)}-${to(m.getDate())}`,
    uge: Math.ceil(((tor - Date.UTC(tor.getUTCFullYear(), 0, 1)) / 864e5 + 1) / 7), naeste };
}
// Køreplanen til en uge (planer fra studie.json). I weekenden åbner siderne på næste uge, men dens køreplan skriver
// Studie-rutinen først søndag kl. 18; til den findes, viser Ugeoverblik og Fag sidste uges med mærket SIDSTE_UGES.
// { plan, sidste: true, når planen er sidste uges i stedet for ugens }
const SIDSTE_UGES = "sidste uges køreplan · ny kommer søndag kl. 18";
function koereplan(planer = [], uge, v = visUge()) {
  const plan = planer.find(p => p.uge === uge) || null;
  if (plan || !v.naeste || uge !== v.uge) return { plan, sidste: false };
  const [a, m, d] = v.mandag.split("-").map(Number), f = new Date(a, m - 1, d - 7), to = n => String(n).padStart(2, "0");
  const forrige = planer.find(p => p.fra === `${f.getFullYear()}-${to(f.getMonth() + 1)}-${to(f.getDate())}`) || null;
  return { plan: forrige, sidste: !!forrige };
}
// Calendar titles and the plans name the courses slightly differently; the first word is stable.
const forsteOrd = s => String(s).split(" ")[0].toLowerCase();
const fagId = navn => FAG.find(f => forsteOrd(f.navn) === forsteOrd(navn))?.id || "";

// På telefonen (gennem Tailscale, se mobil.html) er siderne en del af På farten: en linje tilbage øverst,
// og en service worker, så de også kan åbnes uden net. På Mac'en (kompas.localhost) og på bærbaren (Tailscale-adressen
// med :8443, hele Kompas) sker ingenting af det; telefonens adresse har ingen port.
const paaTelefon = !/(^|\.)localhost$/.test(location.hostname) && !location.port;
if (paaTelefon) {
  const tilbage = () => document.body.insertAdjacentHTML("afterbegin", `<a href="/studie/mobil.html#overblik" style="display:block;padding:12px 16px 0;font-size:14px;color:var(--text-secondary);text-decoration:none">‹ På farten</a>`);
  document.body ? tilbage() : document.addEventListener("DOMContentLoaded", tilbage);
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/studie/mobil-sw.js", { scope: "/studie/" }).catch(() => {});
}
// Ugeoverbliks kalender: på Mac'en fra overblik (loadLiv i liv.js), på telefonen kun kalenderdelen (kalender.json)
async function loadKalender() {
  if (!paaTelefon) return loadLiv();
  const r = await fetch("/studie/kalender.json", { cache: "no-store" });
  if (!r.ok) throw new Error(`kalender.json svarede ${r.status}`);
  return r.json();
}
