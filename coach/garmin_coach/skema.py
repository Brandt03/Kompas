"""Titler fra universitetets skema: "Fagnavn (A) - KURS101.A - Lecture (On Campus)".

Titlerne tolkes kun her. Kalenderhentningen gemmer felterne i calendar_events (fag_navn, fag_kode, fag_art,
fag_form), så dagens program, perioderne, overblik og Kompas' sider læser dem i stedet for at tolke titlen.
"""

from __future__ import annotations

import re

_SKEMA_TITEL = re.compile(r"^(?P<navn>.+?)\s*\([A-Z]{1,3}\)\s+-\s+(?P<kode>[^.\s]+)\.\S+\s+-\s+(?P<type>.+)$")
_ART = {"Lecture": "Forelæsning", "Exercise": "Øvelse", "Supervision": "Vejledning", "Workshop": "Workshop",
            "Exam": "Eksamen"}
# Rækkefølgen tæller: "Online: Pre-recorded" er forudindspillet, ikke online
_FORM = [("Pre-recorded", "forudindspillet"), ("Online", "online"), ("Off ", "uden for campus"),
             ("On Campus", "campus")]
FELTER = ("navn", "kode", "art", "form")


def skema_fag(summary: str | None) -> dict | None:
    """En undervisningsgang fra skemaet som felter: fagets navn og kode, arten (forelæsning, øvelse …) og formen
    (campus, online …). Ukendt art eller form er None. Andre titler giver None."""
    m = _SKEMA_TITEL.match((summary or "").strip())
    if not m:
        return None
    art = next((v for k, v in _ART.items() if m["type"].startswith(k)), None)
    form = next((v for k, v in _FORM if k in m["type"]), None)
    return {"navn": m["navn"], "kode": m["kode"], "art": art, "form": form}


def fag_kolonner(summary: str | None) -> dict:
    """skema_fag som kolonnerne i calendar_events; alle None for andre titler."""
    fag = skema_fag(summary) or {}
    return {f"fag_{k}": fag.get(k) for k in FELTER}


def short_title(summary: str | None) -> str:
    """Fjern hold- og fagkode fra titler fra skemaet; andre titler røres ikke."""
    if not summary:
        return "(uden titel)"
    m = _SKEMA_TITEL.match(summary.strip())
    return f"{m['navn']} · {m['type']}" if m else summary.strip()
