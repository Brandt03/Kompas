"""Ugereviewet som visningen "Ugen" på Form & Fokus (https://localhost/form/).

Et review gemmes som modellens tekst plus et øjebliksbillede af tallene,
regnet her: rapporten (afvigelser og sammenhænge), ugens dage og pas fra
Garmin og kalenderen for ugen og ugen efter. Kalenderen i garmin-coach
dækker kun ca. 14 dage bagud, så uden øjebliksbilledet ville en gammel uges
kalender forsvinde fra siden.

`eksport` skriver liv.json til Form & Fokus-mappen. Siden (index.html)
bygges af garmin-coach og henter filen ved siden af sig selv. Den skriver
også kalenderen for forrige, denne og næste uge, som den ser ud nu, til
Ugeoverblik i Kompas; reviewets øjebliksbillede er fra mandag og viser ikke
ændringer senere i ugen."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config, rapport
from .db import KOLONNER
from .kilder import mandag as mandag_i

TEKST_LISTER = ("udskilte", "sammenhaenge", "kommende_uge", "forbehold")


def _garmin() -> sqlite3.Connection | None:
    if not config.GARMIN_DB.exists():
        return None
    conn = sqlite3.connect(f"{config.GARMIN_DB.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _t(s: float | None) -> float | None:
    return None if s is None else round(s / 3600, 2)


def _dage(g: sqlite3.Connection, m: date) -> list[dict]:
    """Ugens syv dage. En dag uden Garmin-data står med null, ikke 0."""
    rows = {r["date"]: r for r in g.execute(
        """SELECT date, sleep_s, deep_s, rem_s, light_s, awake_s, sleep_score, hrv_last_night,
                  resting_hr, stress_avg, steps, bb_high, training_readiness
           FROM daily WHERE date BETWEEN ? AND ?""",
        [m.isoformat(), (m + timedelta(days=6)).isoformat()])}
    ud = []
    for i in range(7):
        d = (m + timedelta(days=i)).isoformat()
        r = rows.get(d)
        ud.append({"dato": d} | ({} if r is None else {
            "soevn_t": _t(r["sleep_s"]), "dyb_t": _t(r["deep_s"]), "rem_t": _t(r["rem_s"]),
            "let_t": _t(r["light_s"]), "vaagen_t": _t(r["awake_s"]),
            "soevnscore": r["sleep_score"], "hrv": r["hrv_last_night"], "hvilepuls": r["resting_hr"],
            "stress": r["stress_avg"], "skridt": r["steps"], "bb_top": r["bb_high"],
            "readiness": r["training_readiness"],
        }))
    return ud


def _pas(g: sqlite3.Connection, m: date) -> list[dict]:
    return [
        {"dato": r["date"], "start": r["start_local"][11:16], "sport": r["sport"], "navn": r["name"],
         "minutter": round((r["duration_s"] or 0) / 60), "belastning": None if r["garmin_load"] is None else round(r["garmin_load"])}
        for r in g.execute(
            """SELECT date, start_local, sport, name, duration_s, garmin_load FROM activities
               WHERE date BETWEEN ? AND ? ORDER BY start_local""",
            [m.isoformat(), (m + timedelta(days=6)).isoformat()])
    ]


def _type(titel: str) -> str:
    if config.KURSUSKODE in titel:
        return "undervisning"
    if titel.startswith(config.SELVSTUDIE_PRAEFIKS):
        return "selvstudie"
    return "andet"


def _kalender(g: sqlite3.Connection, m: date) -> list[dict]:
    return [
        {"dato": r["start_local"][:10], "start": None if r["all_day"] else r["start_local"][11:16],
         "slut": None if r["all_day"] or not r["end_local"] else r["end_local"][11:16],
         "titel": r["summary"] or "", "heldag": bool(r["all_day"]), "type": _type(r["summary"] or "")}
        for r in g.execute(
            """SELECT start_local, end_local, summary, all_day FROM calendar_events
               WHERE date(start_local) BETWEEN ? AND ? ORDER BY start_local""",
            [m.isoformat(), (m + timedelta(days=6)).isoformat()])
    ]


def snapshot(conn: sqlite3.Connection, m: date) -> dict:
    """Alle tal for ugen der starter mandag m. Kommende uge er ugen efter."""
    r = rapport.lav(conn, m)
    if "fejl" in r:
        raise ValueError(r["fejl"])
    r.pop("seneste_uger", None)
    doc = {"uge": r.pop("uge"), "mandag": r.pop("mandag"), "rapport": r}
    g = _garmin()
    if g is not None:
        doc |= {"dage": _dage(g, m), "pas": _pas(g, m), "kalender": _kalender(g, m),
                "kommende": _kalender(g, m + timedelta(days=7))}
        g.close()
    return doc


def _check_tekst(t: dict) -> None:
    if not isinstance(t, dict) or not isinstance(t.get("saetning"), str) or not t["saetning"].strip():
        raise ValueError("teksten skal være et objekt med en ikke-tom 'saetning'")
    for k in TEKST_LISTER:
        if k in t and not isinstance(t[k], list):
            raise ValueError(f"tekst.{k} skal være en liste")
    if "en_ting" in t and not isinstance(t["en_ting"], str):
        raise ValueError("tekst.en_ting skal være en streng")


def gem_review(conn: sqlite3.Connection, m: date, tekst: dict) -> dict:
    _check_tekst(tekst)
    doc = snapshot(conn, m) | {"tekst": tekst, "genereret": datetime.now().isoformat(timespec="seconds")}
    with conn:
        conn.execute(
            "INSERT INTO reviews (uge, doc) VALUES (?, ?) ON CONFLICT(uge) DO UPDATE SET doc = excluded.doc",
            [doc["uge"], json.dumps(doc, ensure_ascii=False)])
    return doc


def reviews(conn: sqlite3.Connection) -> list[dict]:
    return [json.loads(r["doc"]) for r in conn.execute("SELECT doc FROM reviews ORDER BY uge")]


# Samme opdeling som rapport.py, så siden farver som reviewet vurderer.
def _god(k: str) -> str | None:
    return "op" if k in rapport.HOEJ_ER_GODT else "ned" if k in rapport.LAV_ER_GODT else None


def eksport(conn: sqlite3.Connection, mappe: Path = config.SITE_DIR) -> dict:
    rs = reviews(conn)
    # Sidste hele uge uden review vises med tal men uden tekst, så siden ikke
    # halter en uge efter, hvis den planlagte opgave ikke har kørt.
    sidste = mandag_i(date.today()) - timedelta(days=7)
    if not any(r["mandag"] == sidste.isoformat() for r in rs):
        try:
            rs.append(snapshot(conn, sidste) | {"tekst": None})
        except ValueError:
            pass
    denne = mandag_i(date.today())
    g = _garmin()
    kalender = {} if g is None else {
        m.isoformat(): _kalender(g, m) for m in (denne - timedelta(days=7), denne, denne + timedelta(days=7))}
    if g is not None:
        g.close()
    ud = {
        "genereret": datetime.now().isoformat(timespec="seconds"),
        "kalender": kalender,
        "z_graense": rapport.Z_GRAENSE,
        "min_uger_korrelation": rapport.MIN_UGER_KORRELATION,
        "selvstudie_fra": config.SELVSTUDIE_FRA,
        "kolonner": [{"k": k, "forklaring": f, "god": _god(k)} for k, f in KOLONNER],
        "uger": [dict(r) for r in conn.execute("SELECT * FROM uger ORDER BY mandag")],
        "kilder": [dict(r) for r in conn.execute("SELECT * FROM kilder ORDER BY kilde")],
        "reviews": rs,
    }
    mappe.mkdir(parents=True, exist_ok=True)
    tmp = mappe / "liv.json.tmp"
    tmp.write_text(json.dumps(ud, ensure_ascii=False))
    os.replace(tmp, mappe / "liv.json")  # atomisk, så Caddy aldrig leverer en halv fil
    return {"fil": str(mappe / "liv.json"), "uger": len(ud["uger"]), "reviews": len(rs)}
