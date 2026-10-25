"""Et gemt review får tidspunkt med tidszone og metoden, tallene er regnet efter. Ældre reviews røres ikke."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone

from overblik import cli, rapport, side
from overblik.db import connect

TEKST = {"saetning": "En rolig uge.", "udskilte": [], "sammenhaenge": ["Ingen stærke sammenhænge."],
         "kommende_uge": [], "en_ting": "Læg selvstudie før forelæsningen."}


def test_gem_review_gemmer_metode_og_tidspunkt_med_tidszone(miljoe):
    cli.opdater()
    conn = connect()
    m = miljoe["mandag"] + timedelta(days=7)
    doc = side.gem_review(conn, m, TEKST, nu=datetime(2026, 10, 12, 7, 3, 11))
    assert doc["metode"] == rapport.METODE
    t = datetime.fromisoformat(doc["genereret"])
    assert t.tzinfo is not None and t.utcoffset() is not None
    assert doc["genereret"].startswith("2026-10-12T07:03:11")  # lokal tid, så de første 10 tegn er den lokale dato
    gemt = side.reviews(conn)[0]
    assert (gemt["metode"], gemt["genereret"]) == (doc["metode"], doc["genereret"])


def test_eksport_har_felterne_paa_nye_reviews_og_ikke_paa_gamle(miljoe):
    cli.opdater()
    conn = connect()
    m = miljoe["mandag"]
    # Et review gemt før metode-feltet fandtes: genereret uden tidszone, ingen metode
    gl = side.snapshot(conn, m) | {"tekst": TEKST, "genereret": "2026-10-07T11:32:46"}
    with conn:
        conn.execute("INSERT INTO reviews (uge, doc) VALUES (?, ?)", [gl["uge"], json.dumps(gl, ensure_ascii=False)])
    side.gem_review(conn, m + timedelta(days=7), TEKST)

    side.eksport(conn, miljoe["tmp"] / "site")
    ud = json.loads((miljoe["tmp"] / "site" / "liv.json").read_text())
    gamle, nye = ud["reviews"]
    assert "metode" not in gamle and gamle["genereret"] == "2026-10-07T11:32:46"  # intet påført bagefter
    assert nye["metode"] == rapport.METODE
    assert datetime.fromisoformat(nye["genereret"]).tzinfo is not None
    assert ud["metode"] == rapport.METODE
    # Det gamle review i databasen er uændret
    assert json.loads(conn.execute("SELECT doc FROM reviews WHERE uge = ?", [gl["uge"]]).fetchone()["doc"]) == gl


def test_uge_uden_review_faar_hverken_metode_eller_tidspunkt(miljoe):
    cli.opdater()
    conn = connect()
    side.eksport(conn, miljoe["tmp"] / "site")
    (r,) = json.loads((miljoe["tmp"] / "site" / "liv.json").read_text())["reviews"]
    assert r["tekst"] is None and "metode" not in r and "genereret" not in r


def test_cli_gem_review_skriver_metoden(miljoe, capsys, monkeypatch):
    cli.opdater()
    monkeypatch.setattr(side.eksport, "__defaults__", (miljoe["tmp"] / "site",))
    f = miljoe["tmp"] / "tekst.json"
    f.write_text(json.dumps(TEKST, ensure_ascii=False))
    m = miljoe["mandag"] + timedelta(days=7)
    assert cli.main(["gem-review", str(f), "--uge", m.isoformat()]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["metode"] == rapport.METODE and out["reviews"] == 1
    r = json.loads((miljoe["tmp"] / "site" / "liv.json").read_text())["reviews"][0]
    assert r["metode"] == rapport.METODE


def test_naetter_har_sengetid_og_sen_skaermtid_under_aftenens_dato(miljoe):
    cli.opdater()
    conn = connect()
    i_dag = datetime.now().date()
    aften, forrige = i_dag - timedelta(days=1), i_dag - timedelta(days=2)
    # Sengetid 23.48 lokal tid; Garmin dater natten ved opvågningen, altså i dag
    ms = int(datetime(aften.year, aften.month, aften.day, 23, 48, tzinfo=timezone.utc).timestamp() * 1000)
    g = sqlite3.connect(miljoe["tmp"] / "coach.db")
    g.execute("INSERT OR IGNORE INTO daily (date) VALUES (?)", [i_dag.isoformat()])  # testdataene stopper i går
    g.execute("UPDATE daily SET raw = ? WHERE date = ?",
              [json.dumps({"sleep": {"dailySleepDTO": {"sleepStartTimestampLocal": ms}}}), i_dag.isoformat()])
    g.commit()
    g.close()
    (miljoe["tmp"] / "skaermtid.json").write_text(json.dumps({"dage": [
        {"dato": aften.isoformat(), "sen_timer": 0.4, "enheder": {"Mac": {}}},
        {"dato": forrige.isoformat(), "sen_timer": 0.0, "enheder": {}},  # ingen enhed sendte data: ukendt, ikke 0
    ]}))
    side.eksport(conn, miljoe["tmp"] / "site")
    n = {x["dato"]: x for x in json.loads((miljoe["tmp"] / "site" / "liv.json").read_text())["naetter"]}
    assert len(n) == side.NAETTER and max(n) == aften.isoformat()
    assert (n[aften.isoformat()]["sengetid"], n[aften.isoformat()]["sengetid_t"]) == ("23:48", 5.8)
    assert n[aften.isoformat()]["sen_skaermtid_t"] == 0.4
    assert n[forrige.isoformat()]["sen_skaermtid_t"] is None and n[forrige.isoformat()]["sengetid"] is None


def test_dagsplan_lægger_skaerm_selvstudie_og_pas_i_de_planlagte_blokke(miljoe):
    cli.opdater()
    conn = connect()
    d = (datetime.now() - timedelta(days=1)).date().isoformat()
    g = sqlite3.connect(miljoe["tmp"] / "coach.db")
    g.executemany("INSERT INTO calendar_events (uid, start_local, end_local, summary, fag_kode, fag_navn, kalender) VALUES (?, ?, ?, ?, ?, ?, 'Test')", [
        ("p1", f"{d}T10:00", f"{d}T12:00", "Øvelse", "KURS102", "Beta – dolor sit amet"),
        ("p2", f"{d}T13:00", f"{d}T14:00", "Delta indhentning", None, None),
        ("p3", f"{d}T13:30", f"{d}T14:00", "Selvstudie · Delta", None, None),  # CalTask: logget selvstudie, ikke plan
        ("p4", f"{d}T05:30", f"{d}T05:45", "Før døgnskiftet", None, None),  # hører til dagen før
    ])
    g.execute("INSERT INTO activities (activity_id, date, start_local, sport, name, duration_s) VALUES (9, ?, ?, 'running', 'Løb', 1800)",
              [d, f"{d} 13:45:00"])
    g.commit()
    g.close()
    (miljoe["tmp"] / "skaermtid.json").write_text(json.dumps({"dage": [{"dato": d, "forloeb": [
        {"start": f"{d}T13:00+02:00", "slut": f"{d}T13:30+02:00", "kategori": "Studie", "gruppe": "Produktiv"},
        {"start": f"{d}T13:30+02:00", "slut": f"{d}T13:45+02:00", "kategori": "Sociale medier", "gruppe": "Passiv"}]}]}))
    (miljoe["tmp"] / "studie.json").write_text(json.dumps({"fag": [{"status": {"rytme": {"dage": {d: 4}}}},
                                                                   {"status": {"rytme": {"dage": {d: 3}}}}]}))
    side.eksport(conn, miljoe["tmp"] / "site")
    plan = {x["dato"]: x for x in json.loads((miljoe["tmp"] / "site" / "liv.json").read_text())["dagsplan"]}
    dag = plan[d]
    typer = {p["titel"]: p["type"] for p in dag["plan"]}  # testmiljøet har også sine egne forelæsninger
    assert (typer["Øvelse"], typer["Delta indhentning"]) == ("undervisning", "blok") and "Selvstudie · Delta" not in typer
    assert [x["type"] for x in dag["logget"]] == ["selvstudie", "traening"]
    blok = next(p for p in dag["plan"] if p["titel"] == "Delta indhentning")["faktisk"]
    assert blok == {"minutter": 60, "skaerm": {"Produktiv": 30, "Passiv": 15}, "kategorier": {"Studie": 30, "Sociale medier": 15},
                    "uden_skaerm": 15, "selvstudie": 30, "traening": 15}
    assert dag["studiesvar"] == 7
    assert all(p["titel"] != "Før døgnskiftet" for p in dag["plan"])


def test_nat_sammenhaeng_venter_paa_nok_naetter_og_tester_saa(miljoe):
    cli.opdater()
    conn = connect()
    i_dag = datetime.now().date()
    (miljoe["tmp"] / "skaermtid.json").write_text(json.dumps({"dage": [
        {"dato": (i_dag - timedelta(days=i)).isoformat(), "sen_timer": 0.5, "enheder": {"Mac": {}}} for i in range(2, 12)]}))  # testdataenes søvn stopper i går
    side.eksport(conn, miljoe["tmp"] / "site")
    nat = json.loads((miljoe["tmp"] / "site" / "liv.json").read_text())["nat_sammenhaeng"]
    assert (nat["n_naetter"], nat["status"]) == (10, "for få nætter (10 af 28)") and "rho" not in nat
    # 40 nætter, hvor mere sen skærmtid går med lavere søvnscore
    g = sqlite3.connect(miljoe["tmp"] / "coach.db")
    dage = [i_dag - timedelta(days=i) for i in range(0, 41)]
    g.executemany("INSERT OR REPLACE INTO daily (date, sleep_score) VALUES (?, ?)", [(d.isoformat(), 90 - 2 * (i % 20)) for i, d in enumerate(dage)])
    g.commit()
    g.close()
    (miljoe["tmp"] / "skaermtid.json").write_text(json.dumps({"dage": [
        {"dato": (d - timedelta(days=1)).isoformat(), "sen_timer": round(0.1 * (i % 20), 2), "enheder": {"Mac": {}}} for i, d in enumerate(dage)]}))
    side.eksport(conn, miljoe["tmp"] / "site")
    nat = json.loads((miljoe["tmp"] / "site" / "liv.json").read_text())["nat_sammenhaeng"]
    assert nat["n_naetter"] >= side.NAT_MIN and nat["rho"] < -0.9 and nat["status"] == "stærk"


def _glippede_med(miljoe, begivenheder, hentet):
    cli.opdater()
    g = sqlite3.connect(miljoe["tmp"] / "coach.db")
    g.executemany("INSERT OR REPLACE INTO calendar_events (uid, start_local, end_local, summary, fag_kode, plan_blok, kalender) "
                  "VALUES (?, ?, ?, ?, NULL, ?, 'Test')", begivenheder)
    g.execute("DELETE FROM sync_state WHERE key = 'last_calendar_sync'")
    if hentet:
        g.execute("INSERT INTO sync_state VALUES ('last_calendar_sync', ?)", [hentet])
    g.commit()
    g.close()
    side.eksport(connect(), miljoe["tmp"] / "site")
    return json.loads((miljoe["tmp"] / "site" / "liv.json").read_text())["glippede"]


def test_glippede_kraever_to_doegn_med_planblokke_uden_logget_selvstudie(miljoe):
    # To og tre dage tilbage er altid blandt de tre seneste afsluttede døgn, også før kl. 6
    a, b = ((date.today() - timedelta(days=n)).isoformat() for n in (2, 3))
    blokke = [("p1", f"{a}T09:00", f"{a}T10:30", "Alfa · fagnoter", 1), ("p2", f"{a}T11:00", f"{a}T12:00", "Beta · e4", 1),
              ("p3", f"{b}T09:00", f"{b}T10:00", "Gamma · fagnoter", 1),
              ("t1", f"{b}T15:00", f"{b}T16:00", "Tandlæge", 0)]  # uden mærket: ikke en del af planen
    hentet = date.today().isoformat()
    gl = _glippede_med(miljoe, blokke, hentet)
    assert gl["vis"] and [d["dato"] for d in gl["glippet"]] == [b, a]
    assert gl["glippet"][1] | {"studiesvar": None} == {"dato": a, "blokke": 2, "minutter": 150,
                                                        "titler": ["Alfa · fagnoter", "Beta · e4"], "studiesvar": None}
    assert gl["glippet"][0]["titler"] == ["Gamma · fagnoter"]

    # Selvstudie logget på et andet tidspunkt samme døgn tæller også: så er kun ét døgn glippet
    gl = _glippede_med(miljoe, blokke + [("l1", f"{a}T20:00", f"{a}T20:30", "Selvstudie · Delta", 0)], hentet)
    assert not gl["vis"] and [d["dato"] for d in gl["glippet"]] == [b]


def test_glippede_siger_intet_naar_kalenderen_er_gammel(miljoe):
    a = (date.today() - timedelta(days=2)).isoformat()
    blokke = [(f"p{i}", f"{a}T0{i}:00", f"{a}T0{i}:30", "Alfa · fagnoter", 1) for i in (7, 8)]
    gl = _glippede_med(miljoe, blokke, (date.today() - timedelta(days=3)).isoformat())
    assert not gl["vis"] and gl["glippet"] == [] and "ikke hentet" in gl["status"]
    assert "aldrig" in _glippede_med(miljoe, blokke, None)["status"]


def _studieuge_med(miljoe, begivenheder, hentet):
    """Som _glippede_med, men ugetabellen regnes efter begivenhederne, så det loggede selvstudie kommer med."""
    _glippede_med(miljoe, begivenheder, hentet)
    cli.opdater()
    side.eksport(connect(), miljoe["tmp"] / "site")
    return json.loads((miljoe["tmp"] / "site" / "liv.json").read_text())["studieuge"]


def test_studieuge_maaler_logget_selvstudie_mod_ugens_planlagte_blokke(miljoe):
    m = date.today() - timedelta(days=date.today().weekday())
    blokke = [("p1", f"{m}T09:00", f"{m}T10:30", "Alfa · fagnoter", 1),
              ("p2", f"{m + timedelta(days=6)}T11:00", f"{m + timedelta(days=6)}T12:00", "Beta · e4", 1),  # søndag tæller med
              ("p3", f"{m + timedelta(days=7)}T09:00", f"{m + timedelta(days=7)}T10:00", "Næste uge", 1),
              ("t1", f"{m}T15:00", f"{m}T16:00", "Tandlæge", 0),  # uden mærket: ikke en del af planen
              ("l1", f"{m}T00:00", f"{m}T00:30", "Selvstudie · Delta", 0)]  # CalTask tæller kun det, der er slut
    uge = _studieuge_med(miljoe, blokke, date.today().isoformat())
    assert uge == {"mandag": m.isoformat(), "planlagt_timer": 2.5, "planlagt_blokke": 2,
                   "selvstudie_timer": 0.5, "selvstudie_dage": 1}

    uge = _studieuge_med(miljoe, blokke, (date.today() - timedelta(days=3)).isoformat())
    assert "ikke hentet" in uge["status"]


def test_studietid_pr_fag_og_uge(miljoe):
    m = date.today() - timedelta(days=date.today().weekday())
    blokke = [("p1", f"{m}T00:00", f"{m}T00:30", "Alfa · fagnoter uge 38", 1),          # forbi
              ("p2", f"{m + timedelta(days=7)}T09:00", f"{m + timedelta(days=7)}T11:00", "Alfa · fagnoter uge 39", 1),  # kommer
              ("l1", f"{m}T00:00", f"{m}T00:30", "Selvstudie · Delta💽", 0),
              ("l2", f"{m + timedelta(days=7)}T09:00", f"{m + timedelta(days=7)}T10:00", "Selvstudie · Beta🤖", 0),  # ikke slut
              ("t1", f"{m}T00:00", f"{m}T00:15", "Tandlæge", 0)]
    _glippede_med(miljoe, blokke, date.today().isoformat())
    # Den samme undervisning to gange i kalenderen (fx to feeds) tæller én gang
    g = sqlite3.connect(miljoe["tmp"] / "coach.db")
    g.executemany("INSERT INTO calendar_events (uid, start_local, end_local, summary, fag_kode, fag_navn, kalender) VALUES (?, ?, ?, ?, ?, ?, 'Test')",
                  [(f"d{i}", f"{m}T00:00", f"{m}T00:45", "Forelæsning", "TEST1", "Testfag", ) for i in (1, 2)])
    g.commit(); g.close()
    side.eksport(connect(), miljoe["tmp"] / "site")
    st = json.loads((miljoe["tmp"] / "site" / "liv.json").read_text())["studietid"]
    assert st["selvstudie"] == [{"navn": "Delta", "timer": 0.5, "uger": {m.isoformat(): 0.5}, "dage": {m.isoformat(): 0.5},
                                 "sessioner": {m.isoformat(): 1}}]
    assert st["studieblokke"] == [{"navn": "Alfa", "timer": 0.5, "planlagt_timer": 2.5, "uger": {m.isoformat(): 0.5}}]
    assert all(u["timer"] > 0 for u in st["undervisning"])  # testkalenderens undervisning med fag_kode
    # Hvert fag har sin undervisning pr. slags (art og form), og slagene giver tilsammen fagets timer
    assert all(abs(sum(f["timer"] for f in u["former"]) - u["timer"]) < 0.05 for u in st["undervisning"])
    assert "Tandlæge" not in json.dumps(st, ensure_ascii=False)
    assert next(u for u in st["undervisning"] if u["kode"] == "TEST1")["timer"] == 0.75
