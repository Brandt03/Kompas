// Fælles for Karriere-siderne i Kompas. Data og alle ændringer går gennem kompas_server.py (/karriere/api/).
// Jobopslag vises som tekst (escapet); intet herfra sendes nogen steder hen.
const API = "/karriere/api";
const STATUS_TEKST = { vurderet: "Ny", "vil søge": "Vil søge", fravalgt: "Fravalgt",
  "søgt": "Sendt", samtale: "Samtale", tilbud: "Tilbud", afslag: "Afslag" };
const AABEN = ["vurderet"];

async function hentData() {
  const r = await fetch(`${API}/data`, { cache: "no-store" });
  if (!r.ok) throw new Error(`jobagenten svarede ${r.status}`);
  return r.json();
}
async function post(sti, krop) {
  const r = await fetch(API + sti, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(krop) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.fejl || `svarede ${r.status}`);
  return d;
}
const saetStatus = (id, status, note) => post("/status", { id, status, note });

// Frist: en dato (ÅÅÅÅ-MM-DD) giver nedtælling; "Snarest muligt", "Løbende" osv. vises som tekst
function frist(j) {
  const m = String(j.frist || "").match(/(\d{4}-\d{2}-\d{2})/);
  if (!m) return { tekst: j.frist || "Ikke oplyst", dage: null };
  const dage = daysUntil(m[1]);
  return { dato: m[1], dage, tekst: dage < 0 ? `frist ${dayMonth(parseDate(m[1]))} (overskredet)` : dage === 0 ? "frist i dag" : dage === 1 ? "frist i morgen" : `frist ${dayMonth(parseDate(m[1]))}` };
}
function fristBadge(j) {
  const f = frist(j);
  // Løbende samtaler: stillingen kan blive besat før fristen, så søg hurtigt
  const lb = j.loebende && !/løbende/i.test(f.tekst) && !(f.dage != null && f.dage < 0)
    ? `<span class="badge bad" title="De læser ansøgninger eller holder samtaler løbende. Søg inden for få dage.">${icon("rotate-cw", 12)}Løbende samtaler</span>` : "";
  return fristTekstBadge(j, f) + lb;
}
function fristTekstBadge(j, f) {
  if (f.dage == null) return `<span class="badge">${icon("clock", 12)}${esc(f.tekst)}</span>`;
  const cls = f.dage < 0 ? "" : f.dage <= 3 ? "bad" : "";
  const t = f.dage < 0 ? "Frist overskredet" : f.dage === 0 ? "Frist i dag" : f.dage === 1 ? "Frist i morgen" : f.dage <= 13 ? `Frist om ${f.dage} dage` : `Frist ${dayMonth(parseDate(f.dato))}`;
  return `<span class="badge ${cls}">${icon("clock", 12)}${t}</span>`;
}
const udloebet = j => { const f = frist(j); return f.dage != null && f.dage < 0; };

// ── skuffe til opslaget ──
function skuffe(titel, underTitel, html, knapper = "") {
  let el = document.getElementById("skuffe");
  if (!el) {
    el = document.createElement("div"); el.id = "skuffe";
    el.innerHTML = `<div class="sk-bag"></div><aside class="sk-panel" role="dialog" aria-modal="true" aria-labelledby="sk-t"><header><div><h2 id="sk-t"></h2><p class="meta" id="sk-u"></p></div><button type="button" class="nav-btn" id="sk-luk" aria-label="Luk">${icon("x", 16)}</button></header><div class="sk-knapper" id="sk-k"></div><div class="sk-indhold" id="sk-i"></div></aside>`;
    document.body.appendChild(el);
    el.querySelector(".sk-bag").onclick = lukSkuffe;
    el.querySelector("#sk-luk").onclick = lukSkuffe;
    document.addEventListener("keydown", e => { if (e.key === "Escape") lukSkuffe(); });
  }
  el.querySelector("#sk-t").textContent = titel;
  el.querySelector("#sk-u").textContent = underTitel || "";
  el.querySelector("#sk-k").innerHTML = knapper;
  el.querySelector("#sk-i").innerHTML = html;
  el.classList.add("aaben");
  el.querySelector("#sk-luk").focus();
  return el;
}
function lukSkuffe() { document.getElementById("skuffe")?.classList.remove("aaben"); }

async function visOpslag(j) {
  const r = await fetch(`${API}/opslag?id=${encodeURIComponent(j.id)}`, { cache: "no-store" });
  const t = r.ok ? await r.text() : "";
  skuffe(j.stilling, `${j.virksomhed} · teksten som jobagenten hentede den`,
    t.trim() ? `<div class="opslag">${esc(t.trim())}</div>` : `<p class="meta">Teksten er ikke gemt. Se opslaget på Jobindex.</p>`,
    `<a class="btn ghost" href="${esc(j.link)}" target="_blank" rel="noopener">${icon("external-link", 14)}Åbn på Jobindex</a>`);
}

// ── besked nederst med fortryd ──
let toastTimer;
function toast(tekst, fortryd) {
  let el = document.getElementById("toast");
  if (!el) { el = document.createElement("div"); el.id = "toast"; el.setAttribute("role", "status"); document.body.appendChild(el); }
  el.innerHTML = `<span>${esc(tekst)}</span>${fortryd ? `<button type="button">${icon("undo", 14)}Fortryd</button>` : ""}`;
  if (fortryd) el.querySelector("button").onclick = () => { el.classList.remove("vis"); fortryd(); };
  el.classList.add("vis");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("vis"), 6000);
}

function fejlkort(e) {
  return `<div class="card empty">Jobagentens side svarer ikke (${esc(e.message)}).<br>Den kører normalt altid i baggrunden.
    Se <code>~/.kompas/karriere.log</code>, eller genstart den: <code>launchctl kickstart -k gui/$(id -u)/local.kompas.karriere</code></div>`;
}
