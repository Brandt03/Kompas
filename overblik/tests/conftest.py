"""Fælles opsætning. Alle stier peges mod en midlertidig mappe, før overblik importeres, så testene aldrig
rører liv.db, coach.db, Sures eksport eller liv.json. Hver test får desuden sine egne filer (`miljoe`)."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="liv-test-"))
for _env, _navn in {"LIV_DB": "liv.db", "LIV_GARMIN_DB": "coach.db", "LIV_BELASTNING_JSON": "belastning.json",
                    "LIV_SURE_JSON": "data.json", "LIV_SITE": "site"}.items():
    os.environ[_env] = str(_TMP / _navn)

import pytest  # noqa: E402

from overblik import config, db, kilder  # noqa: E402

GARMIN_SCHEMA = """
CREATE TABLE daily (date TEXT PRIMARY KEY, hrv_last_night REAL, resting_hr REAL, sleep_s REAL, sleep_score REAL,
                    stress_avg REAL, steps REAL, deep_s REAL, rem_s REAL, light_s REAL, awake_s REAL, bb_high REAL,
                    training_readiness REAL);
CREATE TABLE activities (activity_id INTEGER PRIMARY KEY, date TEXT, start_local TEXT, sport TEXT, name TEXT,
                         duration_s REAL);
CREATE TABLE calendar_events (uid TEXT NOT NULL, start_local TEXT NOT NULL, end_local TEXT, summary TEXT,
                              all_day INTEGER DEFAULT 0, start_utc TEXT, end_utc TEXT, fag_navn TEXT, fag_kode TEXT,
                              fag_art TEXT, fag_form TEXT, kalender TEXT, PRIMARY KEY (uid, start_local));
CREATE TABLE sync_state (key TEXT PRIMARY KEY, value TEXT);
"""


def idag() -> date:
    return date.today()


def lav_garmin(path: Path, dage: list[date], begivenheder: list[tuple], state: dict | None = None) -> None:
    """En lille coach.db: én døgnrække pr. dag og kalenderbegivenheder (uid, start, slut, titel, fag_kode)."""
    if path.exists():
        path.unlink()
    g = sqlite3.connect(path)
    g.executescript(GARMIN_SCHEMA)
    for d in dage:
        g.execute("INSERT INTO daily (date, hrv_last_night, resting_hr, sleep_s, sleep_score, stress_avg, steps) "
                  "VALUES (?, 60, 50, 27000, 80, 25, 9000)", [d.isoformat()])
    for uid, start, slut, titel, fag_kode in begivenheder:
        g.execute("INSERT INTO calendar_events (uid, start_local, end_local, summary, fag_kode, kalender) "
                  "VALUES (?, ?, ?, ?, ?, 'Test')", [uid, start, slut, titel, fag_kode])
    for k, v in (state or {}).items():
        g.execute("INSERT INTO sync_state VALUES (?, ?)", [k, v])
    g.commit()
    g.close()


def lav_sure(path: Path, transaktioner: list[dict], last_sync: str) -> None:
    path.write_text(json.dumps({"generated_at": last_sync, "last_sync": last_sync, "transactions": transaktioner}))


@pytest.fixture
def miljoe(tmp_path, monkeypatch):
    """Egne stier pr. test, med tre ugers Garmin-data, kalender (også fremtidige begivenheder) og Sure."""
    monkeypatch.setattr(config, "GARMIN_DB", tmp_path / "coach.db")
    monkeypatch.setattr(config, "BELASTNING_JSON", tmp_path / "belastning.json")
    monkeypatch.setattr(config, "SURE_JSON", tmp_path / "data.json")
    monkeypatch.setattr(config, "SITE_DIR", tmp_path / "site")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "liv.db")
    m = kilder.mandag(idag()) - timedelta(days=14)
    monkeypatch.setattr(config, "FOERSTE_UGE", m.isoformat())
    monkeypatch.setattr(config, "SELVSTUDIE_FRA", m.isoformat())
    dage = [m + timedelta(days=i) for i in range((idag() - m).days)]
    begivenheder = [(f"u{i}", f"{(m + timedelta(days=7 * i + 1)).isoformat()}T10:00",
                     f"{(m + timedelta(days=7 * i + 1)).isoformat()}T12:00", "Forelæsning", "PROG") for i in range(5)]
    lav_garmin(config.GARMIN_DB, dage, begivenheder)
    lav_sure(config.SURE_JSON, [
        {"date": (m + timedelta(days=2)).isoformat(), "amount": 120, "group": "Variable udgifter",
         "category": "Take-away og mad ude"},
        {"date": (m + timedelta(days=9)).isoformat(), "amount": 80, "group": "Variable udgifter",
         "category": "Take-away og mad ude"},
    ], (idag() - timedelta(days=1)).isoformat())
    return {"tmp": tmp_path, "mandag": m}
