"""Det ugentlige review regnet ud: hvad afveg fra dit normale, og hvilke
sammenhænge holder statistisk. Modellen får resultatet og skriver teksten,
men afgør ikke selv hvad der er signifikant."""

from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from statistics import median

from .db import KOLONNER
from .kilder import mandag

BASELINE_UGER = 8
# |robust z| over denne grænse regnes som en tydelig afvigelse.
Z_GRAENSE = 1.5
MIN_UGER_KORRELATION = 12
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


def spearman(a: list[float], b: list[float]) -> tuple[float, float]:
    """Rangkorrelation og tosidet p-værdi ved permutation, som ikke
    forudsætter normalfordeling og holder ved små n."""
    ra, rb = _rang(a), _rang(b)
    rho = _pearson(ra, rb)
    rng = random.Random(0)
    rb2 = rb[:]
    mindst_saa_stor = 0
    for _ in range(PERMUTATIONER):
        rng.shuffle(rb2)
        if abs(_pearson(ra, rb2)) >= abs(rho) - 1e-12:
            mindst_saa_stor += 1
    return rho, (mindst_saa_stor + 1) / (PERMUTATIONER + 1)


def _afvigelse(kol: str, v: float | None, historik: list[float]) -> dict | None:
    if v is None or len(historik) < 4:
        return None
    med = median(historik)
    mad = median(abs(x - med) for x in historik) * 1.4826
    z = (v - med) / mad if mad > 0 else 0.0
    retning = "over" if v > med else "under" if v < med else "som"
    vurdering = None
    if abs(z) >= Z_GRAENSE:
        if kol in HOEJ_ER_GODT:
            vurdering = "godt" if v > med else "skidt"
        elif kol in LAV_ER_GODT:
            vurdering = "godt" if v < med else "skidt"
    return {
        "vaerdi": v,
        "normal": round(med, 2),
        "normal_interval": [round(min(historik), 2), round(max(historik), 2)],
        "robust_z": round(z, 2),
        "retning": retning,
        "tydelig": abs(z) >= Z_GRAENSE,
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
    brugbare = [u for u in alle[: idx + 1] if (u["garmin_dage"] or 0) >= 5]
    grænse_stærk = 0.05 / len(HYPOTESER)
    sammenhaenge = []
    for x, y, spoergsmaal in HYPOTESER:
        par = [(u[x], u[y]) for u in brugbare if u[x] is not None and u[y] is not None]
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
            "Afvigelse: robust z = (værdi − median) / (1,4826·MAD) over baseline-ugerne; "
            f"|z| ≥ {Z_GRAENSE} er tydelig. Sammenhæng: Spearman med permutationstest, "
            f"kun uger med ≥5 dages Garmin-data. 'stærk' = p < {grænse_stærk:.4f} "
            f"(0,05 delt på {len(HYPOTESER)} hypoteser) og |rho| ≥ 0,3; 'antydning' = p < 0,05. "
            "Korrelation er ikke årsag."
        ),
        "seneste_uger": alle[max(0, idx - 7): idx + 1],
    }
