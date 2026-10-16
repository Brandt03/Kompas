"""liv — kommandolinjen.

    liv opdater                           genberegn ugetabellen fra kilderne
    liv uger [-n 8] [--json]              vis de seneste uger
    liv rapport [--opdater]               tallene til ugereviewet af seneste hele uge (JSON)
    liv status                            hvor friske er kilderne
    liv gem-review TEKST.json [--uge M]   gem ugereviewets tekst med ugens tal
    liv eksport                           skriv liv.json til Kompas (I dag, Form & fokus)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from . import config, kilder, rapport, side
from .db import KOLONNER, connect, gem_kilde, gem_uge


def opdater(nu: datetime | None = None) -> dict[str, dict]:
    """Genberegn ugetabellen. Hver kilde læses for sig (kilder.saml); en kilde, der fejlede, skrives til stderr og
    står med fejlen i kilder-tabellen, mens de andre gemmes."""
    fra = date.fromisoformat(config.FOERSTE_UGE)
    uger, status = kilder.saml(fra)
    conn = connect()
    with conn:
        for m, v in sorted(uger.items()):
            d = date.fromisoformat(m)
            iso = d.isocalendar()
            gem_uge(conn, f"{iso.year}-W{iso.week:02d}", m, v)
        nu_s = (nu or datetime.now()).isoformat(timespec="seconds")
        for navn, s in status.items():
            gem_kilde(conn, navn, s, nu_s)
    for navn, s in status.items():
        if s["fejl"]:
            print(f"liv: kilden {navn} fejlede, de andre er opdateret: {s['fejl']}", file=sys.stderr)
    return status


def kilde_status(conn) -> list[dict]:
    return kilder.status([dict(r) for r in conn.execute("SELECT * FROM kilder ORDER BY kilde")], date.today())


def hent_uger(n: int) -> list[dict]:
    conn = connect()
    rows = conn.execute("SELECT * FROM uger ORDER BY mandag DESC LIMIT ?", [n]).fetchall()
    return [dict(r) for r in reversed(rows)]


def vis_tabel(uger: list[dict]) -> None:
    if not uger:
        print("Ingen uger endnu — kør `liv opdater`.")
        return
    bredde = max(len(k) for k, _ in KOLONNER)
    print(" " * bredde + "".join(f"{u['uge'][-3:]:>8}" for u in uger))
    for k, _ in KOLONNER:
        celler = []
        for u in uger:
            v = u[k]
            celler.append(f"{'–' if v is None else f'{v:g}':>8}")
        print(f"{k:<{bredde}}" + "".join(celler))


def vis_status() -> None:
    for r in kilde_status(connect()):
        advarsel = f"  ← gammel ({r['alder_dage']} dage)" if r["gammel"] else ""
        if r["fejl"]:
            advarsel += f"  ← fejlede: {r['fejl']}"
        opd = f" opdateret {r['opdateret']}" if r["opdateret"] else ""
        print(f"{r['kilde']:<10} data til {r['data_til'] or '–':<20} hentet {r['hentet'] or '–'}{opd}{advarsel}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="liv", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("opdater", help="genberegn ugetabellen")

    u = sub.add_parser("uger", help="vis seneste uger")
    u.add_argument("-n", type=int, default=8)
    u.add_argument("--json", action="store_true")
    u.add_argument("--opdater", action="store_true", help="kør opdater først")

    r = sub.add_parser("rapport", help="tallene til ugereviewet af seneste hele uge, som JSON")
    r.add_argument("--uge", help="mandagen i ugen, ÅÅÅÅ-MM-DD (standard: sidste hele uge)")
    r.add_argument("--opdater", action="store_true", help="kør opdater først")

    sub.add_parser("status", help="hvor friske er kilderne")

    g = sub.add_parser("gem-review", help="gem ugereviewets tekst sammen med ugens tal, og eksportér")
    g.add_argument("tekst", type=Path, help="JSON med saetning, udskilte, sammenhaenge, kommende_uge, en_ting")
    g.add_argument("--uge", help="mandagen i ugen, ÅÅÅÅ-MM-DD (standard: sidste hele uge)")

    sub.add_parser("eksport", help="skriv liv.json til Kompas (I dag, Form & fokus)")

    a = p.parse_args(argv)

    if a.cmd == "opdater":
        status = opdater()
        for navn, s in status.items():
            print(f"{navn:<10} " + (f"FEJL: {s['fejl']}" if s["fejl"] else f"data til {s['data_til'] or 'ingen data'}"))
        # Ikke-nul, når en kilde fejlede, så opdater.sh i Kompas noterer trinnet som fejlet. De andre er gemt.
        return 1 if any(s["fejl"] for s in status.values()) else 0
    elif a.cmd == "uger":
        if a.opdater:
            opdater()
        uger = hent_uger(a.n)
        if a.json:
            json.dump({"kolonner": dict(KOLONNER), "uger": uger}, sys.stdout, ensure_ascii=False, indent=1)
            print()
        else:
            vis_tabel(uger)
    elif a.cmd == "rapport":
        if a.opdater:
            opdater()
        conn = connect()
        res = rapport.lav(conn, date.fromisoformat(a.uge) if a.uge else None)
        if "fejl" not in res:
            res["kommende_uge"] = rapport.kommende_uge(date.fromisoformat(res["mandag"]), date.today())
        res["kilder"] = kilde_status(conn)
        json.dump(res, sys.stdout, ensure_ascii=False, indent=1)
        print()
    elif a.cmd == "status":
        vis_status()
    elif a.cmd == "gem-review":
        conn = connect()
        m = date.fromisoformat(a.uge) if a.uge else kilder.sidste_hele_uge(date.today())
        doc = side.gem_review(conn, m, json.loads(a.tekst.read_text()))
        print(json.dumps({"gemt": doc["uge"], "metode": doc["metode"], **side.eksport(conn)}, ensure_ascii=False))
    elif a.cmd == "eksport":
        print(json.dumps(side.eksport(connect()), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
