"""Én række pr. ISO-uge. En kolonne er NULL når kilden ikke dækker ugen —
aldrig 0, for et nul er en måling og et hul er ikke."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import DB_PATH

# (kolonne, forklaring). Rækkefølgen er også visningsrækkefølgen.
KOLONNER: list[tuple[str, str]] = [
    # Garmin
    ("garmin_dage", "dage med Garmin-data"),
    ("traening_timer", "træningstimer i alt"),
    ("traening_pas", "antal træningspas"),
    ("belastning", "træningsbelastning, TRIMP fra garmin-coach (styrkepas via Hevy)"),
    ("hrv_snit", "gns. HRV om natten, ms"),
    ("hvilepuls_snit", "gns. hvilepuls, bpm"),
    ("soevn_timer_snit", "gns. søvn pr. nat, timer"),
    ("soevnscore_snit", "gns. søvnscore"),
    ("stress_snit", "gns. stressniveau"),
    ("skridt_snit", "gns. skridt pr. dag"),
    # Økonomi (kr., udgift positiv, refusioner trukket fra)
    ("takeaway_kr", "take-away og mad ude"),
    ("takeaway_koeb", "antal take-away-køb"),
    ("cafe_bar_kr", "café, bar og byture"),
    ("dagligvarer_kr", "dagligvarer"),
    ("variabelt_kr", "variable køb i alt, uden refusioner og deling med venner"),
    # Studie
    ("undervisning_timer", "skemalagt undervisning i kalenderen"),
    ("selvstudie_timer", "selvstudie logget i CalTask"),
    ("selvstudie_dage", "dage med selvstudie"),
]

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS uger (
    uge        TEXT PRIMARY KEY,   -- '2026-W40'
    mandag     TEXT NOT NULL,      -- '2026-09-28'
    {", ".join(f"{k} REAL" for k, _ in KOLONNER)}
);
CREATE TABLE IF NOT EXISTS kilder (
    kilde      TEXT PRIMARY KEY,
    data_til   TEXT,               -- seneste dato kilden har data for
    hentet     TEXT                -- hvornår opdater sidst kørte
);
CREATE TABLE IF NOT EXISTS reviews (
    uge        TEXT PRIMARY KEY,   -- '2026-W39'
    doc        TEXT NOT NULL       -- tekst fra modellen + tal regnet ved gem
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def gem_uge(conn: sqlite3.Connection, uge: str, mandag: str, vaerdier: dict) -> None:
    """Upsert hvor NULL ikke overskriver. Kalenderen i garmin-coach dækker kun
    et vindue omkring i dag, så en uge der er faldet ud af vinduet skal beholde
    det tal den fik mens den var inden for."""
    kol = [k for k, _ in KOLONNER]
    conn.execute(
        f"""INSERT INTO uger (uge, mandag, {", ".join(kol)})
            VALUES (?, ?, {", ".join("?" for _ in kol)})
            ON CONFLICT(uge) DO UPDATE SET
            {", ".join(f"{k} = COALESCE(excluded.{k}, {k})" for k in kol)}""",
        [uge, mandag, *(vaerdier.get(k) for k in kol)],
    )
