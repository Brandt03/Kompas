"""Demodata for Økonomi (/forbrug/): Forbrug, Scenarier og SU-vagt for den opdigtede studerende Alex.

lav(ud, idag) skriver under ud/forbrug/:
  data.json            i samme form som okonomi/dashboard/export.sh trækker ud af Sure: konti, opsparingsmål,
                       budgetter og posteringerne fra den 1. for 12 måneder siden til idag
  config.json          Forbrug-sidens personlige indstillinger (flyttemåned og banktekst -> modtager)
  state/su.json        SU-vagtens gemte forudsætninger (trækprocent, forventet løn og et par lønsedler)
  state/scenarier.json Scenariers gemte valg (job efter studiet, sabbatår, engangsudgift, afkast osv.)
  kompas.json          menuen, kopieret fra okonomi/dashboard/public/kompas.json

Alex studerer i København, får SU som udeboende, har et studiejob og er flyttet på et tidspunkt i løbet af året.
Alt trækkes tilfældigt, hver gang demoen laves: boligtype før og efter flytningen, flyttemåned, husleje, SU efter
skat, løn, boligstøtte, abonnementer og forbrugsvaner. Beløbene hænger sammen (budgettet passer til
posteringerne, og SU-vagtens lønsedler og trækprocent passer til lønnen), men ligner ikke nogens rigtige økonomi.

Ligger der et rigtigt udtræk fra Sure på maskinen (se RIGTIGE_DATA), læses det kun for at sammenligne: intet fast
beløb i demoen (husleje, SU, boligstøtte, abonnementer, budget, mål, saldi) må ligge inden for 4 % af et af dine
egne faste beløb fra udtrækkets seneste tre år. Lønnen fra et studiejob svinger, så her skal Alex' normale niveau
ligge mindst 15 % fra din typiske månedsløn, og ingen udbetaling må ligge inden for 1 % af en af dine. Rammer en
trækning for tæt, trækkes der igen, og der er altid en udvej, så lav lykkes. Intet fra udtrækket skrives nogen
steder.

Butikskæder og tjenester er almindelige firmaer; arbejdsgiver, udlejere, kollegier, forsikring, caféer og
frisør er opdigtede. Som i Sure er udgifter positive og indtægter negative. Kun standardbiblioteket.
"""
from __future__ import annotations

import bisect
import json
import os
import random
from datetime import date, timedelta
from pathlib import Path

ROD = Path(__file__).resolve().parents[2]
KOMPAS_JSON = ROD / "okonomi" / "dashboard" / "public" / "kompas.json"
_KOMPAS = Path(os.environ.get("KOMPAS_HOME", str(Path.home() / "kompas")))
# Rigtige udtræk, demoen holder sig fra (kun læsning): FORBRUG_RIGTIG_DATA, ellers de sædvanlige steder
RIGTIGE_DATA = [os.environ.get("FORBRUG_RIGTIG_DATA"),
                ROD / "okonomi" / "dashboard" / "public" / "data.json",
                _KOMPAS / "okonomi" / "dashboard" / "public" / "data.json",
                _KOMPAS / "sure" / "dashboard" / "public" / "data.json"]

LOENKONTO, BUDGETKONTO, OPSPARING = "Lønkonto", "Budgetkonto", "Opsparing"
IND, FAST, VAR, FLYT = "Indtægter", "Faste udgifter", "Variable udgifter", "Indflytning"
AM = 0.08
TRK = [x / 2 for x in range(68, 85)]      # trækprocenter 34,0–42,0
SU_BRUTTO_2026 = 7426      # su.dk: SU som udeboende pr. måned før skat, 2026 (offentlig sats)

OMRAADER = ["NØRREBRO", "AMAGER", "VALBY", "VANLØSE", "ØSTERBRO", "SYDHAVN", "BRØNSHØJ", "FREDERIKSBERG",
            "VESTERBRO", "BISPEBJERG", "ØRESTAD"]
KOLLEGIER = [("Solgaarden", "Kollegiet Solgaarden"), ("Engtoft", "Engtoft Kollegium"),
             ("Havrevang", "Havrevang Kollegium"), ("Tranehuset", "Kollegiet Tranehuset"),
             ("Kildebakke", "Kildebakke Kollegium")]
UDLEJERE = [("Kærholm", "Boligselskabet Kærholm"), ("Fjordlys", "Ejendomsselskabet Fjordlys"),
            ("Nordvest", "Bolig Nordvest"), ("Søbred", "Administrationsselskabet Søbred")]
ARBEJDSGIVERE = ["Kvadrat Data ApS", "Brobyg Consulting ApS", "Tidevand Studio ApS", "Lysholm Logistik A/S",
                 "Saltværket Software ApS"]
FORSIKRINGER = ["Lindholm Forsikring", "Fjordsikring", "Nordkap Forsikring"]
BOLIGTYPER = ["kollegieværelse", "værelse", "lejlighed"]

KÆDER = [
    ["NETTO", "Netto"], ["REMA ?1000", "Rema 1000"], ["LIDL", "Lidl"], ["F(OE|Ø)TEX", "Føtex"],
    ["COOP ?365", "Coop 365"], ["MENY", "Meny"], ["7-ELEVEN", "7-Eleven"], ["WOLT", "Wolt"], ["JUST ?EAT", "Just Eat"],
    ["ZALANDO", "Zalando"], ["H ?& ?M", "H&M"], ["MATAS", "Matas"], ["APOTEK", "Apotek"], ["IKEA", "IKEA"],
    ["S(Ø|OE)STRENE GRENE", "Søstrene Grene"], ["UNGDOMSKORT", "Ungdomskort"], ["REJSEKORT", "Rejsekort"],
    ["DSB", "DSB"], ["SPOTIFY", "Spotify"], ["NETFLIX", "Netflix"], ["VIAPLAY", "Viaplay"], ["SATS", "SATS"],
]


# ---------- vagt mod rigtige beløb ----------
class Vagt:
    """Beløb fra et rigtigt Sure-udtræk, demoen skal holde sig fra.

    naer(x): x ligger inden for 4 % (mindst 5 kr.) af et fast beløb: husleje, SU, boligstøtte, faste udgifter og
    indtægter, der går igen, budget, mål og saldi.
    naer_loen(x): x ligger inden for 1 % (mindst 5 kr.) af en rigtig lønudbetaling. Lønnen fra et timelønnet job
    svinger fra måned til måned, så den holdes i stedet væk fra det typiske niveau med loen_niveau_naer.
    loen_niveau_naer(x): x ligger inden for 15 % af den typiske månedsløn det seneste år.
    """

    def __init__(self, faste: list[float], loen: list[float] = (), loen_niveau: float = 0.0) -> None:
        self.v = sorted(faste)
        self.loen = sorted(loen)
        self.loen_niveau = loen_niveau

    @classmethod
    def fra_disk(cls) -> "Vagt":
        faste: set[float] = set()
        loen: set[float] = set()
        niveauer: list[float] = []
        for sti in RIGTIGE_DATA:
            if not sti or not Path(sti).is_file():
                continue
            try:
                d = json.loads(Path(sti).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            gentaget: dict[tuple, int] = {}
            loen_pr_maaned: dict[str, float] = {}
            tx = d.get("transactions") or []
            sidst = max((str(t.get("date", "")) for t in tx), default="")
            fra = f"{int(sidst[:4]) - 3}{sidst[4:]}" if sidst[:4].isdigit() else ""   # de seneste tre år
            et_aar = f"{int(sidst[:4]) - 1}{sidst[4:]}" if sidst[:4].isdigit() else ""
            for t in tx:
                dato = str(t.get("date", ""))
                if dato < fra:
                    continue
                try:
                    a = abs(float(t.get("amount")))
                except (TypeError, ValueError):
                    continue
                if a < 15:
                    continue
                if t.get("category") == "Løn":
                    loen.add(round(a, 2))
                    if dato >= et_aar:
                        loen_pr_maaned[dato[:7]] = loen_pr_maaned.get(dato[:7], 0.0) + a
                    continue
                if t.get("category") in ("SU", "Boligstøtte", "Husleje"):
                    faste.add(round(a, 2))
                if t.get("group") in (FAST, IND):   # faste udgifter og indtægter, der går igen
                    k = (t.get("category"), round(a))
                    gentaget[k] = gentaget.get(k, 0) + 1
            faste |= {float(a) for (_, a), n in gentaget.items() if n >= 2}
            for b in d.get("budgets") or []:
                faste |= {abs(float(b[k])) for k in ("income", "spending", "variable") if b.get(k)}
            faste |= {float(g["target"]) for g in d.get("goals") or [] if g.get("target")}
            faste |= {abs(float(a["balance"])) for a in d.get("accounts") or [] if a.get("balance") is not None}
            if loen_pr_maaned:
                v = sorted(loen_pr_maaned.values())
                niveauer.append(v[len(v) // 2])
        return cls(sorted(faste), sorted(loen), max(niveauer, default=0.0))

    @staticmethod
    def _inden_for(liste: list[float], x: float, andel: float) -> bool:
        x = abs(x)
        i = bisect.bisect_left(liste, x)
        return any(abs(x - v) <= max(5.0, andel * v) for v in liste[max(0, i - 1):i + 1])

    def naer(self, x: float) -> bool:
        return self._inden_for(self.v, x, 0.04)

    def naer_loen(self, x: float) -> bool:
        return self._inden_for(self.loen, x, 0.01)

    def loen_niveau_naer(self, x: float) -> bool:
        return bool(self.loen_niveau) and abs(abs(x) - self.loen_niveau) <= 0.15 * self.loen_niveau


def traek(r: random.Random, vagt: Vagt, lav: float, hoej: float, decimaler: int = 0) -> float:
    """Et tilfældigt, skævt beløb i [lav, hoej], der ikke ligner et rigtigt fast beløb."""
    for i in range(2000):
        if i and i % 200 == 0:                              # alt optaget: gør intervallet lidt bredere
            lav, hoej = lav * 0.9, hoej * 1.15
        x = round(r.uniform(lav, hoej), decimaler)
        if decimaler == 0 and x >= 100 and x % 25 == 0:   # ingen runde beløb
            continue
        if not vagt.naer(x):
            return float(x)
    return frit_opad(vagt, round(hoej, decimaler), decimaler)


def frit_opad(vagt: Vagt, x: float, decimaler: int = 0) -> float:
    """Udvejen: gå opad fra x, til beløbet er frit. Der er kun endeligt mange rigtige beløb, så det slutter altid."""
    skridt = 10 ** -decimaler if decimaler < 0 else 1
    while vagt.naer(x):
        x = round(x + max(skridt, abs(x) * 0.02), decimaler)
    return float(x)


def vaek_fra_rigtige(vagt: Vagt, x: float, r: random.Random, skridt: float) -> float:
    """Skubber et afledt, rundet beløb (budget, mål) væk fra rigtige beløb, i skridt af `skridt`."""
    for _ in range(200):
        if not vagt.naer(x):
            return float(x)
        x += r.choice([-1, 1]) * r.randint(1, 4) * skridt
    while vagt.naer(x):
        x += skridt
    return float(x)


# ---------- datoer ----------
def plus_maaneder(y: int, m: int, n: int) -> tuple[int, int]:
    k = y * 12 + (m - 1) + n
    return k // 12, k % 12 + 1


def sidste_dag(y: int, m: int) -> date:
    return date(*plus_maaneder(y, m, 1), 1) - timedelta(days=1)


def bankdag_foer(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def bankdag_efter(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def ym(y: int, m: int) -> str:
    return f"{y}-{m:02d}"


def tidspunkt(r: random.Random, d: date, fra: int = 8, til: int = 22) -> str:
    return f"{d.isoformat()}T{r.randint(fra, til):02d}:{r.randint(0, 59):02d}:{r.randint(0, 59):02d}"


# ---------- Alex ----------
def bolig(r: random.Random, vagt: Vagt, type_: str, omraade: str) -> dict:
    """Husleje, boligstøtte og evt. internet for én bolig."""
    if type_ == "kollegieværelse":
        kort, navn = r.choice(KOLLEGIER)
        return {"husleje": traek(r, vagt, 2700, 4900), "tekst": f"BS {navn} husleje", "modtager": [kort, navn],
                "omraade": omraade, "internet": None,
                "boligstoette": traek(r, vagt, 550, 1900) if r.random() < 0.8 else 0}
    if type_ == "værelse":
        return {"husleje": traek(r, vagt, 2300, 4700), "tekst": "MobilePay Husleje værelse", "modtager": None,
                "omraade": omraade, "internet": ("MobilePay Internet deling", traek(r, vagt, 60, 220)),
                "boligstoette": traek(r, vagt, 400, 1300) if r.random() < 0.35 else 0}
    kort, navn = r.choice(UDLEJERE)
    return {"husleje": traek(r, vagt, 4800, 8900), "tekst": f"BS {navn} husleje", "modtager": [kort, navn],
            "omraade": omraade,
            "internet": (f"BS {r.choice(['Hiper', 'Kviknet', 'Fastspeed'])} internet", traek(r, vagt, 169, 329)),
            "boligstoette": traek(r, vagt, 650, 2400) if r.random() < 0.5 else 0}


def profil(r: random.Random, vagt: Vagt, idag: date) -> dict:
    """Alex' niveauer og vaner, trukket på ny hver gang."""
    fra_type, til_type = r.sample(BOLIGTYPER, 2)
    fra_omr, til_omr = r.sample(OMRAADER, 2)
    mobil = r.choice(["Oister", "Lebara", "CBB Mobil", "Greentel"])
    faste = [(f"BS {mobil} mobil", traek(r, vagt, 69, 189), "Mobil og internet", BUDGETKONTO, r.randint(1, 8)),
             (f"BS {r.choice(FORSIKRINGER)} indbo", traek(r, vagt, 55, 215), "Forsikringer", BUDGETKONTO, r.randint(1, 10))]
    for navn, lav, hoej in r.sample([("Spotify Premium", 59, 139), ("NETFLIX.COM", 79, 169), ("VIAPLAY", 99, 189),
                                      ("YouTube Premium", 59, 129), ("Mofibo", 99, 159)], r.randint(1, 3)):
        faste.append((navn, traek(r, vagt, lav, hoej), "Streaming", LOENKONTO, r.randint(1, 28)))
    if r.random() < 0.7:
        navn, lav, hoej = r.choice([("SATS Danmark", 189, 359), ("Fitnessdk", 149, 299), ("Klatreklubben", 110, 260)])
        faste.append((navn, traek(r, vagt, lav, hoej), "Sport og fitness", LOENKONTO, r.randint(1, 5)))
    ungdomskort = r.random() < 0.7
    if ungdomskort:
        faste.append(("DOT Ungdomskort", traek(r, vagt, 320, 590), "Transport", LOENKONTO, r.randint(1, 4)))
    return {
        "flyt": plus_maaneder(idag.year, idag.month, -r.randint(2, 11)),
        "fra": bolig(r, vagt, fra_type, fra_omr), "til": bolig(r, vagt, til_type, til_omr),
        "trk": r.choice(TRK),
        "fradrag": r.randint(3650, 4750),                      # personfradrag pr. måned på hovedkortet
        "hovedkort": r.choice(["su", "loen"]),                 # hvem der har fradraget: SU eller lønnen
        "arbejdsgiver": r.choice(ARBEJDSGIVERE), "timeloen": round(r.uniform(128, 192), 2),
        "timer": r.uniform(20, 64), "sommer": r.uniform(0.3, 2.6),   # sommeren: ferie eller fuld tid
        "loendag": r.choice(["sidste", "foerste"]),
        "faste": faste, "ungdomskort": ungdomskort,
        "skat_tilbage": (r.randint(3, 6), traek(r, vagt, 300, 4200)) if r.random() < 0.6 else None,
        # forbrugsvaner: hvor meget og hvor ofte
        "mad_pr_tur": r.uniform(75, 215), "ture": r.randint(7, 17),
        "butikker": r.sample(["NETTO", "REMA1000", "LIDL", "FØTEX", "COOP 365", "MENY", "7-ELEVEN"], r.randint(3, 5)),
        "cafe": r.uniform(0.2, 2.0), "takeaway": r.uniform(0.2, 2.0), "toej": r.uniform(0.2, 2.0),
        "fritid": r.uniform(0.3, 2.0), "rejse_maaned": r.randint(5, 8), "rejse": r.uniform(1500, 8000),
        "boeger": r.sample([1, 2, 8, 9], 2),
    }


def su_netto(p: dict, y: int) -> float:
    """SU som udeboende efter skat, med personfradraget, hvis SU har hovedkortet."""
    brutto = SU_BRUTTO_2026 * 1.03 ** (y - 2026)
    fradrag = p["fradrag"] if p["hovedkort"] == "su" else 0
    return float(round(brutto - (brutto - fradrag) * p["trk"] / 100))


def loen_netto(p: dict, bl: float) -> float:
    """Udbetalt løn: efter AM-bidrag og A-skat, med personfradraget, hvis lønnen har hovedkortet."""
    personlig = bl * (1 - AM)
    fradrag = p["fradrag"] if p["hovedkort"] == "loen" else 0
    return round(personlig - p["trk"] / 100 * max(personlig - fradrag, 0), 2)


# ---------- posteringer ----------
def posteringer(r: random.Random, vagt: Vagt, p: dict, idag: date) -> tuple[list[dict], dict[str, float]]:
    """Alle posteringer fra den 1. for 12 måneder siden til idag, og bruttolønnen pr. udbetalingsmåned."""
    start = date(*plus_maaneder(idag.year, idag.month, -12), 1)
    ud: list[dict] = []
    brutto: dict[str, float] = {}

    def post(d: date, beloeb: float, navn: str, kategori: str, gruppe: str, konto: str = LOENKONTO) -> None:
        if start <= d <= idag:
            ud.append({"date": d.isoformat(), "amount": round(beloeb, 2), "name": navn, "account": konto,
                       "category": kategori, "group": gruppe, "merchant": None})

    def antal(snit: float) -> int:          # et antal omkring snit, aldrig negativt
        return max(0, int(round(r.gauss(snit, max(1.0, snit * 0.45)))))

    # SU pr. år må ikke ramme et rigtigt beløb. SU-satsen er offentlig, så kun kort, trækprocent og fradrag kan
    # flyttes: vælg tilfældigt blandt de kombinationer, der giver frie beløb, så bredere intervaller. Er intet frit,
    # bruges den trukne kombination (udvejen, så lav altid lykkes).
    def su_fri(q: dict) -> bool:
        return not any(vagt.naer(su_netto(q, aar)) for aar in range(start.year, idag.year + 2))

    if not su_fri(p):
        for trk_liste, fradrag_liste in ((TRK, range(3650, 4751, 10)),
                                         ([x / 2 for x in range(60, 93)], range(3000, 5501, 10))):
            frie = [q for q in ({"trk": t, "fradrag": f, "hovedkort": k}
                                for k in ("su", "loen") for t in trk_liste for f in fradrag_liste) if su_fri(q)]
            if frie:
                p.update(r.choice(frie))
                break

    # Den udbetalte løn: en måneds løn må ikke ramme et rigtigt fast beløb eller en rigtig lønudbetaling, og det
    # normale niveau skal ligge mindst 15 % fra din typiske månedsløn. Ellers flyttes timetal og timeløn.
    def loen_fri(netto: float) -> bool:
        return not vagt.naer(netto) and not vagt.naer_loen(netto)

    for _ in range(300):
        if not vagt.loen_niveau_naer(loen_netto(p, p["timer"] * p["timeloen"])):
            break
        p["timer"], p["timeloen"] = r.uniform(12, 80), round(r.uniform(128, 192), 2)

    y, m = start.year, start.month
    while (y, m) <= (idag.year, idag.month):
        b = p["til"] if (y, m) >= p["flyt"] else p["fra"]
        omr = b["omraade"]
        sidst = sidste_dag(y, m).day
        dag = lambda d: date(y, m, min(max(d, 1), sidst))  # noqa: E731
        en_dag = lambda: dag(r.randint(1, sidst))  # noqa: E731
        lune = min(max(r.lognormvariate(0, 0.28), 0.6), 1.7)    # nogle måneder bruger man bare mere

        # Indtægter: SU for næste måned sidste bankdag, løn, boligstøtte først på måneden
        post(bankdag_foer(sidste_dag(y, m)), -su_netto(p, plus_maaneder(y, m, 1)[0]), "SU-udbetaling", "SU", IND)
        faktor = {1: 0.6, 6: 0.65, 12: 0.75, 7: p["sommer"]}.get(m, 1.0)
        for i in range(400):
            spredning = 0.22 if i < 100 else 0.7     # er måneden optaget omkring det normale, så længere ud
            bl = round(p["timer"] * faktor * r.lognormvariate(0, spredning) * p["timeloen"], 2)
            netto = loen_netto(p, bl)
            if loen_fri(netto):
                break
        else:                               # udvej: lidt flere timer, til den udbetalte løn er fri
            while not loen_fri(netto):
                bl = round(bl * 1.01 + 1, 2)
                netto = loen_netto(p, bl)
        loendag = bankdag_foer(sidste_dag(y, m)) if p["loendag"] == "sidste" else bankdag_efter(dag(1))
        if start <= loendag <= idag:
            brutto[ym(loendag.year, loendag.month)] = bl
        post(loendag, -netto, f"Løn {p['arbejdsgiver']}", "Løn", IND)
        if b["boligstoette"]:
            post(bankdag_efter(dag(1)), -b["boligstoette"], "Boligstøtte Udbetaling Danmark", "Boligstøtte", IND)
        if p["skat_tilbage"] and m == p["skat_tilbage"][0]:
            post(bankdag_efter(dag(r.randint(8, 20))), -p["skat_tilbage"][1], "Overskydende skat", "Andre indtægter", IND)

        # Faste udgifter
        post(bankdag_efter(dag(1)), b["husleje"], b["tekst"], "Husleje", FAST, BUDGETKONTO)
        if b["internet"]:
            post(dag(3), b["internet"][1], b["internet"][0], "Mobil og internet", FAST, BUDGETKONTO)
        for navn, beloeb, kat, konto, d in p["faste"]:
            post(dag(d), beloeb, navn, kat, FAST, konto)
        if not p["ungdomskort"]:
            for _ in range(r.randint(1, 4)):
                post(en_dag(), traek(r, vagt, 90, 350), "REJSEKORT optankning", "Transport", FAST)
        if m in p["boeger"]:
            post(dag(r.randint(1, 12)), traek(r, vagt, 280, 1900), r.choice(["Studieboghandlen", "Saxo.com", "Bog & Idé"]),
                 "Studiebøger", FAST)

        # Variable udgifter
        for _ in range(antal(p["ture"] * lune)):
            beloeb = min(max(p["mad_pr_tur"] * r.lognormvariate(-0.15, 0.65), 12), 950)
            post(en_dag(), beloeb, f"{r.choice(p['butikker'])} {omr}", "Dagligvarer", VAR)
        for _ in range(antal(5 * p["cafe"] * lune)):
            if r.random() < 0.55:
                post(en_dag(), r.randint(26, 78), r.choice(["Café Lindely", "Kaffebar Stjernen", "Bageriet Hjørnet"]),
                     "Café og bar", VAR)
            else:
                post(en_dag(), r.randint(85, 560), r.choice(["MobilePay Fredagsbar", "Bodegaen", "Bar Ugle", "Studenterbaren"]),
                     "Café og bar", VAR)
        for _ in range(antal(2.5 * p["takeaway"] * lune)):
            navn = r.choice(["WOLT", "JUST EAT", "Shawarma Hjørnet", "Pizzeria Bella Vista"])
            post(en_dag(), round(r.uniform(59, 320), r.choice([0, 2])), navn, "Take-away", VAR)
        for _ in range(antal(0.9 * p["toej"] * lune)):
            navn = r.choice(["H&M", "ZALANDO", "Weekday", "Genbrugsbutikken"])
            post(en_dag(), round(r.uniform(79, 1250), r.choice([0, 2])), navn, "Tøj og sko", VAR)
            if navn == "ZALANDO" and r.random() < 0.3:
                post(en_dag(), -round(r.uniform(149, 699)), "ZALANDO retur", "Tøj og sko", VAR)
        for _ in range(antal(1.6 * p["fritid"] * lune)):
            navn, lav, hoej = r.choice([("Nordisk Film Biografer", 85, 260), ("Ticketmaster", 190, 820),
                                        ("Bog & Idé", 99, 349), ("Københavns Museum", 60, 140),
                                        ("Klatrehallen", 95, 190), ("Steam", 39, 399)])
            post(en_dag(), round(r.uniform(lav, hoej)), navn, "Fritid og kultur", VAR)
        for _ in range(antal(0.8)):
            post(en_dag(), round(r.uniform(35, 320), 2), f"MATAS {omr}", "Personlig pleje", VAR)
        if r.random() < 0.45:
            post(en_dag(), r.randint(160, 560), "Frisøren", "Personlig pleje", VAR)
        for _ in range(antal(1.0)):
            post(en_dag(), round(r.uniform(22, 280)), r.choice(["SØSTRENE GRENE", "Normal", "Flying Tiger"]),
                 "Husholdning", VAR)
        for _ in range(antal(0.6)):
            post(en_dag(), round(r.uniform(32, 290), 2), f"APOTEK {omr}", "Sundhed", VAR)
        if r.random() < 0.08:
            post(en_dag(), round(r.uniform(380, 1450)), "Tandlægeklinikken", "Sundhed", VAR)
        if r.random() < 0.1:
            post(en_dag(), round(r.uniform(140, 950)), "Cykelsmeden", "Cykel", VAR)
        if m == 12:
            for _ in range(r.randint(2, 5)):
                post(dag(r.randint(1, 22)), round(r.uniform(110, 950)), r.choice(["Bilka", "Magasin", "Bog & Idé", "Kop & Kande"]),
                     "Gaver", VAR)
            for d in (r.randint(18, 23), r.randint(26, 30)):
                post(dag(d), round(r.uniform(160, 520)), "DSB", "Ferie og rejser", VAR)
        elif r.random() < 0.2:
            post(en_dag(), round(r.uniform(120, 600)), r.choice(["Bog & Idé gave", "Kop & Kande"]), "Gaver", VAR)
        if m == p["rejse_maaned"]:
            rest = p["rejse"]
            for navn in ("Ryanair", "Hostelworld", "Supermercado Lisboa", "Uber"):
                del_ = rest * r.uniform(0.25, 0.6) if navn != "Uber" else rest
                post(dag(r.randint(1, 20)), del_, navn, "Ferie og rejser", VAR)
                rest -= del_
        elif r.random() < 0.15:
            post(en_dag(), round(r.uniform(180, 690)), "DSB", "Ferie og rejser", VAR)

        # Indflytning: flyttebil og møbler i flyttemåneden, lidt mere måneden efter
        if (y, m) == p["flyt"]:
            post(dag(r.randint(1, 4)), round(r.uniform(420, 1350)), r.choice(["GoMore flyttebil", "Flyttemand.dk"]),
                 "Flytning", FLYT)
            for _ in range(r.randint(1, 3)):
                post(dag(r.randint(2, 15)), round(r.uniform(250, 3800), 2), r.choice(["IKEA", "JYSK", "SØSTRENE GRENE"]),
                     "Møbler og indretning", FLYT)
        if (y, m) == plus_maaneder(*p["flyt"], 1) and r.random() < 0.7:
            post(dag(r.randint(3, 25)), round(r.uniform(120, 1600), 2), "IKEA", "Møbler og indretning", FLYT)

        y, m = plus_maaneder(y, m, 1)

    ud.sort(key=lambda t: t["date"])
    return ud, brutto


def scenarier(r: random.Random, idag: date) -> dict:
    """Scenariers gemte valg i samme form, som siden gemmer dem (det, der afviger fra standarden). Tilfældige, men
    inden for det, en studerende plausibelt ville taste: jobbet efter studiet giver overskud, og sabbatåret er kort."""
    om = lambda lav, hoej: ym(*plus_maaneder(idag.year, idag.month, r.randint(lav, hoej)))  # noqa: E731
    jobloen = r.randint(420, 640) * 50
    return {
        "years": r.randint(6, 20), "infl": r.choice([1.5, 2, 2.5, 3]), "incomeInfl": True,
        "cashRate": r.choice([0.5, 0.75, 1, 1.25, 1.5, 2]), "investShare": r.choice([0, 10, 20, 30, 40, 50, 60]),
        "ret": r.choice([4, 4.5, 5, 5.5, 6, 6.5, 7]), "vol": r.randint(10, 20), "overrun": r.choice([-10, -5, 0, 5, 10]),
        "job": {"on": r.random() < 0.85, "from": om(26, 60), "income": jobloen,
                "spend": jobloen - r.randint(110, 220) * 50},
        "sabbat": {"on": r.random() < 0.3, "from": om(8, 30), "months": r.randint(3, 9),
                   "income": r.randint(30, 90) * 100, "spend": r.randint(70, 115) * 100, "delays": r.random() < 0.6},
        "oneoff": {"on": r.random() < 0.6, "date": om(3, 20), "amount": r.randint(8, 40) * 500,
                   "label": r.choice(["Udveksling", "Ny computer", "Rejse", "Depositum", "Kørekort"])},
        "saved_at": tidspunkt(r, idag - timedelta(days=r.randint(2, 40))) + "+02:00",
    }


# ---------- filer ----------
def skriv(sti: Path, data) -> None:
    sti.parent.mkdir(parents=True, exist_ok=True)
    sti.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def lav(ud: Path, idag: date) -> None:
    """Skriver Økonomis demodata under ud/forbrug. Nye tilfældige tal hver gang."""
    r = random.Random()
    vagt = Vagt.fra_disk()
    mappe = ud / "forbrug"

    # En studerende, hvis budget løber rundt med et lille overskud, så Scenarier er værd at se på
    for _ in range(40):
        p = profil(r, vagt, idag)
        tx, brutto = posteringer(r, vagt, p, idag)

        # Budgettet: Alex' egne gennemsnit over de hele måneder, rundet som et rigtigt budget
        hele = {t["date"][:7] for t in tx} - {ym(idag.year, idag.month)}
        snit = lambda gruppe: sum(t["amount"] for t in tx  # noqa: E731
                                  if t["group"] == gruppe and t["date"][:7] in hele) / max(len(hele), 1)
        indkomst = vaek_fra_rigtige(vagt, round(-snit(IND) * r.uniform(0.95, 1.02), -2), r, 100)
        variabel = vaek_fra_rigtige(vagt, round(snit(VAR) * r.uniform(0.9, 1.05), -2), r, 100)
        til = p["til"]
        fast = til["husleje"] + (til["internet"][1] if til["internet"] else 0) + sum(f[1] for f in p["faste"])
        forbrug = vaek_fra_rigtige(vagt, round(fast + variabel, -2), r, 100)
        if forbrug + 300 <= indkomst <= forbrug + 3500:
            break

    saldi = {LOENKONTO: traek(r, vagt, 600, 14000, 2), BUDGETKONTO: traek(r, vagt, 150, 6500, 2),
             OPSPARING: traek(r, vagt, 1500, 28000, 2)}
    maal = vaek_fra_rigtige(vagt, round((sum(saldi.values()) + r.uniform(5000, 22000)) / 2500) * 2500, r, 2500)
    skriv(mappe / "data.json", {
        "generated_at": tidspunkt(r, idag, 6, 9),
        "last_sync": tidspunkt(r, idag, 5, 6),
        "accounts": [{"name": n, "balance": saldi[n], "classification": "asset"} for n in sorted(saldi)],
        "goals": [{"name": r.choice(["Nødbuffer", "Nødbuffer", "Buffer"]), "target": maal,
                   "target_date": sidste_dag(*plus_maaneder(idag.year, idag.month, r.randint(5, 20))).isoformat()}],
        "budgets": [{"month": ym(*plus_maaneder(idag.year, idag.month, n)), "spending": forbrug,
                     "income": indkomst, "variable": variabel} for n in range(-3, 3)],
        "transactions": tx,
    })

    modtagere = [b["modtager"] for b in (p["fra"], p["til"]) if b["modtager"]] + KÆDER
    skriv(mappe / "config.json", {"flytning": ym(*p["flyt"]), "modtagere": modtagere})

    # SU-vagten: samme trækprocent som lønnen, forventet løn omkring den typiske og årets første lønsedler
    aar = str(idag.year)
    loensedler = [(k, v) for k, v in sorted(brutto.items()) if k.startswith(aar)][:r.randint(2, 4)]
    typisk = sorted(brutto.values())[len(brutto) // 2] if brutto else 6000.0
    skriv(mappe / "state" / "su.json", {
        "trk": p["trk"], "fradrag": p["fradrag"] if p["hovedkort"] == "loen" else 0, "forventet": traek(r, vagt, typisk * 0.85, typisk * 1.2, -1), "laan": 0,
        "years": {aar: {"status": {}, "brutto": dict(loensedler)}},
        "saved_at": tidspunkt(r, idag - timedelta(days=r.randint(2, 30))) + "+02:00",
    })
    skriv(mappe / "state" / "scenarier.json", scenarier(r, idag))

    (mappe / "kompas.json").write_text(KOMPAS_JSON.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    import sys
    import tempfile

    with tempfile.TemporaryDirectory() as t:
        lav(Path(t), date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today())
        for f in sorted(Path(t).rglob("*.json")):
            print(f.relative_to(t), f.stat().st_size, "bytes")
