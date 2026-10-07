"""liv — kommandolinjen.

    liv opdater                           genberegn ugetabellen fra kilderne
    liv uger [-n 8] [--json]              vis de seneste uger
    liv rapport [--opdater]               review af seneste hele uge (JSON)
    liv status                            hvor friske er kilderne
    liv gem-review TEKST.json [--uge M]   gem reviewets tekst med ugens tal
    liv eksport                           skriv liv.json til Form & Fokus
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config, kilder, rapport, side
from .db import KOLONNER, connect, gem_uge


def opdater() -> dict[str, str | None]:
    fra = date.fromisoformat(config.FOERSTE_UGE)
    uger, data_til = kilder.saml(fra)
    conn = connect()
    with conn:
        for m, v in sorted(uger.items()):
            d = date.fromisoformat(m)
            iso = d.isocalendar()
            gem_uge(conn, f"{iso.year}-W{iso.week:02d}", m, v)
        nu = datetime.now().isoformat(timespec="seconds")
        for navn, til in data_til.items():
            conn.execute(
                """INSERT INTO kilder VALUES (?, ?, ?) ON CONFLICT(kilde) DO UPDATE
                   SET data_til = coalesce(excluded.data_til, data_til), hentet = excluded.hentet""",
                [navn, til, nu],
            )
    return data_til


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
    conn = connect()
    idag = date.today()
    for r in conn.execute("SELECT * FROM kilder ORDER BY kilde"):
        til = r["data_til"]
        alder = (idag - date.fromisoformat(til[:10])).days if til else None
        advarsel = "  ← gammel" if alder is not None and alder > 3 else ""
        print(f"{r['kilde']:<10} data til {til or '–':<20} hentet {r['hentet']}{advarsel}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="liv", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("opdater", help="genberegn ugetabellen")

    u = sub.add_parser("uger", help="vis seneste uger")
    u.add_argument("-n", type=int, default=8)
    u.add_argument("--json", action="store_true")
    u.add_argument("--opdater", action="store_true", help="kør opdater først")

    r = sub.add_parser("rapport", help="review af seneste hele uge, som JSON")
    r.add_argument("--uge", help="mandagen i ugen, ÅÅÅÅ-MM-DD (standard: sidste hele uge)")
    r.add_argument("--opdater", action="store_true", help="kør opdater først")

    sub.add_parser("status", help="hvor friske er kilderne")

    g = sub.add_parser("gem-review", help="gem reviewets tekst sammen med ugens tal, og eksportér")
    g.add_argument("tekst", type=Path, help="JSON med saetning, udskilte, sammenhaenge, kommende_uge, en_ting")
    g.add_argument("--uge", help="mandagen i ugen, ÅÅÅÅ-MM-DD (standard: sidste hele uge)")

    sub.add_parser("eksport", help="skriv liv.json til Form & Fokus-siden")

    a = p.parse_args(argv)

    if a.cmd == "opdater":
        for navn, til in opdater().items():
            print(f"{navn:<10} data til {til or 'ingen data'}")
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
        res["kilder"] = [dict(k) for k in conn.execute("SELECT * FROM kilder ORDER BY kilde")]
        json.dump(res, sys.stdout, ensure_ascii=False, indent=1)
        print()
    elif a.cmd == "status":
        vis_status()
    elif a.cmd == "gem-review":
        conn = connect()
        m = date.fromisoformat(a.uge) if a.uge else kilder.mandag(date.today()) - timedelta(days=7)
        doc = side.gem_review(conn, m, json.loads(a.tekst.read_text()))
        print(json.dumps({"gemt": doc["uge"], **side.eksport(conn)}, ensure_ascii=False))
    elif a.cmd == "eksport":
        print(json.dumps(side.eksport(connect()), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
