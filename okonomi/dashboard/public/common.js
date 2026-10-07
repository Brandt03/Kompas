// Shared helpers for the Scenarier and SU-vagt pages (plain script, exposes window.Dash).
(() => {
  "use strict";
  const MONTHS = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"];
  const MONTHS_LONG = ["januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober", "november", "december"];

  const kr = new Intl.NumberFormat("da-DK", { style: "currency", currency: "DKK", maximumFractionDigits: 0 });
  const num = new Intl.NumberFormat("da-DK", { maximumFractionDigits: 0 });
  const pct = new Intl.NumberFormat("da-DK", { style: "percent", maximumFractionDigits: 0 });

  const $ = (id) => document.getElementById(id);
  const el = (tag, props = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === "style") n.setAttribute("style", v);
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else if (k === "text") n.textContent = v;
      else if (k === "value") n.value = v;
      else if (k === "checked") n.checked = !!v;
      else n.setAttribute(k, v === true ? "" : v);
    }
    kids.flat().forEach((c) => c != null && c !== false && n.append(c));
    return n;
  };
  const svgEl = (tag, attrs = {}) => {
    const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    return n;
  };

  const ym = (d) => d.slice(0, 7);
  const addMonths = (k, n) => { const [y, m] = k.split("-").map(Number); const d = new Date(y, m - 1 + n, 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };
  const monthsBetween = (a, b) => { const out = []; for (let k = a; k <= b; k = addMonths(k, 1)) out.push(k); return out; };
  const monthDiff = (a, b) => { const [ya, ma] = a.split("-").map(Number); const [yb, mb] = b.split("-").map(Number); return (yb - ya) * 12 + (mb - ma); };
  const monthName = (k, long) => { const [y, m] = k.split("-").map(Number); return `${(long ? MONTHS_LONG : MONTHS)[m - 1]} ${y}`; };
  const now = new Date();
  const TODAY_KEY = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;

  function niceStep(raw) {
    if (!(raw > 0)) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(raw)));
    for (const m of [1, 2, 2.5, 5, 10]) if (raw <= m * p) return m * p;
    return 10 * p;
  }

  // ---------- data ----------
  async function loadData() {
    const r = await fetch("../data.json", { cache: "no-store" });
    if (!r.ok) throw new Error(`data.json: ${r.status}`);
    const d = await r.json();
    d.transactions = d.transactions.map((t) => ({
      ...t, amount: Number(t.amount), ym: ym(t.date), category: t.category || "Ukategoriseret", group: t.group || t.category || "Ukategoriseret",
    }));
    return d;
  }
  function metaLine(d) {
    const fmt = (s) => s ? new Date(s).toLocaleString("da-DK", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "–";
    return [`Bank synkroniseret ${fmt(d.last_sync)} · data hentet ${fmt(d.generated_at)} · `, el("a", { href: "/", target: "_top", text: "Åbn Sure" })];
  }

  // ---------- saved settings ----------
  // Read from Caddy (works while Sure is closed), written through Sure (PUT /dashboard-state/<name>).
  // localStorage is only a fallback copy for when Sure isn't running.
  function store(name, onStatus) {
    const LS = `dash-state-${name}`;
    let timer = null;
    const lsGet = () => { try { return JSON.parse(localStorage.getItem(LS) || "null"); } catch { return null; } };
    const lsSet = (v) => { try { localStorage.setItem(LS, JSON.stringify(v)); } catch { /* private mode */ } };
    return {
      async load() {
        let server = null;
        try {
          const r = await fetch(`../state/${name}.json`, { cache: "no-store" });
          if (r.ok) server = await r.json();
        } catch { /* offline */ }
        const local = lsGet();
        // an unsynced local copy is newer than the server's
        if (local && local._unsynced && (!server || (local._local_at || "") > (server.saved_at || ""))) return local;
        return server || local || {};
      },
      save(value) {
        clearTimeout(timer);
        lsSet({ ...value, _unsynced: true, _local_at: new Date().toISOString() });
        onStatus("Gemmer …", false);
        timer = setTimeout(async () => {
          try {
            const body = { ...value }; delete body._unsynced; delete body._local_at; delete body.saved_at;
            const r = await fetch(`/dashboard-state/${name}`, {
              method: "PUT", credentials: "same-origin",
              headers: { "Content-Type": "application/json", Accept: "application/json" },
              body: JSON.stringify(body),
            });
            if (!r.ok) throw new Error(r.status);
            lsSet(body);
            onStatus("Gemt", false);
          } catch {
            onStatus("Kun gemt i denne browser – Sure svarer ikke (lukket eller ikke logget ind)", true);
          }
        }, 600);
      },
    };
  }

  // ---------- tooltip ----------
  let tip;
  function showTip(ev, head, lines) {
    tip = tip || $("tip");
    tip.replaceChildren(el("div", { class: "t-head", text: head }));
    for (const [color, label, value] of lines) {
      tip.append(el("div", { class: "t-row" }, el("i", { style: `background:${color}` }), el("span", { text: label }), el("b", { text: value })));
    }
    let x, y;
    if (ev.clientX != null && ev.type !== "focus") { x = ev.clientX; y = ev.clientY; }
    else { const r = ev.target.getBoundingClientRect(); x = r.left + r.width / 2; y = r.top; }
    tip.style.opacity = 1;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.min(Math.max(8, x + 14), innerWidth - w - 8) + "px";
    tip.style.top = Math.min(Math.max(8, y - h - 12), innerHeight - h - 8) + "px";
  }
  function hideTip() { if (tip) tip.style.opacity = 0; }

  // y-axis gridlines + labels; returns the value->y mapping
  function yAxis(svg, { min = 0, max, top, bottom, left, right, fmt = (v) => num.format(v) }) {
    const step = niceStep((max - min) / 4 || 1);
    const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step || step;
    const y = (v) => top + (bottom - top) * (1 - (v - lo) / (hi - lo));
    for (let v = lo; v <= hi + step / 1000; v += step) {
      svg.append(svgEl("line", { x1: left, x2: right, y1: y(v), y2: y(v), stroke: Math.abs(v) < step / 1000 ? "var(--axis)" : "var(--grid)", "stroke-width": 1 }));
      const t = svgEl("text", { x: left - 8, y: y(v) + 4, "text-anchor": "end" }); t.textContent = fmt(v); svg.append(t);
    }
    return y;
  }

  window.Dash = { MONTHS, MONTHS_LONG, kr, num, pct, $, el, svgEl, ym, addMonths, monthsBetween, monthDiff, monthName, TODAY_KEY, niceStep, loadData, metaLine, store, showTip, hideTip, yAxis };
})();
