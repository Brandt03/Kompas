// Shared helpers for the projects' pages (Kompas, Studie, Karriere, Form & Fokus): escaping, number and date
// formats, countdowns, calendar events' course fields, and loadLiv() for overblik's liv.json (served at /form/liv.json).
// Every name here is a global the pages call directly, so renaming one means changing the pages too.
// Nothing is calculated here beyond formatting.
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const nf = d => new Intl.NumberFormat("da-DK", { minimumFractionDigits: d, maximumFractionDigits: d });
const fmt = (x, d = 0) => (x == null ? "–" : nf(d).format(x));

const DAYS = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"];
const MONTHS = ["jan.", "feb.", "mar.", "apr.", "maj", "jun.", "jul.", "aug.", "sep.", "okt.", "nov.", "dec."];
const parseDate = s => { const [y, m, d] = s.slice(0, 10).split("-").map(Number); return new Date(y, m - 1, d); };
const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const dayMonth = d => `${d.getDate()}. ${MONTHS[d.getMonth()]}`;
const weekday = d => DAYS[(d.getDay() + 6) % 7];
const weekNo = s => Number(String(s).split("-W")[1]);
const isoWeek = d => { const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7));
  return Math.ceil(((t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 864e5 + 1) / 7); };
const range = (monday) => { const a = parseDate(monday), b = addDays(a, 6);
  return a.getMonth() === b.getMonth() ? `${a.getDate()}.–${dayMonth(b)}` : `${dayMonth(a)} – ${dayMonth(b)}`; };
const stamp = s => { if (!s) return "–"; const d = new Date(s.length === 19 ? s : s.replace("Z", "+00:00"));
  return `${dayMonth(d)} kl. ${String(d.getHours()).padStart(2, "0")}.${String(d.getMinutes()).padStart(2, "0")}`; };

async function loadLiv() {
  const r = await fetch("/form/liv.json", { cache: "no-store" });
  if (!r.ok) throw new Error(`liv.json svarede ${r.status}`);
  return r.json();
}
const latestReview = liv => [...(liv.reviews || [])].sort((a, b) => a.uge.localeCompare(b.uge)).pop() || null;

// Et kalenderpunkt fra liv.json -> { ...e, fag, kode, art, form } som tekst. garmin-coach har allerede delt
// undervisningen fra universitetets skema op (feltet `fag`); titlerne tolkes kun dér. Andre punkter får null.
function parseEvent(e) {
  const f = e.fag || {};
  return { ...e, fag: f.navn ?? null, kode: f.kode ?? null, art: f.art ?? null, form: f.form ?? null };
}
const hours = e => {
  if (!e.start || !e.slut) return 0;
  const [a, b] = [e.start, e.slut].map(t => { const [h, m] = t.split(":").map(Number); return h * 60 + m; });
  return Math.max(0, b - a) / 60;
};
// Whole days from today to an ISO date (negative when it has passed)
const daysUntil = isoStr => Math.round((parseDate(isoStr) - new Date(new Date().toDateString())) / 864e5);
// Nedtælling med samme præcision som datoen: en præcis dato tælles i dage, en frist med kun en uge
// (dato = ugens mandag) i uger. I dag, Deadlines og Fag bruger den, så samme frist hedder det samme overalt.
function nedtaelling(isoStr, kunUge = false) {
  if (kunUge) {
    const idag = new Date(new Date().toDateString()), mandag = addDays(idag, -((idag.getDay() + 6) % 7));
    const u = Math.round((parseDate(isoStr) - mandag) / 6048e5);
    return u < 0 ? "overstået" : u === 0 ? "denne uge" : u === 1 ? "næste uge" : `om ${u} uger`;
  }
  const n = daysUntil(isoStr);
  return n < 0 ? "overstået" : n === 0 ? "i dag" : n === 1 ? "i morgen" : `om ${n} dage`;
}
