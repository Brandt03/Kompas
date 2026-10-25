"""Form & fokus som lokal side på https://localhost/form/.

    python -m garmin_coach.site byg
    python -m garmin_coach.site perioder
    python -m garmin_coach.site gem-periode START SLUT VURDERING.json [--foreloebig]
    python -m garmin_coach.site importer MAPPE

byg          skriver data (perioder, oversigt) og index.html, der sender /form/ videre til Perioder, til
             ~/.garmin-coach/site, som Caddy leverer. Kører når programmet Kompas åbnes.
             Skriver også Kompas-siderne (perioder, ugereview og kroppen, med
             kroppen.json; soevn.json og coach.json til Kompas' I dag) og kompas.json, som fortæller Kompas
             (https://kompas.localhost) hvilke sider projektet har.
perioder     udskriver alle gemte perioder som JSON.
gem-periode  regner periodens tal med periode_rapport, lægger vurderingen fra
             filen på og gemmer den. En endelig periode fjerner foreløbige.
             Tallene regnes her, så de aldrig skal skrives af i hånden.
             Afviser en endelig periode, der ikke slutter på en fredag, og en
             start, der ikke er dagen efter forrige endelige periodes slut.
importer     indlæser periode-dokumenter (én JSON-fil pr. periode), fx fra
             den tidligere claude.ai-side.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import metrics
from .db import connect
from .kroppen import byg_filer, kroppen
from .metrics import maanedsoversigt, periode_rapport

log = logging.getLogger(__name__)

SITE_DIR = Path(os.environ.get("GC_SITE", "~/.garmin-coach/site")).expanduser()
PAGE = Path(__file__).resolve().parent.parent / "site" / "index.html"  # sender /form/ videre til Perioder
VURDERING_LISTER = ("gaar_godt", "gaar_daarligt", "forbedring", "fokus", "opfoelgning")
UGEDAGE = ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag")
EKSTRA_SIDER = ("perioder.html", "uge.html", "kroppen.html", "form.css")
# Sider og data, der er lagt sammen med andre eller ikke bruges mere; byg fjerner den gamle kopi, så Caddy ikke
# leverer den. maaneder.json hørte til den gamle samlede side på /form/.
FJERNEDE_SIDER = ("soevn.html", "coach.html", "maaneder.json")

# Det Kompas viser i menuen for dette projekt. Stierne er dem Caddy leverer siden på.
# Siderne er Kompas' version af Form & fokus i Sures stil; index.html sender https://kompas.localhost/form/ og
# https://localhost/form/ videre til Perioder.
KOMPAS = {
    "omraade": "Form & fokus", "ikon": "activity", "raekkefoelge": 30,
    "kilde": "garmin-coach (python -m garmin_coach.site byg)",
    "sider": [
        {"titel": "Perioder", "ikon": "calendar-range", "sti": "/form/perioder.html"},
        {"titel": "Ugereview", "ikon": "calendar", "sti": "/form/uge.html"},
        {"titel": "Kroppen i tal", "ikon": "chart-bar", "sti": "/form/kroppen.html"},
    ],
}


def _kompas(conn: sqlite3.Connection, out: Path, ps: list[dict] | None = None) -> dict:
    """Manifestet med "nyt" pr. side: en nøgle for sidens nyeste indhold. Skifter den, viser
    menuen i Kompas en prik, til siden er åbnet. Ugereview viser ugereviewet fra overblik i
    liv.json, som `liv` skriver i samme mappe."""
    nyt = {}
    endelige = [p for p in (perioder(conn) if ps is None else ps) if p.get("status") == "endelig"]
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


def _laes_perioder(conn: sqlite3.Connection) -> tuple[list[dict], list[str]]:
    """Alle læsbare perioder, ældste først, og nøglerne på dem der blev sprunget over.

    Et defekt dokument (ikke JSON, ikke et objekt, eller uden gyldig start og slut) må
    ikke vælte siden eller de andre perioder: det springes over med en advarsel i loggen."""
    ud, sprunget = [], []
    for r in conn.execute("SELECT start, doc FROM perioder ORDER BY start"):
        try:
            doc = json.loads(r["doc"])
            if not isinstance(doc, dict):
                raise ValueError("dokumentet er ikke et objekt")
            date.fromisoformat(doc["start"]), date.fromisoformat(doc["slut"])
        except (KeyError, TypeError, ValueError) as e:
            grund = f"mangler {e}" if isinstance(e, KeyError) else str(e)
            log.warning("Springer periode %s over, dokumentet er defekt: %s", r["start"], grund)
            sprunget.append(r["start"])
            continue
        ud.append(doc)
    return ud, sprunget


def perioder(conn: sqlite3.Connection) -> list[dict]:
    return _laes_perioder(conn)[0]


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


def _check_datoer(conn: sqlite3.Connection, start: str, slut: str, status: str) -> None:
    """Perioderne går lørdag til fredag og følger lige efter hinanden.

    En endelig periode skal slutte på en fredag. Starten skal være dagen efter forrige
    endelige periodes slut (eller en lørdag, hvis der ingen er), og perioden må ikke gå ind
    i en senere endelig periode. En foreløbig periode slutter midt i perioden, så kun dens
    start tjekkes. Gemte perioder rettes aldrig her."""
    try:
        s, e = date.fromisoformat(start), date.fromisoformat(slut)
    except ValueError:
        raise ValueError(f"start og slut skal være datoer som ÅÅÅÅ-MM-DD, ikke {start!r} og {slut!r}") from None
    if e < s:
        raise ValueError(f"slut ({slut}) ligger før start ({start})")
    if status == "endelig" and e.weekday() != 4:
        raise ValueError(f"slut skal være en fredag, men {slut} er en {UGEDAGE[e.weekday()]}. "
                         "Perioderne går lørdag til fredag.")
    endelige = [p for p in perioder(conn) if p.get("status") == "endelig"]
    foer = [p for p in endelige if p["start"] < s.isoformat()]
    if foer:
        ventet = date.fromisoformat(foer[-1]["slut"]) + timedelta(days=1)
        if s != ventet:
            raise ValueError(f"start skal være dagen efter forrige periodes slut ({foer[-1]['slut']}), "
                             f"altså {ventet.isoformat()}, ikke {start}.")
    elif s.weekday() != 5:
        raise ValueError(f"start skal være en lørdag, men {start} er en {UGEDAGE[s.weekday()]}. "
                         "Perioderne går lørdag til fredag.")
    efter = [p for p in endelige if p["start"] > s.isoformat()]
    if efter and e.isoformat() >= efter[0]["start"]:
        raise ValueError(f"perioden går ind i den næste, der starter {efter[0]['start']}")


def ny_periode(conn: sqlite3.Connection, start: str, slut: str, vurdering: dict,
               status: str = "endelig") -> dict:
    _check_vurdering(vurdering)
    _check_datoer(conn, start, slut, status)
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
    """Nat for nat de seneste `dage` dage plus restitutionsstatus fra metrics.recovery, til Kompas' I dag
    (Søvn i nat). En nat uden måling står med null, ikke 0."""
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


def coach(conn: sqlite3.Connection, ps: list[dict] | None = None) -> dict:
    """Til Kompas' forside I dag: dagens restitution, råd og belastning, de næste tre dage og fokus fra den
    seneste endelige periode. Kroppen i tal viser rådet, belastningen og intensiteten fra kroppen.json; selve
    samtalen med coachen foregår i Claude via garmin-coach-værktøjerne."""
    tl = metrics.training_load(conn, weeks=6)
    endelige = [p for p in (perioder(conn) if ps is None else ps) if p.get("status") == "endelig"]
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
    for navn in FJERNEDE_SIDER:
        (out / navn).unlink(missing_ok=True)
    ps, sprunget = _laes_perioder(conn)  # defekte perioder springes over med én advarsel hver
    # Søvn, Coach og belastningen må ikke vælte resten af siden, hvis data er for tynde til en beregning
    for navn, f in (("soevn.json", soevn), ("kroppen.json", kroppen), ("coach.json", lambda c: coach(c, ps)),
                    ("belastning.json", belastning)):
        try:
            data = f(conn)
        except Exception as e:  # noqa: BLE001
            log.warning("%s kunne ikke beregnes: %s: %s", navn, type(e).__name__, e)
            data = {"fejl": f"{type(e).__name__}: {e}", "genereret": _now()}
        _write(out / navn, json.dumps(data, ensure_ascii=False, default=str))
    # Kroppen i tal: døgn- og månedsfilerne, så siden kan gå tilbage i tid; kun de ændrede skrives
    try:
        byg_filer(conn, out, _write)
    except Exception as e:  # noqa: BLE001
        log.warning("Kroppen i tal: døgn- og månedsfilerne kunne ikke bygges: %s: %s", type(e).__name__, e)
    ov = maanedsoversigt(conn)
    months = [r["maaned"] for r in ov["maaneder"]]
    # Perioder gemt før løb og svømning kom med, får dem regnet her ud fra aktiviteterne, som ikke ændrer sig
    ps = [p if "kondition" in p else p | {"kondition": metrics.kondition(conn, p["start"], p["slut"])} for p in ps]
    _write(out / "perioder.json", json.dumps(ps, ensure_ascii=False))

    _write(out / "oversigt.json", json.dumps({
        "udvikling": ov.get("udvikling"), "forbehold": ov.get("forbehold", []),  # uden data: ingen udvikling
        "fra": months[0] if months else None, "til": months[-1] if months else None,
        "genereret": _now(),
    }, ensure_ascii=False))
    # Manifestet til sidst: menuens prik og "opdateret" peger først på nyt, når siderne bag dem er skrevet.
    # Fejler noget ovenfor, står det gamle manifest urørt.
    _write(out / "kompas.json", json.dumps(_kompas(conn, out, ps), ensure_ascii=False))
    return {"mappe": str(out), "perioder": len(ps), "maaneder": len(months),
            **({"sprunget_over": sprunget} if sprunget else {})}


def importer(conn: sqlite3.Connection, mappe: Path) -> int:
    n = 0
    for f in sorted(mappe.glob("*.json")):
        doc = json.loads(f.read_text())
        doc.pop("id", None)
        gem(conn, doc)
        n += 1
    return n


def _cli() -> None:
    # Advarsler (fx en defekt periode) på stderr, så stdout forbliver ren JSON
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
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
            try:
                doc = ny_periode(conn, args[1], args[2], json.loads(Path(args[3]).expanduser().read_text()), status)
            except ValueError as e:
                sys.exit(f"gem-periode: intet gemt. {e}")
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
