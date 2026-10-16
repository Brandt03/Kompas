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
  // Read from Caddy (/forbrug/state/<name>.json, works while Sure is closed), written through Sure
  // (PUT /dashboard-state/<name>, needs a Sure login on this address). localStorage is only a reserve copy for
  // when Sure can't be reached.
  // A copy that only exists in this browser (a save that failed, or tal from before the server had any) is
  // never pushed by itself: the page shows a banner, and the user sends it with "Gem på serveren".
  // A failed save shows the same banner with the reason and "Prøv igen", not just a grey word in the header.
  function store(name, onStatus) {
    const LS = `dash-state-${name}`;
    let timer = null;   // debounce for save()
    let pending = null; // what still has to reach the server
    let bar = null;
    const lsGet = () => { try { return JSON.parse(localStorage.getItem(LS) || "null"); } catch { return null; } };
    const lsSet = (v) => { try { localStorage.setItem(LS, JSON.stringify(v)); } catch { /* private mode */ } };
    const clean = (v) => { const b = { ...v }; delete b._unsynced; delete b._local_at; delete b.saved_at; return b; };
    const hasData = (v) => !!v && Object.keys(clean(v)).length > 0;
    const fmtTime = (s) => { const d = new Date(s); return isNaN(d) ? "" : d.toLocaleString("da-DK", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }); };

    // The banner sits right under the page header: icon + label + text + one button (never colour alone).
    function banner(kind, label, text, button) {
      if (!bar) {
        bar = el("section", { class: "card status save-bar", role: "alert" });
        const head = document.querySelector("header");
        if (head) head.after(bar); else document.body.prepend(bar);
      }
      bar.className = `card status save-bar ${kind}`;
      bar.hidden = false;
      bar.replaceChildren(
        el("div", { class: "ic", "aria-hidden": "true", text: "!" }),
        el("div", {},
          el("div", { class: "lbl", text: label }),
          el("div", { class: "sub", text }),
          button ? el("button", { type: "button", class: "save-btn", text: button, onclick: () => flush() }) : null));
    }
    const hideBanner = () => { if (bar) bar.hidden = true; };

    // Why Sure didn't take it, in words the user can act on
    function reason(e) {
      const host = location.host;
      if (e.kind === "login") return `Sure bad om login. Du er ikke logget ind i Sure på ${host} (login gælder pr. adresse). Log ind under Økonomi › Oversigt, og tryk så Prøv igen.`;
      if (e.kind === "closed") return "Sure kører ikke. Åbn programmet Kompas, vent til Sure svarer, og tryk så Prøv igen.";
      if (e.kind === "net") return `Ingen forbindelse til ${host}.`;
      return `Sure svarede ${e.status}${e.status === 404 ? " (findes /dashboard-state ikke? se custom/dashboard_tabs.rb)" : ""}.`;
    }

    async function put(body, keepalive = false) {
      let r;
      try {
        r = await fetch(`/dashboard-state/${name}`, {
          method: "PUT", credentials: "same-origin", redirect: "manual", keepalive,
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(body),
        });
      } catch (err) { throw { kind: "net", err }; }
      // Not signed in: Sure answers 302 to /sessions/new. Following it would turn into an unrelated 404.
      if (r.type === "opaqueredirect" || r.status === 401) throw { kind: "login" };
      if ([502, 503, 504].includes(r.status)) throw { kind: "closed", status: r.status };
      if (!r.ok) throw { kind: "http", status: r.status };
      const j = await r.json().catch(() => null);
      return (j && j.saved_at) || new Date().toISOString();
    }

    async function flush(keepalive = false) {
      clearTimeout(timer); timer = null;
      if (!pending) return;
      const body = pending;
      onStatus("Gemmer …", false);
      try {
        const savedAt = await put(body, keepalive);
        if (pending !== body) return; // changed again meanwhile; that save is on its way
        pending = null;
        lsSet({ ...body, saved_at: savedAt });
        hideBanner();
        onStatus(`Gemt i Sure ${fmtTime(savedAt)}`, false);
      } catch (e) {
        console.error(`[dashboard-state] PUT /dashboard-state/${name} fejlede`, e);
        onStatus("Ikke gemt på serveren", true);
        banner("critical", "Ikke gemt på serveren", `${reason(e)} Indtil da er tallene kun gemt i denne browser.`, "Prøv igen");
      }
    }
    // A change made less than 600 ms before leaving the page is still sent (keepalive outlives the page)
    addEventListener("pagehide", () => { if (timer) flush(true); });

    return {
      async load() {
        let server = null, serverOk = false;
        try {
          const r = await fetch(`../state/${name}.json`, { cache: "no-store" });
          if (r.ok) { server = await r.json(); serverOk = true; } else if (r.status === 404) serverOk = true; // 404: nothing saved yet
        } catch { /* offline */ }
        const local = lsGet();
        // Local wins only when the server has nothing, or the local copy is an unsent change made after the
        // server's version. That copy is offered to the server, not sent behind the user's back.
        const localOnly = hasData(local) && serverOk &&
          (!server || (local._unsynced && (local._local_at || "") > (server.saved_at || "")));
        if (localOnly) {
          pending = clean(local);
          const when = local._local_at ? ` (ændret ${fmtTime(local._local_at)})` : "";
          banner("warning", "Kun gemt i denne browser",
            `Tallene her${when} ligger kun i denne browser på ${location.host}, ikke i Sure. Så ser andre adresser og browsere dem ikke, og de forsvinder, hvis browserens data ryddes. Er det de rigtige tal, så tryk Gem på serveren.`,
            "Gem på serveren");
          onStatus("Ikke gemt på serveren", true);
          return local;
        }
        if (!server && hasData(local)) onStatus("Serveren kunne ikke læses – viser kopien i denne browser", true);
        else if (server && server.saved_at) onStatus(`Gemt i Sure ${fmtTime(server.saved_at)}`, false);
        return server || local || {};
      },
      save(value) {
        clearTimeout(timer);
        pending = clean(value);
        lsSet({ ...pending, _unsynced: true, _local_at: new Date().toISOString() });
        onStatus("Gemmer …", false);
        timer = setTimeout(() => flush(), 600);
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
