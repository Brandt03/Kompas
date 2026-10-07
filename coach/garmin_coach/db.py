"""Lokal SQLite-database. Alt rådata gemmes her, så du aldrig mister historik
hvis Garmins uofficielle endpoints ændrer sig."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import CONFIG

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    activity_id      TEXT PRIMARY KEY,
    start_local      TEXT NOT NULL,
    date             TEXT NOT NULL,
    sport            TEXT,
    name             TEXT,
    duration_s       REAL,
    distance_m       REAL,
    avg_hr           REAL,
    max_hr           REAL,
    elev_gain_m      REAL,
    calories         REAL,
    garmin_load      REAL,
    aerobic_te       REAL,
    anaerobic_te     REAL,
    raw              TEXT
);
CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(date);

CREATE TABLE IF NOT EXISTS daily (
    date                TEXT PRIMARY KEY,
    resting_hr          REAL,
    hrv_last_night      REAL,
    hrv_status          TEXT,
    sleep_s             REAL,
    deep_s              REAL,
    rem_s               REAL,
    light_s             REAL,
    awake_s             REAL,
    sleep_score         REAL,
    stress_avg          REAL,
    bb_high             REAL,
    bb_low              REAL,
    steps               REAL,
    training_readiness  REAL,
    vo2max              REAL,
    weight_kg           REAL,
    raw                 TEXT
);

CREATE TABLE IF NOT EXISTS activity_zones (
    activity_id  TEXT NOT NULL,
    zone         INTEGER NOT NULL,
    seconds      REAL,
    low_bpm      REAL,
    PRIMARY KEY (activity_id, zone)
);

-- start_local/end_local er lokal vægurstid uden offset ('2026-09-23T08:00'),
-- så SQLites time()/date() giver samme tid som man ser i kalenderen. Med et
-- offset i strengen omregner SQLite stille til UTC. start_utc/end_utc er de
-- entydige tidspunkter ('2026-09-23T06:00Z').
CREATE TABLE IF NOT EXISTS calendar_events (
    uid          TEXT NOT NULL,
    start_local  TEXT NOT NULL,
    end_local    TEXT,
    start_utc    TEXT,
    end_utc      TEXT,
    summary      TEXT,
    all_day      INTEGER DEFAULT 0,
    PRIMARY KEY (uid, start_local)
);
CREATE INDEX IF NOT EXISTS idx_cal_start ON calendar_events(start_local);

-- Styrkepas fra Hevy. activity_id peger på samme pas i activities: enten
-- Garmin-passet Hevy selv har synket dertil, eller 'hevy:<id>' hvis Garmin
-- ikke har det. Et pas er dermed altid én række i activities.
CREATE TABLE IF NOT EXISTS hevy_workouts (
    workout_id   TEXT PRIMARY KEY,
    activity_id  TEXT,
    title        TEXT,
    start_utc    TEXT NOT NULL,
    end_utc      TEXT,
    updated_at   TEXT,
    raw          TEXT
);
CREATE INDEX IF NOT EXISTS idx_hevy_activity ON hevy_workouts(activity_id);

CREATE TABLE IF NOT EXISTS hevy_sets (
    workout_id      TEXT NOT NULL,
    exercise_index  INTEGER NOT NULL,
    set_index       INTEGER NOT NULL,
    exercise        TEXT,
    template_id     TEXT,
    set_type        TEXT,
    weight_kg       REAL,
    reps            REAL,
    duration_s      REAL,
    distance_m      REAL,
    rpe             REAL,
    PRIMARY KEY (workout_id, exercise_index, set_index)
);

-- Form & Fokus-perioder: tallene fra periode_rapport plus vurderingen som ét
-- JSON-dokument pr. periode, med start ('ÅÅÅÅ-MM-DD') som nøgle.
CREATE TABLE IF NOT EXISTS perioder (
    start  TEXT PRIMARY KEY,
    doc    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
    key    TEXT PRIMARY KEY,
    value  TEXT
);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or CONFIG.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate_calendar_times(conn)
    return conn


def connect_readonly(db_path: Path | None = None) -> sqlite3.Connection:
    """Forbindelse der ikke kan skrive, til SQL der kommer udefra.

    Et tjek på at teksten starter med SELECT er ikke nok: SQLite accepterer
    'WITH x AS (...) DELETE ...'. Her afviser SQLite selv enhver skrivning.
    """
    path = Path(db_path or CONFIG.db_path)
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _migrate_calendar_times(conn: sqlite3.Connection) -> None:
    """Flyt kalendertider fra 'lokal med offset' til 'lokal uden offset + UTC'.

    Ældre versioner gemte '2026-09-23T08:00+02:00' i start_local. SQLites
    datofunktioner læser det som 06:00, så rå SQL viste tider 1-2 timer for
    tidligt. Offsettet i strengen er det lokale, så vægurstiden er blot
    strengen uden offset, og UTC regnes ud fra offsettet.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(calendar_events)")}
    for col in ("start_utc", "end_utc"):
        if col not in cols:
            conn.execute(f"ALTER TABLE calendar_events ADD COLUMN {col} TEXT")

    rows = conn.execute(
        "SELECT uid, start_local, end_local FROM calendar_events "
        "WHERE length(start_local) > 16 OR length(end_local) > 16"
    ).fetchall()
    for r in rows:
        start_local, start_utc = split_local_utc(r["start_local"])
        end_local, end_utc = split_local_utc(r["end_local"])
        conn.execute(
            "UPDATE calendar_events SET start_local = ?, end_local = ?, "
            "start_utc = ?, end_utc = ? WHERE uid = ? AND start_local = ?",
            (start_local, end_local, start_utc, end_utc, r["uid"], r["start_local"]),
        )
    if rows:
        conn.commit()


def split_local_utc(value: str | None) -> tuple[str | None, str | None]:
    """'2026-09-23T08:00+02:00' -> ('2026-09-23T08:00', '2026-09-23T06:00Z')."""
    if not value:
        return value, None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.strftime("%Y-%m-%dT%H:%M"), None
    return (
        dt.strftime("%Y-%m-%dT%H:%M"),
        dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
    )


def upsert(conn: sqlite3.Connection, table: str, row: dict, pk: list[str]) -> None:
    """Indsæt eller opdatér. Felter med None overskriver ikke eksisterende værdier,
    så en delvist fejlet sync ikke sletter data du allerede har."""
    cols = [k for k in row if row[k] is not None]
    if not cols:
        return
    placeholders = ", ".join("?" for _ in cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in pk)
    sql = (
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT({', '.join(pk)}) DO UPDATE SET {updates}"
        if updates
        else f"INSERT OR IGNORE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    )
    conn.execute(sql, [row[c] for c in cols])


def get_state(conn: sqlite3.Connection, key: str) -> str | None:
    cur = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,))
    row = cur.fetchone()
    return row["value"] if row else None


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO sync_state (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
