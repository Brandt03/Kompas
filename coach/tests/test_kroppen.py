"""Kroppen i tal: i dag tæller ikke med i døgntallenes snit, et døgn uden række står tomt, og nattens faser læses."""

import json
from datetime import date

from garmin_coach import kroppen as kroppen_mod
from garmin_coach.kroppen import kroppen

I_DAG = date(2026, 10, 23)


def _dag(conn, dato, skridt, sleep_s=None, levels=None):
    raw = {"stats": {"includesWellnessData": True, "totalSteps": skridt, "highStressDuration": 3600},
           "sleep": {"dailySleepDTO": {}, "sleepLevels": levels or []}}
    conn.execute("INSERT INTO daily (date, sleep_s, raw) VALUES (?, ?, ?)", (dato, sleep_s, json.dumps(raw)))
    conn.commit()


def test_i_dag_er_ude_af_doegntallene_men_natten_tæller(conn):
    _dag(conn, "2026-10-21", 8000, sleep_s=7 * 3600)
    _dag(conn, "2026-10-23", 200, sleep_s=9 * 3600)  # i dag indtil nu; 22. mangler helt
    k = kroppen(conn, dage=3, today=I_DAG)
    assert [d["dato"] for d in k["dage"]] == ["2026-10-21", "2026-10-22", "2026-10-23"]
    assert k["dage"][1] == {"dato": "2026-10-22", "pas": 0, "traening_min": 0, "belastning": 0.0}
    assert k["resume"]["skridt"] == {"snit": 8000, "min": 8000, "maks": 8000, "n": 1}
    assert k["resume"]["soevn_t"]["n"] == 2
    assert k["uge"]["snit"]["skridt"] == 8000
    assert k["uge"]["dage"][0]["dato"] == "2026-10-23"
    assert k["maaned"]["datoer"] == ["2026-10-21", "2026-10-22"]


def test_ugen_foer_er_de_syv_hele_doegn_foer_ugen(conn):
    _dag(conn, "2026-10-08", 9000)  # for tidligt
    _dag(conn, "2026-10-09", 4000)
    _dag(conn, "2026-10-15", 6000)
    _dag(conn, "2026-10-16", 8000)  # i ugen
    _dag(conn, "2026-10-23", 200)  # i dag indtil nu
    k = kroppen(conn, dage=3, today=I_DAG)
    assert k["uge"]["foer"]["fra"] == "2026-10-09" and k["uge"]["foer"]["til"] == "2026-10-15"
    assert k["uge"]["foer"]["snit"]["skridt"] == 5000 and k["uge"]["foer"]["snit"]["soevn_t"] is None
    # En afsluttet måned: ugen før ligger lige før dens sidste syv døgn
    m = kroppen_mod.maaned(conn, "2026-09", today=I_DAG)
    assert (m["uge"]["foer"]["fra"], m["uge"]["foer"]["til"]) == ("2026-09-17", "2026-09-23")


def test_uden_data_fra_uret_er_stats_tomme(conn):
    conn.execute("INSERT INTO daily (date, raw) VALUES (?, ?)",
                 ("2026-10-22", json.dumps({"stats": {"includesWellnessData": False, "totalSteps": 0}})))
    conn.commit()
    k = kroppen(conn, dage=2, today=I_DAG)
    assert k["dage"][0]["skridt"] is None


def test_nattens_faser_i_minutter_efter_kl_18(conn):
    levels = [{"startGMT": "2026-10-22T22:00:00.0", "endGMT": "2026-10-22T23:00:00.0", "activityLevel": 0.0},
              {"startGMT": "2026-10-22T23:00:00.0", "endGMT": "2026-10-22T23:30:00.0", "activityLevel": 2.0}]
    _dag(conn, "2026-10-23", 0, sleep_s=5400, levels=levels)
    nat = kroppen_mod.doegnet(conn, "2026-10-23")["nat"]
    # 22.00 GMT er 00.00 dansk sommertid, altså 6 timer efter kl. 18
    assert nat["faser"][0] == {"fra": 360.0, "til": 420.0, "fra_kl": "00:00", "til_kl": "01:00", "fase": "dyb", "min": 60}
    assert nat["min_i_fase"] == {"dyb": 60, "let": 0, "rem": 30, "vaagen": 0}


def test_doegnets_kurver_i_minutter_efter_midnat(conn):
    # 2026-10-22 00.00 dansk tid er 22.00 GMT dagen før (1792620000000 ms)
    nul = 1792620000000
    raw = {"stats": {"includesWellnessData": True},
           "heart_rates": {"heartRateValues": [[nul, 70], [nul + 120000, None], [nul + 240000, 72]]},
           "all_day_stress": {"stressValuesArray": [[nul, 30], [nul + 180000, -1]],
                              "bodyBatteryValuesArray": [[nul, "MEASURED", 18, 3.0]]},
           "steps_day": [{"startGMT": "2026-10-21T22:15:00.0", "steps": 12, "primaryActivityLevel": "sleeping"}]}
    conn.execute("INSERT INTO daily (date, raw) VALUES (?, ?)", ("2026-10-22", json.dumps(raw)))
    conn.commit()
    d = kroppen_mod.doegnet(conn, "2026-10-22")
    assert d["har_kurver"]
    assert d["puls"]["punkter"] == [[0.0, 70], [4.0, 72]]  # et hul står ikke som 0
    assert d["stress"]["punkter"] == [[0.0, 30]]           # -1 er ingen måling
    assert d["bb"]["punkter"] == [[0.0, 18]]
    assert d["skridt"] == [[15, 12, "sleeping"]]
    assert kroppen_mod.doegnet(conn, "2026-10-21") is None


def test_byg_filer_skriver_kun_det_aendrede(conn, tmp_path):
    _dag(conn, "2026-09-30", 5000)
    _dag(conn, "2026-10-01", 6000)
    skrevet = []
    skriv = lambda p, t: (skrevet.append(p.relative_to(tmp_path).as_posix()), p.write_text(t))  # noqa: E731
    kroppen_mod.byg_filer(conn, tmp_path, skriv, today=I_DAG)
    assert {"kroppen/dag/2026-09-30.json", "kroppen/dag/2026-10-01.json",
            "kroppen/maaned/2026-09.json", "kroppen/maaned/2026-10.json"} <= set(skrevet)
    index = json.loads((tmp_path / "kroppen" / "index.json").read_text())
    assert index["dage"] == ["2026-09-30", "2026-10-01"]
    assert [m["id"] for m in index["maaneder"]] == ["2026-10", "2026-09"]

    skrevet.clear()
    conn.execute("UPDATE daily SET raw = ? WHERE date = '2026-10-01'", (json.dumps({"stats": {"totalSteps": 7000}}),))
    conn.commit()
    kroppen_mod.byg_filer(conn, tmp_path, skriv, today=I_DAG)
    assert sorted(s for s in skrevet if s.startswith(("kroppen/dag", "kroppen/maaned"))) == [
        "kroppen/dag/2026-10-01.json", "kroppen/maaned/2026-10.json"]


def test_maaned_er_hele_kalendermaaneden(conn):
    _dag(conn, "2026-09-15", 4000)
    m = kroppen_mod.maaned(conn, "2026-09", today=I_DAG)
    assert (m["fra"], m["til"], len(m["dage"])) == ("2026-09-01", "2026-09-30", 30)
    assert m["periode"] == {"id": "2026-09", "navn": "September 2026"}
    assert m["resume"]["skridt"]["n"] == 1 and len(m["uge"]["dage"]) == 7


def test_dagens_pas_med_tempo_og_markoer_i_index(conn, tmp_path):
    _dag(conn, "2026-10-20", 9000)
    raw = {"averageSpeed": 1000 / 312, "movingDuration": 1500, "duration": 1800, "trainingEffectLabel": "TEMPO",
           "moderateIntensityMinutes": 0, "locationName": "København"}
    conn.execute("""INSERT INTO activities (activity_id, start_local, date, sport, name, duration_s, distance_m, avg_hr, max_hr, raw)
                    VALUES ('1', '2026-10-20 07:30:00', '2026-10-20', 'running', 'Morgenløb', 1800, 5000, 150, 170, ?)""",
                 (json.dumps(raw),))
    conn.commit()
    p = kroppen_mod.doegnet(conn, "2026-10-20")["aktiviteter"][0]
    assert (p["sport_navn"], p["start"], p["slut"], p["fra_min"], p["til_min"]) == ("Løb", "07:30", "08:00", 450, 480)
    tal = {t["navn"]: t.get("tekst", t.get("v")) for t in p["noegletal"]}
    assert tal["Tempo"] == "5:12 /km" and tal["I bevægelse"] == 25 and tal["Primær effekt"] == "Tempo"
    assert "Moderat intensitet" not in tal  # 0 minutter står ikke
    kroppen_mod.byg_filer(conn, tmp_path, lambda q, t: q.write_text(t), today=I_DAG)
    index = json.loads((tmp_path / "kroppen" / "index.json").read_text())
    assert index["aktiviteter"] == {"2026-10-20": [{"sport": "running", "gruppe": "loeb", "sport_navn": "Løb", "navn": "Morgenløb"}]}
    assert kroppen_mod.gruppe("paddelball") == "andet" and kroppen_mod.gruppe("bouldering") == "klatring"
    uge = kroppen(conn, dage=7, today=I_DAG)["uge"]["dage"]
    assert next(d for d in uge if d["dato"] == "2026-10-20")["traening_min"] == 30


def test_hrv_status_paa_dansk(conn):
    raw = {"stats": {"includesWellnessData": True}}
    conn.execute("INSERT INTO daily (date, hrv_last_night, hrv_status, raw) VALUES ('2026-10-20', 70, 'UNBALANCED', ?)", (json.dumps(raw),))
    conn.commit()
    assert kroppen_mod.doegnet(conn, "2026-10-20")["doegn"]["hrv_status"] == "ubalanceret"
    assert [kroppen_mod.hrv_status(s) for s in ("BALANCED", "LOW", "NONE", None, "NY_STATUS")] == [
        "balanceret", "lav", "ingen status", None, "ny_status"]


def test_pas_har_tid_i_zoner_og_resten_af_passet(conn):
    # Et styrkepas på 97 min med 2 min puls i zone 1: siden skal kunne skrive "2 af 97 min" uden selv at regne
    _dag(conn, "2026-10-15", 5000)
    conn.execute("""INSERT INTO activities (activity_id, start_local, date, sport, name, duration_s, raw)
                    VALUES ('2', '2026-10-15 16:00:00', '2026-10-15', 'strength_training', 'Styrke', 5820, '{}')""")
    conn.execute("INSERT INTO activity_zones (activity_id, zone, seconds) VALUES ('2', 1, 120), ('2', 2, 0)")
    conn.commit()
    p = kroppen_mod.doegnet(conn, "2026-10-15")["aktiviteter"][0]
    assert (p["varighed_min"], p["min_i_zoner"], p["uden_zone_min"]) == (97, 2, 95)
    assert p["zoner_min"] == [2.0, 0.0, 0.0, 0.0, 0.0]


def test_pas_uden_zoner_har_ingen_zonetid(conn):
    assert kroppen_mod._zonetid(None, 1800) == {"min_i_zoner": None, "uden_zone_min": None}
    assert kroppen_mod._zonetid([1800.0, 0, 0, 0, 0], None) == {"min_i_zoner": 30, "uden_zone_min": None}
