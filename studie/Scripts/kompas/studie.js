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
// Calendar titles and the plans name the courses slightly differently; the first word is stable.
const forsteOrd = s => String(s).split(" ")[0].toLowerCase();
const fagId = navn => FAG.find(f => forsteOrd(f.navn) === forsteOrd(navn))?.id || "";

// På telefonen (gennem Tailscale, se mobil.html) er siderne en del af appen På farten: en linje tilbage øverst,
// og en service worker, så de også kan åbnes uden net. På Mac'en (kompas.localhost) sker ingenting af det.
const paaTelefon = !/(^|\.)localhost$/.test(location.hostname);
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
