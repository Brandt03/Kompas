"""Laver demodata til Kompas i demo/ud, med datoer omkring i dag. Alt indhold er opdigtet.

Hvert område har sit eget modul i demo/projekter/ med en funktion lav(ud, idag), der skriver de filer, områdets
sider læser (fx ud/form/coach.json for /form/coach.json). Kun standardbiblioteket.

    python3 demo/lav.py              skriv demo/ud for i dag
    python3 demo/lav.py 2026-11-02   som om det var en anden dag
"""
from __future__ import annotations

import importlib
import shutil
import sys
from datetime import date
from pathlib import Path

DEMO = Path(__file__).resolve().parent
UD = DEMO / "ud"
OMRAADER = ["form", "studie", "karriere", "forbrug"]


def lav(ud: Path = UD, idag: date | None = None) -> None:
    idag = idag or date.today()
    if ud.exists():
        shutil.rmtree(ud)
    ud.mkdir(parents=True)
    sys.path.insert(0, str(DEMO / "projekter"))
    for navn in OMRAADER:
        importlib.import_module(navn).lav(ud, idag)


if __name__ == "__main__":
    lav(idag=date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None)
    print(f"Demodata skrevet i {UD}")
