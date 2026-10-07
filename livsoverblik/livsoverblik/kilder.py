"""Læser de tre kilder og giver ugetal tilbage. Hver funktion returnerer
{mandag: {kolonne: værdi}} og udelader uger kilden ikke dækker."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta

from . import config


def mandag(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _r(x: float | None, n: int = 1) -> float | None:
    return None if x is None else round(x, n)


# --- Garmin -----------------------------------------------------------------

def garmin(fra: date) -> tuple[dict, str | None]:
    if not config.GARMIN_DB.exists():
        return {}, None
    conn = sqlite3.connect(f"{config.GARMIN_DB.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    data_til = conn.execute("SELECT max(date) FROM daily").fetchone()[0]

    # Mandagen i SQL: træk 6 dage fra og ryk frem til næste mandag.
    uge = "date(date, '-6 days', 'weekday 1')"
    ud: dict[str, dict] = {}
    for r in conn.execute(
        f"""SELECT {uge} AS m, count(*) AS dage,
                   avg(hrv_last_night) AS hrv, avg(resting_hr) AS rhr,
                   avg(sleep_s) / 3600.0 AS soevn, avg(sleep_score) AS score,
                   avg(stress_avg) AS stress, avg(steps) AS skridt
            FROM daily WHERE date >= ? GROUP BY m""",
        [fra.isoformat()],
    ):
        ud[r["m"]] = {
            "garmin_dage": r["dage"],
            "hrv_snit": _r(r["hrv"]),
            "hvilepuls_snit": _r(r["rhr"]),
            "soevn_timer_snit": _r(r["soevn"], 2),
            "soevnscore_snit": _r(r["score"]),
            "stress_snit": _r(r["stress"]),
            "skridt_snit": _r(r["skridt"], 0),
            # En uge med døgndata men ingen pas er en uge uden træning.
            "traening_timer": 0.0,
            "traening_pas": 0,
            "belastning": 0.0,
        }
    for r in conn.execute(
        f"""SELECT {uge} AS m, count(*) AS pas, sum(duration_s) / 3600.0 AS timer,
                   coalesce(sum(garmin_load), 0) AS load
            FROM activities WHERE date >= ? GROUP BY m""",
        [fra.isoformat()],
    ):
        if r["m"] in ud:
            ud[r["m"]].update(
                traening_pas=r["pas"], traening_timer=_r(r["timer"], 2), belastning=_r(r["load"], 0)
            )
    conn.close()
    return ud, data_til


# --- Økonomi (Sure) ---------------------------------------------------------

KATEGORIER = {
    "Take-away og mad ude": "takeaway_kr",
    "Café, bar og byture": "cafe_bar_kr",
    "Dagligvarer": "dagligvarer_kr",
}
UDEN_FOR_VARIABELT = {"Deling med venner"}


def oekonomi(fra: date) -> tuple[dict, str | None]:
    if not config.SURE_JSON.exists():
        return {}, None
    eksport = json.loads(config.SURE_JSON.read_text())
    # last_sync er seneste banksynk. Uger efter den er ikke dækket endnu, og
    # posteringer med dato efter den er planlagte (fx kommende PBS-træk).
    synk = (eksport.get("last_sync") or eksport["generated_at"])[:10]
    slut = date.fromisoformat(synk)

    ud: dict[str, dict] = {}
    m = mandag(fra)
    while m <= slut:
        ud[m.isoformat()] = {k: 0.0 for k in (*KATEGORIER.values(), "variabelt_kr")} | {"takeaway_koeb": 0}
        m += timedelta(days=7)

    for t in eksport["transactions"]:
        d = date.fromisoformat(t["date"])
        if d < fra or d > slut:
            continue
        uge = ud[mandag(d).isoformat()]
        belob = float(t["amount"])  # Sure: udgift positiv, indtægt negativ
        # Kun køb, ikke refusioner: en refusion fra sygeforsikringen hører til
        # en anden uges udgift og kan ellers gøre ugen negativ. Deling med
        # venner er udlæg for andre og siger intet om eget forbrug.
        if t["group"] == "Variable udgifter" and t["category"] not in UDEN_FOR_VARIABELT and belob > 0:
            uge["variabelt_kr"] += belob
        if (kol := KATEGORIER.get(t["category"])) is not None:
            uge[kol] += belob
            if kol == "takeaway_kr" and belob > 0:
                uge["takeaway_koeb"] += 1

    for uge in ud.values():
        for k, v in uge.items():
            uge[k] = round(v)
    return ud, synk


# --- Studie -----------------------------------------------------------------

def kalender(fra: date) -> tuple[dict, str | None]:
    """Undervisning og selvstudie fra kalenderen i garmin-coach.

    Undervisning er begivenheder med en kursuskode (config.KURSUSKODE). Selvstudie er
    CalTask-begivenheder ("Selvstudie · Alfa"), og varigheden er den tid der blev
    logget. Kun uger som kalendervinduet dækker fra mandag af tæller med —
    ellers ville ugen tælle for lavt. Selvstudie før logningen begyndte er
    ukendt, ikke 0."""
    if not config.GARMIN_DB.exists():
        return {}, None
    conn = sqlite3.connect(f"{config.GARMIN_DB.resolve().as_uri()}?mode=ro", uri=True)
    foerste, sidste = conn.execute(
        "SELECT min(date(start_local)), max(date(start_local)) FROM calendar_events"
    ).fetchone()
    if foerste is None:
        return {}, None
    rows = conn.execute(
        """SELECT start_local, end_local, summary FROM calendar_events
           WHERE all_day = 0 AND end_local IS NOT NULL AND date(start_local) >= ?""",
        [fra.isoformat()],
    ).fetchall()
    conn.close()

    start = max(fra, date.fromisoformat(foerste))
    m = mandag(start) if start.weekday() == 0 else mandag(start) + timedelta(days=7)
    studie_fra = mandag(date.fromisoformat(config.SELVSTUDIE_FRA))
    # Kun uger der er begyndt; fremtidige uger har intet at sammenligne med.
    nu = datetime.now()
    ud: dict[str, dict] = {}
    while m <= min(mandag(nu.date()), date.fromisoformat(sidste)):
        ud[m.isoformat()] = {"undervisning_timer": 0.0}
        if m >= studie_fra:
            ud[m.isoformat()] |= {"selvstudie_timer": 0.0, "_dage": set()}
        m += timedelta(days=7)

    for start_s, slut_s, titel in rows:
        s, e = datetime.fromisoformat(start_s), datetime.fromisoformat(slut_s)
        uge = ud.get(mandag(s.date()).isoformat())
        if uge is None:
            continue
        timer = (e - s).total_seconds() / 3600
        if config.KURSUSKODE in (titel or ""):
            uge["undervisning_timer"] += timer
        elif (titel or "").startswith(config.SELVSTUDIE_PRAEFIKS) and "_dage" in uge and e <= nu and timer > 0:
            uge["selvstudie_timer"] += timer
            uge["_dage"].add(s.date())

    for uge in ud.values():
        uge["undervisning_timer"] = round(uge["undervisning_timer"], 1)
        if "_dage" in uge:
            uge["selvstudie_timer"] = round(uge["selvstudie_timer"], 2)
            uge["selvstudie_dage"] = len(uge.pop("_dage"))
    return ud, sidste


# --- Samlet -----------------------------------------------------------------

KILDER = {
    "garmin": garmin,
    "sure": oekonomi,
    "kalender": kalender,
}


def saml(fra: date) -> tuple[dict[str, dict], dict[str, str | None]]:
    uger: dict[str, dict] = defaultdict(dict)
    data_til: dict[str, str | None] = {}
    for navn, fn in KILDER.items():
        tal, til = fn(fra)
        data_til[navn] = til
        for m, v in tal.items():
            uger[m].update(v)
    return dict(uger), data_til
