// Sprogreglerne som HTML, fælles for Regler (regler.html) og fanen Regler på telefonen (mobil.html).
// Bruger esc og md fra designkittet (liv.js og md.js), som siderne henter først. Reglerne skrives af rutinen
// (sprog.js regel); siderne viser dem bare.
(() => {
  const css = `
  .regler { display: grid; gap: 10px; }
  details.regel { padding: 0; }
  details.regel > summary { list-style: none; display: flex; align-items: center; gap: 10px; padding: 14px 16px; cursor: pointer; color: var(--text-primary); font-size: 15px; margin: 0; }
  details.regel > summary::-webkit-details-marker { display: none; }
  details.regel > summary::after { content: "›"; margin-left: auto; color: var(--text-subdued); font-size: 18px; transition: transform .15s; }
  details.regel[open] > summary::after { transform: rotate(90deg); }
  details.regel .rt { font-weight: 500; }
  details.regel .rind { padding: 0 16px 16px; display: grid; gap: 10px; }
  details.regel .rlbl { font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-top: 4px; }
  details.regel ul { margin: 0; padding: 0; list-style: none; display: grid; gap: 8px; }
  details.regel li { font-size: 14.5px; line-height: 1.45; }
  details.regel li small { display: block; color: var(--text-secondary); font-size: 13px; }
  details.regel li s { color: var(--destructive); text-decoration-thickness: 1px; }
  details.regel li b { font-weight: 500; color: var(--success); }
  details.regel .rfod { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 4px; }`;
  const st = document.createElement("style"); st.textContent = css; document.head.append(st);

  // r: reglen, stemme: sprogets stemme (lang-attribut), opts.aaben: foldet ud, opts.fod: HTML til knapper nederst
  window.regelHTML = (r, stemme, { aaben = false, fod = "" } = {}) => `<details class="card regel" id="regel-${esc(r.id)}"${aaben ? " open" : ""}>
    <summary><span class="rt">${esc(r.titel)}</span>${r.niveau ? `<span class="meta">${esc(r.niveau)}</span>` : ""}</summary>
    <div class="rind">
      <div class="md">${md(r.forklaring)}</div>
      <div class="rlbl">Eksempler</div>
      <ul lang="${esc(stemme || "")}">${r.eksempler.map(e => `<li>${esc(e.tekst)}${e.oversaettelse ? `<small lang="da">${esc(e.oversaettelse)}</small>` : ""}</li>`).join("")}</ul>
      ${r.fejl?.length ? `<div class="rlbl">Typiske fejl</div>
      <ul>${r.fejl.map(f => `<li><s>${esc(f.fejl)}</s> → <b>${esc(f.rettet)}</b>${f.hvorfor ? `<small lang="da">${esc(f.hvorfor)}</small>` : ""}</li>`).join("")}</ul>` : ""}
      ${fod ? `<div class="rfod">${fod}</div>` : ""}
    </div>
  </details>`;

  // Reglerne for ét sprog, nyeste niveau sidst (A1 før A2), inden for niveauet den ældste først
  window.reglerFor = (regler, sprog) => regler.filter(r => r.sprog === sprog)
    .sort((a, b) => String(a.niveau || "").localeCompare(String(b.niveau || "")) || String(a.oprettet).localeCompare(String(b.oprettet)));
})();
