// Shared by the study project's pages (served at /studie/): loads studie.json from Scripts/kompas-eksport.js.
async function loadStudie() {
  const r = await fetch("/studie/studie.json", { cache: "no-store" });
  if (!r.ok) throw new Error(`studie.json svarede ${r.status}`);
  return r.json();
}
// Calendar titles and the plans name the courses slightly differently; the first word is stable.
const fagId = navn => ({ alfa: "alfa", beta: "beta", gamma: "gamma" })[String(navn).split(" ")[0].toLowerCase()] || "";
const FAG_FARVE = { alfa: "var(--c1)", beta: "var(--c2)", gamma: "var(--c3)" };

// På telefonen (gennem Tailscale, se mobil.html) er siderne en del af appen På farten: en linje tilbage øverst,
// og en service worker, så de også kan åbnes uden net. På Mac'en (kompas.localhost) sker ingenting af det.
const paaTelefon = !/(^|\.)localhost$/.test(location.hostname);
if (paaTelefon) {
  const tilbage = () => document.body.insertAdjacentHTML("afterbegin", `<a href="/studie/mobil.html#overblik" style="display:block;padding:12px 16px 0;font-size:14px;color:var(--text-secondary);text-decoration:none">‹ På farten</a>`);
  document.body ? tilbage() : document.addEventListener("DOMContentLoaded", tilbage);
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/studie/mobil-sw.js", { scope: "/studie/" }).catch(() => {});
}
// Ugeoverbliks kalender: på Mac'en fra livsoverblik (loadLiv i liv.js), på telefonen kun kalenderdelen (kalender.json)
async function loadKalender() {
  if (!paaTelefon) return loadLiv();
  const r = await fetch("/studie/kalender.json", { cache: "no-store" });
  if (!r.ok) throw new Error(`kalender.json svarede ${r.status}`);
  return r.json();
}
