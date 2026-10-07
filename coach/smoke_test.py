"""Smoke-test af beregningslaget med syntetiske data.

Kører uden Garmin-adgang, så du kan verificere at logikken virker før du
overhovedet logger ind. Kør: python smoke_test.py
"""

import json
import os
import random
import sqlite3
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

os.environ["GC_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from garmin_coach import db, metrics  # noqa: E402
from garmin_coach.db import connect, set_state, upsert  # noqa: E402

random.seed(7)
conn = connect()
today = date.today()

# 90 dage med træning 4-5 gange om ugen og realistisk spredning i wellness-tal
for i in range(90, -1, -1):
    d = today - timedelta(days=i)
    iso = d.isoformat()

    if d.weekday() in (0, 2, 4, 5) or (d.weekday() == 6 and random.random() < 0.4):
        hard = d.weekday() in (2, 5)
        dur = random.uniform(2700, 5400) if not hard else random.uniform(3600, 7200)
        upsert(conn, "activities", {
            "activity_id": f"a{i}",
            "start_local": f"{iso} 17:30:00",
            "date": iso,
            "sport": "running" if d.weekday() != 4 else "cycling",
            "name": "Intervaller" if hard else "Rolig tur",
            "duration_s": dur,
            "distance_m": dur * random.uniform(2.6, 3.4),
            "avg_hr": random.uniform(155, 172) if hard else random.uniform(128, 142),
            "max_hr": random.uniform(175, 188),
            "elev_gain_m": random.uniform(20, 180),
            "calories": dur * 0.18,
            "garmin_load": None,
        }, pk=["activity_id"])

    upsert(conn, "daily", {
        "date": iso,
        "resting_hr": round(random.gauss(48, 2.5), 1),
        "hrv_last_night": round(random.gauss(62, 7), 1),
        "hrv_status": "BALANCED",
        "sleep_s": random.gauss(7.1, 0.9) * 3600,
        "sleep_score": round(random.gauss(76, 9)),
        "stress_avg": round(random.gauss(30, 8)),
        "bb_high": round(random.gauss(82, 9)),
        "bb_low": round(random.gauss(24, 8)),
        "steps": round(random.gauss(9500, 2500)),
        "training_readiness": round(random.gauss(68, 12)),
        "vo2max": round(50 + (90 - i) * 0.012, 1),
        "weight_kg": round(80 - (90 - i) * 0.015 + random.gauss(0, 0.3), 1),
    }, pk=["date"])

# Kalender i morgen: tre skematimer, en heldagsbegivenhed, og en række i det
# gamle format (lokal tid med offset) som migreringen skal rette.
tomorrow = today + timedelta(days=1)
t_iso = tomorrow.isoformat()
for h, dur_h, title in [
    (9, 1, "Gamma – consectetur (C) - KURS103.C - Lecture (On Campus)"),
    (11, 2, "Alfa – lorem ipsum (A) - KURS101.A - Exercise (On Campus)"),
]:
    s = datetime.combine(tomorrow, datetime.min.time()).replace(hour=h)
    upsert(conn, "calendar_events", {
        "uid": f"evt-{h}",
        "start_local": s.strftime("%Y-%m-%dT%H:%M"),
        "end_local": (s + timedelta(hours=dur_h)).strftime("%Y-%m-%dT%H:%M"),
        "summary": title,
        "all_day": 0,
    }, pk=["uid", "start_local"])
upsert(conn, "calendar_events", {
    "uid": "fest", "start_local": f"{t_iso}T00:00",
    "end_local": f"{(tomorrow + timedelta(days=1)).isoformat()}T00:00",
    "summary": "Semesterstartsfest", "all_day": 1,
}, pk=["uid", "start_local"])
conn.execute(
    "INSERT INTO calendar_events (uid, start_local, end_local, summary, all_day) "
    "VALUES ('legacy', ?, ?, '1:1', 0)",
    (f"{t_iso}T15:00+02:00", f"{t_iso}T16:00+02:00"),
)
db._migrate_calendar_times(conn)  # det connect() gør ved næste opstart
conn.commit()

ath = metrics.athlete(conn)
print("AUTO-UDLEDT ATLET (ingen config sat)")
print("  makspuls:", ath.hr_max, "| hvilepuls:", ath.hr_rest, "| køn:", ath.sex)
print("  kilder:", ath.sources, "\n")

print("TRIMP-kontrol")
print("  60 min @ 135 bpm (rolig):", metrics.banister_trimp(3600, 135, ath))
print("  60 min @ 168 bpm (hård): ", metrics.banister_trimp(3600, 168, ath))
print("  → hård skal give markant mere end rolig ved samme varighed\n")

load = metrics.training_load(conn, weeks=8)
print("BELASTNING")
for k in ("akut_7d", "kronisk_uge_snit_28d", "acwr", "acwr_fortolkning",
          "monotoni_7d", "strain_7d"):
    print(f"  {k}: {load[k]}")
print("  ugentligt (nyeste først):", load["ugentligt"][:4])
print("  fordeling:", load["fordeling_28d"], "\n")

rec = metrics.recovery(conn, days=14)
print("RESTITUTION")
print("  hrv:", rec["hrv"])
print("  hvilepuls:", rec["hvilepuls"])
print("  søvn:", rec["søvn_timer"])
print("  flag:", rec["flag"] or "ingen", "\n")

print("KROP")
print(" ", metrics.body_trend(conn, days=90), "\n")

sched = metrics.schedule(conn, days_ahead=3)
print("KALENDER")
for day in sched["dage"]:
    print(f"  {day['ugedag']} {day['dato']}: {day['begivenheder']} begivenheder, "
          f"{day['optaget_timer']}t optaget, frie vinduer {day['frie_vinduer']}")
    for e in day["program"]:
        print(f"    {e['tid']}  {e['titel']}")

# Migreringen: offset fjernet fra lokaltid, UTC udfyldt
leg = conn.execute("SELECT * FROM calendar_events WHERE uid = 'legacy'").fetchone()
assert (leg["start_local"], leg["start_utc"]) == (f"{t_iso}T15:00", f"{t_iso}T13:00Z"), dict(leg)
# Rå SQL og værktøjet skal vise samme klokkeslæt
assert conn.execute(
    "SELECT time(start_local) FROM calendar_events WHERE uid = 'evt-9'"
).fetchone()[0] == "09:00:00"
assert conn.execute(
    "SELECT date(start_local) FROM calendar_events WHERE uid = 'fest'"
).fetchone()[0] == t_iso

day = metrics.schedule(conn, days_ahead=3)["dage"][1]
assert "møder" not in day
assert day["begivenheder"] == 4, day
assert day["program"][0] == {"tid": "heldag", "titel": "Semesterstartsfest"}
assert {"tid": "09:00–10:00", "titel": "Gamma – consectetur · Lecture (On Campus)"} in day["program"]
assert {"tid": "15:00–16:00", "titel": "1:1"} in day["program"]
# Heldag tæller ikke med i optaget tid, første start eller sidste slut
assert day["optaget_timer"] == 4.0, day
assert (day["første_møde"], day["sidste_slut"]) == ("09:00", "16:00"), day
assert all(d["program"] == [] for i, d in enumerate(metrics.schedule(conn, 3)["dage"]) if i != 1)
print("  → titler, heldag og tider i SQL og værktøj stemmer overens")

# Zonedata hvor grænserne skifter midt i perioden: den ældste halvdel af
# passene har zone 5 fra 178, den nyeste halvdel fra 183. Tærsklen er 178.
OLD = {1: 99, 2: 119, 3: 139, 4: 158, 5: 178}
NEW = {1: 125, 2: 140, 3: 154, 4: 169, 5: 183}
zone_since = (today - timedelta(days=28)).isoformat()
pas = [r["activity_id"] for r in conn.execute(
    "SELECT activity_id FROM activities WHERE date >= ? ORDER BY start_local",
    (zone_since,))]
half = len(pas) // 2
for n, aid in enumerate(pas):
    bounds = OLD if n < half else NEW
    for z, low in bounds.items():
        upsert(conn, "activity_zones", {
            "activity_id": aid, "zone": z,
            "seconds": random.uniform(300, 1500), "low_bpm": low,
        }, pk=["activity_id", "zone"])
set_state(conn, "profile_lthr", "178.0")
set_state(conn, "zone_method", "HR_MAX")
set_state(conn, "zone_max_hr", "198")
set_state(conn, "zone_floors", json.dumps({f"zone{z}": b for z, b in NEW.items()}))
conn.commit()

zd = metrics.zone_distribution(conn, days=28)
print("\nZONER MED SKIFTENDE GRÆNSER")
print("  fra_bpm:", [z["fra_bpm"] for z in zd["zoner"]])
print("  sæt:", zd["zonegrænser_ændret"]["sæt"])
print("  forbehold:", zd["forbehold_zoner"])
assert [z["fra_bpm"] for z in zd["zoner"]] == list(NEW.values())
saet = zd["zonegrænser_ændret"]["sæt"]
assert [s["grænser_bpm"]["zone5"] for s in saet] == [183, 178]
assert [s["pas"] for s in saet] == [len(pas) - half, half]
assert "starter ved 183" in zd["forbehold_zoner"]
assert "178 (%d pas)" % half in zd["forbehold_zoner"]

# Gælder 178 for de nyeste pas, er tærsklen ikke under zone 5: intet forbehold,
# men skiftet i grænser skal stadig fremgå.
conn.execute("UPDATE activity_zones SET low_bpm = CASE zone "
             "WHEN 1 THEN 99 WHEN 2 THEN 119 WHEN 3 THEN 139 WHEN 4 THEN 158 "
             "ELSE 178 END WHERE activity_id IN (%s)" % ",".join("?" * len(pas[half:])),
             pas[half:])
conn.execute("UPDATE activity_zones SET low_bpm = CASE zone "
             "WHEN 1 THEN 125 WHEN 2 THEN 140 WHEN 3 THEN 154 WHEN 4 THEN 169 "
             "ELSE 183 END WHERE activity_id IN (%s)" % ",".join("?" * half), pas[:half])
zd = metrics.zone_distribution(conn, days=28)
assert "forbehold_zoner" not in zd
assert [s["grænser_bpm"]["zone5"] for s in zd["zonegrænser_ændret"]["sæt"]] == [178, 183]

# Ens grænser i hele perioden: intet felt om skift, forbehold uden ældre-note.
conn.execute("UPDATE activity_zones SET low_bpm = CASE zone "
             "WHEN 1 THEN 125 WHEN 2 THEN 140 WHEN 3 THEN 154 WHEN 4 THEN 169 "
             "ELSE 183 END")
zd = metrics.zone_distribution(conn, days=28)
assert "zonegrænser_ændret" not in zd
assert "starter ved 183" in zd["forbehold_zoner"]
assert "Ældre pas" not in zd["forbehold_zoner"]

# Makspuls: Garmins konfigurerede tal vinder over den registrerede...
ath = metrics.athlete(conn)
assert ath.hr_max == 198 and ath.sources["hr_max"] == "Garmins zoneopsætning", ath
assert "målt" not in ath.sources["hr_max"]
# ...medmindre den registrerede ligger over, så er Garmins tal for lavt
set_state(conn, "zone_max_hr", "180")
ath = metrics.athlete(conn)
assert ath.hr_max > 180 and "for lavt" in ath.sources["hr_max"], ath
set_state(conn, "zone_max_hr", "198")
print("  → makspuls følger Garmins opsætning og siger hvor den kommer fra")
print("  → felterne opfører sig rigtigt i alle tre scenarier")

# opslag: SQLite skal selv afvise skrivning, også forklædt som WITH
from garmin_coach import server  # noqa: E402
n_before = conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0]
try:
    server.opslag("WITH x AS (SELECT 1) DELETE FROM calendar_events")
    raise AssertionError("opslag slap en DELETE igennem")
except server.ToolError as exc:
    assert "readonly" in str(exc), exc
assert conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0] == n_before
res = server.opslag("SELECT date FROM daily UNION ALL SELECT date FROM daily "
                    "UNION ALL SELECT date FROM daily UNION ALL SELECT date FROM daily "
                    "UNION ALL SELECT date FROM daily UNION ALL SELECT date FROM daily")
assert res["afkortet"] and res["antal"] == 500 and len(res["rækker"]) == 500
assert not server.opslag("SELECT COUNT(*) n FROM daily")["afkortet"]
print("\nOPSLAG\n  → skrivebeskyttet og siger til når svaret er afkortet")

# Sync mod et Garmin der fejler: gemte rådata må ikke gå tabt, og en dag hvor
# alt fejler må ikke dukke op som en synket dag.
from garmin_coach import ingest_garmin  # noqa: E402

ingest_garmin.THROTTLE_S = 0


class HalfBroken:
    def get_stats(self, iso):
        return {"totalSteps": 1234}

    def __getattr__(self, name):
        def fail(*a):
            raise RuntimeError("429 Too Many Requests")
        return fail


class Dead:
    def __getattr__(self, name):
        def fail(*a):
            raise RuntimeError("401")
        return fail


y_iso = (today - timedelta(days=1)).isoformat()
conn.execute("UPDATE daily SET raw = ? WHERE date = ?",
             (json.dumps({"stats": {}, "hrv": {"x": 1}, "sleep": {"y": 2}}), y_iso))
before = conn.execute("SELECT hrv_last_night FROM daily WHERE date = ?", (y_iso,)).fetchone()[0]
assert ingest_garmin.sync_daily(HalfBroken(), conn, today - timedelta(days=1),
                                today - timedelta(days=1)) == 1
row = conn.execute("SELECT raw, hrv_last_night, steps FROM daily WHERE date = ?", (y_iso,)).fetchone()
assert set(json.loads(row["raw"])) == {"stats", "hrv", "sleep"}, row["raw"]
assert row["hrv_last_night"] == before and row["steps"] == 1234

future = today + timedelta(days=5)
assert ingest_garmin.sync_daily(Dead(), conn, future, future) == 0
assert conn.execute("SELECT COUNT(*) FROM daily WHERE date = ?", (future.isoformat(),)).fetchone()[0] == 0

# En række uden målinger må ikke gøre datafriskheden "aktuel"
conn.execute("INSERT INTO daily (date, steps) VALUES (?, 10)", (future.isoformat(),))
assert metrics.freshness(conn)["seneste_data"] == today.isoformat()
conn.execute("DELETE FROM daily WHERE date = ?", (future.isoformat(),))
assert metrics._gap_days(conn, 28) == 0
conn.execute("DELETE FROM daily WHERE date = ?", (y_iso,))
assert metrics._gap_days(conn, 28) == 1  # manglende række er et hul
conn.rollback()
print("\nSYNC MED FEJL\n  → rådata flettes, tomme dage skrives ikke, huller tælles")

# Belastning: kort visning skal stadig give ACWR, forældede data må ikke
# ligne nedtrapning, og en ny bruger må ikke få ACWR regnet på nuller.
from unittest import mock  # noqa: E402

short = metrics.training_load(conn, weeks=2)
assert short["acwr"] == metrics.training_load(conn, weeks=8)["acwr"] is not None
assert len(short["ugentligt"]) == 2
assert short["beregnet_til_og_med"] == (today - timedelta(days=1)).isoformat()


class Later(date):
    @classmethod
    def today(cls):
        return today + timedelta(days=10)


with mock.patch.object(metrics, "date", Later):
    stale = metrics.training_load(conn, weeks=8)
    assert stale["acwr"] is None and "Kør sync" in stale["acwr_fortolkning"], stale
    assert stale["kronisk_uge_snit_28d"] is None and stale["monotoni_7d"] is None
    assert stale["beregnet_til_og_med"] == today.isoformat()
    assert any("for få" in f for f in metrics.recovery(conn)["flag"])

fresh = connect(Path(tempfile.mkdtemp()) / "ny.db")
for i in range(5):
    d = (today - timedelta(days=i)).isoformat()
    upsert(fresh, "activities", {"activity_id": f"n{i}", "start_local": f"{d} 07:00:00",
                                 "date": d, "duration_s": 3600, "avg_hr": 150}, pk=["activity_id"])
    upsert(fresh, "daily", {"date": d, "resting_hr": 50, "hrv_last_night": 60}, pk=["date"])
new = metrics.training_load(fresh, weeks=8)
assert new["acwr"] is None and "4 dage" in new["acwr_fortolkning"]  # vinduet slutter i går, new["acwr_fortolkning"]
assert new["i_dag_indtil_nu"] > 0
rec = metrics.recovery(fresh)["hrv"]
assert rec["aktuelle_datapunkter"] == 5 and rec["afvigelse_sd"] is None  # for kort baseline
fresh.close()
print("\nBELASTNING, KANTTILFÆLDE\n  → forældet, kort visning og ny bruger håndteres ærligt")

# Restitution: "14 nætter" er 14, og dagens råd følger restitutionen
assert metrics.recovery(conn, days=14)["søvn_timer"]["målte_nætter"] == 14
raad_db = connect(Path(tempfile.mkdtemp()) / "raad.db")
for i in range(60, -1, -1):
    upsert(raad_db, "daily", {"date": (today - timedelta(days=i)).isoformat(), "resting_hr": 52 + (i % 3) - 1,
                              "hrv_last_night": 68 + (i % 5) - 2, "sleep_s": 7.4 * 3600,
                              "training_readiness": 80}, pk=["date"])
def raad(**idag):
    upsert(raad_db, "daily", {"date": today.isoformat(), **idag}, pk=["date"])
    return metrics.dagens_raad(raad_db)
assert raad(training_readiness=82)["niveau"] == "klar"
assert raad(training_readiness=62)["niveau"] == "moderat"
r = raad(training_readiness=32, sleep_s=3.22 * 3600)
assert r["niveau"] == "rolig" and r["grunde"][:2] == ["readiness 32 (lav)", "3 t 13 min søvn i nat"], r
assert raad(training_readiness=85, sleep_s=4.5 * 3600)["niveau"] == "rolig"  # kort nat trumfer høj readiness
raad_db.execute("UPDATE daily SET training_readiness = NULL WHERE date = ?", (today.isoformat(),))
assert metrics.dagens_raad(raad_db)["niveau"] is None
raad_db.close()
print("\nDAGENS RÅD\n  → rolig, moderat og klar følger restitutionen; uden måling intet råd")

# Kalender: overlap tælles ikke dobbelt, og passeret tid foreslås ikke
at = lambda h, m=0: datetime.combine(tomorrow, datetime.min.time()).replace(hour=h, minute=m)
overlap = [(at(16, 15), at(17, 55)), (at(16, 45), at(21)), (at(8), at(9))]
assert round(metrics._busy_minutes(overlap)) == 60 + 285  # 16:15-21:00 + 08-09
assert metrics._free_windows([], tomorrow, not_before=at(14, 30)) == ["14:30–22:00"]
assert metrics._free_windows([], tomorrow, not_before=at(21, 30)) == []
assert metrics._free_windows(overlap, tomorrow) == ["06:00–08:00", "09:00–16:15", "21:00–22:00"]
assert "Heldagsbegivenheder" in metrics.schedule(conn, 2)["note"]
print("\nKALENDER, KANTTILFÆLDE\n  → overlap slås sammen, dagens vinduer starter ved nu")

# Hevy: seks styrkepas der også ligger i Garmin (med puls), og ét der kun
# findes i Hevy. Samme træning må kun tælle én gang, og RPE skal gøre en
# forskel uden at manglende RPE bliver gættet.
from garmin_coach import ingest_hevy  # noqa: E402

hconn = connect(Path(tempfile.mkdtemp()) / "hevy.db")
hath = metrics.Athlete(hr_max=198, hr_rest=52, sex="m")


def hevy_workout(i, day, rpe, types=("normal",) * 4):
    start = datetime.combine(day, datetime.min.time()).replace(hour=15)
    return {
        "id": f"w{i}", "title": f"Styrke {i}",
        "start_time": start.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "end_time": (start + timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "updated_at": "2026-01-01T00:00:00Z",
        "exercises": [{
            "index": 0, "title": "Bench Press", "exercise_template_id": "x",
            "sets": [{"index": 0, "type": "warmup", "weight_kg": 20, "reps": 10, "rpe": None}] + [
                {"index": j + 1, "type": t, "weight_kg": 60, "reps": 8, "rpe": rpe}
                for j, t in enumerate(types)
            ] + [{"index": 9, "type": "normal", "distance_meters": 1000,
                  "duration_seconds": 180, "reps": None, "rpe": None}],  # kardio, tæller ikke
        }],
    }


days = [today - timedelta(days=d) for d in (20, 17, 13, 10, 6, 3, 2)]
workouts = [hevy_workout(i, d, rpe) for i, (d, rpe) in
            enumerate(zip(days, (9, 9, 8, None, 10, 9, None)))]
workouts[3] = hevy_workout(3, days[3], None, types=("normal", "failure", "normal", "normal"))
for i, d in enumerate(days[:6]):  # Garmin-kopier med puls; w6 findes kun i Hevy
    gmt = f"{d.isoformat()} 15:00:00"
    upsert(hconn, "activities", {
        "activity_id": f"g{i}", "start_local": f"{d.isoformat()} 17:00:00", "date": d.isoformat(),
        "sport": "strength_training", "name": f"Styrke {i}", "duration_s": 3600,
        "avg_hr": 100 + i, "raw": json.dumps({"startTimeGMT": gmt}),
    }, pk=["activity_id"])
upsert(hconn, "daily", {"date": today.isoformat(), "resting_hr": 52}, pk=["date"])


def fake_api(pages):
    def get(path):
        return pages(path)
    return get


res = ingest_hevy.sync_hevy(hconn, fake_api(
    lambda path: {"page": 1, "page_count": 1, "workouts": workouts}))
assert res == {"pas_hentet": 7, "pas_slettet": 0, "nyligt_parret_med_garmin": 6,
               "kun_i_hevy": 1}, res
# Ingen dobbelttælling: én række pr. pas
assert hconn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 7

ctx = metrics.load_context(hconn, hath)
assert ctx.trimp_per_point and ctx.calibration_sessions == 6
by_id = {r["activity_id"]: r for r in hconn.execute("SELECT * FROM activities")}
loads = {aid: metrics.session_load_detail(r, hath, ctx) for aid, r in by_id.items()}
assert all(k == "hevy" for _, k in loads.values()), loads
# Pas kun i Hevy, uden puls, får alligevel belastning
assert loads["hevy:w6"][0] > 0
# RPE 10 vejer mere end RPE 8; manglende RPE giver kun sættene, intet gæt
k = ctx.trimp_per_point
assert loads["g4"][0] > loads["g2"][0]
assert abs(loads["g2"][0] - k * 4) < 1e-9          # RPE 8: ingen tillæg
assert abs(loads["hevy:w6"][0] - k * 4) < 1e-9     # ingen RPE: ingen tillæg, intet gæt
assert ctx.hevy["hevy:w6"]["med_anstrengelse"] == 0
assert ctx.hevy["g3"]["med_anstrengelse"] == 1     # failure-sættet uden RPE

# Garmin-kopien dukker op senere: parres og hevy:-rækken forsvinder
upsert(hconn, "activities", {
    "activity_id": "g6", "start_local": f"{days[6].isoformat()} 17:00:00",
    "date": days[6].isoformat(), "sport": "strength_training", "duration_s": 3600,
    "raw": json.dumps({"startTimeGMT": f"{days[6].isoformat()} 15:00:30"}),
}, pk=["activity_id"])
assert ingest_hevy.link_workouts(hconn) == {"nyligt_parret_med_garmin": 1, "kun_i_hevy": 0}
assert hconn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 7

# Slettet i Hevy: sæt og kobling væk, Garmin-passet står tilbage uden Hevy-data
ingest_hevy.sync_hevy(hconn, fake_api(lambda path: {
    "page": 1, "page_count": 1,
    "events": [{"type": "deleted", "id": "w0", "deleted_at": "2026-01-01T00:00:00Z"}]}))
assert hconn.execute("SELECT COUNT(*) FROM hevy_sets WHERE workout_id='w0'").fetchone()[0] == 0
assert metrics.session_load_detail(by_id["g0"], hath, metrics.load_context(hconn, hath))[1] == "puls"

# Styrkeuger: RPE-tal kun når dækningen er høj nok
weeks = metrics.strength_weeks(hconn, today - timedelta(days=1), 3)
# uge 0: RPE 10, 9 og et pas uden RPE → 67 %, snit kun over de vurderede
assert (weeks[0]["arbejdssæt"], weeks[0]["rpe_dækning_pct"], weeks[0]["snit_rpe"]) == (12, 67, 9.5)
# uge 1: RPE 8 og et pas uden RPE → 50 %, under grænsen: ingen RPE-tal
assert weeks[1]["rpe_dækning_pct"] == 50 and weeks[1]["snit_rpe"] is None
assert "rpe_note" in weeks[1]
assert weeks[2]["rpe_dækning_pct"] == 100 and weeks[2]["snit_rpe"] == 9
hconn.close()
print("\nHEVY\n  → parring uden dobbelttælling, RPE-tillæg uden gæt, sletning og sen Garmin-kopi")

# Periode-rapport: samme felter som Form & Fokus-siden, og belastning på
# samme skala som traeningsbelastning
S, E = (today - timedelta(days=13)).isoformat(), today.isoformat()
rap = server.periode(S, E)
assert set(rap) >= {"start", "slut", "dage_med_data", "sundhed", "traening", "styrke",
                    "studie", "forbehold"}
assert rap["dage_med_data"] == 14 and rap["sundhed"]["sovn_t"] is not None
assert rap["traening"]["pas"] == conn.execute(
    "SELECT COUNT(*) FROM activities WHERE date BETWEEN ? AND ?", (S, E)).fetchone()[0]
assert abs(rap["traening"]["belastning"] - sum(
    metrics.daily_loads(conn, date.fromisoformat(S), today, metrics.athlete(conn)).values())) <= 1
assert {x["navn"] for x in rap["traening"]["sport"]} <= {"Løb", "Cykling"}
assert rap["studie"] is None and any("Kalenderdata" in f for f in rap["forbehold"])
try:
    server.periode("2026-13-01", E)
    raise AssertionError("ugyldig dato slap igennem")
except server.ToolError:
    pass
print("\nPERIODE\n  → sidens felter, samme belastningsskala, forbehold ved manglende kalender")

# e1RM: kun frie vægte og højst 12 gentagelser; RPE følger med som oplysning.
# Selvstudie er null før første CalTask-session, ikke 0.
lconn = connect(Path(tempfile.mkdtemp()) / "loeft.db")
d0 = (today - timedelta(days=3)).isoformat()
upsert(lconn, "activities", {"activity_id": "g1", "start_local": f"{d0} 17:00:00",
                             "date": d0, "sport": "strength_training", "duration_s": 3600,
                             "avg_hr": 100}, pk=["activity_id"])
lconn.execute("INSERT INTO hevy_workouts (workout_id, activity_id, start_utc) VALUES "
              "('w1', 'g1', ?)", (f"{d0}T15:00:00+00:00",))
for i, (ex, w, r, rpe) in enumerate([
    ("Bench Press (Barbell)", 80, 5, 9.5),     # e1RM 93,3
    ("Bench Press (Barbell)", 60, 15, 10),     # 90 — for mange reps, tæller ikke
    ("Bench Press (Barbell)", 100, 1, None),   # 103,3 — bedste, uden RPE
    ("Chest Fly (Machine)", 70, 10, 9),        # maskine, tæller ikke
    ("Shoulder Press (Dumbbell)", 20, 8, None),
]):
    lconn.execute("INSERT INTO hevy_sets (workout_id, exercise_index, set_index, exercise, "
                  "set_type, weight_kg, reps, rpe) VALUES ('w1', ?, 0, ?, 'normal', ?, ?, ?)",
                  (i, ex, w, r, rpe))
upsert(lconn, "calendar_events", {"uid": "c1", "start_local": f"{d0}T09:00",
                                  "end_local": f"{d0}T10:00", "summary": "Forelæsning",
                                  "all_day": 0}, pk=["uid", "start_local"])
set_state(lconn, "calendar_covered_from", (today - timedelta(days=30)).isoformat())
rap = metrics.periode_rapport(lconn, (today - timedelta(days=13)).isoformat(), today.isoformat())
st = rap["styrke"]
assert set(st["e1rm"]) == {"bench_press_barbell", "shoulder_press_dumbbell"}, st["e1rm"]
assert st["e1rm"]["bench_press_barbell"] == 103.3
assert st["loeft"]["bench_press_barbell"] == {"navn": "Bænkpres", "hevy": "Bench Press (Barbell)",
                                             "bedste_saet": "100 kg × 1", "rpe": None}
assert rap["studie"]["undervisning_t"] == 0 and rap["studie"]["selvstudie_t"] is None
assert rap["studie"]["pr_fag"] is None
upsert(lconn, "calendar_events", {"uid": "c2", "start_local": f"{d0}T12:00",
                                  "end_local": f"{d0}T13:00", "summary": "Selvstudie · Gamma🤖",
                                  "all_day": 0}, pk=["uid", "start_local"])
rap = metrics.periode_rapport(lconn, (today - timedelta(days=13)).isoformat(), today.isoformat())
assert rap["studie"]["selvstudie_t"] == 1.0 and rap["studie"]["pr_fag"] == [{"fag": "Gamma", "timer": 1.0}]
assert any("delvist dækket" in f for f in rap["forbehold"])
lconn.close()
print("\nLØFT OG SELVSTUDIE\n  → frie vægte ≤12 reps med bedste sæt og RPE; selvstudie null før logning")

# Kalender-sync: fejler ét feed, må intet slettes; lykkes alle, ryddes vinduet
from garmin_coach import ingest_calendar  # noqa: E402

ics = (f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//EN\r\nBEGIN:VEVENT\r\nUID:ok-1\r\n"
       f"DTSTART:{tomorrow.strftime('%Y%m%d')}T080000Z\r\nDTEND:{tomorrow.strftime('%Y%m%d')}T090000Z\r\n"
       f"SUMMARY:Test\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n").encode()


def fake_load(src):
    if src == "bad":
        raise OSError("timeout")
    return ics


orig_load, orig_sources = ingest_calendar._load, ingest_calendar.CONFIG.ics_sources
ingest_calendar._load = fake_load
try:
    before = conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0]
    ingest_calendar.CONFIG.ics_sources = ["good", "bad"]
    res = ingest_calendar.sync_calendar(conn)
    assert res == {"begivenheder": 1, "fejlede_feeds": 1}, res
    assert conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0] == before + 1
    assert conn.execute("SELECT 1 FROM calendar_events WHERE uid = 'fest'").fetchone()
    ingest_calendar.CONFIG.ics_sources = ["good"]
    assert ingest_calendar.sync_calendar(conn) == {"begivenheder": 1, "fejlede_feeds": 0}
    assert conn.execute("SELECT uid FROM calendar_events").fetchall()[0][0] == "ok-1"
    assert conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0] == 1
    assert metrics.get_state(conn, "calendar_covered_from") == (today - timedelta(days=14)).isoformat()
finally:
    ingest_calendar._load, ingest_calendar.CONFIG.ics_sources = orig_load, orig_sources
print("\nKALENDER-SYNC\n  → et fejlende feed sletter intet; fuld sync rydder vinduet")

# Backfill: dage med målinger springes over, og efter MAX_FAILURES dage i
# træk uden svar stoppes der med de hentede dage gemt.
bconn = connect(Path(tempfile.mkdtemp()) / "backfill.db")
b0 = today - timedelta(days=9)
upsert(bconn, "daily", {"date": (b0 + timedelta(days=2)).isoformat(), "resting_hr": 50},
       pk=["date"])


class Counting(HalfBroken):
    def __init__(self):
        self.days = []

    def get_stats(self, iso):
        self.days.append(iso)
        return {"totalSteps": 1000, "restingHeartRate": 48}


api = Counting()
assert ingest_garmin.sync_daily(api, bconn, b0, b0 + timedelta(days=4), skip_measured=True) == 4
assert (b0 + timedelta(days=2)).isoformat() not in api.days and len(api.days) == 4


class FailsFromDay5(Counting):
    def get_stats(self, iso):
        if iso >= (b0 + timedelta(days=5)).isoformat():
            raise RuntimeError("429")
        return super().get_stats(iso)


api = FailsFromDay5()
try:
    ingest_garmin.sync_daily(api, bconn, b0, today, skip_measured=True, max_failures=3)
    raise AssertionError("backfill fortsatte mod et Garmin der afviser")
except ingest_garmin.GarminUnavailable as exc:
    assert "3 dage i træk" in str(exc), exc
assert api.days == []  # dag 0-4 var allerede hentet, så kun fejlende dage blev prøvet
assert bconn.execute("SELECT COUNT(*) FROM daily").fetchone()[0] == 5
bconn.close()
print("\nBACKFILL\n  → springer hentede dage over og stopper når Garmin afviser")

# Månedsoversigt: én række pr. måned med data, mængder pr. uge, og den
# igangværende måned markeret
mo = server.maanedsoversigt()
first_m = (today - timedelta(days=90)).strftime("%Y-%m")
assert mo["maaneder"][0]["maaned"] == first_m and mo["maaneder"][-1].get("igangvaerende")
assert all(not r.get("igangvaerende") for r in mo["maaneder"][:-1])
full_month = mo["maaneder"][1]
assert full_month["dage_med_data"] >= 28 and full_month["timer_pr_uge"] > 0
assert full_month["styrke_arbejdssaet_pr_uge"] is None  # ingen Hevy i testdata
assert mo["udvikling"] is None  # kræver 6 fulde måneder
# Zonetesten ovenfor endte med ens grænser overalt: intet zoneforbehold
assert not any("zone 3" in f for f in mo["forbehold"]), mo["forbehold"]
conn.execute("UPDATE activity_zones SET low_bpm = 139 WHERE zone = 3 AND activity_id = ?", (pas[0],))
conn.commit()
assert any("mellem 139 og 154" in f for f in server.maanedsoversigt()["forbehold"])
try:
    server.maanedsoversigt("2026-13")
    raise AssertionError("ugyldig måned slap igennem")
except server.ToolError:
    pass
print("\nMÅNEDSOVERSIGT\n  → måned for måned, pr. uge, igangværende måned markeret")

# Eksport til siden: én fil pr. måned plus oversigten, og batch-skrivninger
# der peger på filerne i bidder på højst 50
from garmin_coach import export  # noqa: E402

out = Path(tempfile.mkdtemp())
batches = export.export_maaneder(conn, out)
writes = [w for b in batches for w in b]
assert all(len(b) <= 50 for b in batches)
assert [w["doc_id"] for w in writes[:-1]] == [r["maaned"] for r in mo["maaneder"]]
assert writes[-1] == {"op": "set", "collection": "oversigt", "doc_id": "seneste",
                      "file_path": str(out / "oversigt.json")}
first = json.loads(Path(writes[0]["file_path"]).read_text())
assert first["maaned"] == mo["maaneder"][0]["maaned"] and "genereret" in first
assert json.loads((out / "oversigt.json").read_text())["til"] == mo["maaneder"][-1]["maaned"]
print("\nEKSPORT\n  → én fil pr. måned og batch-skrivninger med file_path")

# Lokal Form & Fokus-side: perioder gemmes med tal regnet af periode_rapport,
# en endelig periode fjerner foreløbige, og byg skriver siden og dens data
from garmin_coach import site  # noqa: E402

S1, E1 = (today - timedelta(days=27)).isoformat(), (today - timedelta(days=14)).isoformat()
S2 = (today - timedelta(days=13)).isoformat()
site.ny_periode(conn, S2, today.isoformat(), {"resume": "Midt i perioden."}, "foreløbig")
doc = site.ny_periode(conn, S1, E1, {"resume": "God periode.", "fokus": ["Sov mere"]})
assert doc["traening"] == metrics.periode_rapport(conn, S1, E1)["traening"]
assert [p_["start"] for p_ in site.perioder(conn)] == [S1]  # den foreløbige er væk
try:
    site.ny_periode(conn, S2, today.isoformat(), {"gaar_godt": []})
    raise AssertionError("vurdering uden resume slap igennem")
except ValueError:
    pass
out = Path(tempfile.mkdtemp())
res = site.byg(conn, out)
assert res["perioder"] == 1 and (out / "index.html").stat().st_size > 10000
assert json.loads((out / "perioder.json").read_text())[0]["vurdering"]["resume"] == "God periode."
assert json.loads((out / "maaneder.json").read_text())[-1].get("igangvaerende")
assert "claude.use" not in (out / "index.html").read_text()
sider = {x["sti"]: x for x in json.loads((out / "kompas.json").read_text())["sider"]}
assert sider["/form/perioder.html"]["nyt"] == S1 and "nyt" not in sider["/form/uge.html"]  # ingen liv.json her
(out / "liv.json").write_text(json.dumps({"reviews": [{"uge": "2026-W39", "tekst": {"saetning": "En uge."}}, {"uge": "2026-W40", "tekst": None}]}))
site.byg(conn, out)
assert json.loads((out / "kompas.json").read_text())["sider"][1]["nyt"] == "2026-W39"  # kun reviews med tekst
print("\nLOKAL SIDE\n  → perioder gemmes med beregnede tal, siden bygges med data")

print("\nAlle beregninger kørte uden fejl.")
conn.close()

