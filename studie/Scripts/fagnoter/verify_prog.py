"""Tjekker en notes-fil for et fag med kode (brug: verify_prog.py <notes.py>): format, og at hver '// →'-kommentar i kodeblokkene stemmer med node.

Konvention i kodeblokkene:
  kode;            // → forventet            (inline: output fra denne linje)
  // → forventet                             (egen linje: næste output i rækkefølge)
  '  ← forklaring' efter det forventede ignoreres ved sammenligningen.
  '  (string)' / '  (number)' osv. efter det forventede tjekkes mod typeof af første argument.
"""
import importlib.util, json, os, re, subprocess, sys, tempfile

spec = importlib.util.spec_from_file_location("notes", sys.argv[1])
N = importlib.util.module_from_spec(spec)
spec.loader.exec_module(N)

PRE = r"""
const __util = require('util');
const __out = [];
console.log = (...a) => {
  const t = __util.format(...a);
  t.split('\n').forEach((line, i) =>
    __out.push({t: line, ty: i === 0 ? typeof a[0] : null}));
};
process.on('exit', () => process.stdout.write(JSON.stringify(__out)));
"""

TYPE_RE = re.compile(r"^(.*?)\s{2,}\((string|number|boolean|undefined|object|function)\)$")
problems = []


def expected(code):
    exp = []
    for line in code.split("\n"):
        if "// →" not in line:
            continue
        txt = line.split("// →", 1)[1]
        txt = txt[1:] if txt.startswith(" ") else txt
        txt = txt.split("  ←", 1)[0].rstrip()
        m = TYPE_RE.match(txt)
        ty = None
        if m:
            txt, ty = m.group(1).rstrip(), m.group(2)
        exp.append((txt, ty, line))
    return exp


def run(code):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(PRE + "\n" + code + "\n")
        path = f.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True, timeout=20)
    finally:
        os.unlink(path)
    if r.returncode != 0:
        return None, r.stderr.strip().splitlines()[-1] if r.stderr else "exit %d" % r.returncode
    return json.loads(r.stdout), None


n_blocks = n_checks = 0
for w, d in N.WEEKS.items():
    for key in ("begreber", "fejl"):
        for t in d.get(key, []):
            if t.count(" — ") != 1:
                problems.append(f"uge {w} {key}: ikke præcis én ' — ': {t[:70]}")
            elif len(t.split(" — ")[0]) > 70:
                problems.append(f"uge {w} {key}: lang fed del: {t.split(' — ')[0]}")
    for img, cap, width in d.get("modeller_files", []):
        if not os.path.exists(img):
            problems.append(f"uge {w}: billede mangler {img}")
    for title, code in d["kode"]:
        n_blocks += 1
        lines = code.split("\n")
        if len(lines) > 12:
            problems.append(f"uge {w} '{title}': {len(lines)} linjer")
        for ln in lines:
            if len(ln) > 64:
                problems.append(f"uge {w} '{title}': linje {len(ln)} tegn: {ln}")
            ind = len(ln) - len(ln.lstrip(" "))
            if ind % 2 and not ln.lstrip().startswith("//"):
                problems.append(f"uge {w} '{title}': ulige indrykning: {ln}")
        exp = expected(code)
        out, err = run(code)
        if err:
            problems.append(f"uge {w} '{title}': node-fejl: {err}")
            continue
        if len(out) != len(exp):
            problems.append(f"uge {w} '{title}': {len(out)} outputs, {len(exp)} forventede\n"
                            f"   faktisk: {[o['t'] for o in out]}\n   forventet: {[e[0] for e in exp]}")
            continue
        for o, (txt, ty, line) in zip(out, exp):
            n_checks += 1
            if o["t"].rstrip() != txt:
                problems.append(f"uge {w} '{title}': forventet {txt!r}, node gav {o['t']!r}  [{line.strip()}]")
            if o["t"] != o["t"].rstrip():
                problems.append(f"uge {w} '{title}': trailing whitespace i output {o['t']!r}")
            if ty and o["ty"] != ty:
                problems.append(f"uge {w} '{title}': type {ty} angivet, typeof gav {o['ty']}  [{line.strip()}]")

for lab, items in getattr(N, "EKSAMEN", {}).items():   # ugens notes-fil har ingen EKSAMEN
    for t in items:
        if not t.strip():
            problems.append(f"EKSAMEN {lab}: tomt punkt")

print(f"{n_blocks} kodeblokke, {n_checks} '// →'-tjek kørt i node")
for w, d in N.WEEKS.items():
    print(f"uge {w}: {len(d['begreber'])} begreber, {len(d['kode'])} kodeblokke, {len(d['fejl'])} fejl, "
          f"{len(d.get('modeller_files', []))} billeder, {len(d['uafklaret'])} uafklaret")
print("PROBLEMER:" if problems else "Ingen problemer.")
for p in problems:
    print(" -", p)
sys.exit(1 if problems else 0)
