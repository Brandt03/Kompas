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

render({ studie: studie([]), genkald, coach: { restitution: { flag: "ikke en liste" } } });
tjek("defekt coach: Søvn og krop nævnes", /Søvn og krop kunne ikke vises/.test(root()), root());
tjek("defekt coach: Genkald vises stadig", /href="\/studie\/genkald\.html#idag"/.test(root()));

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
render({ genkald });
tjek("uden Sprog-server: intet sprogkort", !/sprogkort i dag/.test(root()) && !/kunne ikke vises/.test(root()), root());

console.log(fejl ? `${fejl} fejl` : "ok");
process.exit(fejl ? 1 : 0);
