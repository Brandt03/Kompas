// README'ens skærmbilleder af demoen, taget med headless Chrome over DevTools-protokollen (Node 22, ingen pakker).
// Start demoen først (python3 demo/serve.py), og kør så:
//   node demo/skaermbilleder.mjs [http://localhost:8000] [docs/skaermbilleder]
// Chrome findes på macOS' sti; sæt CHROME til en anden. Klokken står på 09.25 i dag, så en forelæsning er i gang
// på I dag. Chrome kører med en midlertidig profil, ikke din egen.
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [BASE = "http://localhost:8000", UD = "docs/skaermbilleder"] = process.argv.slice(2);
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9333;

const nu = new Date(); nu.setHours(9, 25, 0, 0);
const DATO = `(() => { const D = Date, start = ${nu.getTime()}, t0 = D.now();
  class F extends D { constructor(...a) { super(...(a.length ? a : [start + (D.now() - t0)])); } static now() { return start + (D.now() - t0); } }
  globalThis.Date = F; })();`;
const klik = tekst => `[...document.querySelector("iframe").contentDocument.querySelectorAll("button")].find(b => b.textContent.trim() === ${JSON.stringify(tekst)}).click()`;

// navn, adresse, bredde, højde, tema, skala, evt. et klik efter indlæsning
const BILLEDER = [
  ["i-dag", "/", 1440, 1300, "dark"],
  ["i-dag-lys", "/", 1440, 1300, "light"],
  ["forbindelser", "/#/kompas/forbindelser.html", 1440, 1500, "dark"],
  ["studie", "/#/studie/", 1440, 1000, "dark"],
  ["genkald", "/#/studie/genkald.html", 1440, 1000, "dark"],
  ["perioder", "/#/form/perioder.html", 1440, 1000, "dark"],
  ["soevn", "/#/form/soevn.html", 1440, 1000, "dark"],
  ["karriere", "/#/karriere/", 1440, 1000, "dark"],
  ["forbrug", "/#/forbrug/", 1440, 1000, "dark", 1, klik("12 mdr.")],
  ["scenarier", "/#/forbrug/scenarier/", 1440, 1000, "dark"],
  ["su", "/#/forbrug/su/", 1440, 1000, "dark"],
  ["mobil", "/studie/mobil.html", 390, 844, "dark", 2],
];

const vent = ms => new Promise(r => setTimeout(r, ms));
const profil = mkdtempSync(join(tmpdir(), "kompas-skaerm-"));
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profil}`,
  "--no-first-run", "--disable-extensions", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });

try {
  let url;
  for (let i = 0; i < 50 && !url; i++) {
    try { url = (await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json()).webSocketDebuggerUrl; } catch { await vent(200); }
  }
  if (!url) throw new Error(`Chrome svarede ikke (${CHROME})`);
  const ws = new WebSocket(url);
  await new Promise((ok, fejl) => { ws.onopen = ok; ws.onerror = fejl; });
  let id = 0; const svar = new Map();
  ws.onmessage = e => { const m = JSON.parse(e.data); if (svar.has(m.id)) { svar.get(m.id)(m); svar.delete(m.id); } };
  const send = (method, params = {}, sessionId) => new Promise((ok, fejl) => {
    const n = ++id; svar.set(n, m => m.error ? fejl(new Error(`${method}: ${m.error.message}`)) : ok(m.result));
    ws.send(JSON.stringify({ id: n, method, params, sessionId }));
  });

  for (const [navn, sti, w, h, tema, skala = 1, efter] of BILLEDER) {
    const { targetId } = await send("Target.createTarget", { url: "about:blank" });
    const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
    const s = (m, p) => send(m, p, sessionId);
    await s("Page.enable");
    await s("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: skala, mobile: skala > 1 });
    await s("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: tema }] });
    await s("Page.addScriptToEvaluateOnNewDocument", { source: DATO });   // gælder også rammens iframe
    await s("Page.navigate", { url: BASE + sti });
    await vent(4000);
    if (efter) { await s("Runtime.evaluate", { expression: efter }); await vent(1500); }
    const { data } = await s("Page.captureScreenshot", { format: "png", clip: { x: 0, y: 0, width: w, height: h, scale: 1 } });
    writeFileSync(join(UD, `${navn}.png`), Buffer.from(data, "base64"));
    console.log(`${navn}.png`);
    await send("Target.closeTarget", { targetId });
  }
  ws.close();
} finally {
  const lukket = new Promise(r => chrome.once("exit", r));
  chrome.kill();
  await lukket;
  rmSync(profil, { recursive: true, force: true });
}
