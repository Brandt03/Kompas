// Sprog: kommandoerne, Dagens kort og serveren på en midlertidig datamappe med egen port; de rigtige svar røres ikke.
//   node tests/test_sprog.js
"use strict";
const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn, execFileSync } = require("child_process");

const ROD = path.join(__dirname, "..", "sprog");
const data = fs.mkdtempSync(path.join(os.tmpdir(), "sprog-test-"));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "sprog-test-ind-"));
process.env.SPROG_DATA = data;
// Studies eksport med eksamensdatoerne: en falsk fil, som testene skriver selv (ingen eksamen til at begynde med)
const studieJson = path.join(tmp, "studie.json");
const eksamen = (dage, ekstra = {}) => { const d = new Date(); d.setDate(d.getDate() + dage);
  fs.writeFileSync(studieJson, JSON.stringify({ deadlines: [{ type: "eksamen", fag: "Alfa", dato: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`, ...ekstra }] })); };
fs.writeFileSync(studieJson, JSON.stringify({ deadlines: [] }));
process.env.SPROG_STUDIE_JSON = studieJson;
const K = require(path.join(ROD, "kerne.js"));
const PORT = 18769;
const env = { ...process.env, SPROG_DATA: data, SPROG_PORT: String(PORT), HOME: tmp };

const cli = (...a) => JSON.parse(execFileSync(process.execPath, [path.join(ROD, "sprog.js"), ...a], { env, encoding: "utf8" }));
const cliFejl = (...a) => { try { execFileSync(process.execPath, [path.join(ROD, "sprog.js"), ...a], { env, encoding: "utf8", stdio: "pipe" }); } catch (e) { return e.stderr; } assert.fail(`forventede fejl: ${a.join(" ")}`); };
const fil = (navn, v) => { const f = path.join(tmp, navn); fs.writeFileSync(f, typeof v === "string" ? v : JSON.stringify(v)); return f; };
const frase = (sprog, forside, ekstra = {}) => ({ sprog, type: "frase", forside, bagside: `${forside} (${sprog})`, kilde: "test", ...ekstra });

let ok = 0;
async function test(navn, fn) { await fn(); ok++; console.log(`ok  ${navn}`); }

(async () => {
  await test("tilfoej: id'er pr. sprog, dubletter springes over, ugyldige kort gemmer intet", () => {
    let r = cli("tilfoej", fil("a.json", [frase("es", "Kan vi få regningen?", { situation: "restaurant" }), frase("es", "Hvor er stationen?"), frase("de", "Godmorgen")]));
    assert.deepStrictEqual(r.tilfoejet, ["es-0001", "es-0002", "de-0001"]);
    r = cli("tilfoej", fil("b.json", [frase("es", "kan vi få regningen"), frase("es", "Jeg vil gerne have en kaffe")]));
    assert.deepStrictEqual(r.tilfoejet, ["es-0003"]);
    assert.strictEqual(r.sprunget_over[0].grund, "findes allerede");
    assert.match(cliFejl("tilfoej", fil("c.json", [frase("es", "Ny"), { sprog: "fr", type: "frase", forside: "x", bagside: "y", kilde: "t" }])), /kort 2: ukendt sprog/);
    assert.strictEqual(K.kortListe().length, 4);
  });

  await test("Dagens kort: nye pr. sprog efter nye_pr_dag, det aktive sprog først", () => {
    // es: 3 nye om dagen, de: 1 (STANDARD)
    cli("tilfoej", fil("d.json", [frase("es", "En"), frase("es", "To"), frase("de", "Drei")]));
    const r = K.repetition();
    assert.deepStrictEqual(r.kort.map(k => k.id), ["es-0001", "es-0002", "es-0003", "de-0001"]);
    assert.strictEqual(r.statistik.sprog.es.nye_venter, 5);
    assert.strictEqual(r.kort[0].opgave, "Sig det på spansk");
  });

  await test("niveautesten kommer først, uden loft, og kun én gang", () => {
    cli("tilfoej", fil("t.json", [1, 2, 3, 4, 5].map(i => ({ sprog: "es", type: "test", niveau: "A1", forside: `Test ${i}`, bagside: `Prueba ${i}`, kilde: "niveautest" }))));
    let r = K.repetition();
    assert.deepStrictEqual(r.kort.slice(0, 5).map(k => k.type), ["test", "test", "test", "test", "test"]);
    const t1 = r.kort[0].id;
    K.gemSvar({ id: t1, karakter: 1, svar: "no sé" });
    r = K.repetition();
    assert.ok(!r.kort.some(k => k.id === t1), "et besvaret testkort kommer ikke igen");
    assert.strictEqual(r.statistik.sprog.es.test_tilbage, 4);
    // Testkort tæller ikke med i dagens nye
    assert.strictEqual(r.kort.filter(k => k.sprog === "es" && k.type === "frase").length, 3);
  });

  await test("repetition: et svar i går med 'sad' er ikke forfaldent i dag; blankt for 3 dage siden er", () => {
    const igår = new Date(Date.now() - K.DAG).toISOString(), for3 = new Date(Date.now() - 3 * K.DAG).toISOString();
    fs.appendFileSync(K.FIL.log, JSON.stringify({ tid: igår, type: "svar", id: "es-0001", karakter: 3 }) + "\n");
    fs.appendFileSync(K.FIL.log, JSON.stringify({ tid: for3, type: "svar", id: "es-0002", karakter: 1 }) + "\n");
    const r = K.repetition(), ids = r.kort.map(k => k.id);
    assert.ok(!ids.includes("es-0001"));
    assert.ok(ids.includes("es-0002"));
    assert.strictEqual(r.kort.find(k => k.id === "es-0002").ny, false);
    // es-0001 og es-0002 er taget før i dag, så der er stadig 3 nye spanske i dag
    assert.strictEqual(r.kort.filter(k => k.sprog === "es" && k.ny && k.type === "frase").length, 3);
  });

  await test("tekst og feedback: feedback kræver et svar", () => {
    const t = fil("tekst.json", { sprog: "es", niveau: "A2", titel: "En el mercado", tekst: "Hola. Compro **fruta**.", ord: [{ ord: "fruta", betydning: "frugt" }], spoergsmaal: ["¿Qué compras?"] });
    const r = cli("tekst", t, "--uge", "2026-W43");
    assert.strictEqual(r.uge, "2026-W43");
    assert.match(cliFejl("tekst", t, "--uge", "2026-W43"), /allerede en tekst/);
    assert.match(cliFejl("feedback", "2026-W43", fil("fb.md", "Godt!")), /intet svar/);
    K.gemTekstSvar({ uge: "2026-W43", tekst: "Compro manzanas." });
    cli("feedback", "2026-W43", fil("fb.md", "**Godt.** Husk accent."));
    const x = K.tekster()[0];
    assert.strictEqual(x.svar.tekst, "Compro manzanas.");
    assert.strictEqual(x.feedback.tekst, "**Godt.** Husk accent.");
    assert.throws(() => K.gemTekstSvar({ uge: "2026-W44", tekst: "x" }), /ukendt uge/);
  });

  await test("niveau og aktivt sprog", () => {
    assert.match(cliFejl("niveau", "es", "B7", "x"), /niveauet skal være/);
    assert.match(cliFejl("niveau", "es", "A2"), /begrundelse/);
    cli("niveau", "es", "A2", "testen: A1 sad, A2 halvt");
    assert.strictEqual(K.sprogTilstand().sprog.es.niveau, "A2");
    assert.match(cliFejl("aktivt", "da"), /kun spansk og tysk/);
    cli("aktivt", "de");
    const S = K.sprogTilstand();
    assert.strictEqual(S.aktivt, "de");
    assert.deepStrictEqual([S.sprog.de.rolle, S.sprog.de.nye_pr_dag, S.sprog.es.rolle, S.sprog.es.nye_pr_dag], ["aktiv", 3, "vedligehold", 1]);
    assert.strictEqual(K.repetition().kort[0].sprog, "de");
    cli("aktivt", "es");
  });

  await test("pause: ingen nye kort; aktivt kan tage sproget op igen", () => {
    assert.match(cliFejl("rolle", "es", "pause"), /ikke er aktivt/);
    assert.match(cliFejl("rolle", "de", "aktiv"), /vedligehold eller pause/);
    cli("rolle", "de", "pause");
    assert.deepStrictEqual([K.sprogTilstand().sprog.de.rolle, K.sprogTilstand().sprog.de.nye_pr_dag], ["pause", 0]);
    assert.ok(!K.repetition().kort.some(k => k.sprog === "de" && k.ny));
    cli("aktivt", "de");
    assert.strictEqual(K.sprogTilstand().sprog.de.rolle, "aktiv");
    cli("aktivt", "es");
    cli("rolle", "de", "vedligehold");
    assert.strictEqual(K.sprogTilstand().sprog.de.nye_pr_dag, 1);
  });

  await test("eksamensperiode: ingen nye kort fra 14 dage før en eksamen til og med dagen", () => {
    const nye = () => K.repetition().kort.filter(k => k.ny && k.type !== "test").length;
    assert.ok(nye() > 0);
    eksamen(15);
    assert.ok(nye() > 0, "15 dage før: ikke endnu");
    eksamen(14);
    assert.strictEqual(nye(), 0);
    assert.deepStrictEqual(K.repetition().statistik.eksamensperiode.fag, "Alfa");
    assert.ok(K.repetition().kort.some(k => !k.ny), "gentagelsen fortsætter");
    eksamen(0);
    assert.strictEqual(nye(), 0, "på eksamensdagen");
    // Rapporten skriver til næste uge: en eksamen 20 dage fremme giver eksamensperiode i den uge, uanset ugedag i dag
    eksamen(20);
    assert.strictEqual(cli("rapport").eksamener_inden_for_14_dage.length, 1);
    eksamen(-1);
    assert.ok(nye() > 0, "dagen efter");
    eksamen(3, { faerdig: "2026-10-01" });
    assert.ok(nye() > 0, "en eksamen markeret færdig tæller ikke");
    fs.writeFileSync(studieJson, "ikke json");
    assert.ok(nye() > 0, "ulæselig eksport: ingen eksamensperiode");
    assert.strictEqual(cli("rapport").eksamener_kendt, false);
    eksamen(5);
    const r = cli("rapport");
    assert.strictEqual(r.eksamener_inden_for_14_dage[0].fag, "Alfa");
    fs.writeFileSync(studieJson, JSON.stringify({ deadlines: [] }));
  });

  await test("regler: gemmes med sprog i id'et, kort peger på dem og kommer først blandt de nye", () => {
    const g = { sprog: "es", id: "ser-estar", niveau: "A1", titel: "ser og estar", forklaring: "**ser**: hvad noget er. **estar**: hvor og hvordan.",
      eksempler: [{ tekst: "Soy de Dinamarca.", oversaettelse: "Jeg er fra Danmark." }], fejl: [{ fejl: "Soy cansado", rettet: "Estoy cansado", hvorfor: "en tilstand" }], kilde: "test" };
    assert.strictEqual(cli("regel", fil("g.json", g)).gemt, "es-ser-estar");
    assert.match(cliFejl("regel", fil("g.json", g)), /findes allerede/);
    cli("regel", fil("g.json", { ...g, titel: "ser og estar (rettet)" }), "--erstat");
    assert.strictEqual(K.reglerListe()[0].titel, "ser og estar (rettet)");
    assert.match(cliFejl("regel", fil("g2.json", { ...g, id: "Ser Estar" })), /id skal være/);
    assert.match(cliFejl("tilfoej", fil("u.json", [{ sprog: "es", type: "udfyld", forside: "Yo soy cansado.", bagside: "x", kilde: "t" }])), /___/);
    assert.match(cliFejl("tilfoej", fil("u.json", [{ sprog: "da", type: "udfyld", forside: "Det ___ fint.", bagside: "x", regel: "es-ser-estar", kilde: "t" }])), /ukendt regel for da/);
    const r = cli("tilfoej", fil("u.json", [{ sprog: "es", type: "udfyld", forside: "Hoy ___ cansado. (estar)", bagside: "Hoy estoy cansado.", regel: "es-ser-estar", kilde: "t" }]));
    const id = r.tilfoejet[0];
    const nye = K.repetition().kort.filter(k => k.sprog === "es" && k.ny && k.type !== "test");
    assert.strictEqual(nye[0].id, id, "kortet til reglen kommer først blandt de nye");
    assert.strictEqual(nye[0].regel, "es-ser-estar");
    assert.strictEqual(nye[0].opgave, "Sæt det manglende ind");
    const p = K.pakke();
    assert.strictEqual(p.sidst_svar, K.logPoster().filter(x => ["svar", "tekst-svar"].includes(x.type)).at(-1).tid, "dit seneste svar, til I dag");
    assert.strictEqual(p.regler.length, 1);
    assert.deepStrictEqual(p.regelkort.map(k => k.id), [id]);
    assert.strictEqual(cli("rapport").regler[0].kort, 1);
  });

  await test("rapport: ugens svar med kortet, niveautesten og svære kort", () => {
    const r = cli("rapport");
    assert.strictEqual(r.aktivt, "es");
    assert.ok(r.ugens_svar.some(s => s.id === "es-0002" && s.karakter === 1 && s.bagside));
    assert.strictEqual(r.niveautest.es.kort, 5);
    assert.strictEqual(r.niveautest.es.besvaret, 1);
    assert.strictEqual(r.niveautest.es.svar[0].svar, "no sé");
    assert.ok(r.tekster.some(t => t.uge === "2026-W43" && t.feedback === "skrevet"));
  });

  // ── serveren ──
  const srv = spawn(process.execPath, [path.join(ROD, "server.js")], { env, stdio: ["ignore", "pipe", "pipe"] });
  let srvLog = ""; srv.stdout.on("data", d => srvLog += d); srv.stderr.on("data", d => srvLog += d);
  try {
    for (let i = 0; i < 50 && !srvLog.includes("lytter"); i++) await new Promise(r => setTimeout(r, 100));
    const url = `http://127.0.0.1:${PORT}`;
    const post = (sti, krop, origin = "https://kompas.localhost") => fetch(url + sti, { method: "POST", headers: { "Content-Type": "application/json", Origin: origin }, body: JSON.stringify(krop) });

    await test("server: sider, manifest og pakke", async () => {
      let r = await fetch(`${url}/sprog/`);
      assert.strictEqual(r.status, 200);
      assert.match(await r.text(), /<title>Sprog · Oversigt<\/title>/);
      assert.strictEqual((await fetch(`${url}/sprog/mobil.html`)).status, 200);
      assert.strictEqual((await fetch(`${url}/sprog/../kerne.js`)).status, 404);
      assert.strictEqual((await fetch(`${url}/sprog/%2e%2e%2fkerne.js`)).status, 404);
      const m = await (await fetch(`${url}/sprog/kompas.json`)).json();
      assert.strictEqual(m.omraade, "Sprog");
      assert.strictEqual(m.sider[0].nyt, "2026-W43-feedback");
      assert.strictEqual(m.sider[2].titel, "Regler");
      assert.ok(m.sider[2].nyt, "en ny regel giver en prik i menuen");
      assert.strictEqual((await fetch(`${url}/sprog/regler.html`)).status, 200);
      assert.strictEqual((await fetch(`${url}/sprog/regel.js`)).status, 200);
      assert.strictEqual((await (await fetch(`${url}/sprog/api/regler`)).json()).length, 1);
      const p = await (await fetch(`${url}/sprog/api/pakke`)).json();
      assert.ok(p.kort.length && p.kort[0].bagside);
    });

    await test("server: kun Kompas må skrive, og kun kendte værter", async () => {
      assert.strictEqual((await post("/sprog/api/svar", { id: "es-0003", karakter: 3 }, "https://ond.example")).status, 403);
      // fetch sender ikke en anden Host, så her bruges http direkte
      const kode = await new Promise((ok, nej) => require("http").get({ host: "127.0.0.1", port: PORT, path: "/sprog/api/pakke", headers: { Host: "ond.example" } }, r => { r.resume(); ok(r.statusCode); }).on("error", nej));
      assert.strictEqual(kode, 403);
      assert.strictEqual((await post("/sprog/api/svar", { id: "findes-ikke", karakter: 3 })).status, 400);
      assert.strictEqual((await post("/sprog/api/svar", { id: "es-0003", karakter: 3, svar: "Quiero un café" })).status, 200);
    });

    await test("server: sync gemmer hver post én gang med dit tidspunkt", async () => {
      const tid = new Date(Date.now() - 36e5).toISOString();
      const poster = [{ id: "abcdefgh-1", type: "svar", tid, data: { id: "de-0001", karakter: 4, svar: "Guten Morgen" } },
        { id: "abcdefgh-2", type: "svar", tid, data: { id: "xx", karakter: 4 } }];
      let r = await (await post("/sprog/api/sync", { poster })).json();
      assert.deepStrictEqual(r.resultater.map(x => x.ok), [true, false]);
      await new Promise(ok => setTimeout(ok, 50));
      assert.match(srvLog, /sync: 1 af 2 poster afvist/, "en afvist post fra telefonen står i loggen");
      r = await (await post("/sprog/api/sync", { poster: poster.slice(0, 1) })).json();
      assert.strictEqual(r.resultater[0].allerede, true);
      const gemt = K.logPoster().filter(p => p.sync_id === "abcdefgh-1");
      assert.strictEqual(gemt.length, 1);
      assert.strictEqual(gemt[0].tid, tid);
    });

    await test("ny tekst efter feedback: feedbacken på ugen før står forrest, til den nye er besvaret", async () => {
      const nyt = async () => (await (await fetch(`${url}/sprog/kompas.json`)).json()).sider[0].nyt;
      const pk = async () => (await fetch(`${url}/sprog/api/pakke`)).json();
      assert.strictEqual((await pk()).ny_feedback, null, "feedbacken er på den nyeste tekst");
      cli("tekst", fil("tekst2.json", { sprog: "es", niveau: "A2", titel: "En la estación", tekst: "Hola.", spoergsmaal: ["¿Adónde vas?"] }), "--uge", "2026-W44");
      let p = await pk();
      assert.strictEqual(p.ny_feedback.uge, "2026-W43");
      assert.strictEqual(p.ny_feedback.titel, "En el mercado");
      assert.ok(p.tekster.find(t => t.uge === "2026-W43").feedback, "feedbacken er med i pakken");
      assert.strictEqual(await nyt(), "2026-W44+2026-W43-feedback", "prikken kommer med den nye tekst og feedbacken");
      assert.strictEqual((await post("/sprog/api/tekst-svar", { uge: "2026-W44", tekst: "Voy a Madrid." })).status, 200);
      p = await pk();
      assert.strictEqual(p.ny_feedback, null, "den nye tekst er besvaret");
      assert.strictEqual(await nyt(), "2026-W44+2026-W43-feedback", "dit eget svar giver ingen prik");
    });
  } finally {
    srv.kill();
  }
  fs.rmSync(data, { recursive: true, force: true });
  fs.rmSync(tmp, { recursive: true, force: true });
  console.log(`\n${ok} tests ok`);
})().catch(e => { console.error(e); process.exit(1); });
