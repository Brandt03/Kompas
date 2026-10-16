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
    hentet     TEXT,               -- hvornår opdater sidst læste kilden uden fejl
    opdateret  TEXT,               -- hvornår kilden selv sidst blev hentet eller ændret (se KILDE_KOLONNER)
    aftryk     TEXT,               -- kalenderens indhold som hash, så en ændring kan ses
    fejl       TEXT                -- fejlen fra sidste opdater, NULL hvis kilden kunne læses
);
CREATE TABLE IF NOT EXISTS reviews (
    uge        TEXT PRIMARY KEY,   -- '2026-W39'
    doc        TEXT NOT NULL       -- tekst fra modellen + tal regnet ved gem
);
"""


# Kolonner i kilder, der kom til efter den første version. En ældre liv.db får dem ved connect.
# opdateret findes, fordi data_til ikke siger noget om friskhed for kalenderen: dens seneste dato er en
# begivenhed langt fremme, så en kalender, der ikke er hentet i ugevis, så frisk ud.
KILDE_KOLONNER = ("opdateret", "aftryk", "fejl")


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    findes = {r["name"] for r in conn.execute("PRAGMA table_info(kilder)")}
    for k in KILDE_KOLONNER:
        if k not in findes:
            conn.execute(f"ALTER TABLE kilder ADD COLUMN {k} TEXT")
    return conn


def gem_kilde(conn: sqlite3.Connection, navn: str, s: dict, nu: str) -> None:
    """Gem én kildes status fra opdater. En kilde, der fejlede, får kun fejlen skrevet; resten står som ved sidste
    vellykkede læsning, så status viser, hvor gamle tallene er.

    opdateret er kildens egen hentetid, når den kendes. Ellers (kalenderen, så længe garmin-coach ikke gemmer,
    hvornår den sidst hentede den) er det første gang, opdater så det nuværende indhold: er aftrykket det samme som
    sidst, står den gamle tid."""
    if s.get("fejl"):
        conn.execute(
            "INSERT INTO kilder (kilde, fejl) VALUES (?, ?) ON CONFLICT(kilde) DO UPDATE SET fejl = excluded.fejl",
            [navn, s["fejl"]],
        )
        return
    opdateret = s.get("opdateret")
    if opdateret is None and s.get("aftryk") is not None:
        gl = conn.execute("SELECT aftryk, opdateret FROM kilder WHERE kilde = ?", [navn]).fetchone()
        opdateret = gl["opdateret"] if gl and gl["aftryk"] == s["aftryk"] and gl["opdateret"] else nu
    conn.execute(
        """INSERT INTO kilder (kilde, data_til, hentet, opdateret, aftryk, fejl) VALUES (?, ?, ?, ?, ?, NULL)
           ON CONFLICT(kilde) DO UPDATE SET data_til = coalesce(excluded.data_til, data_til),
               hentet = excluded.hentet, opdateret = coalesce(excluded.opdateret, opdateret),
               aftryk = coalesce(excluded.aftryk, aftryk), fejl = NULL""",
        [navn, s.get("data_til"), nu, opdateret, s.get("aftryk")],
    )


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
