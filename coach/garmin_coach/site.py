"""Form & Fokus som lokal side på https://localhost/form/.

    python -m garmin_coach.site byg
    python -m garmin_coach.site perioder
    python -m garmin_coach.site gem-periode START SLUT VURDERING.json [--foreloebig]
    python -m garmin_coach.site importer MAPPE

byg          skriver index.html og data (perioder, måneder, oversigt) til
             ~/.garmin-coach/site, som Caddy leverer. Kører når Kompas-appen åbnes.
             Skriver også Kompas-siderne (perioder, uge, søvn og coach, med
             soevn.json og coach.json) og kompas.json, som fortæller Kompas
             (https://kompas.localhost) hvilke sider projektet har.
perioder     udskriver alle gemte perioder som JSON.
gem-periode  regner periodens tal med periode_rapport, lægger vurderingen fra
             filen på og gemmer den. En endelig periode fjerner foreløbige.
             Tallene regnes her, så de aldrig skal skrives af i hånden.
importer     indlæser periode-dokumenter (én JSON-fil pr. periode), fx fra
             den tidligere claude.ai-side.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from . import metrics
from .db import connect
from .metrics import maanedsoversigt, periode_rapport

SITE_DIR = Path(os.environ.get("GC_SITE", "~/.garmin-coach/site")).expanduser()
PAGE = Path(__file__).resolve().parent.parent / "site" / "index.html"
VURDERING_LISTER = ("gaar_godt", "gaar_daarligt", "forbedring", "fokus", "opfoelgning")
EKSTRA_SIDER = ("perioder.html", "uge.html", "soevn.html", "coach.html", "form.css")

# Det Kompas viser i menuen for dette projekt. Stierne er dem Caddy leverer siden på.
# Siderne er Kompas' version af Form & Fokus i Sures stil; index.html er stadig den samlede side på
# https://localhost/form/.
KOMPAS = {
    "omraade": "Form & fokus", "ikon": "activity", "raekkefoelge": 30,
    "kilde": "garmin-coach (python -m garmin_coach.site byg)",
    "sider": [
        {"titel": "14-dages perioder", "ikon": "calendar-range", "sti": "/form/perioder.html"},
        {"titel": "Ugen i tal", "ikon": "calendar", "sti": "/form/uge.html"},
        {"titel": "Søvn & restitution", "ikon": "moon", "sti": "/form/soevn.html"},
        {"titel": "Coach", "ikon": "message-circle", "sti": "/form/coach.html"},
    ],
}


def _kompas(conn: sqlite3.Connection, out: Path) -> dict:
    """Manifestet med "nyt" pr. side: en nøgle for sidens nyeste indhold. Skifter den, viser
    menuen i Kompas en prik, til siden er åbnet. Ugen i tal viser overbliks review fra
    liv.json, som `liv` skriver i samme mappe."""
    nyt = {}
    endelige = [p for p in perioder(conn) if p.get("status") == "endelig"]
    if endelige:
        nyt["/form/perioder.html"] = endelige[-1]["start"]
    try:
        uger = [r["uge"] for r in json.loads((out / "liv.json").read_text()).get("reviews", []) if r.get("tekst")]
    except (OSError, ValueError):
        uger = []
    if uger:
        nyt["/form/uge.html"] = max(uger)
    return KOMPAS | {"sider": [s | ({"nyt": nyt[s["sti"]]} if s["sti"] in nyt else {}) for s in KOMPAS["sider"]],
                     "opdateret": _now()}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def perioder(conn: sqlite3.Connection) -> list[dict]:
    return [json.loads(r["doc"]) for r in conn.execute("SELECT doc FROM perioder ORDER BY start")]


def gem(conn: sqlite3.Connection, doc: dict) -> None:
    """Gem ét periode-dokument. En endelig periode rydder foreløbige."""
    start = doc["start"]
    conn.execute(
        "INSERT INTO perioder (start, doc) VALUES (?, ?) "
        "ON CONFLICT(start) DO UPDATE SET doc = excluded.doc",
        (start, json.dumps(doc, ensure_ascii=False)),
    )
    if doc.get("status") == "endelig":
        for other in perioder(conn):
            if other["start"] != start and other.get("status") == "foreløbig":
                conn.execute("DELETE FROM perioder WHERE start = ?", (other["start"],))
    conn.commit()


def _check_vurdering(v: dict) -> None:
    if not isinstance(v, dict) or not isinstance(v.get("resume"), str) or not v["resume"].strip():
        raise ValueError("vurdering skal være et objekt med en ikke-tom 'resume'")
    for k in VURDERING_LISTER:
        if k in v and not isinstance(v[k], list):
            raise ValueError(f"vurdering.{k} skal være en liste")


def ny_periode(conn: sqlite3.Connection, start: str, slut: str, vurdering: dict,
               status: str = "endelig") -> dict:
    _check_vurdering(vurdering)
    doc = {
        **periode_rapport(conn, start, slut),
        "status": status, "kilde": "rapport", "genereret": _now(), "vurdering": vurdering,
    }
    gem(conn, doc)
    return doc


def _write(path: Path, text: str) -> None:
    """Skriv atomisk, så Caddy aldrig leverer en halv fil."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def soevn(conn: sqlite3.Connection, dage: int = 60) -> dict:
    """Nat for nat de seneste `dage` dage plus restitutionsstatus fra metrics.recovery.
    En nat uden måling står med null, ikke 0."""
    t = lambda s: None if s is None else round(s / 3600, 2)
    rows = conn.execute(
        """SELECT date, sleep_s, deep_s, rem_s, light_s, awake_s, sleep_score, hrv_last_night, hrv_status,
                  resting_hr, training_readiness, bb_high, stress_avg
           FROM daily WHERE date >= date('now', 'localtime', ?) ORDER BY date""", (f"-{dage - 1} days",))
    naetter = [{
        "dato": r["date"], "soevn_t": t(r["sleep_s"]), "dyb_t": t(r["deep_s"]), "rem_t": t(r["rem_s"]),
        "let_t": t(r["light_s"]), "vaagen_t": t(r["awake_s"]), "soevnscore": r["sleep_score"],
        "hrv": r["hrv_last_night"], "hrv_status": r["hrv_status"], "hvilepuls": r["resting_hr"],
        "readiness": r["training_readiness"], "bb_top": r["bb_high"], "stress": r["stress_avg"],
    } for r in rows]
    return {"naetter": naetter, "restitution": metrics.recovery(conn, days=14), "genereret": _now()}


def coach(conn: sqlite3.Connection) -> dict:
    """Coach-siden: dagens restitution, råd og belastning, de næste tre dage og fokus fra den
    seneste endelige 14-dages rapport. Rådet bruges også af Kompas' forside. Siden viser kun tal og tekst herfra; selve
    samtalen med coachen foregår i Claude via garmin-coach-værktøjerne."""
    tl = metrics.training_load(conn, weeks=6)
    endelige = [p for p in perioder(conn) if p.get("status") == "endelig"]
    seneste = endelige[-1] if endelige else None
    return {
        "restitution": metrics.recovery(conn, days=14),
        "dagens_raad": metrics.dagens_raad(conn),
        "belastning": {k: tl.get(k) for k in (
            "beregnet_til_og_med", "akut_7d", "kronisk_uge_snit_28d", "acwr", "acwr_fortolkning",
            "i_dag_indtil_nu", "ugentligt", "pas_uden_belastning_28d")}
        | {"tre_baand_procent": (tl.get("intensitetsfordeling_28d") or {}).get("tre_baand_procent"),
           "intensitet_note": (tl.get("intensitetsfordeling_28d") or {}).get("note")},
        "kalender": metrics.schedule(conn, days_ahead=3),
        "periode": None if seneste is None else {
            "start": seneste["start"], "slut": seneste["slut"], "vurdering": seneste.get("vurdering")},
        "genereret": _now(),
    }


def belastning(conn: sqlite3.Connection) -> dict:
    """Træningsbelastning pr. dag for hele historikken, regnet ét sted (metrics.daily_loads: Banister-TRIMP ud fra
    puls, styrkepas ud fra Hevy-sæt kalibreret til TRIMP). Til andre projekter, så de ikke regner deres egen
    belastning: pr. dag (overblik lægger dagene sammen til uger) og pr. pas. En dag uden pas er 0, og dage før
    første pas er ikke med."""
    ath = metrics.athlete(conn)
    ctx = metrics.load_context(conn, ath)
    aktiviteter = conn.execute("SELECT * FROM activities ORDER BY date").fetchall()
    dage = metrics.daily_loads(conn, date.fromisoformat(aktiviteter[0]["date"]), date.today(), ath, ctx) if aktiviteter else {}
    return {"metode": "TRIMP (Banister ud fra puls; styrkepas ud fra Hevy-sæt kalibreret til TRIMP)",
            "dage": {d: round(v, 1) for d, v in dage.items()},
            "pas": {str(r["activity_id"]): round(metrics.session_load(r, ath, ctx), 1) for r in aktiviteter},
            "genereret": _now()}


def byg(conn: sqlite3.Connection, out: Path = SITE_DIR) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PAGE, out / "index.html.tmp")
    os.replace(out / "index.html.tmp", out / "index.html")
    for navn in EKSTRA_SIDER:
        if (PAGE.parent / navn).exists():
            shutil.copyfile(PAGE.parent / navn, out / f"{navn}.tmp")
            os.replace(out / f"{navn}.tmp", out / navn)
    # Søvn, Coach og belastningen må ikke vælte resten af siden, hvis data er for tynde til en beregning
    for navn, f in (("soevn.json", soevn), ("coach.json", coach), ("belastning.json", belastning)):
        try:
            data = f(conn)
        except Exception as e:  # noqa: BLE001
            data = {"fejl": f"{type(e).__name__}: {e}", "genereret": _now()}
        _write(out / navn, json.dumps(data, ensure_ascii=False, default=str))
    _write(out / "kompas.json", json.dumps(_kompas(conn, out), ensure_ascii=False))
    ps = perioder(conn)
    ov = maanedsoversigt(conn)
    months = [r["maaned"] for r in ov["maaneder"]]
    _write(out / "perioder.json", json.dumps(ps, ensure_ascii=False))
    _write(out / "maaneder.json", json.dumps(ov["maaneder"], ensure_ascii=False))
    _write(out / "oversigt.json", json.dumps({
        "udvikling": ov["udvikling"], "forbehold": ov["forbehold"],
        "fra": months[0] if months else None, "til": months[-1] if months else None,
        "genereret": _now(),
    }, ensure_ascii=False))
    return {"mappe": str(out), "perioder": len(ps), "maaneder": len(months)}


def importer(conn: sqlite3.Connection, mappe: Path) -> int:
    n = 0
    for f in sorted(mappe.glob("*.json")):
        doc = json.loads(f.read_text())
        doc.pop("id", None)
        gem(conn, doc)
        n += 1
    return n


def _cli() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    conn = connect()
    try:
        cmd = args[0]
        if cmd == "byg":
            out = byg(conn)
        elif cmd == "perioder":
            out = perioder(conn)
        elif cmd == "gem-periode" and len(args) >= 4:
            status = "foreløbig" if "--foreloebig" in args else "endelig"
            doc = ny_periode(conn, args[1], args[2], json.loads(Path(args[3]).read_text()), status)
            out = {"gemt": doc["start"], "slut": doc["slut"], "status": doc["status"], **byg(conn)}
        elif cmd == "importer" and len(args) == 2:
            out = {"importeret": importer(conn, Path(args[1]).expanduser())}
        else:
            sys.exit(__doc__)
    finally:
        conn.close()
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    _cli()
