"""Løb og svømning pr. periode (metrics.kondition), og at byg regner dem for perioder gemt uden."""

import json

from garmin_coach import metrics, site


def _pas(conn, aid, dato, sport, varighed, distance, puls, **raw):
    conn.execute(
        """INSERT INTO activities (activity_id, start_local, date, sport, name, duration_s, distance_m, avg_hr, raw)
           VALUES (?, ?, ?, ?, '', ?, ?, ?, ?)""",
        (aid, f"{dato} 07:00:00", dato, sport, varighed, distance, puls, json.dumps(raw)))
    conn.commit()


def test_loeb_og_svoemning(conn):
    _pas(conn, "1", "2026-10-03", "running", 1800, 5000, 150, movingDuration=1500,
         averageRunningCadenceInStepsPerMinute=160, fastestSplit_1000=280, fastestSplit_5000=1500)
    _pas(conn, "2", "2026-10-07", "treadmill_running", 1200, 3000, 160, movingDuration=1200,
         averageRunningCadenceInStepsPerMinute=170, fastestSplit_1000=390)
    _pas(conn, "3", "2026-10-05", "lap_swimming", 1800, 1000, 140, movingDuration=1200, averageSwolf=40, activeLengths=40)
    _pas(conn, "4", "2026-10-20", "running", 600, 2000, 170)  # efter perioden
    k = metrics.kondition(conn, "2026-09-26", "2026-10-09")
    assert k["loeb"] == {
        "pas": 2, "puls": 154, "laengste_dato": "2026-10-03", "km": 8.0, "laengste_km": 5.0,
        "tempo_s_pr_km": 338,  # (1500 + 1200) s bevægelse / 8 km
        "kadence": 164,  # vægtet med bevægelsestid
        "hurtigste_1km_s": 280, "hurtigste_1km_dato": "2026-10-03",
        "hurtigste_5km_s": 1500, "hurtigste_5km_dato": "2026-10-03",
    }
    assert k["svoemning"] == {"pas": 1, "puls": 140, "laengste_dato": "2026-10-05", "m": 1000, "laengste_m": 1000,
                              "tempo_s_pr_100m": 120, "swolf": 40}


def test_ingen_pas_er_none(conn):
    assert metrics.kondition(conn, "2026-09-26", "2026-10-09") == {"loeb": None, "svoemning": None}


def test_byg_regner_kondition_for_gamle_perioder(conn, tmp_path):
    _pas(conn, "1", "2026-10-03", "running", 1800, 5000, 150)
    site.gem(conn, {"start": "2026-09-26", "slut": "2026-10-09", "status": "endelig", "vurdering": {"resume": "God."}})
    site.byg(conn, tmp_path / "site")
    p = json.loads((tmp_path / "site" / "perioder.json").read_text())[0]
    assert p["kondition"]["loeb"]["km"] == 5.0 and p["kondition"]["svoemning"] is None
    assert "kondition" not in site.perioder(conn)[0]  # det gemte dokument er urørt
