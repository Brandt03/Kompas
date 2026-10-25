// I dag (public/index.html) og latestReview/reviewKilde i public/assets/liv.js. Sidens script køres i en tom browser-attrap
// med designkittets icons.js og liv.js, ligesom browseren henter dem.
//   node tests/test_i_dag.js
"use strict";
process.env.TZ = "Europe/Copenhagen";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const PUBLIC = path.join(__dirname, "..", "public");
const elementer = {};
const element = id => elementer[id] ??= { id, innerHTML: "" };
const kontekst = vm.createContext({
  Date, Intl, Math, JSON, Promise, console: { ...console, error: () => {} },
  document: { getElementById: element, querySelectorAll: () => [] },
  fetch: () => Promise.reject(new Error("ingen net i testen")),
  requestAnimationFrame: () => {}, setInterval: () => 0,
});
for (const f of ["assets/icons.js", "assets/liv.js"]) vm.runInContext(fs.readFileSync(path.join(PUBLIC, f), "utf8"), kontekst);
const side = fs.readFileSync(path.join(PUBLIC, "index.html"), "utf8");
vm.runInContext(side.match(/<script>([\s\S]*?)<\/script>/)[1], kontekst);
const [latestReview, reviewKilde, render, iso, addDays] = ["latestReview", "reviewKilde", "render", "iso", "addDays"].map(n => vm.runInContext(n, kontekst));

let fejl = 0;
const tjek = (navn, ok, detalje = "") => { if (!ok) { fejl++; console.log("FEJL", navn, detalje); } };

// ── latestReview: det nyeste review med tekst ──
const snapshot = { uge: "2026-W41", tekst: null };
const w40 = { uge: "2026-W40", tekst: { en_ting: "Læs før forelæsningen" } };
const w39 = { uge: "2026-W39", tekst: { en_ting: "Gå i seng før midnat" } };
tjek("springer snapshot uden tekst over", latestReview({ reviews: [w39, snapshot, w40] }) === w40);
tjek("vælger på uge, ikke rækkefølge", latestReview({ reviews: [w40, w39] }) === w40);
tjek("kun snapshots giver null", latestReview({ reviews: [snapshot] }) === null);
tjek("ingen reviews giver null", latestReview({}) === null && latestReview(null) === null);

// ── reviewKilde: "Skrevet <dato>" når `genereret` findes, " · metode <metode>" kun når `metode` findes ──
const ny = { uge: "2026-W41", tekst: { en_ting: "Sov otte timer" }, metode: "2026-10-08", genereret: "2026-10-12T00:25:32+02:00" };
tjek("nyt review: dato og metode", reviewKilde(ny) === "Skrevet 12. okt. · metode 2026-10-08", reviewKilde(ny));
tjek("offset: datoen er de første 10 tegn (lokal dato)", reviewKilde({ ...ny, genereret: "2026-10-12T00:25:32+05:00" }) === "Skrevet 12. okt. · metode 2026-10-08");
const gammel = { ...w40, genereret: "2026-10-07T11:32:46" };
tjek("gammelt review uden tidszone og metode: kun dato", reviewKilde(gammel) === "Skrevet 7. okt.", reviewKilde(gammel));
tjek("review uden felterne: intet", reviewKilde(w40) === "" && reviewKilde(null) === "");
tjek("ulæseligt tidspunkt: kun metode", reviewKilde({ ...ny, genereret: "ikke en dato" }) === "metode 2026-10-08");

// ── render: en fejlende sektion koster kun sig selv ──
const root = () => element("root").innerHTML;
const imorgen = iso(addDays(new Date(), 1));
const studie = deadlines => ({ fag: [], deadlines });
// Genkald-kortet er en anden sektion, der skal blive stående, når en sektion fejler
const genkald = { statistik: { klaret_i_dag: 0, laert: 1, i_alt: 2, minutter: 1 }, kort: [] };

render({ studie: studie([{ dato: imorgen, type: "aflevering", fag: "Alfa" }]), genkald });   // frist uden `hvad`
tjek("defekt frist: siden er ikke tom", /class="hello"/.test(root()), root());
tjek("defekt frist: beskeden nævner Frister", /Frister kunne ikke vises/.test(root()), root());
tjek("defekt frist: Genkald vises stadig", /href="\/studie\/genkald\.html#idag"/.test(root()));

render({ studie: studie([{ dato: imorgen, type: "aflevering", fag: "Alfa", hvad: "Alfa-opgaven" }]), genkald });
tjek("hel frist: vises", /<h2>Frister<\/h2>/.test(root()) && /Alfa-opgaven/.test(root()));
tjek("hel frist: ingen fejlbesked", !/kunne ikke vises/.test(root()));

// ── Står stille: kun når der venter noget, og grænsen er nået ──
const før = n => addDays(new Date(), -n).toISOString();
render({ studie: studie([]), sprog: { kort: [{}], sidst_svar: før(8) },
  genkald: { kort: [{}], statistik: { sidst_svar: før(1) } },
  skaermtid: { enheder: [{ navn: "Mac", kendt: true, sidst: før(0) }, { navn: "Stationær", kendt: true, sidst: før(3) }, { navn: "Ukendt", kendt: false, sidst: før(9) }, { navn: "Tablet", kendt: true, sjaelden: true, sidst: før(9) }] } });
tjek("står stille: Sprog efter 8 dage", /Sprog · 8 d/.test(root()), root());
tjek("står stille: Stationær efter 3 dage", /Stationær · 3 d/.test(root()));
tjek("står stille: Genkald i går er ikke stille", !/Genkald · /.test(root()));
tjek("står stille: Mac i dag, ukendt og sjælden enhed vises ikke", !/Mac · |Ukendt · |Tablet · /.test(root()));
render({ studie: studie([]), sprog: { kort: [], sidst_svar: før(30) }, genkald: { kort: [], statistik: { sidst_svar: før(30) } } });
tjek("står stille: intet venter, ingen linje", !/Står stille/.test(root()), root());

// ── Skal tjekkes: forbindelser med fejl eller advarsel fra forbindelser.json, fejl først ──
const forbindelser = { grupper: [
  { titel: "Claude", punkter: [{ navn: "Sprog", type: "Claude-rutine", status: "advarsel", tekst: "nye sprogkort og ugens tekst · slået fra" }, { navn: "Studie", type: "Claude-rutine", status: "ok", tekst: "køreplan" }] },
  { titel: "Kører i baggrunden", punkter: [{ navn: "Sprog-server", type: "LaunchAgent", status: "fejl", tekst: "svarer ikke" }, { navn: "Canvas", type: "downloads", status: "info", tekst: "sorteres" }] }],
  vaerktoejer: [{ navn: "Caddy", status: "ok", til: "Kompas" }, { navn: "Git", status: "fejl", til: "versionering" }] };
render({ studie: studie([]), genkald, forbindelser });
const tjekLinje = (root().match(/Skal tjekkes:<\/span>(.*?)<\/div>/) || [, ""])[1];
tjek("skal tjekkes: fejl og advarsler, fejl først", (tjekLinje.match(/>([^<]+)<\/a>/g) || []).join("") === ">Sprog-server</a>>Git</a>>Rutinen Sprog</a>", tjekLinje);
tjek("skal tjekkes: fejl er røde, og alle linker til Forbindelser", /class="badge bad" href="\/kompas\/forbindelser\.html" title="Kører i baggrunden: svarer ikke"/.test(tjekLinje) && /class="badge" href="\/kompas\/forbindelser\.html" title="Claude: nye sprogkort og ugens tekst · slået fra"/.test(tjekLinje), tjekLinje);
tjek("skal tjekkes: ok og info vises ikke", !/Studie<|Canvas|Caddy/.test(tjekLinje), tjekLinje);
render({ studie: studie([]), genkald, forbindelser: { grupper: [{ titel: "Claude", punkter: [{ navn: "Studie", type: "Claude-rutine", status: "ok" }] }], vaerktoejer: [] } });
tjek("skal tjekkes: alt virker, ingen linje", !/Skal tjekkes/.test(root()), root());
render({ studie: studie([]), genkald });
tjek("skal tjekkes: uden forbindelser.json, ingen linje og ingen fejl", !/Skal tjekkes/.test(root()) && !/kunne ikke vises/.test(root()), root());

// ── Dagen: planlagt mod faktisk under blokke, der er begyndt; tallene står, som overblik har regnet dem ──
{
  const dagsplan = [{ dato: iso(new Date()), plan: [
    { start: `${iso(new Date())}T00:00`, titel: "Gamma · Aflevering 2", plan: true, faktisk: { minutter: 120, skaerm: { Produktiv: 45, Passiv: 30 }, uden_skaerm: 45, selvstudie: 0, traening: 0 } },
    { start: `${iso(new Date())}T00:00`, titel: "Tandlæge", plan: false, faktisk: { minutter: 60, skaerm: {}, uden_skaerm: 60, selvstudie: 0, traening: 0 } },
    { start: `${iso(new Date())}T23:58`, titel: "Senere", plan: true, faktisk: { minutter: 1, skaerm: null, uden_skaerm: null, selvstudie: 0, traening: 0 } }] }];
  const coach = { kalender: { dage: [{ dato: iso(new Date()), program: [{ tid: "00:00–00:01", titel: "Gamma · Aflevering 2 færdig" }, { tid: "23:58–23:59", titel: "Senere" }] }] } };
  render({ coach, studie: studie([]), liv: { dagsplan } });
  const ag = element("agenda").innerHTML;
  tjek("faktisk: blokken med samme start og titel, i overbliks rækkefølge", /(Faktisk|Indtil nu): 45 min produktiv · 30 min passiv · 45 min uden skærm · intet selvstudie logget/.test(ag), ag);
  tjek("faktisk: en blok, der ikke er begyndt, eller uden skærmtid, får ingen linje", (ag.match(/class="fakt"/g) || []).length === 1, ag);
  render({ coach, studie: studie([]) });
  tjek("faktisk: uden liv.json vises programmet uden linjen", /Gamma · Aflevering 2 færdig/.test(element("agenda").innerHTML) && !/class="fakt"/.test(element("agenda").innerHTML), element("agenda").innerHTML);
}

// ── Genkald: ulæste uger pr. fag fra Studie-serveren, sammenhængende uger som et spænd ──
render({ studie: studie([]), genkald: { kort: [{}], statistik: { klaret_i_dag: 0, laert: 0, i_alt: 134, minutter: 19, nye_venter_paa_laesning: 65,
  ulaeste_uger: [{ fag: "alfa", navn: "Alfa", uger: [38, 39, 40, 41], spoergsmaal: 39 }, { fag: "beta", navn: "Beta", uger: [37, 39], spoergsmaal: 26 }] } } });
tjek("ulæste uger: pr. fag med spænd", /<b>Ulæste uger:<\/b> Alfa 38–41 · Beta 37, 39\. 65 spørgsmål venter/.test(root()), root());
render({ studie: studie([]), genkald: { kort: [], statistik: { klaret_i_dag: 0, laert: 0, i_alt: 1, minutter: 1, nye_venter_paa_laesning: 0, ulaeste_uger: [] } } });
tjek("ulæste uger: ingen, ingen linje", !/Ulæste uger/.test(root()), root());

const glippede = vis => ({ glippede: { dage: 3, graense: 2, vis, glippet: [{ dato: "2026-10-16", blokke: 3 }, { dato: "2026-10-17", blokke: 3 }] } });
render({ studie: studie([]), genkald, liv: glippede(true) });
tjek("glippede studieblokke: vises med antal og datoer", /Studieblokke · 2 af 3 d/.test(root()) && /\(16\.10\., 17\.10\.\)/.test(root()) && /href="\/form\/uge\.html"/.test(root()), root());
render({ studie: studie([]), genkald, liv: glippede(false) });
tjek("glippede studieblokke: kun når overblik siger vis", !/Studieblokke/.test(root()), root());
render({ studie: studie([]), genkald, liv: { reviews: [] } });
tjek("glippede studieblokke: liv.json uden feltet", !/Studieblokke/.test(root()) && !/kunne ikke vises/.test(root()), root());

render({ studie: studie([{ dato: imorgen, type: "aflevering", fag: "Alfa", hvad: "<strong>Alfa-præsentation</strong> (Q&amp;A)" }]), genkald });
tjek("frist skrevet som HTML: escapes én gang", /Alfa-præsentation \(Q&amp;A\)/.test(root()) && !/&amp;amp;/.test(root()), root());

render({ studie: studie([]), genkald, coach: { restitution: { flag: "ikke en liste" } } });
tjek("defekt coach: felterne nævnes", /Søvn, ugen og skærmtid kunne ikke vises/.test(root()), root());
tjek("defekt coach: Genkald vises stadig", /href="\/studie\/genkald\.html#idag"/.test(root()));

// ── Felterne: ugens træning og selvstudie fra overblik, dagens skærmtid; uden coach vises resten stadig ──
const idag = iso(new Date()), igaar = iso(addDays(new Date(), -1));
const liv = { studieuge: { mandag: "2026-10-19", planlagt_timer: 12.83, planlagt_blokke: 9, selvstudie_timer: 1.4, selvstudie_dage: 1 },
              uger: [{ mandag: "2026-10-12", traening_timer: 3, traening_pas: 3 }, { mandag: "2026-10-19", traening_timer: 1.5, traening_pas: 2 }] };
const skaermtid = { perioder: { idag: { fra: idag, timer: 1.37, grupper: { Passiv: 0.62 } } }, dage: [{ dato: igaar, timer: 7.12, sen_timer: 0.5 }] };
render({ liv, skaermtid });
const felt = navn => (root().match(new RegExp(`${navn}</span>.*?</a>`)) || [""])[0].replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/\s+/g, " ");
tjek("træning: ugens timer og pas", felt("Træning i ugen") === "Træning i ugen 1 t 30 min 2 pas ", felt("Træning i ugen"));
tjek("selvstudie: mod planlagte blokke, antallet står i teksten", felt("Selvstudie i ugen") === "Selvstudie i ugen 1 t 24 min af 12 t 50 min planlagt i 9 blokke · 1 dag ", felt("Selvstudie i ugen"));
tjek("skærmtid: i dag, passiv og i går med tiden efter kl. 23", felt("Skærmtid i dag") === "Skærmtid i dag 1 t 22 min passiv 37 min · i går 7 t 7 min, heraf 30 min efter kl. 23 ", felt("Skærmtid i dag"));
tjek("felterne: intet ligger kun i title", !/class="card vital"[^>]*title=/.test(root()), root());
render({ liv, skaermtid: { ...skaermtid, dage: [{ dato: igaar, timer: 7.12, sen_timer: 0 }] } });
tjek("skærmtid: intet efter kl. 23, ingen heraf", felt("Skærmtid i dag") === "Skærmtid i dag 1 t 22 min passiv 37 min · i går 7 t 7 min ", felt("Skærmtid i dag"));
tjek("søvn uden coach: streg", felt("Søvn i nat") === "Søvn i nat – søvnscore – ", felt("Søvn i nat"));
render({ liv: { ...liv, studieuge: { ...liv.studieuge, status: "kalenderen er ikke hentet siden 2026-10-19" } } });
tjek("selvstudie: gammel kalender siges", /kalenderen er ikke hentet siden 2026-10-19/.test(felt("Selvstudie i ugen")), felt("Selvstudie i ugen"));
render({ liv: { ...liv, studieuge: { ...liv.studieuge, planlagt_blokke: 0, planlagt_timer: 0 } } });
tjek("selvstudie: ingen blokke", /ingen studieblokke planlagt/.test(felt("Selvstudie i ugen")), felt("Selvstudie i ugen"));
render({ studie: studie([]), genkald });
tjek("ingen af projekterne: ingen felter", !/class="vitals"/.test(root()));

render({ liv: { reviews: [w40, snapshot] } });
tjek("Én ting kommer fra seneste review med tekst", /Læs før forelæsningen/.test(root()), root());

tjek("review uden felterne: ingen skrevet-linje", !/class="kilde"/.test(root()), root());
render({ liv: { reviews: [gammel] } });
tjek("gammelt review: kun Skrevet <dato>", /<small class="kilde">Skrevet 7\. okt\.<\/small>/.test(root()), root());

render({ liv: { reviews: [w40, ny] } });
tjek("nyt review: skrevet-linjen står ved teksten", /Sov otte timer<\/p><small class="kilde">Skrevet 12\. okt\. · metode 2026-10-08<\/small>/.test(root()), root());
render({ liv: { reviews: [{ ...ny, metode: "<b>x</b>" }] } });
tjek("metode escapes", /metode &lt;b&gt;x&lt;\/b&gt;/.test(root()), root());

// ── Sprog: dagens kort, niveautest og ugens tekst; en defekt pakke koster kun Sprog ──
const sprog = (kort, tekster = []) => ({ aktivt: "es", sprog: { es: { navn: "Spansk", niveau: null } }, kort, tekster,
  statistik: { klaret_i_dag: 2, minutter: 3, sprog: { es: { laert: 4, i_alt: 30 } } } });
render({ sprog: sprog([{ type: "test" }, { type: "frase" }], [{ uge: "2026-W43", svar: null }]), genkald });
tjek("sprog: antal kort og minutter", /<div class="big">2<small>sprogkort i dag · ca\. 3 min/.test(root()), root());
tjek("sprog: niveautest og lært fra pakken", /Heraf 1 i niveautesten\. Spansk: 4 af 30 lært\./.test(root()), root());
tjek("sprog: ugens tekst venter", /Ugens tekst venter på dit svar/.test(root()));
const kunTest = sprog([{ type: "test" }]); kunTest.statistik.sprog.es.i_alt = 0;
render({ sprog: kunTest, genkald });
tjek("sprog: kun niveautest, intet '0 af 0 lært'", /Heraf 1 i niveautesten\. <\/p>/.test(root()) && !/0 af 0/.test(root()), root());
render({ sprog: { statistik: {}, kort: [] }, genkald });
tjek("defekt sprogpakke: Sprog nævnes", /Sprog kunne ikke vises/.test(root()), root());
tjek("defekt sprogpakke: Genkald vises stadig", /href="\/studie\/genkald\.html#idag"/.test(root()));
const eks = sprog([{ type: "frase" }]); eks.statistik.eksamensperiode = { fag: "Alfa", dato: "2026-12-10" };
render({ sprog: eks, genkald });
tjek("sprog: eksamensperiode nævnes", /Eksamensperiode: kun gentagelse\./.test(root()), root());
const fb = sprog([{ type: "frase" }], [{ uge: "2026-W43", svar: null }]); fb.ny_feedback = { uge: "2026-W42", titel: "En el bar" };
render({ sprog: fb, genkald });
tjek("sprog: feedback på sidste uges svar nævnes", /Der er feedback på dit svar til uge 42\. Ugens tekst venter på dit svar\./.test(root()), root());
render({ genkald });
tjek("uden Sprog-server: intet sprogkort", !/sprogkort i dag/.test(root()) && !/kunne ikke vises/.test(root()), root());

// ── Frister med kun en uge: ugen i blokken, ikke mandagens dato ──
{
  const mandag = addDays(new Date(), 7 - ((new Date().getDay() + 6) % 7));  // næste mandag
  const fra = iso(mandag), til = iso(addDays(mandag, 6));
  render({ studie: studie([{ dato: null, fra, til, uger: "45", type: "aflevering", fag: "Alfa", hvad: "Alfa-opgaven" },
    { dato: null, fra, til: iso(addDays(mandag, 13)), uger: "46-47", type: "praesentation", fag: "Alfa", hvad: "Præsentation" },
    { dato: imorgen, type: "aflevering", fag: "Gamma", hvad: "Aflevering 3" }]), genkald });
  const blokke = root().match(/<div class="cal[^"]*">.*?<\/div><\/div>/g) || [];
  tjek("frist med uge: UGE 45 i blokken", blokke.some(b => /<div class="m">Uge<\/div><div class="d">45<\/div>/.test(b)), blokke.join("\n"));
  tjek("frist med to uger: 46–47 i mindre skrift", blokke.some(b => /<div class="d uge">46–47<\/div>/.test(b)), blokke.join("\n"));
  tjek("frist med uge: ingen af de to får en måned og en dato", blokke.length === 3 && blokke.filter(b => /class="m">Uge</.test(b)).length === 2, blokke.join("\n"));
  tjek("frist med dato: måned og dag som før", blokke.some(b => new RegExp(`<div class="d">${addDays(new Date(), 1).getDate()}</div>`).test(b) && !/Uge/.test(b)), blokke.join("\n"));
}

// ── Båndet på mobil: kun tallene tæller, når hvert andet skjules (ikke .rail) ──
tjek("båndet: nth-of-type, ikke nth-child", /\.band \.tick:nth-of-type\(even\) \{ display: none; \}/.test(side) && !/\.tick:nth-child/.test(side));
{
  render({ coach: { kalender: { dage: [{ dato: iso(new Date()), program: [{ tid: "09:00–10:00", titel: "Noget" }] }] } }, studie: studie([]) });
  const band = element("band").innerHTML;
  tjek("båndet: .rail er eneste div før tallene, og tallene er de eneste span", /^<div class="rail"><\/div>(<span class="tick"[^>]*>\d+<\/span>){8}<div/.test(band), band);
}

// ── Et projekt, der ikke svarer, nævnes i beskedlinjen; resten vises ──
render({ studie: studie([]), genkald, svarerIkke: ["Sprog"] });
tjek("svarer ikke: Sprog nævnes", /Sprog svarer ikke; resten er vist\./.test(root()), root());
tjek("svarer ikke: Genkald vises stadig", /href="\/studie\/genkald\.html#idag"/.test(root()));
render({ studie: studie([{ dato: imorgen, type: "aflevering", fag: "Alfa" }]), genkald, svarerIkke: ["Sprog", "Ugereview", "Skærmtid"] });
tjek("svarer ikke og defekt sektion: begge i én linje", /Sprog, Ugereview og Skærmtid svarer ikke\. Frister kunne ikke vises; resten er vist\./.test(root()), root());
render({ studie: studie([]), genkald });
tjek("alle svarer: ingen beskedlinje", !/svarer ikke/.test(root()) && !/class="s12 flag"/.test(root()), root());

(async () => {
  const hent = vm.runInContext("hent", kontekst);
  const svar = { "/sprog/api/pakke": null, "/skaermtid/skaermtid.json": 502 };
  kontekst.fetch = url => url in svar && svar[url] == null ? Promise.reject(new TypeError("Failed to fetch"))
    : Promise.resolve({ ok: !(url in svar), status: svar[url] || 200, json: async () => url === "/studie/studie.json" ? studie([]) : {} });
  await hent();
  tjek("hent: afvist kald og fejlkode nævnes, i kildernes rækkefølge", /Sprog og Skærmtid svarer ikke; resten er vist\./.test(root()), root());
  kontekst.fetch = url => url === "/form/soevn.json" || url === "/form/coach.json" ? Promise.reject(new TypeError("Failed to fetch")) : Promise.resolve({ ok: true, json: async () => ({}) });
  await hent();
  tjek("hent: to kald fra samme projekt nævner det én gang", /<span>Form &amp; fokus svarer ikke; resten er vist\./.test(root()), root());
  kontekst.fetch = () => Promise.resolve({ ok: true, json: async () => ({}) });
  await hent();
  tjek("hent: alle svarer, ingen linje", !/svarer ikke/.test(root()), root());
  const hentet = [];
  kontekst.fetch = url => { hentet.push(url); return url === "/sprog/api/pakke" ? Promise.reject(new TypeError("Failed to fetch"))
    : Promise.resolve({ ok: true, json: async () => url === "/kompas/projekter.json" ? { pause: [{ projekt: "Sprog" }] } : {} }); };
  await hent();
  tjek("hent: et projekt på pause hentes ikke og nævnes ikke", !hentet.includes("/sprog/api/pakke") && !/svarer ikke/.test(root()) && !/sprogkort i dag/.test(root()), hentet.join(" ") + root());

  console.log(fejl ? `${fejl} fejl` : "ok");
  process.exit(fejl ? 1 : 0);
})();
