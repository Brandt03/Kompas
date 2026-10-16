"""Opg. 2: en fejlet Hevy-hentning står i sync-svaret og i sync_state (last_hevy_error)."""

import urllib.error

import pytest

from garmin_coach import ingest_calendar, ingest_garmin, ingest_hevy, server
from garmin_coach.config import CONFIG
from garmin_coach.db import connect, get_state, set_state


def _fejler(path):
    raise urllib.error.URLError("_ssl.c:1064: The handshake operation timed out")


def test_fejl_noteres_og_ryddes_ved_naeste_vellykkede(conn):
    set_state(conn, "last_hevy_sync", "2026-10-01T00:00:00Z")
    conn.commit()
    with pytest.raises(urllib.error.URLError):
        ingest_hevy.sync_hevy(conn, _fejler)
    assert get_state(conn, ingest_hevy.FEJL_STATE)
    assert get_state(conn, "last_hevy_sync") == "2026-10-01T00:00:00Z"  # ingen falsk vellykket hentning

    ingest_hevy.sync_hevy(conn, lambda path: {"events": [], "page_count": 1})
    assert get_state(conn, ingest_hevy.FEJL_STATE) is None
    assert get_state(conn, "last_hevy_sync") > "2026-10-01T00:00:00Z"


def test_halv_hentning_gemmer_intet(conn, monkeypatch):
    sider = iter([{"workouts": [{"id": "w1", "title": "Ben", "start_time": "2026-10-01T16:00:00Z",
                                 "end_time": "2026-10-01T17:00:00Z", "exercises": []}], "page_count": 2}])

    def get(path):
        try:
            return next(sider)
        except StopIteration:
            raise urllib.error.URLError("timed out") from None

    monkeypatch.setattr(ingest_hevy.time, "sleep", lambda s: None)
    with pytest.raises(urllib.error.URLError):
        ingest_hevy.sync_hevy(conn, get)
    assert conn.execute("SELECT COUNT(*) FROM hevy_workouts").fetchone()[0] == 0


@pytest.fixture
def falsk_garmin(monkeypatch, tmp_path):
    """run_sync uden Garmin: login og alle hentninger er erstattet."""
    monkeypatch.setattr(CONFIG, "db_path", tmp_path / "sync.db")
    monkeypatch.setattr(ingest_garmin, "login", lambda: object())
    for navn, svar in (("sync_profile", {}), ("sync_hr_zones", {}), ("sync_activities", 1),
                       ("sync_daily", 2), ("sync_weight", 0), ("sync_activity_zones", 0)):
        monkeypatch.setattr(ingest_garmin, navn, lambda *a, _s=svar, **k: _s)

    def hevy_fejler(conn):
        raise urllib.error.URLError("_ssl.c:1064: The handshake operation timed out")

    monkeypatch.setattr(ingest_hevy, "sync_hevy", hevy_fejler)
    return tmp_path / "sync.db"


def test_run_sync_siger_at_hevy_fejlede(falsk_garmin, caplog):
    res = ingest_garmin.run_sync(days=2)
    assert res["fejlede"] == {"hevy": res["hevy"]["fejl"]}
    assert "handshake" in res["fejlede"]["hevy"]
    assert any(r.levelname == "ERROR" and "Hevy-sync fejlede" in r.getMessage() for r in caplog.records)
    c = connect(falsk_garmin)
    assert get_state(c, "last_garmin_sync")  # Garmin kom igennem
    c.close()


def test_mcp_sync_svaret_siger_at_hevy_fejlede(falsk_garmin, monkeypatch):
    monkeypatch.setattr(ingest_calendar, "sync_calendar", lambda conn: {"begivenheder": 3, "fejlede_feeds": 1})
    monkeypatch.setattr(server, "_sync_job", {})
    svar = server.sync(dage=2)
    assert svar["status"] == "færdig"  # så rutinen ikke kalder igen og starter en ny sync
    assert set(svar["fejlede"]) == {"hevy", "kalender"}
    assert svar["besked"].startswith("Garmin er hentet, men Hevy fejlede")
    assert "kalenderen er ufuldstændig" in svar["besked"]


def test_mcp_sync_uden_fejl_har_ingen_fejlede(falsk_garmin, monkeypatch):
    monkeypatch.setattr(ingest_hevy, "sync_hevy", lambda conn: {"pas_hentet": 0})
    monkeypatch.setattr(ingest_calendar, "sync_calendar", lambda conn: {"begivenheder": 3, "fejlede_feeds": 0})
    monkeypatch.setattr(server, "_sync_job", {})
    svar = server.sync(dage=2)
    assert svar["status"] == "færdig" and "fejlede" not in svar and "besked" not in svar
