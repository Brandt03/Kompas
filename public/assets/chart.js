// Small SVG charts for the projects' pages, in Sure's style: thin marks, recessive grid, hover tooltip.
// One series per chart (no dual axes). Needs page.css (.chart-tip) and tokens.css.
//   barChart(el, { points: [{ label, y, tip }], ref: { y, label }, fmt, height })
//   lineChart(el, { points: [{ label, y, tip }], band: { lo, hi, label }, ref: { y, label }, fmt, height })
// A point with y == null is a gap (no measurement), never a zero.
(function () {
  const NS = "http://www.w3.org/2000/svg";
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

  function frame(el, points, opts, extra = []) {
    const W = Math.max(280, el.clientWidth || 600), H = opts.height || 200;
    const L = 36, R = 8, T = 10, B = 22;
    const ys = points.map(p => p.y).filter(v => v != null).concat(extra);
    let lo = opts.min ?? Math.min(...ys), hi = Math.max(...ys);
    if (opts.min == null) lo = Math.floor(lo - (hi - lo) * 0.15);
    hi = hi + (hi - lo) * 0.08 || 1;
    const x = i => L + (i + 0.5) * (W - L - R) / points.length;
    const y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo || 1));
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("class", "chart");
    svg.setAttribute("role", "img"); if (opts.label) svg.setAttribute("aria-label", opts.label);
    let g = "";
    const ticks = 3;
    for (let i = 0; i <= ticks; i++) {
      const v = lo + (hi - lo) * i / ticks, yy = y(v);
      g += `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" class="grid"/>`;
      g += `<text x="${L - 6}" y="${yy + 4}" text-anchor="end">${(opts.fmt || String)(v)}</text>`;
    }
    const every = Math.ceil(points.length / 7);
    points.forEach((p, i) => { if (i % every === 0) g += `<text x="${x(i)}" y="${H - 5}" text-anchor="middle">${p.label}</text>`; });
    return { svg, W, H, L, R, T, B, x, y, lo, hi, g };
  }

  function hover(f, points, el) {
    const step = (f.W - f.L - f.R) / points.length;
    let g = "";
    points.forEach((p, i) => { g += `<rect class="hit" data-i="${i}" x="${f.L + i * step}" y="${f.T}" width="${step}" height="${f.H - f.T - f.B}"/>`; });
    f.g += `<line class="cross" x1="0" x2="0" y1="${f.T}" y2="${f.H - f.B}" style="opacity:0"/>` + g;
    f.svg.innerHTML = f.g;
    const cross = f.svg.querySelector(".cross");
    f.svg.addEventListener("pointermove", ev => {
      const r = ev.target.closest(".hit"); if (!r) return;
      const i = +r.dataset.i, cx = f.x(i);
      cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.style.opacity = "1";
      showTip(points[i].tip, ev);
    });
    f.svg.addEventListener("pointerleave", () => { cross.style.opacity = "0"; hideTip(); });
    el.replaceChildren(f.svg);
  }

  window.barChart = function (el, opts) {
    const pts = opts.points, f = frame(el, pts, { ...opts, min: 0 }, opts.ref ? [opts.ref.y] : []);
    const bw = Math.max(2, Math.min(14, (f.W - f.L - f.R) / pts.length - 3));
    pts.forEach((p, i) => {
      if (p.y == null) return;
      const top = f.y(p.y), base = f.y(0), h = Math.max(1, base - top), r = Math.min(4, bw / 2, h);
      const x0 = f.x(i) - bw / 2;
      f.g += `<path class="bar${p.dim ? " dim" : ""}" d="M${x0},${base} V${top + r} q0,-${r} ${r},-${r} H${x0 + bw - r} q${r},0 ${r},${r} V${base} Z"/>`;
    });
    if (opts.ref) {
      const yy = f.y(opts.ref.y);
      f.g += `<line x1="${f.L}" x2="${f.W - f.R}" y1="${yy}" y2="${yy}" class="ref"/><text x="${f.W - f.R}" y="${yy - 5}" text-anchor="end" class="ref-label">${opts.ref.label}</text>`;
    }
    hover(f, pts, el);
  };

  window.lineChart = function (el, opts) {
    const pts = opts.points, band = opts.band;
    const f = frame(el, pts, opts, [...(band ? [band.lo, band.hi] : []), ...(opts.ref ? [opts.ref.y] : [])]);
    if (band) {
      const y1 = f.y(band.hi), y2 = f.y(band.lo);
      f.g += `<rect class="band" x="${f.L}" y="${y1}" width="${f.W - f.L - f.R}" height="${Math.max(1, y2 - y1)}" rx="4"/>`;
      if (band.label) f.g += `<text x="${f.W - f.R - 6}" y="${y1 + 13}" text-anchor="end" class="ref-label">${band.label}</text>`;
    }
    if (opts.ref) {
      const yy = f.y(opts.ref.y);
      f.g += `<line x1="${f.L}" x2="${f.W - f.R}" y1="${yy}" y2="${yy}" class="ref"/><text x="${f.W - f.R}" y="${yy - 5}" text-anchor="end" class="ref-label">${opts.ref.label}</text>`;
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
  };
})();
