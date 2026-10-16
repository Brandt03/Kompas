// Drill-gæt i Studie-serveren skal læses som værdier og aldrig køres som kode.
// Henter læsVærdi/skrivVærdi direkte fra serveren uden at starte den.   node tests/test_drill_gaet.js
"use strict";
const fs = require("fs");
const path = require("path");
const util = require("util");

const src = fs.readFileSync(path.join(__dirname, "..", "studie", "Scripts", "kompas-server.js"), "utf8");
const kode = src.slice(src.indexOf("const ORD ="), src.indexOf("async function gemDrill"));
const { læsVærdi, skrivVærdi } = new Function(`${kode}; return { læsVærdi, skrivVærdi };`)();
const ens = (a, b) => Object.is(a, b) || util.isDeepStrictEqual(a, b);
let fejl = 0;

// Værdier, en drill kan forvente: læses rigtigt, og serverens form læses tilbage til det samme
const gyldige = {
  "3": 3, "-3": -3, "0.30000000000000004": 0.30000000000000004, "-0": -0, "+5": 5, "1e3": 1000, ".5": 0.5, "1_000": 1000,
  "NaN": NaN, "Infinity": Infinity, "-Infinity": -Infinity, "undefined": undefined, "null": null, "true": true, "false": false,
  '"number"': "number", "'abc'": "abc", "`tekst`": "tekst", '"linje\\nto"': "linje\nto",
  '["paraply","solbriller"]': ["paraply", "solbriller"], "[1, 'a', [true]]": [1, "a", [true]], "[]": [], "{}": {},
  "{a: 1, 'b c': [null]}": { a: 1, "b c": [null] },
};
for (const [gaet, forventet] of Object.entries(gyldige)) {
  try {
    const v = læsVærdi(gaet);
    if (!ens(v, forventet) || !ens(læsVærdi(skrivVærdi(v)), forventet)) { fejl++; console.log("FORKERT", gaet, v); }
  } catch (e) { fejl++; console.log("AFVIST", gaet, e.message); }
}

// Kode, uanset hvordan den er pakket ind, skal afvises
const ondsindede = [
  'this.constructor.constructor("return process")().mainModule.require("fs").writeFileSync("pwn","x")',
  'require("fs").writeFileSync("pwn","x")', "process.exit(1)", "`${process.exit(1)}`", "1 + 1", "(1)",
  "[1].map(x => x)", "{__proto__: {}}", "a", "1; process", "'uafsluttet", "[1, 2", "Function('return 1')()",
  "globalThis", "x => x", "new Date()", "[...'ab']", "({})",
];
for (const gaet of ondsindede) {
  try { const v = læsVærdi(gaet); fejl++; console.log("SLAP IGENNEM", gaet, v); } catch { /* skal afvises */ }
}

console.log(fejl ? `${fejl} fejl` : `${Object.keys(gyldige).length} gyldige gæt og ${ondsindede.length} angreb opførte sig rigtigt`);
process.exit(fejl ? 1 : 0);
