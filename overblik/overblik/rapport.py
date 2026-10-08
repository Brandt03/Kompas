"""Det ugentlige review regnet ud: hvad afveg fra dit normale, og hvilke
sammenhænge holder statistisk. Modellen får resultatet og skriver teksten,
men afgør ikke selv hvad der er signifikant."""

from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from statistics import mean, median

from .db import KOLONNER
from .kilder import mandag

BASELINE_UGER = 8
# |robust z| over denne grænse regnes som en tydelig afvigelse.
Z_GRAENSE = 1.5
# Sammenhænge testes på ugens afvigelse fra medianen af de NABO_UGER nærmeste uger på hver side, så en fælles
# udvikling over tid (sommer mod semester) ikke tæller som en sammenhæng. Naboer på begge sider, ikke kun de
# foregående: en bagudrettet median halter efter, når begge kolonner følger samme sæson, og så ligner det en
# sammenhæng. p-værdien findes ved at blande ugerne i
# blokke af BLOK_UGER sammenhængende uger, fordi uger, der ligger tæt, ligner hinanden, og en almindelig
# permutationstest derfor giver for små p-værdier. Med færre end 6 blokke er der for få måder at blande på til,
# at 0,05/11 overhovedet kan nås, så der kræves mindst 6 blokke.
NABO_UGER = 4
BLOK_UGER = 3
MIN_UGER_KORRELATION = 6 * BLOK_UGER
PERMUTATIONER = 5000

# Faste hypoteser i stedet for alle par mod alle: med 18 kolonner er der 153
# par, og så vil ca. 8 af dem "hænge sammen" ved rent tilfælde.
HYPOTESER: list[tuple[str, str, str]] = [
    ("soevn_timer_snit", "takeaway_kr", "Køber du mere take-away når du sover mindre?"),
    ("stress_snit", "takeaway_kr", "Køber du mere take-away i stressede uger?"),
    ("cafe_bar_kr", "hrv_snit", "Falder HRV i uger med byture?"),
    ("cafe_bar_kr", "soevn_timer_snit", "Sover du mindre i uger med byture?"),
    ("traening_timer", "soevnscore_snit", "Sover du bedre i uger hvor du træner mere?"),
    ("traening_timer", "stress_snit", "Er du mindre stresset i uger hvor du træner mere?"),
    ("undervisning_timer", "traening_timer", "Træner du mindre i tunge undervisningsuger?"),
    ("selvstudie_timer", "traening_timer", "Træner du mindre i uger med meget selvstudie?"),
    ("selvstudie_timer", "soevn_timer_snit", "Sover du mindre i uger med meget selvstudie?"),
    ("selvstudie_timer", "takeaway_kr", "Køber du mere take-away i uger med meget selvstudie?"),
    ("selvstudie_timer", "stress_snit", "Er du mere stresset i uger med meget selvstudie?"),
]

# Kolonner hvor en høj værdi er det gode. Resten er neutrale eller omvendte,
# så modellen ikke kalder mere take-away en forbedring.
HOEJ_ER_GODT = {"hrv_snit", "soevn_timer_snit", "soevnscore_snit", "skridt_snit", "traening_timer",
                "selvstudie_timer"}
LAV_ER_GODT = {"hvilepuls_snit", "stress_snit", "takeaway_kr", "cafe_bar_kr", "variabelt_kr"}


def _rang(xs: list[float]) -> list[float]:
    orden = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(orden):
        j = i
        while j + 1 < len(orden) and xs[orden[j + 1]] == xs[orden[i]]:
            j += 1
        for k in range(i, j + 1):
            r[orden[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def _pearson(a: list[float], b: list[float]) -> float:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    sa = sum((x - ma) ** 2 for x in a) ** 0.5
    sb = sum((y - mb) ** 2 for y in b) ** 0.5
    if sa == 0 or sb == 0:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def spearman(a: list[float], b: list[float], blok: int = BLOK_UGER) -> tuple[float, float]:
    """Rangkorrelation og tosidet p-værdi ved blok-permutation: b's uger blandes i blokke af `blok`
    sammenhængende uger, så ugernes indbyrdes lighed bevares. Forudsætter ikke normalfordeling."""
    ra, rb = _rang(a), _rang(b)
    rho = _pearson(ra, rb)
    rng = random.Random(0)
    blokke = [rb[i:i + blok] for i in range(0, len(rb), blok)]
    mindst_saa_stor = 0
    for _ in range(PERMUTATIONER):
        rng.shuffle(blokke)
        if abs(_pearson(ra, [v for bl in blokke for v in bl])) >= abs(rho) - 1e-12:
            mindst_saa_stor += 1
    return rho, (mindst_saa_stor + 1) / (PERMUTATIONER + 1)


def _fra_normalen(alle: list[dict], kol: str) -> list[float | None]:
    """For hver uge: værdien minus medianen af de NABO_UGER nærmeste uger før og efter (mindst 4 med data).
    De seneste uger har kun naboer bagud."""
    ud = []
    for i, u in enumerate(alle):
        naboer = alle[max(0, i - NABO_UGER):i] + alle[i + 1:i + 1 + NABO_UGER]
        hist = [w[kol] for w in naboer if w[kol] is not None]
        ud.append(None if u[kol] is None or len(hist) < 4 else u[kol] - median(hist))
    return ud


def _afvigelse(kol: str, v: float | None, historik: list[float]) -> dict | None:
    if v is None or len(historik) < 4:
        return None
    med = median(historik)
    # Er over halvdelen af ugerne ens (fx 0 kr. på café i de fleste uger), er MAD 0. Så bruges den gennemsnitlige
    # afvigelse fra medianen (·1,2533 giver samme skala for normalfordelte data). Er også den 0, er alle ugerne
    # ens, og enhver anden værdi er tydelig; z er så None i stedet for uendelig. Før blev z sat til 0, så en uge
    # med 900 kr. efter otte uger med 0 kr. aldrig blev markeret.
    skala = median(abs(x - med) for x in historik) * 1.4826 or mean(abs(x - med) for x in historik) * 1.2533
    z = (v - med) / skala if skala > 0 else (0.0 if v == med else None)
    tydelig = z is None or abs(z) >= Z_GRAENSE
    retning = "over" if v > med else "under" if v < med else "som"
    vurdering = None
    if tydelig:
        if kol in HOEJ_ER_GODT:
            vurdering = "godt" if v > med else "skidt"
        elif kol in LAV_ER_GODT:
            vurdering = "godt" if v < med else "skidt"
    return {
        "vaerdi": v,
        "normal": round(med, 2),
        "normal_interval": [round(min(historik), 2), round(max(historik), 2)],
        "robust_z": round(z, 2) if z is not None else None,
        "retning": retning,
        "tydelig": tydelig,
        "vurdering": vurdering,
    }


def lav(conn: sqlite3.Connection, uge_mandag: date | None = None) -> dict:
    """Review af den seneste hele uge (eller uge_mandag)."""
    uge_mandag = uge_mandag or mandag(date.today()) - timedelta(days=7)
    alle = [dict(r) for r in conn.execute("SELECT * FROM uger ORDER BY mandag")]
    idx = next((i for i, u in enumerate(alle) if u["mandag"] == uge_mandag.isoformat()), None)
    if idx is None:
        return {"fejl": f"ingen data for ugen der starter {uge_mandag}"}
    uge = alle[idx]
    tidligere = alle[max(0, idx - BASELINE_UGER):idx]

    afvigelser = {}
    for kol, forklaring in KOLONNER:
        hist = [u[kol] for u in tidligere if u[kol] is not None]
        a = _afvigelse(kol, uge[kol], hist)
        if a:
            afvigelser[kol] = {"forklaring": forklaring, **a}

    # Uger med under 5 dages Garmin-data er for hullede til at korrelere på.
    op_til = alle[: idx + 1]
    brugbar = [(u["garmin_dage"] or 0) >= 5 for u in op_til]
    normal = {kol: _fra_normalen(op_til, kol) for kol in {k for h in HYPOTESER for k in h[:2]}}
    grænse_stærk = 0.05 / len(HYPOTESER)
    sammenhaenge = []
    for x, y, spoergsmaal in HYPOTESER:
        par = [(a, b) for a, b, ok in zip(normal[x], normal[y], brugbar) if ok and a is not None and b is not None]
        res = {"x": x, "y": y, "spoergsmaal": spoergsmaal, "n_uger": len(par)}
        if len(par) < MIN_UGER_KORRELATION:
            res["status"] = f"for få uger ({len(par)} af {MIN_UGER_KORRELATION})"
        else:
            rho, p = spearman([a for a, _ in par], [b for _, b in par])
            res |= {"rho": round(rho, 2), "p": round(p, 4)}
            if p < grænse_stærk and abs(rho) >= 0.3:
                res["status"] = "stærk"
            elif p < 0.05 and abs(rho) >= 0.3:
                res["status"] = "antydning"
            else:
                res["status"] = "ingen sammenhæng"
        sammenhaenge.append(res)

    return {
        "uge": uge["uge"],
        "mandag": uge["mandag"],
        "baseline": f"de {len(tidligere)} foregående uger",
        "afvigelser": afvigelser,
        "sammenhaenge": sammenhaenge,
        "metode": (
            "Afvigelse: robust z = (værdi − median) / (1,4826·MAD) over baseline-ugerne (er MAD 0, bruges "
            "1,2533 · gennemsnitlig afvigelse; er alle ugerne ens, er enhver anden værdi tydelig); "
            f"|z| ≥ {Z_GRAENSE} er tydelig. Sammenhæng: Spearman på ugens afvigelse fra medianen af de "
            f"{NABO_UGER} nærmeste uger på hver side (så en fælles udvikling over tid ikke tæller), med blok-permutation i "
            f"blokke af {BLOK_UGER} uger; mindst {MIN_UGER_KORRELATION} uger og kun uger med ≥5 dages Garmin-data. "
            f"'stærk' = p < {grænse_stærk:.4f} "
            f"(0,05 delt på {len(HYPOTESER)} hypoteser) og |rho| ≥ 0,3; 'antydning' = p < 0,05. "
            "Korrelation er ikke årsag."
        ),
        "seneste_uger": alle[max(0, idx - 7): idx + 1],
    }
