// Small SVG charts for the projects' pages, in Sure's style: thin marks, recessive grid, hover tooltip.
// One series per chart, except the stacked and lane charts below; barChart and lineChart may add a thin dashed second
// line on its own axis to the right (line2).
// ref/band/line2 labels go in a key above the plot. Needs page.css (.chart-tip) and tokens.css.
//   barChart(el, { points: [{ label, y, y2, tip }], ref: { y, label }, line2: { label, max, fmt }, fmt, height })
//   lineChart(el, { points: [{ label, y, y2, tip }], band: { lo, hi, label }, ref: { y, label }, line2, fmt, height, fyld })
//     fyld: true fills the area under the line, fading down (like a share price)
//   scatterChart(el, { points: [{ x, y, tip }], fmt, xfmt, xlabel, height }): one point per pair; points without both are left out
//   stackChart(el, { series: [{ label, color }], points: [{ label, ys: [..], tip }], ref, fmt, height }): a stacked bar per
//     point, one segment per series in series order; negative values stack down from 0 (fx body battery drained)
//   rangeChart(el, { points: [{ label, lo, hi, tip }], fmt, height }): a floating bar from lo to hi per point
//   pieChart(el, { slices: [{ label, y, color, tip }], midte: { tal, tekst }, height }): a ring cut in slices by share of
//     the total (fx time per subject), with the legend above and a number in the middle; slices with y 0 or null are left out
//   heatGrid(el, { cols: [label], rows: [{ label, cells: [{ niveau: 0–1, tip }] }] }): one row per measure, stronger = higher
//     in that row's own span; a cell with niveau == null is left empty
//   timelineChart(el, { rows: [{ label, color }], segs: [{ row, fra, til, tip }], fra, til, xfmt, height }): segments in lanes
//     along one time axis (fx sleep stages); ticks every hour when fra/til are minutes
//   timeChart(el, { points: [{ x, y, tip }], fra, til, xfmt, zones: [{ lo, hi, label, color }], gap, ref, fmt, height }):
//     a line over a true time axis in minutes (fx puls hen over døgnet), with the area under it filled. zones tint the
//     background (not with bg: false) and colour the line by the zone it is in; a jump of more than `gap` minutes breaks the line. Points with
//     their own `color` colour the line by that instead (fx what you were doing), with `noegle: [{ label, color }]` as legend.
//     spans: [{ fra, til, label }] shades a stretch of time behind the line and names it at the top (fx a workout)
// Every chart takes `color` (a CSS colour) for its marks instead of Sure's blue; heatGrid rows take their own `color`, and
// heatGrid's `vaelg(i)` is called with the column when a cell is clicked or chosen with Enter.
// The charts with several series (stackChart, timelineChart) put their legend above the plot; color follows the series.
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
    const noegle = [opts.ref?.label && { type: "ref", label: opts.ref.label }, opts.band?.label && { type: "band", label: opts.band.label },
      opts.line2?.label && { type: "line2", label: opts.line2.label }].filter(Boolean);
    const L = 36, R = opts.line2 ? 32 : 8, T = noegle.length ? 28 : 10, B = 22;
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
    if (opts.color) farve(svg, opts.color);
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
      g += k.type === "ref" || k.type === "line2" ? `<line class="${k.type}" x1="${kx}" x2="${kx + 16}" y1="9" y2="9"/>` : `<rect class="band" x="${kx}" y="4" width="16" height="10" rx="2"/>`;
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
    el.replaceChildren(...(f.foran || []), f.svg);
    if (havdeFokus) f.svg.focus();
  }

  function ingenMaalinger(el) {
    const p = document.createElement("p");
    p.className = "meta"; p.textContent = "Ingen målinger i perioden";
    el.replaceChildren(p);
  }

  window.barChart = (el, opts) => tegn(el, w => barChart(el, w, opts));
  window.lineChart = (el, opts) => tegn(el, w => lineChart(el, w, opts));
  window.scatterChart = (el, opts) => tegn(el, w => scatterChart(el, w, opts));
  window.stackChart = (el, opts) => tegn(el, w => stackChart(el, w, opts));
  window.rangeChart = (el, opts) => tegn(el, w => rangeChart(el, w, opts));
  window.heatGrid = (el, opts) => tegn(el, w => heatGrid(el, w, opts));
  window.timelineChart = (el, opts) => tegn(el, w => timelineChart(el, w, opts));
  window.pieChart = (el, opts) => tegn(el, w => pieChart(el, w, opts));

  // The legend for charts with several series, as HTML above the plot so it wraps on a narrow chart
  function noegle(series) {
    const d = document.createElement("div");
    d.className = "chart-key";
    d.innerHTML = series.map(s => `<span><i class="dot" style="background:${s.color}"></i>${esc(s.label)}</span>`).join("");
    return d;
  }
  const søjlebredde = (f, n) => Math.max(2, Math.min(14, (f.W - f.L - f.R) / n - 3));
  // The chart's own colour for the marks, the dimmed bars and the band
  function farve(svg, c) {
    svg.style.setProperty("--mark", c);
    svg.style.setProperty("--mark-dim", `color-mix(in oklab, ${c} 40%, transparent)`);
    svg.style.setProperty("--band", `color-mix(in oklab, ${c} 12%, transparent)`);
  }
  let gradienter = 0;
  window.timeChart = (el, opts) => tegn(el, w => timeChart(el, w, opts));

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
    linje2(f, pts, opts);
    hover(f, pts, el);
  }

  // The second line runs from 0 at the bottom to line2.max at the top, labelled on the right; a gap breaks it
  function linje2(f, pts, opts) {
    if (!opts.line2 || !pts.some(p => p.y2 != null)) return;
    const m = opts.line2.max, y2 = v => f.T + (f.H - f.T - f.B) * (1 - v / m), fm = opts.line2.fmt || String;
    for (const v of [0, m / 2, m]) f.g += `<text x="${f.W - f.R + 6}" y="${y2(v) + 4}">${fm(v)}</text>`;
    let d = "", pen = false;
    pts.forEach((p, i) => {
      if (p.y2 == null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${f.x(i).toFixed(1)},${y2(p.y2).toFixed(1)} `; pen = true;
    });
    f.g += `<path class="line2" d="${d}"/>`;
  }

  let fyldNr = 0;
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
    // fyld: arealet under kurven ned til bunden, i kurvens farve, der toner ud (som en kursgraf)
    if (opts.fyld) {
      const id = `fyld${++fyldNr}`, bund = (f.H - f.B).toFixed(1);
      f.g += `<defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style="stop-color:var(--mark);stop-opacity:.28"/>`
        + `<stop offset="1" style="stop-color:var(--mark);stop-opacity:0"/></linearGradient></defs>`;
      for (const seg of d.trim().split(/ (?=M)/)) {
        const xs = [...seg.matchAll(/[ML]([\d.]+),/g)].map(m => m[1]);
        if (xs.length > 1) f.g += `<path d="${seg} L${xs.at(-1)},${bund} L${xs[0]},${bund} Z" style="fill:url(#${id});stroke:none"/>`;
      }
    }
    f.g += `<path class="line" d="${d}"/>`;
    linje2(f, pts, opts);
    const last = pts.map((p, i) => [p, i]).filter(([p]) => p.y != null).pop();
    if (last) f.g += `<circle class="pt" cx="${f.x(last[1])}" cy="${f.y(last[0].y)}" r="4"/>`;
    hover(f, pts, el);
  }

  // Two measures against each other. The y axis is the shared frame's; the x axis gets its own clean ticks, from 0 when
  // all values are positive. Hover or the arrow keys show a point's tooltip.
  function scatterChart(el, width, opts) {
    const pts = opts.points.filter(p => p.x != null && p.y != null);
    if (!pts.length) return ingenMaalinger(el);
    const f = frame(el, width, pts.map(p => ({ y: p.y, label: "" })), { ...opts, ref: null, band: null, line2: null });
    const xs = pts.map(p => p.x), trin = pæntTrin(((Math.max(...xs) - Math.min(0, ...xs)) || 1) / 4);
    const xlo = Math.floor(Math.min(0, ...xs) / trin) * trin, xhi = Math.ceil(Math.max(...xs) / trin) * trin || trin;
    const X = v => f.L + 8 + (f.W - f.L - f.R - 16) * (v - xlo) / (xhi - xlo);
    for (let v = xlo; v <= xhi + 1e-9; v += trin) f.g += `<text x="${X(v).toFixed(1)}" y="${f.H - 5}" text-anchor="middle">${esc((opts.xfmt || String)(+v.toFixed(10)))}</text>`;
    if (opts.xlabel) f.g += `<text x="${f.W - f.R}" y="${f.H - 18}" text-anchor="end" class="noegle">${esc(opts.xlabel)}</text>`;
    pts.forEach((p, i) => { f.g += `<circle class="pt" data-i="${i}" cx="${X(p.x).toFixed(1)}" cy="${f.y(p.y).toFixed(1)}" r="4.5"/>`; });
    f.svg.innerHTML = f.g;
    const vis = (i, ev) => showTip(pts[i].tip, ev);
    f.svg.addEventListener("pointermove", ev => { const c = ev.target.closest("circle[data-i]"); if (c) vis(+c.dataset.i, ev); else hideTip(); });
    f.svg.addEventListener("pointerleave", () => { if (document.activeElement !== f.svg) hideTip(); });
    // Keyboard: the points in order of x, as in the other charts
    const orden = pts.map((p, i) => i).sort((a, b) => pts[a].x - pts[b].x);
    let valgt = 0;
    const vælg = k => {
      valgt = Math.max(0, Math.min(orden.length - 1, k));
      const i = orden[valgt], r = f.svg.getBoundingClientRect(), s = r.width / f.W;
      vis(i, { clientX: r.left + X(pts[i].x) * s, clientY: r.top + f.y(pts[i].y) * s });
      oplæs(pts[i].tip);
    };
    f.svg.setAttribute("tabindex", "0");
    f.svg.setAttribute("aria-label", `${f.svg.getAttribute("aria-label") || "Graf"}. Brug piletasterne for at gå gennem punkterne.`);
    f.svg.addEventListener("focus", () => vælg(valgt));
    f.svg.addEventListener("blur", hideTip);
    f.svg.addEventListener("keydown", ev => {
      const k = { ArrowLeft: valgt - 1, ArrowRight: valgt + 1, Home: 0, End: orden.length - 1 }[ev.key];
      if (k != null) { ev.preventDefault(); vælg(k); } else if (ev.key === "Escape") hideTip();
    });
    el.replaceChildren(f.svg);
  }
  function stackChart(el, width, opts) {
    const pts = opts.points, har = p => (p.ys || []).some(v => v != null);
    if (!pts.some(har)) return ingenMaalinger(el);
    const sum = (p, s) => (p.ys || []).reduce((a, v) => a + (v != null && Math.sign(v) === s ? v : 0), 0);
    const neg = pts.map(p => sum(p, -1));
    const f = frame(el, width, pts.map(p => ({ label: p.label, y: har(p) ? sum(p, 1) : null })),
      { ...opts, min: Math.min(0, ...neg) }, [...neg, ...(opts.ref ? [opts.ref.y] : [])]);
    const bw = søjlebredde(f, pts.length);
    pts.forEach((p, i) => {
      if (!har(p)) return;
      const x0 = f.x(i) - bw / 2;
      for (const s of [1, -1]) {
        const idx = p.ys.map((v, k) => k).filter(k => p.ys[k] != null && p.ys[k] !== 0 && Math.sign(p.ys[k]) === s);
        let acc = 0;
        idx.forEach((k, j) => {
          const a = f.y(acc), b = f.y(acc + p.ys[k]); acc += p.ys[k];
          let t = Math.min(a, b), u = Math.max(a, b);
          const yderst = j === idx.length - 1;
          // A 2px gap toward the next segment, away from 0
          if (!yderst) { if (s > 0) t += 2; else u -= 2; }
          if (u - t < 0.5) return;
          const r = yderst ? Math.min(3, bw / 2, u - t) : 0, c = opts.series[k].color;
          const d = s > 0
            ? `M${x0},${u} V${t + r} q0,-${r} ${r},-${r} H${x0 + bw - r} q${r},0 ${r},${r} V${u} Z`
            : `M${x0},${t} V${u - r} q0,${r} ${r},${r} H${x0 + bw - r} q${r},0 ${r},-${r} V${t} Z`;
          f.g += `<path d="${d}" style="fill:${c}"/>`;
        });
      }
    });
    if (opts.ref) {
      const yy = f.y(opts.ref.y);
      f.g += `<line x1="${f.L}" x2="${f.W - f.R}" y1="${yy}" y2="${yy}" class="ref"/>`;
    }
    f.foran = [noegle(opts.series)];
    hover(f, pts.map(p => ({ ...p, y: har(p) ? sum(p, 1) : null })), el);
  }

  function rangeChart(el, width, opts) {
    const pts = opts.points.map(p => ({ ...p, y: p.lo == null || p.hi == null ? null : p.hi }));
    if (pts.every(p => p.y == null)) return ingenMaalinger(el);
    const f = frame(el, width, pts, opts, pts.filter(p => p.y != null).map(p => p.lo));
    const bw = søjlebredde(f, pts.length);
    pts.forEach((p, i) => {
      if (p.y == null) return;
      const t = f.y(p.hi), u = Math.max(t + 1, f.y(p.lo));
      f.g += `<rect class="bar" x="${f.x(i) - bw / 2}" y="${t}" width="${bw}" height="${u - t}" rx="${Math.min(3, bw / 2)}"/>`;
    });
    hover(f, pts, el);
  }

  // Shared keyboard handling for the charts whose marks are not one per x position: arrows move through `n` marks
  // (or a grid of rows × cols with up/down), the mark's tooltip is shown and read out.
  function tastatur(svg, n, vis, { cols } = {}) {
    let valgt = 0;
    const vælg = i => { valgt = Math.max(0, Math.min(n - 1, i)); vis(valgt); };
    svg.setAttribute("tabindex", "0");
    svg.setAttribute("aria-label", `${svg.getAttribute("aria-label") || "Graf"}. Brug piletasterne for at gå gennem punkterne.`);
    svg.addEventListener("focus", () => vælg(valgt));
    svg.addEventListener("blur", hideTip);
    svg.addEventListener("keydown", ev => {
      const i = { ArrowLeft: valgt - 1, ArrowRight: valgt + 1, Home: 0, End: n - 1,
        ...(cols ? { ArrowUp: valgt - cols, ArrowDown: valgt + cols } : {}) }[ev.key];
      if (i != null) { ev.preventDefault(); vælg(i); } else if (ev.key === "Escape") hideTip();
    });
  }
  function pieChart(el, width, opts) {
    const slices = (opts.slices || []).filter(s => s.y > 0), total = slices.reduce((a, s) => a + s.y, 0);
    if (!total) return ingenMaalinger(el);
    const H = opts.height || 180, D = Math.min(H, width), r = D / 2 - 2, ri = r * 0.62, cx = width / 2, cy = H / 2;
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${H}`); svg.setAttribute("class", "chart");
    svg.setAttribute("role", "group"); svg.setAttribute("aria-roledescription", "graf");
    if (opts.label) svg.setAttribute("aria-label", opts.label);
    const pkt = (v, rr) => [cx + rr * Math.sin(v), cy - rr * Math.cos(v)];
    let g = "", fra = 0;
    slices.forEach((s, i) => {
      const til = fra + 2 * Math.PI * s.y / total;
      // En hel ring (én skive) tegnes som to halve, fordi en bue fra et punkt til sig selv ikke tegnes
      const bue = (a, b) => { const [x1, y1] = pkt(a, r), [x2, y2] = pkt(b, r), [x3, y3] = pkt(b, ri), [x4, y4] = pkt(a, ri);
        return `M${x1},${y1} A${r},${r} 0 ${b - a > Math.PI ? 1 : 0} 1 ${x2},${y2} L${x3},${y3} A${ri},${ri} 0 ${b - a > Math.PI ? 1 : 0} 0 ${x4},${y4} Z`; };
      const d = slices.length === 1 ? bue(0, Math.PI) + bue(Math.PI, 2 * Math.PI - 1e-6) : bue(fra, til);
      g += `<path class="skive" data-i="${i}" d="${d}" style="fill:${s.color || "var(--mark)"};stroke:var(--container);stroke-width:${slices.length > 1 ? 2 : 0}"/>`;
      fra = til;
    });
    if (opts.midte) g += `<text x="${cx}" y="${cy + 2}" text-anchor="middle" style="font-size:20px;font-weight:600;fill:var(--text-primary)">${esc(opts.midte.tal)}</text>`
      + (opts.midte.tekst ? `<text x="${cx}" y="${cy + 18}" text-anchor="middle">${esc(opts.midte.tekst)}</text>` : "");
    svg.innerHTML = g;
    const skiver = svg.querySelectorAll(".skive"), tipFor = i => slices[i].tip || `${esc(slices[i].label)}: <b>${esc(slices[i].y)}</b>`;
    svg.addEventListener("pointermove", ev => { const s = ev.target.closest(".skive"); if (s) showTip(tipFor(+s.dataset.i), ev); else hideTip(); });
    svg.addEventListener("pointerleave", () => { if (document.activeElement !== svg) hideTip(); });
    tastatur(svg, slices.length, i => { showTip(tipFor(i), vedMærke(svg, skiver[i])); oplæs(tipFor(i)); });
    el.replaceChildren(noegle(slices.map(s => ({ label: s.label, color: s.color || "var(--mark)" }))), svg);
  }

  const vedMærke = (svg, m) => { const r = m.getBoundingClientRect(); return { clientX: r.left + r.width / 2, clientY: r.top }; };

  function heatGrid(el, width, opts) {
    const rows = opts.rows, nc = opts.cols.length;
    if (!rows.some(r => r.cells.some(c => c.niveau != null))) return ingenMaalinger(el);
    const W = width, L = W < 520 ? 84 : 116, ch = 18, gap = 2, T = 4, B = 22, H = T + rows.length * (ch + gap) + B;
    const cw = (W - L) / nc;
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("class", "chart");
    svg.setAttribute("role", "group"); svg.setAttribute("aria-roledescription", "graf");
    if (opts.label) svg.setAttribute("aria-label", opts.label);
    let g = "";
    rows.forEach((r, ri) => {
      const y = T + ri * (ch + gap);
      g += `<text x="${L - 8}" y="${y + ch / 2 + 4}" text-anchor="end" class="noegle">${esc(r.label)}</text>`;
      r.cells.forEach((c, ci) => {
        const fyld = c.niveau == null ? "transparent" : `color-mix(in oklab, ${r.color || "var(--mark)"} ${Math.round(10 + 90 * c.niveau)}%, var(--container-inset))`;
        g += `<rect class="celle" data-i="${ri * nc + ci}" x="${(L + ci * cw + gap / 2).toFixed(1)}" y="${y}" width="${Math.max(1, cw - gap).toFixed(1)}" height="${ch}" rx="2" style="fill:${fyld}"/>`;
      });
    });
    const every = Math.ceil(nc / Math.max(2, Math.floor((W - L) / 48)));
    opts.cols.forEach((c, i) => { if (i % every === 0) g += `<text x="${(L + (i + 0.5) * cw).toFixed(1)}" y="${H - 5}" text-anchor="middle">${esc(c)}</text>`; });
    svg.innerHTML = g;
    const celler = svg.querySelectorAll(".celle");
    const tipFor = i => rows[Math.floor(i / nc)].cells[i % nc].tip;
    svg.addEventListener("pointermove", ev => { const c = ev.target.closest(".celle"); if (c) showTip(tipFor(+c.dataset.i), ev); else hideTip(); });
    svg.addEventListener("pointerleave", () => { if (document.activeElement !== svg) hideTip(); });
    let fokus = 0;
    tastatur(svg, rows.length * nc, i => { fokus = i; showTip(tipFor(i), vedMærke(svg, celler[i])); oplæs(tipFor(i)); }, { cols: nc });
    if (opts.vaelg) {
      svg.style.cursor = "pointer";
      svg.addEventListener("click", ev => { const c = ev.target.closest(".celle"); if (c) opts.vaelg(+c.dataset.i % nc); });
      svg.addEventListener("keydown", ev => { if (ev.key === "Enter") opts.vaelg(fokus % nc); });
    }
    el.replaceChildren(svg);
  }

  function timelineChart(el, width, opts) {
    const segs = [...opts.segs].sort((a, b) => a.fra - b.fra);
    if (!segs.length) return ingenMaalinger(el);
    const W = width, L = 52, R = 8, T = 4, B = 22, lane = 20, gap = 4, H = T + opts.rows.length * (lane + gap) + B;
    const X = v => L + (W - L - R) * (v - opts.fra) / ((opts.til - opts.fra) || 1);
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("class", "chart");
    svg.setAttribute("role", "group"); svg.setAttribute("aria-roledescription", "graf");
    if (opts.label) svg.setAttribute("aria-label", opts.label);
    let g = "";
    // Whole hours, every second hour when there's no room for each
    const trin = (W - L - R) / ((opts.til - opts.fra) / 60) < 40 ? 120 : 60;
    for (let v = Math.ceil(opts.fra / trin) * trin; v <= opts.til; v += trin) {
      g += `<line x1="${X(v).toFixed(1)}" x2="${X(v).toFixed(1)}" y1="${T}" y2="${H - B}" class="grid"/>`;
      g += `<text x="${X(v).toFixed(1)}" y="${H - 5}" text-anchor="middle">${esc((opts.xfmt || String)(v))}</text>`;
    }
    opts.rows.forEach((r, ri) => { g += `<text x="${L - 8}" y="${T + ri * (lane + gap) + lane / 2 + 4}" text-anchor="end" class="noegle">${esc(r.label)}</text>`; });
    segs.forEach((s, i) => {
      const x0 = X(s.fra), w = Math.max(1, X(s.til) - x0 - 1), y = T + s.row * (lane + gap);
      g += `<rect class="celle" data-i="${i}" x="${x0.toFixed(1)}" y="${y}" width="${w.toFixed(1)}" height="${lane}" rx="2" style="fill:${opts.rows[s.row].color}"/>`;
    });
    svg.innerHTML = g;
    const rects = svg.querySelectorAll(".celle");
    svg.addEventListener("pointermove", ev => { const c = ev.target.closest(".celle"); if (c) showTip(segs[+c.dataset.i].tip, ev); else hideTip(); });
    svg.addEventListener("pointerleave", () => { if (document.activeElement !== svg) hideTip(); });
    tastatur(svg, segs.length, i => { showTip(segs[i].tip, vedMærke(svg, rects[i])); oplæs(segs[i].tip); });
    el.replaceChildren(noegle(opts.rows), svg);
  }
  function timeChart(el, width, opts) {
    const pts = opts.points.filter(p => p.x != null && p.y != null).sort((a, b) => a.x - b.x);
    if (!pts.length) return ingenMaalinger(el);
    const zs = opts.zones || [];
    const f = frame(el, width, pts.map(p => ({ y: p.y, label: "" })), { ...opts, band: null, line2: null }, opts.ref ? [opts.ref.y] : []);
    const bredde = f.W - f.L - f.R, X = v => f.L + bredde * (v - opts.fra) / ((opts.til - opts.fra) || 1);
    const klip = v => Math.max(f.lo, Math.min(f.hi, v));
    for (const z of zs) {
      if (z.bg === false) continue;  // a zone that only colours the line
      const a = klip(z.lo ?? f.lo), b = klip(z.hi ?? f.hi);
      if (b > a) f.g += `<rect x="${f.L}" y="${f.y(b)}" width="${bredde}" height="${f.y(a) - f.y(b)}" style="fill:color-mix(in oklab, ${z.color} 9%, transparent)"/>`;
    }
    for (const sp of opts.spans || []) {
      const a = X(Math.max(opts.fra, sp.fra)), b = X(Math.min(opts.til, sp.til));
      if (b <= a) continue;
      f.g += `<rect x="${a.toFixed(1)}" y="${f.T}" width="${Math.max(2, b - a).toFixed(1)}" height="${f.H - f.T - f.B}" class="spaen"/>`;
      if (sp.label) f.g += `<text x="${(a + 4).toFixed(1)}" y="${f.T + 12}" class="noegle">${esc(sp.label)}</text>`;
    }
    // Ticks on whole hours, as many as there is room for
    const timer = (opts.til - opts.fra) / 60, trin = 60 * ([1, 2, 3, 4, 6, 12].find(t => bredde / (timer / t) >= 56) || 12);
    for (let v = Math.ceil(opts.fra / trin) * trin; v <= opts.til; v += trin) {
      f.g += `<line x1="${X(v).toFixed(1)}" x2="${X(v).toFixed(1)}" y1="${f.T}" y2="${f.H - f.B}" class="grid"/>`;
      f.g += `<text x="${X(v).toFixed(1)}" y="${f.H - 5}" text-anchor="middle">${esc((opts.xfmt || String)(v))}</text>`;
    }
    // The line takes the colour of the zone it is in, through a gradient with hard stops at the zone edges
    let streg = "var(--mark)";
    if (zs.length) {
      const id = `tc${++gradienter}`, o = v => ((f.hi - klip(v)) / (f.hi - f.lo)).toFixed(4);
      const stop = [...zs].sort((a, b) => (b.lo ?? -Infinity) - (a.lo ?? -Infinity))
        .map(z => `<stop offset="${o(z.hi ?? f.hi)}" style="stop-color:${z.color}"/><stop offset="${o(z.lo ?? f.lo)}" style="stop-color:${z.color}"/>`).join("");
      f.g = `<defs><linearGradient id="${id}" gradientUnits="userSpaceOnUse" x1="0" x2="0" y1="${f.y(f.hi)}" y2="${f.y(f.lo)}">${stop}</linearGradient></defs>` + f.g;
      streg = `url(#${id})`;
    }
    if (opts.ref) {
      const yy = f.y(opts.ref.y);
      f.g += `<line x1="${f.L}" x2="${f.W - f.R}" y1="${yy}" y2="${yy}" class="ref"/>`;
    }
    // One path per run of points with the same colour; a run ends at a gap or a new colour, and the next run starts
    // at the last point of the one before, so the line stays whole
    const gap = opts.gap ?? Infinity, bund = f.y(f.lo), egen = pts.some(p => p.color);
    const xy = p => `${X(p.x).toFixed(1)},${f.y(p.y).toFixed(1)}`;
    let løb = [];
    pts.forEach((p, i) => {
      const fp = pts[i - 1], c = egen ? p.color || "var(--mark)" : streg;
      if (!fp || p.x - fp.x > gap) løb.push({ c, ps: [p] });
      else if (løb[løb.length - 1].c !== c) løb.push({ c, ps: [fp, p] });
      else løb[løb.length - 1].ps.push(p);
    });
    for (const l of løb) {
      const d = "M" + l.ps.map(xy).join(" L");
      f.g += `<path d="${d} L${X(l.ps[l.ps.length - 1].x).toFixed(1)},${bund} L${X(l.ps[0].x).toFixed(1)},${bund} Z" style="fill:${l.c};opacity:.18"/>`;
      f.g += `<path class="line" d="${d}" style="stroke:${l.c}"/>`;
    }
    f.g += `<line class="cross" x1="0" x2="0" y1="${f.T}" y2="${f.H - f.B}" style="opacity:0"/><circle class="pt" r="4" style="display:none"/>`;
    f.svg.innerHTML = f.g;
    const cross = f.svg.querySelector(".cross"), prik = f.svg.querySelector("circle.pt");
    if (zs.length && !egen) prik.style.fill = streg;
    const nærmest = v => { let lo = 0, hi = pts.length - 1; while (hi - lo > 1) { const m = (lo + hi) >> 1; if (pts[m].x < v) lo = m; else hi = m; } return Math.abs(pts[lo].x - v) <= Math.abs(pts[hi].x - v) ? lo : hi; };
    let valgt = pts.length - 1;
    const vis = (i, ev) => {
      valgt = i; const p = pts[i], cx = X(p.x);
      cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.style.opacity = "1";
      prik.setAttribute("cx", cx); prik.setAttribute("cy", f.y(p.y)); prik.style.display = "";
      if (egen) prik.style.fill = p.color || "var(--mark)";
      showTip(p.tip, ev);
    };
    const skjul = () => { cross.style.opacity = "0"; prik.style.display = "none"; hideTip(); };
    f.svg.addEventListener("pointermove", ev => {
      const r = f.svg.getBoundingClientRect(), sx = (ev.clientX - r.left) * f.W / r.width;
      if (sx < f.L || sx > f.W - f.R) return;
      vis(nærmest(opts.fra + (sx - f.L) / bredde * (opts.til - opts.fra)), ev);
    });
    f.svg.addEventListener("pointerleave", () => { if (document.activeElement !== f.svg) skjul(); });
    // Keyboard: arrows one measurement, Page Up/Down one hour, Home/End
    const vælg = i => {
      i = Math.max(0, Math.min(pts.length - 1, i));
      const r = f.svg.getBoundingClientRect(), k = r.width / f.W;
      vis(i, { clientX: r.left + X(pts[i].x) * k, clientY: r.top + f.y(pts[i].y) * k }); oplæs(pts[i].tip);
    };
    f.svg.setAttribute("tabindex", "0");
    f.svg.setAttribute("aria-label", `${f.svg.getAttribute("aria-label") || "Graf"}. Brug piletasterne for at gå gennem målingerne, Page Up og Page Down en time ad gangen.`);
    f.svg.addEventListener("focus", () => vælg(valgt));
    f.svg.addEventListener("blur", skjul);
    f.svg.addEventListener("keydown", ev => {
      const time = nærmest(pts[valgt].x + 60) === valgt ? valgt + 1 : nærmest(pts[valgt].x + 60);
      const i = { ArrowLeft: valgt - 1, ArrowRight: valgt + 1, Home: 0, End: pts.length - 1,
        PageUp: nærmest(pts[valgt].x - 60), PageDown: time }[ev.key];
      if (i != null) { ev.preventDefault(); vælg(i); } else if (ev.key === "Escape") skjul();
    });
    // Only the zones the axis reaches are in the legend
    const nøgle = [...(opts.noegle || []), ...zs.filter(z => z.label && klip(z.hi ?? f.hi) > klip(z.lo ?? f.lo))];
    el.replaceChildren(...(nøgle.length ? [noegle(nøgle)] : []), f.svg);
  }
})();
