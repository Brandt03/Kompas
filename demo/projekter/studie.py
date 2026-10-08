"""Demodata for Studie (/studie/): ugeplaner, frister, genkald, begreber, drills, eksamenssæt og kalender.

Skriver det, Scripts/kompas-eksport.js og Scripts/kompas-server.js ville levere for en opdigtet studerende med tre
fag (Alfa, Beta og Gamma), med alle datoer regnet ud fra idag:

  ud/studie/studie.json, fagnoter.json, kalender.json, kompas.json   eksportens filer
  ud/studie/fagnoter/is/lorem-ipsum.svg                               et billede i fagnoterne
  ud/studie/api/<navn>.json                                           svaret på GET /studie/api/<navn>

Nogle GET-kald har en query (/facit?fag=…&fil=…&nr=…). Til dem skrives både ét svar pr. query i
ud/studie/api/<navn>/<query>.json (parametrene sorteret og procent-kodet, se query_navn) og et standardsvar i
ud/studie/api/<navn>.json, som passer til det, siden viser først.

Indholdet er pladsholdere i lorem ipsum (fag, emner, spørgsmål, facit, begreber, planer, fagnoter, eksamenssæt,
frister og kalender), men med samme form og mængde som det rigtige, så siderne ser fulde ud. Drillene er enkel,
almen JavaScript, så de kan køres. Kun standardbiblioteket; virker med Python 3.9.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

# ── tid ──────────────────────────────────────────────────────────────

MDR = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]
MDR_LANG = ["januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober",
            "november", "december"]
DAGE = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]


def uge(d: date) -> int:
    return d.isocalendar()[1]


def mandag(d: date) -> date:
    return d - timedelta(days=d.weekday())


def ddmm(d: date) -> str:
    return f"{d.day:02d}.{d.month:02d}"


# ── markdown → html (samme regler som md() i kompas-eksport.js) ──────

def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(s: str) -> str:
    koder: list[str] = []

    def gem(m):
        koder.append(m.group(1))
        return f"\x00{len(koder) - 1}\x00"

    s = re.sub(r"`([^`]+)`", gem, _esc(s))
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(^|[^*\w])\*(?!\s)(.+?)\*(?!\w)", r"\1<em>\2</em>", s, flags=re.ASCII)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub("\x00(\\d+)\x00", lambda m: f"<code>{koder[int(m.group(1))]}</code>", s)
    return s.replace("\x01", "<br>")


def md(src: str) -> str:
    ud: list[str] = []
    linjer = src.replace("\r", "").split("\n")
    para: list[str] = []
    liste: dict | None = None

    def luk_para():
        nonlocal para
        if para:
            ud.append(f"<p>{inline(' '.join(para))}</p>")
            para = []

    def luk_liste():
        nonlocal liste
        if not liste:
            return
        pkt = "".join(
            f"<li>{inline(it['tekst'])}"
            + (f"<ul>{''.join(f'<li>{inline(u)}</li>' for u in it['under'])}</ul>" if it["under"] else "")
            + "</li>" for it in liste["items"])
        ud.append(f"<{liste['tag']}>{pkt}</{liste['tag']}>")
        liste = None

    i = 0
    while i < len(linjer):
        l = linjer[i]
        if l.startswith("```"):
            luk_para()
            luk_liste()
            kode = []
            i += 1
            while i < len(linjer) and not linjer[i].startswith("```"):
                kode.append(linjer[i])
                i += 1
            ud.append(f"<pre><code>{_esc(chr(10).join(kode))}</code></pre>")
            i += 1
            continue
        if not l.strip():
            luk_para()
            nx = linjer[i + 1] if i + 1 < len(linjer) else ""
            if liste and not re.match(r"^\s+\S", nx) and not re.match(r"^\s*([-*]|\d+\.)\s", nx):
                luk_liste()
            i += 1
            continue
        if re.match(r"^---+\s*$", l):
            luk_para()
            luk_liste()
            ud.append("<hr>")
            i += 1
            continue
        h = re.match(r"^(#{1,6})\s+(.*)$", l)
        if h:
            luk_para()
            luk_liste()
            n = 3 if len(h.group(1)) <= 3 else 4
            ud.append(f"<h{n}>{inline(h.group(2))}</h{n}>")
            i += 1
            continue
        if re.match(r"^\s*\|", l):
            luk_para()
            luk_liste()
            rows = []
            while i < len(linjer) and re.match(r"^\s*\|", linjer[i]):
                rows.append(linjer[i])
                i += 1

            def celler(r):
                return [c.strip() for c in re.sub(r"^\||\|$", "", r.strip()).split("|")]

            hoved = "".join(f"<th>{inline(c)}</th>" for c in celler(rows[0]))
            krop = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in celler(r)) + "</tr>" for r in rows[2:])
            ud.append(f"<table><thead><tr>{hoved}</tr></thead><tbody>{krop}</tbody></table>")
            continue
        li = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", l)
        if li:
            luk_para()
            tag = "ol" if re.search(r"\d", li.group(2)) else "ul"
            if len(li.group(1)) >= 2 and liste:
                liste["items"][-1]["under"].append(li.group(3))
            else:
                if not liste or liste["tag"] != tag:
                    luk_liste()
                    liste = {"tag": tag, "items": []}
                liste["items"].append({"tekst": li.group(3), "under": []})
            i += 1
            continue
        if liste and re.match(r"^\s+\S", l):
            liste["items"][-1]["tekst"] += ("\x01" if re.match(r"^\s+[a-h]\)\s", l) else " ") + l.strip()
            i += 1
            continue
        luk_liste()
        para.append(l.strip())
        i += 1
    luk_para()
    luk_liste()
    return "\n".join(ud)


# ── fagene ───────────────────────────────────────────────────────────
# Tre opdigtede fag. Alfa har en skriftlig eksamen med multiple choice og tegnede modeller, Beta en mundtlig, og
# Gamma har drills i JavaScript og nummererede afleveringer. Første ord i navnet er fagets kendetegn på siderne;
# kode og hold står i kalendertitlerne.

FAG = [
    {"id": "alfa", "kort": "Alfa", "navn": "Alfa – lorem ipsum", "kode": "KURS101", "hold": "A"},
    {"id": "beta", "kort": "Beta", "navn": "Beta – dolor sit amet", "kode": "KURS102", "hold": "B"},
    {"id": "gamma", "kort": "Gamma", "navn": "Gamma – consectetur", "kode": "KURS103", "hold": "C"},
]
FAGNAVN = {f["id"]: f["kort"] for f in FAG}

ORD = ("lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore "
       "magna aliqua enim ad minim veniam quis nostrud exercitation ullamco laboris nisi aliquip ex ea commodo "
       "consequat duis aute irure in reprehenderit voluptate velit esse cillum fugiat nulla pariatur excepteur sint "
       "occaecat cupidatat non proident sunt culpa qui officia deserunt mollit anim id est laborum").split()


def lorem(n: int, s: int = 0, slut: str = ".") -> str:
    """n ord lorem ipsum, der begynder et sted bestemt af s (samme s giver samme tekst)."""
    return " ".join(ORD[(s * 7 + i) % len(ORD)] for i in range(n)).capitalize() + slut


def fed(n: int, s: int, slut: str = ".") -> str:
    """lorem ipsum med to fede ord i midten."""
    return f"{lorem(n // 2, s, '')} **{lorem(2, s + 3, '').lower()}** {lorem(n - n // 2, s + 5, slut).lower()}"


# Eksamensformerne (tabellen "De tre fag trænes forskelligt" i semestermappens README.md)
EKSAMENSFORM = {
    "alfa": {"Fag": "Alfa", "Eksamen": "Lorem ipsum, 2 timer: dolor, sit og amet",
           "Det der virker": "korte runder med lorem ipsum og at **consectetur** selv"},
    "beta": {"Fag": "Beta", "Eksamen": "Lorem ipsum dolor med en case",
            "Det der virker": "at bruge ugens lorem ipsum på noget, du kender"},
    "gamma": {"Fag": "Gamma", "Eksamen": "Lorem ipsum, 4 timer, og godkendte opgaver",
             "Det der virker": "at **skrive og køre kode** hver uge; lorem ipsum er opvarmning"},
}

# Kursusuge 1–7. Uge 6 er denne uge.
NU = 6
EMNER = {
    "alfa": ["Lorem ipsum", "Dolor sit amet", "Consectetur adipiscing", "Sed do eiusmod", "Tempor incididunt",
           "Ut labore et dolore", "Magna aliqua"],
    "beta": ["Ut enim ad minim", "Quis nostrud", "Exercitation ullamco", "Laboris nisi", "Aliquip ex ea",
            "Commodo consequat", "Duis aute irure"],
    "gamma": ["Reprehenderit", "Voluptate velit", "Esse cillum", "Fugiat nulla", "Pariatur excepteur",
             "Sint occaecat", "Cupidatat non"],
}

# ── ugeplanerne (køreplan-rutinens Uge_Overblik/Ugeplan_*.md) ────────
# Pr. fag og kursusuge: Hurtigt overblik, Kilder, Noter til pensum, evt. Til rapporten og øvelsesspørgsmål.

GAMMA_KODE = {   # et lille stykke JavaScript i Gamma-noterne (vises kun)
    3: "function lorem() {\n  let n = 0;\n  return () => ++n;   // lorem ipsum\n}",
    4: "const ipsum = [];\nipsum.push({ dolor: \"sit\", amet: 35 });\nipsum.length;   // 1",
    5: "const dolor = [35, 20, 50];\ndolor.filter(x => x > 30).map(x => x * 2);   // [70, 100]",
    6: "class Lorem {\n  constructor() { this.ipsum = 0; }\n  dolor(n) { this.ipsum += n; }\n}",
}


def _plan() -> dict:
    ud = {}
    for fi, fag in enumerate(("alfa", "beta", "gamma")):
        ud[fag] = {}
        for k in range(3, 8):
            s = fi * 40 + k * 6
            p = {"overblik": lorem(26, s),
                 "kilder": [f"Lorem ipsum kap. {k + 2}", f"{lorem(3, s + 1, '')} (Canvas)"]
                 + ([f"Øvelse {k}: {lorem(2, s + 2, '').lower()}"] if k < 7 else [])}
            if fag == "gamma":
                p["noter"] = f"{lorem(14, s + 3)}\n\n{lorem(12, s + 4)}" + (
                    f"\n\n```js\n{GAMMA_KODE[k]}\n```" if k in GAMMA_KODE else "")
                if k in (4, 6):
                    p["rapport"] = lorem(14, s + 5)
            else:
                p["noter"] = [f"**{lorem(2, s + 3 + j, '')}**: {lorem(9, s + 4 + j).lower()}" for j in range(4 if k < 7 else 2)]
                if k < 7:
                    p["oevelse"] = [(lorem(11, s + 6 + j, "?"), lorem(16, s + 8 + j)) for j in range(2)]
                if fag == "alfa" and 4 <= k <= 6:
                    p["rapport"] = lorem(15, s + 5)
            ud[fag][k] = p
    return ud


PLAN = _plan()

# Vigtigst i ugen (pr. kursusuge); {o3} erstattes med afleveringsdagen for Opgave 3
VIGTIGST = {k: [lorem(12, 200 + k * 4 + j) for j in range(3)] for k in range(3, 8)}
VIGTIGST[6][0] = "**Opgave 3** afleveres {o3} kl. 14.00. " + lorem(7, 233)

# Genkaldelse fra sidste uge, nederst i planen (pr. kursusuge, fra uge 4)
GENKALDELSE = {k: [(lorem(9, 260 + k * 5 + j, "?"), lorem(13, 262 + k * 5 + j)) for j in range(3 if k == 6 else 2)]
               for k in range(4, 8)}

# ── genkald (*/Genkald/genkald-*.md + -svar.md) ──────────────────────
# Pr. fag: filer med spørgsmål som (kursusuge, spørgsmål, facit).

def _genkald(filer: list, s0: int) -> list:
    ud, s = [], s0
    for uger in filer:
        fil = []
        for k in uger:
            fil.append((k, fed(11, s, "?"), f"{lorem(14, s + 1)} {fed(12, s + 2)}"))
            s += 3
        ud.append(fil)
    return ud


GENKALD = {
    "alfa": _genkald([[1, 1, 2, 2, 3, 3, 3], [4, 4, 5, 5, 5]], 300),
    "beta": _genkald([[1, 1, 2, 2], [3, 3, 4, 4, 5, 5, 5]], 360),
}

# Markeringer i genkald-filerne: (fag, filnummer, spørgsmål) → (markering, dage siden, dit svar eller None)
MARKERINGER = {
    ("alfa", 0, 1): ("✓", 9, lorem(10, 401)),
    ("alfa", 0, 2): ("✓", 9, None),
    ("alfa", 0, 3): ("~", 5, lorem(8, 403)),
    ("alfa", 0, 4): ("✗", 1, lorem(9, 404)),
    ("alfa", 0, 5): ("✓", 4, lorem(7, 405)),
    ("alfa", 0, 6): ("~", 4, None),
    ("alfa", 1, 1): ("✓", 2, lorem(12, 407)),
    ("beta", 0, 1): ("✓", 8, None),
    ("beta", 0, 2): ("✓", 8, lorem(11, 409)),
    ("beta", 0, 3): ("~", 2, lorem(10, 410)),
    ("beta", 0, 4): ("✗", 6, None),
}

# Uger markeret som læst under Fag → Styr på (kursusuger). Beta uge 4 og 5 venter.
LAEST = {"alfa": [1, 2, 3, 4], "beta": [1, 2, 3]}

# ── begreber (*/Genkald/begreber.md) ─────────────────────────────────
# (kursusuge, begreb, din definition, hvad det får dig til at se (kun Beta), kilde)

def _begreber(navne: list, s0: int, se: bool) -> list:
    return [(k, navn, lorem(12, s0 + i) if udfyldt else "",
             (lorem(13, s0 + 30 + i) if udfyldt and se_her else "") if se else None, str(kilde))
            for i, (k, navn, udfyldt, se_her, kilde) in enumerate(navne)]


BEGREBER = {
    "alfa": _begreber([(1, "Lorem", True, False, 4), (1, "Ipsum", True, False, 5), (1, "Dolor", False, False, 7),
                     (2, "Sit amet", True, False, 14), (2, "Consectetur", True, False, 22), (2, "Adipiscing", False, False, 31),
                     (3, "Elit sed", True, False, 112), (3, "Eiusmod", True, False, 113), (3, "Tempor", False, False, 118),
                     (4, "Incididunt", True, False, 141), (4, "Labore", False, False, 144), (4, "Magna aliqua", False, False, 147),
                     (5, "Veniam", False, False, 170), (5, "Nostrud", False, False, 171)], 450, False),
    "beta": _begreber([(1, "Ullamco", True, True, 18), (1, "Laboris", True, True, 24), (2, "Commodo", True, True, 52),
                      (2, "Consequat", False, False, 48), (3, "Aute irure", True, False, 71), (3, "Voluptate", False, False, 79),
                      (4, "Cillum", True, True, 102), (4, "Fugiat", False, False, 106), (5, "Pariatur", False, False, 133),
                      (5, "Excepteur", False, False, 137)], 500, True),
}
BEGREB_FORFALDEN = {("alfa", "Eiusmod"): (1, 3, 3), ("beta", "Commodo"): (0, 2, 2)}   # (niveau, dage siden, interval)
BEGREB_I_MORGES = {"Lorem", "Elit sed", "Ullamco"}

# ── drills (Gamma/vscode/Drills/kap*.js) ─────────────────────────────
# ("afsnit", navn) | ("kode", js) | ("stub", js) | ("tjek", beskrivelse, udtryk, dit gæt eller None, hvad JavaScript giver)
# "Hvad JavaScript giver" er tjek.js' visning (JSON.stringify, NaN og undefined som tekst). Koden er enkel, almen
# JavaScript, så drillene kan køres; titler og beskrivelser er pladsholdere.

DRILLS = [
    ("kap01-lorem.js", "Kap. 1 — Lorem ipsum", 1, [
        ("afsnit", "lorem"),
        ("tjek", "Lorem ipsum", "() => typeof 42", '"number"', '"number"'),
        ("tjek", "Dolor sit", '() => typeof "42"', '"string"', '"string"'),
        ("tjek", "Amet consectetur       ← lorem ipsum", "() => typeof null", '"null"', '"object"'),
        ("afsnit", "ipsum"),
        ("tjek", "Adipiscing elit", '() => "5" + 3', '"53"', '"53"'),
        ("tjek", "Sed do eiusmod", '() => "5" - 3', '"2"', "2"),
        ("tjek", "Tempor incididunt", '() => "5" * "2"', "10", "10"),
        ("tjek", "Ut labore", "() => true + 1", "2", "2"),
        ("afsnit", "dolor"),
        ("tjek", "Et dolore", "() => null == undefined", "true", "true"),
        ("tjek", "Magna aliqua", "() => null === undefined", "false", "false"),
        ("tjek", "Ut enim", '() => Boolean("0")', "false", "true"),
    ]),
    ("kap02-ipsum.js", "Kap. 2 — Dolor sit amet", 2, [
        ("afsnit", "sit"),
        ("tjek", "Minim veniam", "() => { const a = 1; a = 2; return a; }", '"TypeError"', '"TypeError"'),
        ("tjek", "Quis nostrud           ← dolor sit amet", "() => { for (var i = 0; i < 3; i++) {} return i; }", "2", "3"),
        ("tjek", "Exercitation", "() => { for (let j = 0; j < 3; j++) {} return typeof j; }", None, '"undefined"'),
        ("afsnit", "amet"),
        ("tjek", "Ullamco laboris", "() => { let n = 0; while (true) { n += 2; if (n > 5) break; } return n; }", None, "6"),
        ("tjek", "Nisi ut aliquip", '() => { let s = ""; for (let i = 3; i > 0; i--) s += i; return s; }', '"321"', '"321"'),
        ("tjek", "Ex ea commodo", '() => (7 % 2 === 0 ? "lorem" : "ipsum")', '"ipsum"', '"ipsum"'),
    ]),
    ("kap03-dolor.js", "Kap. 3 — Consectetur adipiscing", 3, [
        ("kode", "function lorem(x) {\n  return x * x;\n}"),
        ("kode", 'const ipsum = (ord = "dolor") => `Lorem ${ord}!`;'),
        ("kode", "function sitAmet() {\n  let n = 0;\n  return () => ++n;\n}"),
        ("afsnit", "consectetur"),
        ("tjek", "Duis aute", "() => lorem(4)", "16", "16"),
        ("tjek", "Irure dolor", "() => lorem()", "undefined", "NaN"),
        ("tjek", "In reprehenderit", "() => ipsum()", '"Lorem dolor!"', '"Lorem dolor!"'),
        ("tjek", "Voluptate velit", '() => ipsum("amet")', None, '"Lorem amet!"'),
        ("afsnit", "adipiscing"),
        ("tjek", "Esse cillum", "() => { const t = sitAmet(); t(); return t(); }", None, "2"),
        ("tjek", "Fugiat nulla", "() => { const a = sitAmet(), b = sitAmet(); a(); a(); return b(); }", None, "1"),
        ("afsnit", "elit"),
        ("stub", "// Lorem ipsum dolor sit amet (fx consectetur(4) === 24).\nfunction consectetur(n) {\n  // DIN KODE HER\n}"),
    ]),
    ("kap04-amet.js", "Kap. 4 — Sed do eiusmod", 4, [
        ("kode", "const dolor = [3, 1, 2];"),
        ("kode", 'const sit = { lorem: "ipsum", amet: 21 };'),
        ("afsnit", "sed"),
        ("tjek", "Pariatur", "() => dolor.length", "3", "3"),
        ("tjek", "Excepteur sint", "() => dolor.includes(2)", None, "true"),
        ("tjek", "Occaecat", "() => [...dolor].sort()", None, "[1,2,3]"),
        ("tjek", "Cupidatat non", "() => dolor.indexOf(5)", None, "-1"),
        ("afsnit", "eiusmod"),
        ("tjek", "Proident sunt", "() => sit.lorem", None, '"ipsum"'),
        ("tjek", "Culpa qui", '() => "amet" in sit', None, "true"),
        ("tjek", "Officia deserunt", "() => Object.keys(sit)", None, '["lorem","amet"]'),
    ]),
]

# Korte forklaringer (Drills/forklaringer/<drill>.md). Vises kun for tjek, du har gættet på.
FORKLARINGER = {
    "Amet consectetur": "Lorem ipsum dolor sit amet: `typeof null` er `\"object\"`.",
    "Adipiscing elit": "Lorem ipsum dolor sit amet, consectetur `+` adipiscing elit.",
    "Sed do eiusmod": "Lorem ipsum `-` dolor sit amet, consectetur adipiscing elit sed do.",
    "Ut enim": "Lorem ipsum dolor `\"\"` sit amet, consectetur `\"0\"` adipiscing.",
    "Quis nostrud": "Lorem ipsum `var` dolor sit amet, consectetur adipiscing elit `i` er 3.",
    "Irure dolor": "Lorem ipsum `undefined * undefined` dolor sit amet `NaN`.",
    "Minim veniam": "Lorem ipsum `const` dolor sit amet `TypeError`.",
}
DRILL_FORFALDEN = {   # gættet forkert mindst én gang: (fil, beskrivelse uden note) → (niveau, dage siden, interval)
    ("kap01-lorem.js", "Amet consectetur"): (0, 1, 1),
    ("kap01-lorem.js", "Sed do eiusmod"): (2, 2, 7),
    ("kap01-lorem.js", "Ut enim"): (1, 1, 3),
    ("kap02-ipsum.js", "Quis nostrud"): (0, 1, 1),
    ("kap03-dolor.js", "Irure dolor"): (0, 0, 1),
}

# ── eksamenstræning (<Fag>/Eksamenstræning/<id>.md + <id>-svar.md) ───

def _mc(s: int) -> str:
    return f"{lorem(9, s, '?')}\n\n" + "\n".join(f"{b}) {lorem(5, s + 2 + i, '').lower()}" for i, b in enumerate("abcd"))


def _liste(n: int, s: int, nummer: bool = False) -> str:
    return "\n".join(f"{f'{i + 1}.' if nummer else '-'} {lorem(8, s + i)}" for i in range(n))


def eksamenssaet(U: dict) -> list:
    return [
        {"fag": "alfa", "id": "lorem-a", "titel": "Alfa — Lorem ipsum A", "meta": "2 timer · lorem ipsum dolor",
         "intro": lorem(14, 600),
         "sektioner": [
             ("Del A — Lorem ipsum", 40, "", [
                 (_mc(610), f"Lorem · uge {U[1]}", f"**b)** {lorem(9, 611)}"),
                 (_mc(615), f"Ipsum · uge {U[3]}", f"**c)** {lorem(6, 616)}"),
                 (_mc(620), f"Dolor · uge {U[5]}", f"**c)** {lorem(7, 621)}"),
                 (_mc(625), f"Sit amet · uge {U[6]}", f"**b)** {lorem(8, 626)}"),
             ]),
             ("Del B — Dolor sit", 30, "", [
                 (lorem(28, 630), f"Consectetur · uge {U[4]}", f"{lorem(3, 631)}\n\n{_liste(4, 632)}"),
             ]),
             ("Del C — Amet", 30, "", [
                 (lorem(20, 640), f"Adipiscing · uge {U[6]}", f"{lorem(3, 641)}\n\n{_liste(3, 642)}"),
             ]),
         ],
         "resultat": {1: "sad", 2: "blankt", 3: "sad", 4: "sad", 5: "halvt"}, "proever": []},
        {"fag": "gamma", "id": "lorem-a", "titel": "Gamma — Lorem ipsum A", "meta": "4 timer · lorem ipsum",
         "intro": lorem(18, 650),
         "sektioner": [
             ("Opgave 1 — Lorem", 20, "", [
                 (f"{lorem(6, 660, '')} `lorem(tal)` {lorem(10, 661, '').lower()} `0`.", "Lorem · kap. 3", _liste(3, 662)),
                 (f"{lorem(6, 665, '')} `ipsum(tekst)` {lorem(12, 666, '').lower()}.", "Ipsum · kap. 2", _liste(3, 667)),
             ]),
             ("Opgave 2 — Ipsum dolor", 40,
              f"{lorem(7, 670)}\n\n```js\nconst dolor = [\n  {{ lorem: \"ipsum\", sit: 12 }},\n"
              "  { lorem: \"dolor\", sit: 30 },\n  { lorem: \"amet\", sit: 3 },\n];\n```", [
                 (f"{lorem(5, 675, '')} `sitAmet(dolor, n)` {lorem(11, 676, '').lower()}.", "Dolor · kap. 5", _liste(3, 677)),
                 (f"{lorem(5, 680, '')} `consectetur(dolor)` {lorem(4, 681, '').lower()} `reduce`.", "Dolor · kap. 5", _liste(3, 682)),
             ]),
             ("Opgave 3 — Sit amet", 40, "", [
                 (f"{lorem(5, 690, '')} `Lorem` {lorem(14, 691, '').lower()}.", "Sit amet · kap. 6", _liste(3, 692)),
             ]),
         ],
         "resultat": {}, "proever": []},
        {"fag": "beta", "id": "ipsum", "titel": "Beta — Lorem ipsum", "meta": "Lorem ipsum · 15 min",
         "intro": lorem(16, 700),
         "sektioner": [
             (f"Uge {U[2]} — {EMNER['beta'][1]}", None, "", [
                 (lorem(16, 710, "?"), f"Lorem · uge {U[2]}", _liste(4, 711, True)),
             ]),
             (f"Uge {U[3]} — {EMNER['beta'][2]}", None, "", [
                 (lorem(12, 720, "?"), f"Ipsum · uge {U[3]}", _liste(3, 721, True)),
             ]),
             (f"Uge {U[5]} — {EMNER['beta'][4]}", None, "", [
                 (lorem(18, 730, "?"), f"Dolor · uge {U[5]}", _liste(4, 731, True)),
             ]),
         ],
         "resultat": {1: "sad", 2: "halvt"}, "proever": []},
    ]


# ── fagnoterne (Word, udfyldt efter ugen; eksporten læser dem som html) ──
# (fag, kursusuge) → (i egne ord, uafklaret spørgsmål / typiske fejl for Gamma)

FAGNOTER = {(fag, k): (lorem(22, 800 + i * 10 + k), lorem(10, 805 + i * 10 + k, "?") if fag != "gamma"
                       else [f"{lorem(6, 807 + k, '')} `lorem` {lorem(4, 808 + k, '').lower()}.", lorem(10, 809 + k)])
            for i, fag in enumerate(("alfa", "beta", "gamma")) for k in (3, 4, 5)}
FN_UDEN_SLIDES = {("beta", 5)}   # "Slides til uge N var ikke uploadet"


def _fn_label(navn: str, graa: str | None = None) -> str:
    return (f'<h4 class="fn-label"><strong>{navn}</strong>'
            + (f' <span class="fn-graa"><em>{graa}</em></span>' if graa else "") + "</h4>")


def fagnote_html(fag: str, k: int, U: dict) -> str:
    p = PLAN[fag][k]
    egne, sidst = FAGNOTER[(fag, k)]
    ud = []
    if (fag, k) in FN_UDEN_SLIDES:
        ud.append(f'<p><span class="fn-graa">Slides til uge {U[k]} var ikke uploadet; lorem ipsum dolor.</span></p>')
    ud.append(_fn_label("Kilder"))
    ud.append(f"<p>{inline(' · '.join(p['kilder']))}</p>")
    ud.append(_fn_label("Kernebegreber", "lorem ipsum dolor"))
    if fag == "gamma":
        tekst = re.sub(r"```js\n[\s\S]*?```", "", p["noter"]).strip()
        ud.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in tekst.split("\n\n") if x.strip()) + "</ul>")
    else:
        ud.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in p["noter"]) + "</ul>")
    ud.append(_fn_label("I egne ord"))
    ud.append(f"<p>{inline(egne)}</p>")
    if fag == "gamma":
        ud.append(_fn_label("Syntaks og eksempler"))
        ud.append(f"<pre><code>{_esc(GAMMA_KODE[k])}</code></pre>")
        ud.append(_fn_label("Typiske fejl"))
        ud.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in sidst) + "</ul>")
        ud.append(_fn_label("Modeller"))
        ud.append("<p>Lorem ipsum.</p>")
    else:
        ud.append(_fn_label("Modeller"))
        if (fag, k) == ("alfa", 4):
            ud.append('<p class="fn-midt"><img src="fagnoter/is/lorem-ipsum.svg" alt="Diagram: Lorem, Ipsum, Dolor og Amet" '
                      'loading="lazy"></p>')
            ud.append(f'<p class="fn-midt"><span class="fn-graa">{lorem(12, 850)}</span></p>')
        elif (fag, k) == ("alfa", 5):
            ud.append(f"<p>{lorem(16, 855)} <code>Alfa/Modeller/lorem-ipsum.drawio</code>.</p>")
        else:
            ud.append("<p>Lorem ipsum.</p>")
        ud.append(_fn_label("Uafklaret"))
        ud.append(f"<ul><li>{inline(sidst)}</li></ul>")
    return "\n".join(ud)


DIAGRAM_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="720" height="190" viewBox="0 0 720 190" font-family="Helvetica, Arial, sans-serif" font-size="13">
<rect width="720" height="190" fill="#fff"/>
<g fill="none" stroke="#333" stroke-width="1.5">
<line x1="150" y1="80" x2="200" y2="80"/><line x1="330" y1="80" x2="380" y2="80"/><line x1="530" y1="80" x2="580" y2="80"/>
</g>
<g fill="#333" font-size="12"><text x="156" y="72">1</text><text x="186" y="72">N</text>
<text x="336" y="72">1</text><text x="366" y="72">N</text><text x="536" y="72">N</text><text x="566" y="72">1</text></g>
<g stroke="#333" stroke-width="1.5" fill="#f5f5f5">
<rect x="20" y="40" width="130" height="110" rx="6"/><rect x="200" y="40" width="130" height="110" rx="6"/>
<rect x="380" y="40" width="150" height="110" rx="6"/><rect x="580" y="40" width="120" height="110" rx="6"/>
</g>
<g font-weight="bold" fill="#111"><text x="30" y="62">Lorem</text><text x="210" y="62">Ipsum</text>
<text x="390" y="62">Dolor</text><text x="590" y="62">Amet</text></g>
<g fill="#333"><text x="30" y="88" text-decoration="underline">LoremID</text><text x="30" y="108">Sit</text><text x="30" y="128">Elit</text>
<text x="210" y="88" text-decoration="underline">IpsumID</text><text x="210" y="108">Sed</text><text x="210" y="128">LoremID</text>
<text x="390" y="88" text-decoration="underline">IpsumID, AmetID</text><text x="390" y="108">Tempor</text><text x="390" y="128">Labore</text>
<text x="590" y="88" text-decoration="underline">AmetID</text><text x="590" y="108">Magna</text><text x="590" y="128">Aliqua</text></g>
<text x="20" y="178" fill="#666" font-size="11">Lorem ipsum dolor sit amet.</text>
</svg>
"""

# ── kalenderen (overbliks kalender; eksporten skriver kun den del i kalender.json) ──
# Bruges kun, når form-modulet ikke har skrevet ud/form/liv.json. Undervisningen ligger i de faste moduler
# 08:15–10:00, 10:15–12:00, 13:00–14:45 og 15:00–16:45.

SKEMA = [  # (ugedag, start, slut, fag, art, form)
    (0, "08:15", "10:00", "alfa", "Lecture", "On Campus"),
    (0, "10:15", "12:00", "alfa", "Exercise", "On Campus"),
    (1, "10:15", "12:00", "gamma", "Lecture", "Online"),
    (1, "13:00", "14:45", "gamma", "Exercise", "On Campus"),
    (2, "08:15", "10:00", "beta", "Lecture", "On Campus"),
    (2, "13:00", "14:45", "beta", "Exercise", "On Campus"),
    (3, "15:00", "16:45", "gamma", "Exercise", "On Campus"),
]
ANDET = [  # (ugedag, start, slut, titel, hvilke uger: offset fra denne uge, eller None for alle)
    (0, "18:30", "20:00", "Lorem ipsum dolor", None),
    (4, "16:00", "21:00", "Sit amet", None),
    (3, "17:15", "18:00", "Consectetur adipiscing", (-1, 0)),
    (5, None, None, "Sed do eiusmod", (1,)),
    (6, "11:00", "13:00", "Tempor incididunt", (-1,)),
    (4, "09:00", "09:30", "Ut labore", (1,)),
]
SELVSTUDIE = [  # (ugedag, start, slut, titel); "Selvstudie · " er præfikset, overblik kender selvstudie på
    (0, "13:00", "14:00", "Selvstudie · Alfa"),
    (1, "15:00", "16:30", "Selvstudie · Gamma"),
    (3, "10:00", "11:30", "Selvstudie · Gamma"),
    (4, "10:00", "12:00", "Selvstudie · Beta"),
    (6, "15:00", "16:30", "Selvstudie · Beta"),
]


def _ugens_kalender(m: date, offset: int, idag: date) -> list:
    fag = {f["id"]: f for f in FAG}
    ev = []
    for dag, start, slut, f, art, form in SKEMA:
        x = fag[f]
        ev.append({"dato": (m + timedelta(days=dag)).isoformat(), "start": start, "slut": slut,
                   "titel": f"{x['navn']} ({x['hold']}) - {x['kode']}.{x['hold']} - {art} ({form})",
                   "heldag": False, "type": "undervisning"})
    for dag, start, slut, titel, uger in ANDET:
        if uger is None or offset in uger:
            ev.append({"dato": (m + timedelta(days=dag)).isoformat(), "start": start, "slut": slut, "titel": titel,
                       "heldag": start is None, "type": "andet"})
    for dag, start, slut, titel in SELVSTUDIE:
        d = m + timedelta(days=dag)
        if d < idag:
            ev.append({"dato": d.isoformat(), "start": start, "slut": slut, "titel": titel, "heldag": False,
                       "type": "selvstudie"})
    return sorted(ev, key=lambda e: (e["dato"], e["start"] or ""))


def kalender(idag: date) -> dict:
    """Kalenderen, som kalender.json har den (samme form som "kalender" og "reviews" i overbliks liv.json).

    Bruges kun, når form-modulet ikke har skrevet ud/form/liv.json."""
    m0 = mandag(idag)
    nu = datetime.combine(idag, datetime.min.time()).replace(hour=7, minute=30)
    return {
        "genereret": nu.strftime("%Y-%m-%dT%H:%M:%S"),
        "selvstudie_fra": (m0 - timedelta(days=14)).isoformat(),
        "kalender": {(m0 + timedelta(days=7 * o)).isoformat(): _ugens_kalender(m0 + timedelta(days=7 * o), o, idag)
                     for o in (-1, 0, 1)},
        "reviews": [{"mandag": (m0 - timedelta(days=14)).isoformat(),
                     "kalender": _ugens_kalender(m0 - timedelta(days=14), -2, idag),
                     "kommende": _ugens_kalender(m0 - timedelta(days=7), -1, idag)}],
    }

# ── opbygning ────────────────────────────────────────────────────────

INTERVAL = {"sad": 21, "halvt": 2, "blankt": 1}   # dage til næste gang (✓ som tredje ✓ i træk: 21 dage)
MARK_RES = {"✓": "sad", "~": "halvt", "✗": "blankt"}
KL = ["07:42", "12:18", "20:05", "21:31", "16:47"]


def query_navn(params: dict) -> str:
    """Filnavnet for et GET-kald med query: parametrene sorteret og procent-kodet, fx fag=is&fil=x.md&nr=3."""
    return "&".join(f"{k}={quote(str(v), safe='')}" for k, v in sorted(params.items()))


def mandag_i_uge(aar: int, u: int) -> date:
    jan4 = date(aar, 1, 4)
    return jan4 - timedelta(days=jan4.weekday()) + timedelta(days=7 * (u - 1))


def deadline(r: dict, aar: int, plan_uge: int = 40) -> dict:
    """En række fra en Deadlines-tabel, som deadline() i kompas-eksport.js læser den."""
    uger = [int(x) for x in re.findall(r"\d+", r.get("Uge") or "")]
    if uger and uger[0] < 26 and plan_uge >= 26:
        aar += 1
    hvad = r.get("Aktivitet") or r.get("Hvad") or ""
    ren = re.sub(r"\*\*|`", "", hvad)
    typ = ("proeve" if re.search("prøveeksamen", ren, re.I) else "aflevering" if re.search(r"\bopgave \d+\b|aflever", ren, re.I)
           else "praesentation" if re.search("præsentation", ren, re.I)
           else "eksamen" if re.search(r"stedprøve|eksamen|prøve\b", ren, re.I) else "ferie" if re.search("ferie", ren, re.I)
           else "andet")
    fra = mandag_i_uge(aar, uger[0]) if uger else None
    til = mandag_i_uge(aar, uger[-1]) + timedelta(days=6) if uger else None
    kilde = r["Dato"] if r.get("Dato") is not None else ren
    interval = r.get("Dato") is not None and re.search(r"\d\.?\s*[-–]\s*\d", r["Dato"])
    praecis = None if interval else re.search(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?(?!\d)", kilde)
    dato = None
    if praecis and fra:
        d = date(int(praecis.group(3)) if praecis.group(3) else aar, int(praecis.group(2)), int(praecis.group(1)))
        if fra - timedelta(days=1) <= d <= til + timedelta(days=1):
            dato = d
    t = re.search(r"kl\.\s*(\d{1,2})[:.](\d{2})(?:\s*[-–]\s*(\d{1,2})[:.](\d{2}))?", ren)
    tid = (f"{t.group(1).zfill(2)}.{t.group(2)}" + (f"–{t.group(3).zfill(2)}.{t.group(4)}" if t.group(3) else "")) if t else None
    fag = (r.get("Fag") or "").strip()
    return {"uger": r.get("Uge") or "", "dato_tekst": r.get("Dato") or None,
            "fag": "Alle" if re.match(r"^(—|–|-|alle)?$", fag, re.I) else fag, "hvad": inline(hvad),
            "note": inline(r["Bemærkning"]) if r.get("Bemærkning") else None, "type": typ,
            "fra": fra.isoformat() if fra else None, "til": til.isoformat() if til else None,
            "dato": dato.isoformat() if dato else None, "tid": tid}


def eksamensdage(idag: date) -> tuple:
    """Eksamenerne: Alfa en tirsdag om ca. 7 uger, Gamma en fredag om ca. 14 uger."""
    return mandag(idag + timedelta(days=49)) + timedelta(days=1), mandag(idag + timedelta(days=98)) + timedelta(days=4)


class Studie:
    def __init__(self, idag: date):
        self.idag = idag
        self.m0 = mandag(idag)
        self.M = {k: self.m0 + timedelta(days=7 * (k - NU)) for k in range(1, 8)}   # kursusuge → mandag
        self.U = {k: uge(m) for k, m in self.M.items()}                               # kursusuge → ugenummer
        self.nu = datetime.now() if idag == date.today() else datetime.combine(idag, datetime.min.time()).replace(hour=8)

    def tid(self, dage: int, i: int = 0) -> datetime:
        """Et tidspunkt for et forsøg, dage siden (i vælger klokkeslæt)."""
        h, m = (int(x) for x in KL[i % len(KL)].split(":"))
        t = datetime.combine(self.idag - timedelta(days=dage), datetime.min.time()).replace(hour=h, minute=m)
        return min(t, self.nu - timedelta(minutes=20 + i))

    @staticmethod
    def iso(t: datetime) -> str:
        return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # ── frister ──
    # Rækkerne er dem, eksporten læser i ugeplanens Deadlines-tabel (med Dato-kolonne) og i semestermappens
    # CLAUDE.md under "Vigtige datoer" (datoen står i teksten). deadline() gør det samme som i kompas-eksport.js.
    def deadlines(self) -> list:
        idag, M = self.idag, self.M

        def dato(d, aar=False):   # "07.10", med år for eksamener, og når ugen hører til et andet år
            return ddmm(d) + (f".{d.year}" if aar or d.isocalendar()[0] != d.year else "")

        def dag(d, aar=False):    # "onsdag 07.10"
            return f"{DAGE[d.weekday()]} {dato(d, aar)}"

        o1, o2, o3, o4 = M[3] + timedelta(days=3), M[5] + timedelta(days=4), idag + timedelta(days=4), idag + timedelta(days=20)
        kontrakt, beta_case, projekt = M[2] + timedelta(days=4), idag + timedelta(days=15), idag + timedelta(days=10)
        ferie, praes = mandag(idag + timedelta(days=25)), mandag(idag + timedelta(days=29))
        alfa_eks, gamma_eks = eksamensdage(idag)
        fs = ferie + timedelta(days=6)
        rk = [   # (ugens dag, række, færdig)
            (kontrakt, {"Fag": "Beta", "Aktivitet": "Lorem ipsum dolor afleveres", "Dato": dato(kontrakt),
                        "Bemærkning": lorem(4, 900)}, (kontrakt - timedelta(days=1)).isoformat()),
            (o1, {"Fag": "Gamma", "Hvad": f"**Opgave 1** (lorem ipsum) afleveres — **{dag(o1)} kl. 14:00**, dolor sit amet"},
             ddmm(o1 - timedelta(days=1))),
            (o2, {"Fag": "Gamma", "Hvad": f"**Opgave 2** (dolor sit) afleveres — **{dag(o2)} kl. 14:00**, dolor sit amet"},
             ddmm(o2)),
            (o3, {"Fag": "Gamma", "Hvad": f"**Opgave 3** (amet consectetur) afleveres — **{dag(o3)} kl. 14:00**, dolor sit amet",
                  "Bemærkning": lorem(6, 901)}, None),
            (projekt, {"Fag": "Alfa", "Hvad": "**Lorem ipsum** afleveres (gruppe, PDF)"}, None),
            (beta_case, {"Fag": "Beta", "Aktivitet": "**Dolor sit amet** afleveres kl. 10:00: consectetur adipiscing",
                        "Dato": dato(beta_case)}, None),
            (ferie, {"Fag": "—", "Aktivitet": "Lorem ipsum-ferie, ingen undervisning",
                     "Dato": f"{ferie.day:02d}.-{fs.day:02d}.{fs.month:02d}"}, None),
            (o4, {"Fag": "Gamma", "Hvad": "**Opgave 4** (sed do eiusmod) afleveres"}, None),
            (praes, {"Fag": "Alfa", "Hvad": "**Præsentation af lorem ipsum** i øvelsestimen, forudsætning for eksamen",
                     "Uge": f"{uge(praes)}-{uge(praes + timedelta(days=7))}"}, None),
            (alfa_eks, {"Fag": "Alfa", "Hvad": f"**Eksamen: lorem ipsum (2 t)** — **{dag(alfa_eks, True)} kl. 10:00-12:00**, "
                                           "dolor sit amet"}, None),
            (gamma_eks, {"Fag": "Gamma", "Hvad": f"**Eksamen: lorem ipsum (4 t)** — **{dag(gamma_eks, True)} "
                                               "kl. 13:00-17:00**, dolor sit amet"}, None),
        ]
        ud = []
        for d, r, faerdig in rk:
            r.setdefault("Uge", str(uge(d)))
            x = deadline(r, d.isocalendar()[0], uge(d))
            nr = re.search(r"\bopgave (\d+)\b", re.sub(r"<[^>]+>", "", x["hvad"]), re.I)
            u = re.search(r"\d+", x["uger"])
            x["noegle"] = f"{x['fag']}|Opgave {nr.group(1)}" if nr else f"{x['fag']}|{x['type']}|{u.group(0) if u else ''}"
            x["faerdig"] = faerdig
            ud.append(x)
        ud.sort(key=lambda x: x["dato"] or x["fra"])
        self.o1, self.o2, self.o3, self.o4 = o1, o2, o3, o4
        return ud

    def proeveplan(self) -> list:
        alfa_eks, gamma_eks = (mandag(d) for d in eksamensdage(self.idag))

        def p(fag, hvad, fra):
            return {"uger": str(uge(fra)), "fag": fag, "hvad": inline(hvad), "fra": fra.isoformat(),
                    "til": (fra + timedelta(days=6)).isoformat()}

        return sorted([p("Alfa", "Prøveeksamen 1 (2 t, lorem ipsum)", alfa_eks - timedelta(days=21)),
                       p("Alfa", "Prøveeksamen 2 (2 t)", alfa_eks - timedelta(days=7)),
                       p("Gamma", "Prøveeksamen 1 (4 t, lorem ipsum)", gamma_eks - timedelta(days=35)),
                       p("Gamma", "Prøveeksamen 2 (4 t)", gamma_eks - timedelta(days=14))], key=lambda x: x["fra"])

    # ── ugeplaner ──
    def planer(self) -> list:
        ud = []
        sidste = NU + (1 if self.idag.weekday() >= 5 else 0)   # næste uges plan skrives søndag
        for k in range(3, sidste + 1):
            fra, til = self.M[k], self.M[k] + timedelta(days=6)
            u = self.U[k]
            interval = (f"{fra.day:02d}-{til.day:02d}{MDR[til.month - 1]}" if fra.month == til.month
                        else f"{fra.day:02d}{MDR[fra.month - 1]}-{til.day:02d}{MDR[til.month - 1]}")
            plan = {"uge": u, "aar": til.year, "fil": f"Uge_Overblik/Ugeplan_uge{u}_{interval}_{til.year}.md",
                    "titel": f"Køreplan uge {u} · {fra.day}. {MDR_LANG[fra.month - 1]} – {til.day}. {MDR_LANG[til.month - 1]} {til.year}",
                    "fra": fra.isoformat(), "til": til.isoformat(),
                    "ændret": self.iso(min(datetime.combine(fra - timedelta(days=1), datetime.min.time()).replace(hour=18, minute=7),
                                           self.nu - timedelta(minutes=30))),
                    "fag": {}, "vigtigst": None, "genkaldelse": None, "øvrigt": []}
            for f in FAG:
                p = PLAN[f["id"]][k]
                a = {"overskrift": f["navn"], "Hurtigt overblik": md(p["overblik"]),
                     "Kilder": md("\n".join(f"- {x}" for x in p["kilder"]))}
                noter = p["noter"] if isinstance(p["noter"], str) else "\n".join(f"- {x}" for x in p["noter"])
                if p.get("oevelse"):
                    spm = "*Øvelsesspørgsmål (svar på papir, før du kigger):*\n\n" + "\n".join(
                        f"{i}. {q}" for i, (q, _) in enumerate(p["oevelse"], 1))
                    svar = "\n".join(f"{i}. {s}" for i, (_, s) in enumerate(p["oevelse"], 1))
                    a["oevelse"] = {"spoergsmaal": md(spm), "svar": md(svar)}
                    noter += f"\n\n{spm}\n\n*Svar:*\n\n{svar}"
                a["Noter til pensum"] = md(noter)
                if p.get("rapport"):
                    a["Til rapporten"] = md(p["rapport"])
                plan["fag"][f["id"]] = a
            plan["vigtigst"] = md("\n".join(f"- {x}" for x in VIGTIGST[k]).replace(
                "{o3}", f"{DAGE[self.o3.weekday()]} {self.o3.day}. {MDR_LANG[self.o3.month - 1]}"))
            if k in GENKALDELSE:
                spm = "\n".join(f"{i}. {q}" for i, (q, _) in enumerate(GENKALDELSE[k], 1))
                svar = "\n".join(f"{i}. {s}" for i, (_, s) in enumerate(GENKALDELSE[k], 1))
                plan["genkaldelse"] = {"titel": f"Genkaldelse fra uge {self.U[k - 1]}",
                                       "html": md(f"{spm}\n\n*Svar:*\n\n{svar}"), "spoergsmaal": md(spm), "svar": md(svar)}
            ud.append(plan)
        return ud

    # ── genkald ──
    def genkald(self) -> list:
        """Som GET /studie/api/genkald, plus _facit (facit), _k (kursusuge) og _fi (filnummer) til eget brug."""
        ud = []
        for fag in ("alfa", "beta"):
            for fi, qs in enumerate(GENKALD[fag]):
                a, b = self.U[qs[0][0]], self.U[qs[-1][0]]
                fil = f"genkald-uge{a}-{b}.md"
                uger = f"uge {a}" if a == b else f"uge {a}–{b}"
                spm = []
                for nr, (k, tekst, facit) in enumerate(qs, 1):
                    m = MARKERINGER.get((fag, fi, nr))
                    t = self.tid(m[1], nr) if m else None
                    spm.append({"nr": nr, "afsnit": f"Uge {self.U[k]} — {EMNER[fag][k - 1]}", "tekst": tekst,
                                "mark": m[0] if m else None, "svar": m[2] if m and m[2] else None,
                                "dato": ddmm(t.date()) if m and m[2] else None, "uge": self.U[k],
                                "sidst": self.iso(t) if t else None, "_k": k, "_facit": facit})
                ud.append({"fag": fag, "fil": fil, "titel": f"Genkald {FAGNAVN[fag]} — {uger}", "uger": uger,
                           "har_facit": True, "spoergsmaal": spm, "_fi": fi})
        return ud

    def laest(self) -> dict:
        return {fag: {str(self.U[k]): min(self.M[k] + timedelta(days=6), self.idag - timedelta(days=1)).isoformat()
                      for k in ks} for fag, ks in LAEST.items()}

    # ── begreber ──
    def begreber(self) -> dict:
        ud = {}
        for fag in ("alfa", "beta"):
            rows = []
            for i, (k, navn, d, se, kilde) in enumerate(BEGREBER[fag]):
                h = self.begreb_historik(fag, navn, i)
                rows.append({"begreb": navn, "definition": d, "se": se if fag == "beta" else None, "kilde": kilde,
                             "afsnit": f"Uge {self.U[k]} — {EMNER[fag][k - 1]}",
                             "sidst": self.iso(h[1]) if d else None})
            ud[fag] = {"hoved_se": "Hvad det får dig til at se" if fag == "beta" else None, "begreber": rows}
        return ud

    def begreb_historik(self, fag: str, navn: str, i: int):
        """(niveau, sidst, interval i dage) for et begreb med definition."""
        if (fag, navn) in BEGREB_FORFALDEN:
            niveau, dage, interval = BEGREB_FORFALDEN[(fag, navn)]
            return niveau, self.tid(dage, i), interval
        if navn in BEGREB_I_MORGES:   # overhørt i morges
            return 3, self.tid(0, 0), 21
        return 3, self.tid(5 + i % 4, i), 21

    # ── drills ──
    def drills(self) -> list:
        """Som GET /studie/api/drills, plus kildeteksten (_kilde) til at afprøve drillene med node."""
        ud = []
        navne = re.compile(r"(?<![.\w$])[A-Za-z_$][\w$]*", re.ASCII)
        for fil, titel, kap, spec in DRILLS:
            linjer = [f"// {titel}", f"// Uge {self.U[kap]}", "//", f"// Kør:  node --watch Drills/{fil}", "//",
                      "// Erstat TOM med dit gæt på, hvad udtrykket giver. Gæt først, kør bagefter.", "",
                      'const { tjek, TOM, opsummer } = require("./tjek.js");', ""]
            defs, tjek, stubbe, afsnit = [], [], [], ""
            for item in spec:
                if item[0] == "kode":
                    defs.append((re.match(r"(?:function|const)\s+(\w+)", item[1]).group(1), item[1]))
                    linjer += item[1].split("\n") + [""]
                elif item[0] == "afsnit":
                    afsnit = item[1]
                    if linjer[-1]:
                        linjer.append("")
                    linjer += [f"// ── {afsnit} " + "─" * max(4, 66 - len(afsnit)), ""]
                elif item[0] == "stub":
                    start = len(linjer) + 1
                    linjer += item[1].split("\n") + [""]
                    for j, l in enumerate(item[1].split("\n")):
                        if "DIN KODE HER" in l:
                            stubbe.append({"linje": start + j, "navn": re.search(r"function (\w+)", item[1]).group(1)})
                else:
                    _, besk, udtryk, gaet, js = item
                    # Koden fra filen, udtrykket bruger (funktioner og konstanter øverst i filen)
                    valgt, koe = [], list(navne.findall(udtryk))
                    while koe:
                        n = koe.pop()
                        for dn, dk in defs:
                            if dn == n and (dn, dk) not in valgt:
                                valgt.append((dn, dk))
                                koe += navne.findall(dk)
                    kontekst = "\n\n".join(dk for dn, dk in defs if (dn, dk) in valgt) or None
                    status = "tom" if gaet is None else "rigtig" if gaet == js else "forkert"
                    nogle = re.sub(r"\s*←.*$", "", besk).strip()
                    tjek.append({"linje": len(linjer) + 1, "afsnit": afsnit, "beskrivelse": besk, "udtryk": udtryk,
                                 "kontekst": kontekst, "gaet": gaet, "status": status,
                                 "javascript": js if status == "forkert" else None,
                                 "forklaring": FORKLARINGER.get(nogle) if gaet is not None else None, "_js": js})
                    linjer.append(f"tjek({json.dumps(besk, ensure_ascii=False)}, {udtryk}, {gaet or 'TOM'});")
            linjer += ["", "opsummer();", ""]
            ok = sum(t["status"] == "rigtig" for t in tjek)
            fejl = sum(t["status"] == "forkert" for t in tjek)
            tom = sum(t["status"] == "tom" for t in tjek)
            ud.append({"fil": fil, "titel": titel, "sti": f"/Users/alex/Studie/Gamma/vscode/Drills/{fil}", "tjek": tjek,
                       "stubbe": stubbe, "opsum": f"{ok} rigtige · {fejl} forkerte · {tom} ikke udfyldt (af {len(tjek)})",
                       "crash": None, "_kilde": "\n".join(linjer)})
        return ud

    # ── eksamen ──
    def eksamen(self) -> list:
        ud = []
        for s in eksamenssaet(self.U):
            meta = s["meta"]
            t, mi = re.search(r"(\d+)\s*time", meta, re.I), re.search(r"(\d+)\s*min", meta, re.I)
            varighed = int(t.group(1)) * 60 if t else int(mi.group(1)) if mi else None
            sektioner, nr = [], 0
            for titel, vaegt, intro, qs in s["sektioner"]:
                spm = []
                for tekst, emne, facit in qs:
                    nr += 1
                    u, kap = re.search(r"uge\s+(\d+)", emne, re.I), re.search(r"kap\.?\s*(\d+)", emne, re.I)
                    spm.append({"nr": nr, "tekst": tekst, "emne": emne, "uge": int(u.group(1)) if u else None,
                                "kap": int(kap.group(1)) if kap else None, "_facit": facit})
                sektioner.append({"titel": titel, "vaegt": vaegt, "intro": intro, "spoergsmaal": spm})
            res = {"sad": 0, "halvt": 0, "blankt": 0}
            for v in s["resultat"].values():
                res[v] += 1
            ud.append({**s, "varighed": varighed, "sektioner": sektioner, "res": res})
        return ud

    # ── repetition (Dagens kort) ──
    def repetition(self, G: list, B: dict, D: list, E: list) -> tuple:
        dag_slut = datetime.combine(self.idag, datetime.max.time())
        laest = {fag: set(int(u) for u in ugr) for fag, ugr in self.laest().items()}
        alle, svar = [], {}
        for f in G:
            for q in f["spoergsmaal"]:
                noegle = f"{f['fag']}/{f['fil']}#{q['nr']}"
                kort = {"type": "genkald", "noegle": noegle, "fag": f["fag"], "uge": q["uge"],
                        "laest": q["uge"] in laest[f["fag"]], "kicker": f"{FAGNAVN[f['fag']]} · {f['uger']} · {q['afsnit']}",
                        "titel": f"Spørgsmål {q['nr']}", "spoergsmaal": q["tekst"], "ny": not q["mark"]}
                if q["mark"]:
                    res = MARK_RES[q["mark"]]
                    sidst = datetime.strptime(q["sidst"], "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
                    kort.update(niveau=3 if res == "sad" else 0, _sidst=sidst, _forfald=sidst + timedelta(days=INTERVAL[res]))
                alle.append(kort)
                svar[f"genkald:{noegle}"] = {"svar": q["_facit"], "form": "md"}
        for fag in ("alfa", "beta"):
            for i, b in enumerate(B[fag]["begreber"]):
                if not b["definition"]:
                    continue
                niveau, sidst, interval = self.begreb_historik(fag, b["begreb"], i)
                noegle = f"{fag}/begreb/{b['begreb']}"
                alle.append({"type": "begreb", "noegle": noegle, "fag": fag, "kicker": f"{FAGNAVN[fag]} · begreb · {b['afsnit']}",
                             "titel": b["begreb"], "spoergsmaal": f"Forklar **{b['begreb']}** med dine egne ord"
                             + (", og sig hvad det får dig til at se i en organisation" if fag == "beta" else "") + ".",
                             "niveau": niveau, "_sidst": sidst, "_forfald": sidst + timedelta(days=interval)})
                svar[f"begreb:{noegle}"] = {"svar": b["definition"], "se": b["se"] or None, "form": "tekst"}
        for k in D:
            for t in k["tjek"]:
                n = re.sub(r"\s*←.*$", "", t["beskrivelse"]).strip()
                h = DRILL_FORFALDEN.get((k["fil"], n))
                if not h or not t["udtryk"]:
                    continue
                sidst = self.tid(h[1], len(n))
                noegle = f"drill/{k['fil']}#{t['beskrivelse']}"
                alle.append({"type": "drill", "noegle": noegle, "fag": "gamma",
                             "kicker": f"{FAGNAVN['gamma']} · drill · {k['titel']}", "titel": n, "spoergsmaal": "Hvad giver udtrykket?",
                             "udtryk": t["udtryk"], "kontekst": t["kontekst"], "niveau": h[0], "_sidst": sidst,
                             "_forfald": sidst + timedelta(days=h[2])})
                svar[f"drill:{noegle}"] = {"svar": t["javascript"] if t["status"] == "forkert" else t["gaet"], "form": "kode",
                                           "forklaring": FORKLARINGER.get(n)}
        oevet = {"alfa": 1, "beta": 3, "gamma": 0}   # dage siden øvelsen i sættet
        for s in E:
            for sek in s["sektioner"]:
                for q in sek["spoergsmaal"]:
                    res = s["resultat"].get(q["nr"])
                    noegle = f"{s['fag']}/{s['id']}#{q['nr']}"
                    if not res or res == "sad":
                        continue
                    svar[f"eksamen:{noegle}"] = {"svar": q["_facit"], "form": "md"}
                    sidst = self.tid(oevet[s["fag"]], q["nr"])
                    alle.append({"type": "eksamen", "noegle": noegle, "fag": s["fag"],
                                 "kicker": f"{FAGNAVN[s['fag']]} · eksamen · {re.sub(r'^[A-Za-z]+ — ', '', s['titel'])} · {sek['titel']}",
                                 "titel": f"Opgave {q['nr']}",
                                 "spoergsmaal": (sek["intro"] + "\n\n" if s["fag"] == "gamma" and sek["intro"] else "") + q["tekst"],
                                 "niveau": 0, "_sidst": sidst, "_forfald": sidst + timedelta(days=INTERVAL[res])})

        forfaldne = sorted((k for k in alle if not k.get("ny") and k["_forfald"] <= dag_slut), key=lambda k: k["_forfald"])
        nye = [k for k in alle if k.get("ny") and k["laest"]][:5]
        venter = [k for k in alle if k.get("ny") and not k["laest"]]
        valgt = forfaldne[:max(0, 25 - len(nye))] + nye
        spor = [[k for k in valgt if k["type"] == t] for t in ("genkald", "eksamen", "begreb", "drill")]
        koe = []
        while any(spor):
            for x in spor:
                if x:
                    koe.append(x.pop(0))
        naeste = min((k["_forfald"] for k in alle if not k.get("ny") and k["_forfald"] > dag_slut), default=None)

        def ud(k):
            o = {x: v for x, v in k.items() if not x.startswith("_")}
            o.update(id=f"{k['type']}:{k['noegle']}", forfald=self.iso(k["_forfald"]) if k.get("_forfald") else None,
                     sidst=self.iso(k["_sidst"]) if k.get("_sidst") else None)
            return o

        kalibrering = {"sikker": {"n": 38, "sad": 30, "halvt": 5, "blankt": 3},
                       "usikker": {"n": 24, "sad": 10, "halvt": 8, "blankt": 6},
                       "gaet": {"n": 11, "sad": 2, "halvt": 2, "blankt": 7}}
        rep = {"kort": [ud(k) for k in koe],
               "statistik": {"forfaldne": len(forfaldne), "nye": len(nye), "nye_venter_paa_laesning": len(venter),
                             "nye_klar": len([k for k in alle if k.get("ny") and k["laest"]]), "klaret_i_dag": 3,
                             "i_alt": len(alle), "laert": len([k for k in alle if not k.get("ny") and k.get("niveau", 0) >= 2]),
                             "naeste": self.iso(naeste) if naeste else None, "kalibrering": kalibrering,
                             "minutter": max(1, round(len(koe) * 0.75))}}
        return rep, svar

    # ── status pr. fag (eksportens optælling) ──
    def fag_status(self, G: list, B: dict, D: list) -> list:
        def akt(filer):
            return [{"fil": f, "ændret": self.iso(self.tid(d, i))} for i, (f, d) in enumerate(filer)]

        ud = []
        for f in FAG:
            fid = f["id"]
            s = {"aktivitet": [], "eksamenssaet": ["Eksamenstræning"] + (["Lorem_ipsum.pdf"] if fid != "beta" else []),
                 "fagnoter": [{"fil": f"Fagnoter - {f['kort']}.docx", "ændret": self.iso(self.tid(2, 3))}]}
            if fid in ("alfa", "beta"):
                rows = B[fid]["begreber"]
                ugr = []
                for r in rows:
                    if not ugr or ugr[-1]["uge"] != r["afsnit"]:
                        ugr.append({"uge": r["afsnit"], "udfyldt": 0, "i_alt": 0})
                    ugr[-1]["i_alt"] += 1
                    ugr[-1]["udfyldt"] += 1 if r["definition"] else 0
                s["begreber"] = {"udfyldt": sum(u["udfyldt"] for u in ugr), "i_alt": len(rows), "uger": ugr,
                                 "ændret": self.iso(self.tid(1, 1))}
                s["genkald"] = []
                for g in (x for x in G if x["fag"] == fid):
                    n = {"sad": 0, "halvt": 0, "blankt": 0, "umarkeret": 0}
                    for q in g["spoergsmaal"]:
                        n[MARK_RES[q["mark"]] if q["mark"] else "umarkeret"] += 1
                    s["genkald"].append({"fil": g["fil"], "uger": g["uger"], "spoergsmaal": len(g["spoergsmaal"]), **n,
                                         "ændret": self.iso(self.tid(1 if g["_fi"] == 0 else 2, 2))})
            if fid == "alfa":
                s["modeller"] = 3
                s["aktivitet"] = akt([("Alfa/Genkald/genkald-uge%d-%d.md" % (self.U[1], self.U[3]), 1),
                                      ("Alfa/Genkald/begreber.md", 1), ("Alfa/Modeller/lorem-ipsum.drawio", 2),
                                      ("Alfa/Genkald/genkald-uge%d-%d.md" % (self.U[4], self.U[5]), 2),
                                      ("Alfa/Modeller/dolor-sit.drawio", 4), ("Alfa/Fagnoter - Alfa.docx", 2)])
            elif fid == "beta":
                s["aktivitet"] = akt([("Beta/Genkald/genkald-uge%d-%d.md" % (self.U[1], self.U[2]), 2),
                                      ("Beta/Genkald/begreber.md", 3), ("Beta/Eksamenstræning/besvarelser/ipsum-"
                                      f"{(self.idag - timedelta(days=3)).isoformat()}.md", 3), ("Beta/Fagnoter - Beta.docx", 2)])
            else:
                s["drills"] = [{"fil": k["fil"], "titel": k["titel"], "pladser": len(k["tjek"]),
                                "tomme": sum(t["status"] == "tom" for t in k["tjek"]),
                                "gættet": sum(t["status"] != "tom" for t in k["tjek"]), "stubbe": len(k["stubbe"]),
                                "ændret": self.iso(self.tid(1 + i * 3, i))} for i, k in enumerate(D)]
                s["oevelser_i_gang"] = ["lorem.js"]
                s["oevelser_faerdige"] = 7
                rk = []
                for i in range(1, 7):
                    u = {1: uge(self.o1), 2: uge(self.o2), 3: uge(self.o3), 4: uge(self.o4)}.get(i) or uge(self.idag + timedelta(days=7 * (i + 1)))
                    afl = {1: ddmm(self.o1 - timedelta(days=1)), 2: ddmm(self.o2)}.get(i)
                    rk.append({"opgave": f"Opgave {i}", "uge": str(u), "afleveret": afl,
                               "godkendt": "Ja" if i == 1 else "–" if i == 2 else None,
                               "drillede": lorem(3, 950 + i) if i <= 2 else None, "mappe": i <= 3})
                s["afleveringer"] = {"raekker": rk, "afleveret": 2, "godkendt": 1, "krav": 4, "ud_af": 6}
                s["aktivitet"] = akt([("Gamma/vscode/Opgaver/Opgave 3/lorem.js", 0), ("Gamma/vscode/lorem.js", 1),
                                      ("Gamma/vscode/Drills/kap04-amet.js", 1), ("Gamma/vscode/Opgaver/README.md", 2),
                                      ("Gamma/vscode/Drills/kap03-dolor.js", 3), ("Gamma/vscode/Øvelser/ipsum.js", 4),
                                      ("Gamma/vscode/Opgaver/Opgave 3/rapport.md", 0)])
                s["aktivitet"].sort(key=lambda a: a["ændret"], reverse=True)
            if fid != "gamma":
                s["aktivitet"].sort(key=lambda a: a["ændret"], reverse=True)
            ud.append({"id": fid, "kort": f["kort"], "navn": f["navn"], "eksamen": EKSAMENSFORM[fid], "status": s})
        return ud


def _skriv(sti: Path, data) -> None:
    sti.parent.mkdir(parents=True, exist_ok=True)
    sti.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")


def lav(ud: Path, idag: date) -> None:
    """Skriver Studies demodata under ud/studie."""
    S = Studie(idag)
    rod, api = ud / "studie", ud / "studie" / "api"

    def svar(navn: str, data, **query) -> None:
        _skriv(api / navn / f"{query_navn(query)}.json" if query else api / f"{navn}.json", data)

    deadlines = S.deadlines()
    planer = S.planer()
    G, B, D, E = S.genkald(), S.begreber(), S.drills(), S.eksamen()
    rep, rep_svar = S.repetition(G, B, D, E)
    genereret = S.iso(S.nu - timedelta(minutes=12))

    # ── eksportens filer ──
    fag = S.fag_status(G, B, D)
    studie = {"genereret": genereret, "uge_nu": S.U[NU], "aktuel_uge": S.U[NU], "planer": planer,
              "deadlines": deadlines, "deadline_kilde": f"{planer[-1]['fil']} og CLAUDE.md", "proeveplan": S.proeveplan(),
              "fag": fag}
    _skriv(rod / "studie.json", studie)
    fn = {}
    for f in FAG:
        fn[f["id"]] = {"fil": f"{f['kort']}/Fagnoter - {f['kort']}.docx", "ændret": S.iso(S.tid(2, 3)),
                       "stempel": f"{int(S.tid(2, 3).timestamp() * 1000)}:{(310 + 47 * len(f['id'])) * 1024}",
                       "uger": {str(S.U[k]): {"titel": f"Uge {S.U[k]} — {EMNER[f['id']][k - 1]}", "udfyldt": True,
                                              "kun_bog": (f["id"], k) in FN_UDEN_SLIDES, "html": fagnote_html(f["id"], k, S.U)}
                                for k in (3, 4, 5)}}
    _skriv(rod / "fagnoter.json", fn)
    _skriv(rod / "fagnoter" / "alfa" / "lorem-ipsum.svg", DIAGRAM_SVG)
    # Som eksporten: kun kalenderdelen af overbliks liv.json (form-modulet skriver den først). Uden den bruges
    # demoens egen kalender.
    try:
        liv = json.loads((ud / "form" / "liv.json").read_text(encoding="utf-8"))
        kal = {"genereret": liv.get("genereret"), "selvstudie_fra": liv.get("selvstudie_fra") or None,
               "kalender": liv.get("kalender") or {},
               "reviews": [{"mandag": r.get("mandag"), "kalender": r.get("kalender"), "kommende": r.get("kommende")}
                           for r in liv.get("reviews") or []]}
    except (OSError, ValueError):
        kal = kalender(idag)
    _skriv(rod / "kalender.json", kal)
    fn_uger = sum(1 for f in fn.values() for u in f["uger"].values() if u["udfyldt"])
    nyeste = max(p["uge"] for p in planer)
    frister = "\n".join(sorted(f"{d['noegle']}@{d['dato'] or d['uger']}" for d in deadlines))
    _skriv(rod / "kompas.json", {
        "omraade": "Studie", "ikon": "graduation-cap", "raekkefoelge": 20,
        "kilde": "Studie (Scripts/kompas-eksport.js) · ugeplaner fra køreplan-rutinen", "opdateret": genereret,
        "sider": [
            {"titel": "Ugeoverblik", "ikon": "calendar", "sti": "/studie/", "nyt": f"uge {nyeste}"},
            {"titel": "Fag", "ikon": "book-open", "sti": "/studie/fag.html", "nyt": f"uge {nyeste} · {fn_uger} fagnote-uger"},
            {"titel": "Genkald", "ikon": "brain", "sti": "/studie/genkald.html"},
            {"titel": "Eksamen", "ikon": "file-text", "sti": "/studie/eksamen.html"},
            {"titel": "Deadlines", "ikon": "clipboard-check", "sti": "/studie/deadlines.html",
             "nyt": hashlib.sha1(frister.encode()).hexdigest()[:10]},
        ]})

    # ── API: GET /studie/api/… ──
    ren = lambda o: {k: v for k, v in o.items() if not k.startswith("_")}   # noqa: E731
    genkald = [{**ren(f), "spoergsmaal": [ren(q) for q in f["spoergsmaal"]]} for f in G]
    svar("genkald", genkald)
    forste = None   # det spørgsmål, Genkald-fanen viser først (Alfa, første uforsøgte i filens orden)
    for f in G:
        for q in f["spoergsmaal"]:
            svar("facit", {"facit": q["_facit"]}, fag=f["fag"], fil=f["fil"], nr=q["nr"])
            if f["fag"] == "alfa" and not q["mark"] and not forste:
                forste = q["_facit"]
    svar("facit", {"facit": forste})
    svar("begreber", B)
    svar("drills", [{**ren(k), "tjek": [ren(t) for t in k["tjek"]]} for k in D])
    svar("laest", S.laest())
    svar("repetition", rep)
    for noegle, s in rep_svar.items():
        svar("repetition/svar", s, noegle=noegle)
    svar("repetition/svar", rep_svar[rep["kort"][0]["id"]] if rep["kort"] else {"svar": None, "form": "md"})

    eksamen = []
    for s in E:
        eksamen.append({"fag": s["fag"], "id": s["id"], "titel": s["titel"], "meta": s["meta"], "varighed": s["varighed"],
                        "antal": sum(len(x["spoergsmaal"]) for x in s["sektioner"]),
                        "sektioner": [{"titel": x["titel"], "vaegt": x["vaegt"], "antal": len(x["spoergsmaal"])} for x in s["sektioner"]],
                        "har_facit": True, "resultat": s["res"], "proever": s["proever"]})
        saet = {"titel": s["titel"], "meta": s["meta"], "varighed": s["varighed"], "intro": s["intro"],
                "sektioner": [{"titel": x["titel"], "vaegt": x["vaegt"], "intro": x["intro"],
                               "spoergsmaal": [ren(q) for q in x["spoergsmaal"]]} for x in s["sektioner"]]}
        alle = {str(q["nr"]): q["_facit"] for x in s["sektioner"] for q in x["spoergsmaal"]}
        svar("eksamen/saet", saet, fag=s["fag"], id=s["id"])
        svar("eksamen/facit", {"facit": alle}, fag=s["fag"], id=s["id"])
        for nr, f in alle.items():
            svar("eksamen/facit", {"facit": f}, fag=s["fag"], id=s["id"], nr=nr)
        if s["fag"] == "alfa":   # Eksamen-siden åbner på Alfa; uden query svares med første opgave, som "Øv opgaver" starter på
            svar("eksamen/saet", saet)
            svar("eksamen/facit", {"facit": alle["1"]})
    svar("eksamen", eksamen)

    # På farten: dagens kort med facit, ekstra genkald, tomme begreber og ugættede drills
    i_dag = {k["id"] for k in rep["kort"]}
    laest = {fag: set(int(u) for u in ugr) for fag, ugr in S.laest().items()}
    vaegt = {"✗": 1, "~": 2, "✓": 3}
    kand = [(f, q) for f in G for q in f["spoergsmaal"]
            if f"genkald:{f['fag']}/{f['fil']}#{q['nr']}" not in i_dag and (q["mark"] or q["uge"] in laest[f["fag"]])]
    kand.sort(key=lambda fq: (vaegt.get(fq[1]["mark"], 0), fq[1]["sidst"] or "" if fq[1]["mark"] else ""))
    svar("pakke", {
        "genereret": genereret,
        "kort": [{**k, "facit": rep_svar.get(k["id"])} for k in rep["kort"]],
        "ekstra": [{"id": f"genkald:{f['fag']}/{f['fil']}#{q['nr']}", "type": "genkald",
                    "noegle": f"{f['fag']}/{f['fil']}#{q['nr']}", "fag": f["fag"],
                    "kicker": f"{FAGNAVN[f['fag']]} · {f['uger']} · {q['afsnit']}", "titel": f"Spørgsmål {q['nr']}",
                    "spoergsmaal": q["tekst"], "ny": not q["mark"], "mark": q["mark"],
                    "facit": {"svar": q["_facit"], "form": "md"}} for f, q in kand[:20]],
        "begreber": [{"fag": fag_, "begreb": b["begreb"], "afsnit": b["afsnit"], "kilde": b["kilde"],
                      "se": "" if fag_ == "beta" else None} for fag_ in ("alfa", "beta") for b in B[fag_]["begreber"] if not b["definition"]],
        "drills": [{"fil": k["fil"], "titel": k["titel"], "linje": t["linje"], "afsnit": t["afsnit"], "beskrivelse": t["beskrivelse"],
                    "udtryk": t["udtryk"], "kontekst": t["kontekst"]} for k in D for t in k["tjek"] if t["status"] == "tom"],
        "statistik": {x: rep["statistik"][x] for x in ("klaret_i_dag", "laert", "i_alt", "naeste", "kalibrering")},
    })
