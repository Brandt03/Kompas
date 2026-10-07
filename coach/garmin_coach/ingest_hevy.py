"""Henter styrkepas fra Hevy.

Hevy synker selv pas til Garmin, men kun som varighed og en tekst: sæt, vægt,
reps og RPE går tabt undervejs. Her hentes de direkte fra Hevys API og hænges
på det Garmin-pas der svarer til, så samme træning aldrig tæller to gange.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .config import CONFIG
from .db import connect, get_state, set_state, upsert
from .ingest_calendar import _SSL

log = logging.getLogger(__name__)

API = "https://api.hevyapp.com"
# Et Hevy-pas og dets kopi i Garmin starter i praksis på samme sekund.
MATCH_WINDOW_S = 120


def _http_get(path: str) -> dict:
    req = Request(API + path, headers={"api-key": CONFIG.hevy_api_key or "",
                                       "accept": "application/json"})
    with urlopen(req, timeout=30, context=_SSL) as resp:  # noqa: S310
        return json.loads(resp.read())


def _pages(get: Callable[[str], dict], path: str, key: str):
    page = 1
    while True:
        sep = "&" if "?" in path else "?"
        data = get(f"{path}{sep}page={page}&pageSize=10")
        yield from data.get(key) or []
        if page >= (data.get("page_count") or 1):
            return
        page += 1
        time.sleep(0.3)


def _store_workout(conn: sqlite3.Connection, w: dict) -> None:
    upsert(conn, "hevy_workouts", {
        "workout_id": w["id"],
        "title": w.get("title"),
        "start_utc": w["start_time"],
        "end_utc": w.get("end_time"),
        "updated_at": w.get("updated_at"),
        "raw": json.dumps(w, default=str),
    }, pk=["workout_id"])
    # Sæt kan være tilføjet, fjernet eller flyttet: erstat dem alle
    conn.execute("DELETE FROM hevy_sets WHERE workout_id = ?", (w["id"],))
    for e in w.get("exercises") or []:
        for s in e.get("sets") or []:
            conn.execute(
                "INSERT INTO hevy_sets (workout_id, exercise_index, set_index, exercise, "
                "template_id, set_type, weight_kg, reps, duration_s, distance_m, rpe) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (w["id"], e.get("index"), s.get("index"), e.get("title"),
                 e.get("exercise_template_id"), s.get("type"), s.get("weight_kg"),
                 s.get("reps"), s.get("duration_seconds"), s.get("distance_meters"),
                 s.get("rpe")),
            )


def _delete_workout(conn: sqlite3.Connection, workout_id: str) -> None:
    row = conn.execute(
        "SELECT activity_id FROM hevy_workouts WHERE workout_id = ?", (workout_id,)
    ).fetchone()
    conn.execute("DELETE FROM hevy_sets WHERE workout_id = ?", (workout_id,))
    conn.execute("DELETE FROM hevy_workouts WHERE workout_id = ?", (workout_id,))
    if row and row["activity_id"] and row["activity_id"].startswith("hevy:"):
        conn.execute("DELETE FROM activities WHERE activity_id = ?", (row["activity_id"],))
    elif row and row["activity_id"]:
        # Hevy sletter ikke nødvendigvis kopien i Garmin. Passet bliver stående
        # som almindeligt Garmin-pas; det skal fjernes i Garmin Connect.
        log.warning("Hevy-pas %s er slettet, men findes stadig i Garmin som %s",
                    workout_id, row["activity_id"])


def link_workouts(conn: sqlite3.Connection) -> dict:
    """Knyt hvert Hevy-pas til præcis én række i activities.

    Findes Garmin-kopien, bruges den (og en evt. midlertidig 'hevy:'-række
    fjernes). Ellers oprettes 'hevy:<id>', så træningen ikke forsvinder.
    """
    tz = ZoneInfo(CONFIG.timezone)
    linked = own = 0
    rows = conn.execute(
        "SELECT * FROM hevy_workouts WHERE activity_id IS NULL OR activity_id LIKE 'hevy:%'"
    ).fetchall()
    for w in rows:
        match = conn.execute(
            f"""SELECT activity_id FROM activities
               WHERE activity_id NOT LIKE 'hevy:%'
                 AND activity_id NOT IN (SELECT activity_id FROM hevy_workouts
                                         WHERE activity_id IS NOT NULL)
                 AND json_extract(raw, '$.startTimeGMT') IS NOT NULL
                 AND abs(strftime('%s', replace(json_extract(raw, '$.startTimeGMT'), ' ', 'T'))
                         - strftime('%s', ?)) <= {MATCH_WINDOW_S}
               ORDER BY abs(strftime('%s', replace(json_extract(raw, '$.startTimeGMT'), ' ', 'T'))
                            - strftime('%s', ?))
               LIMIT 1""",
            (w["start_utc"], w["start_utc"]),
        ).fetchone()
        if match:
            if w["activity_id"]:
                conn.execute("DELETE FROM activities WHERE activity_id = ?", (w["activity_id"],))
            conn.execute("UPDATE hevy_workouts SET activity_id = ? WHERE workout_id = ?",
                         (match["activity_id"], w["workout_id"]))
            linked += 1
            continue
        if w["activity_id"]:
            own += 1
            continue
        start = datetime.fromisoformat(w["start_utc"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(w["end_utc"].replace("Z", "+00:00")) if w["end_utc"] else start
        local = start.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
        aid = f"hevy:{w['workout_id']}"
        upsert(conn, "activities", {
            "activity_id": aid,
            "start_local": local,
            "date": local[:10],
            "sport": "strength_training",
            "name": w["title"],
            "duration_s": (end - start).total_seconds(),
            "raw": w["raw"],
        }, pk=["activity_id"])
        conn.execute("UPDATE hevy_workouts SET activity_id = ? WHERE workout_id = ?",
                     (aid, w["workout_id"]))
        own += 1
    total_own = conn.execute(
        "SELECT COUNT(*) FROM hevy_workouts WHERE activity_id LIKE 'hevy:%'"
    ).fetchone()[0]
    return {"nyligt_parret_med_garmin": linked, "kun_i_hevy": total_own}


def sync_hevy(conn: sqlite3.Connection, get: Callable[[str], dict] | None = None) -> dict:
    """Første gang hentes alle pas; derefter kun ændringer siden sidst,
    inklusive pas der er rettet eller slettet i Hevy."""
    if get is None:
        if not CONFIG.hevy_api_key:
            return {"status": "HEVY_API_KEY ikke sat — springer Hevy over"}
        get = _http_get
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    since = get_state(conn, "last_hevy_sync")
    updated = deleted = 0
    if since is None:
        for w in _pages(get, "/v1/workouts", "workouts"):
            _store_workout(conn, w)
            updated += 1
    else:
        for ev in _pages(get, f"/v1/workouts/events?since={since}", "events"):
            if ev.get("type") == "deleted":
                _delete_workout(conn, ev.get("id"))
                deleted += 1
            elif isinstance(ev.get("workout"), dict):
                _store_workout(conn, ev["workout"])
                updated += 1
    result = {"pas_hentet": updated, "pas_slettet": deleted, **link_workouts(conn)}
    set_state(conn, "last_hevy_sync", started)
    conn.commit()
    if result["kun_i_hevy"]:
        log.warning("%d Hevy-pas findes ikke i Garmin — tjek Hevys Garmin-synkronisering",
                    result["kun_i_hevy"])
    return result


def _cli() -> Any:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    conn = connect()
    print(json.dumps(sync_hevy(conn), indent=2, ensure_ascii=False))
    conn.close()


if __name__ == "__main__":
    _cli()
