// Small SVG charts for the projects' pages, in Sure's style: thin marks, recessive grid, hover tooltip.
// One series per chart (no dual axes). ref/band labels go in a key above the plot. Needs page.css (.chart-tip) and tokens.css.
//   barChart(el, { points: [{ label, y, tip }], ref: { y, label }, fmt, height })
//   lineChart(el, { points: [{ label, y, tip }], band: { lo, hi, label }, ref: { y, label }, fmt, height })
// A point with y == null is a gap (no measurement), never a zero; a chart with no measurements says so.
// The chart is drawn at the width it is shown at and redrawn when that width changes, so text stays 11px and
// lines 2px. It waits to draw until the element has a width (e.g. a hidden tab).
// Keyboard: Tab focuses a chart, arrow keys/Home/End move between points, Escape closes; a live region reads the point.
(function () {
  const NS = "http://www.w3.org/2000/svg";
  // Same as esc in liv.js; kept here so chart.js works without it
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  // el -> { tegn(width), w: width drawn at, valgt: the point the keyboard is on }
  const tegninger = new WeakMap();
  const ro = typeof ResizeObserver === "function" ? new ResizeObserver(es => es.forEach(e => {
    // A chart the page has replaced is let go, so old elements aren't kept alive
    if (!e.target.isConnected) { ro.unobserve(e.target); tegninger.delete(e.target); return; }
    const t = tegninger.get(e.target), w = Math.round(e.contentRect.width);
    if (t && w && w !== t.w) { t.w = w; t.tegn(w); }
  })) : null;
  // The content width, as ResizeObserver measures it (clientWidth includes padding)
  function indholdsbredde(el) {
    const cs = getComputedStyle(el);
    return Math.round(el.clientWidth - parseFloat(cs.paddingLeft || 0) - parseFloat(cs.paddingRight || 0));
  }
  function tegn(el, fn) {
    const t = { ...tegninger.get(el), tegn: fn, w: indholdsbredde(el) };
    tegninger.set(el, t);
    if (ro) ro.observe(el);
    if (t.w > 0) fn(t.w);
    else if (!ro) fn(600);  // no ResizeObserver: draw at a fixed width and let it scale
  }
  // Tick step: 1, 2 or 5 times a power of ten, so the axis reads 0 / 5 / 10, never 0 / 4.7 / 9.4
  function pæntTrin(r) {
    const p = 10 ** Math.floor(Math.log10(r)), f = r / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
  }
  let tipEl;
  function tip() {
    if (!tipEl) { tipEl = document.createElement("div"); tipEl.className = "chart-tip"; document.body.appendChild(tipEl); }
    return tipEl;
  }
  function showTip(html, ev) {
    const t = tip(); t.innerHTML = html; t.style.opacity = "1";
    const w = t.offsetWidth, h = t.offsetHeight;
    let x = ev.clientX + 14, y = ev.clientY - h - 10;
    if (x + w > innerWidth - 8) x = ev.clientX - w - 14;
    if (y < 8) y = ev.clientY + 14;
    t.style.left = x + "px"; t.style.top = y + "px";
  }
  const hideTip = () => { if (tipEl) tipEl.style.opacity = "0"; };
  // A hidden live region, so a screen reader reads the selected point
  let liveEl;
  function oplæs(html) {
    if (!liveEl) {
      liveEl = document.createElement("div"); liveEl.setAttribute("aria-live", "polite");
      liveEl.style.cssText = "position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap";
      document.body.appendChild(liveEl);
    }
    // Line breaks and blocks in the tooltip become " · ", the way the tooltip itself reads
    const d = document.createElement("div"); d.innerHTML = String(html || "").replace(/<br\s*\/?>|<\/(div|p|li)>/gi, " · ");
    liveEl.textContent = d.textContent.replace(/\s+/g, " ").replace(/(\s·\s)+/g, " · ").replace(/^[\s·]+|[\s·]+$/g, "");
  }

  function frame(el, width, points, opts, extra = []) {
    const W = width, H = opts.height || 200;
    // Reference and band labels sit in a key row above the plot, so they never cover the data
    const noegle = [opts.ref?.label && { type: "ref", label: opts.ref.label }, opts.band?.label && { type: "band", label: opts.band.label }].filter(Boolean);
    const L = 36, R = 8, T = noegle.length ? 28 : 10, B = 22;
    const ys = points.map(p => p.y).filter(v => v != null).concat(extra);
    let lo = opts.min ?? Math.min(...ys), hi = Math.max(...ys);
    const ikkeNegativ = Math.min(...ys) >= 0;
    if (opts.min == null) lo -= (hi - lo) * 0.15;
    if (ikkeNegativ) lo = Math.max(0, lo);
    hi += (hi - lo) * 0.04;
    if (!(hi > lo)) hi = lo + 1;
    // The axis starts on a clean tick and ends just above the highest value; ticks only where they are clean
    // A step finer than the page shows ("49 49 50 50" at 0 decimals) goes up to the next clean step
    let trin = pæntTrin((hi - lo) / 4), tal = [];
    for (let n = 0; n < 6; n++) {
      const bund = Math.floor(lo / trin) * trin;
      tal = [];
      for (let v = bund; v <= hi + 1e-9; v += trin) tal.push(+v.toFixed(10));
      const tekst = tal.map(opts.fmt || String);
      if (new Set(tekst).size === tekst.length) break;
      trin = pæntTrin(trin * 1.5);
    }
    lo = tal[0];
    const x = i => L + (i + 0.5) * (W - L - R) / points.length;
    const y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo || 1));
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("class", "chart");
    // Focusable and keyboard-driven (see hover), so a group with its own role description rather than an image
    svg.setAttribute("role", "group"); svg.setAttribute("aria-roledescription", "graf");
    if (opts.label) svg.setAttribute("aria-label", opts.label);
    let g = "";
    for (const v of tal) {
      const yy = y(v);
      g += `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" class="grid"/>`;
      g += `<text x="${L - 6}" y="${yy + 4}" text-anchor="end">${(opts.fmt || String)(v)}</text>`;
    }
    // At most 7 x labels, and about 48px apart so they fit on a narrow chart
    const every = Math.ceil(points.length / Math.max(2, Math.min(7, Math.floor((W - L - R) / 48))));
    points.forEach((p, i) => { if (i % every === 0) g += `<text x="${x(i)}" y="${H - 5}" text-anchor="middle">${esc(p.label)}</text>`; });
    let kx = L;
    for (const k of noegle) {
      g += k.type === "ref" ? `<line class="ref" x1="${kx}" x2="${kx + 16}" y1="9" y2="9"/>` : `<rect class="band" x="${kx}" y="4" width="16" height="10" rx="2"/>`;
      g += `<text x="${kx + 22}" y="13" class="noegle">${esc(k.label)}</text>`;
      kx += 22 + k.label.length * 6.5 + 14;
    }
    return { svg, W, H, L, R, T, B, x, y, lo, hi, g };
  }

  function hover(f, points, el) {
    const step = (f.W - f.L - f.R) / points.length;
    let g = "";
    points.forEach((p, i) => { g += `<rect class="hit" data-i="${i}" x="${f.L + i * step}" y="${f.T}" width="${step}" height="${f.H - f.T - f.B}"/>`; });
    f.g += `<line class="cross" x1="0" x2="0" y1="${f.T}" y2="${f.H - f.B}" style="opacity:0"/>` + g;
    f.svg.innerHTML = f.g;
    const cross = f.svg.querySelector(".cross");
    const vis = (i, ev) => {
      const cx = f.x(i);
      cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.style.opacity = "1";
      showTip(points[i].tip, ev);
    };
    const skjul = () => { cross.style.opacity = "0"; hideTip(); };
    f.svg.addEventListener("pointermove", ev => {
      const r = ev.target.closest(".hit"); if (r) vis(+r.dataset.i, ev);
    });
    f.svg.addEventListener("pointerleave", () => { if (document.activeElement !== f.svg) skjul(); });

    // Keyboard: Tab to the chart, arrow keys between points, Home/End, Escape closes. The value is read out.
    // The selected point is kept per chart, so a redraw (new width) doesn't move it.
    const t = tegninger.get(el) || {};
    let valgt = Math.min(t.valgt ?? points.length - 1, points.length - 1);
    const vælg = i => {
      valgt = t.valgt = Math.max(0, Math.min(points.length - 1, i));
      const r = f.svg.getBoundingClientRect(), k = r.width / f.W, p = points[valgt];
      vis(valgt, { clientX: r.left + f.x(valgt) * k, clientY: r.top + f.y(p.y ?? f.lo) * k });
      oplæs(points[valgt].tip);
    };
    f.svg.setAttribute("tabindex", "0");
    f.svg.setAttribute("aria-label", `${f.svg.getAttribute("aria-label") || "Graf"}. Brug piletasterne for at gå gennem punkterne.`);
    f.svg.addEventListener("focus", () => vælg(valgt));
    f.svg.addEventListener("blur", skjul);
    f.svg.addEventListener("keydown", ev => {
      const i = { ArrowLeft: valgt - 1, ArrowRight: valgt + 1, Home: 0, End: points.length - 1 }[ev.key];
      if (i != null) { ev.preventDefault(); vælg(i); }
      else if (ev.key === "Escape") skjul();
    });
    // A chart redrawn (new width) while it has focus keeps focus
    const havdeFokus = el.contains(document.activeElement);
    el.replaceChildren(f.svg);
    if (havdeFokus) f.svg.focus();
  }

  function ingenMaalinger(el) {
    const p = document.createElement("p");
    p.className = "meta"; p.textContent = "Ingen målinger i perioden";
    el.replaceChildren(p);
  }

  window.barChart = (el, opts) => tegn(el, w => barChart(el, w, opts));
  window.lineChart = (el, opts) => tegn(el, w => lineChart(el, w, opts));

  function barChart(el, width, opts) {
    if (opts.points.every(p => p.y == null)) return ingenMaalinger(el);
    const pts = opts.points, f = frame(el, width, pts, { ...opts, min: 0 }, opts.ref ? [opts.ref.y] : []);
    const bw = Math.max(2, Math.min(14, (f.W - f.L - f.R) / pts.length - 3));
    pts.forEach((p, i) => {
      if (p.y == null) return;
      const top = f.y(p.y), base = f.y(0), h = Math.max(1, base - top), r = Math.min(4, bw / 2, h);
      const x0 = f.x(i) - bw / 2;
      f.g += `<path class="bar${p.dim ? " dim" : ""}" d="M${x0},${base} V${top + r} q0,-${r} ${r},-${r} H${x0 + bw - r} q${r},0 ${r},${r} V${base} Z"/>`;
    });
    if (opts.ref) {
      const yy = f.y(opts.ref.y);
      f.g += `<line x1="${f.L}" x2="${f.W - f.R}" y1="${yy}" y2="${yy}" class="ref"/>`;
    }
    hover(f, pts, el);
  }

  function lineChart(el, width, opts) {
    if (opts.points.every(p => p.y == null)) return ingenMaalinger(el);
    const pts = opts.points, band = opts.band;
    const f = frame(el, width, pts, opts, [...(band ? [band.lo, band.hi] : []), ...(opts.ref ? [opts.ref.y] : [])]);
    if (band) {
      const y1 = f.y(band.hi), y2 = f.y(band.lo);
      f.g += `<rect class="band" x="${f.L}" y="${y1}" width="${f.W - f.L - f.R}" height="${Math.max(1, y2 - y1)}" rx="4"/>`;
    }
    if (opts.ref) {
      const yy = f.y(opts.ref.y);
      f.g += `<line x1="${f.L}" x2="${f.W - f.R}" y1="${yy}" y2="${yy}" class="ref"/>`;
    }
    let d = "", pen = false;
    pts.forEach((p, i) => {
      if (p.y == null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${f.x(i).toFixed(1)},${f.y(p.y).toFixed(1)} `; pen = true;
    });
    f.g += `<path class="line" d="${d}"/>`;
    const last = pts.map((p, i) => [p, i]).filter(([p]) => p.y != null).pop();
    if (last) f.g += `<circle class="pt" cx="${f.x(last[1])}" cy="${f.y(last[0].y)}" r="4"/>`;
    hover(f, pts, el);
  }
})();
