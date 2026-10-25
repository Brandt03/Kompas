"""Kalenderens friskhed (måles på hentning/ændring, ikke på seneste begivenhed) og at hver kilde læses for sig."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta

from conftest import idag, lav_garmin

from overblik import cli, config, db, kilder


def _kilder(conn) -> dict[str, dict]:
    return {r["kilde"]: r for r in cli.kilde_status(conn)}


# --- opgave 1: kalenderens friskhed ------------------------------------------

def test_kalender_data_til_er_fremtidig_men_friskhed_kommer_fra_opdateret(miljoe):
    cli.opdater(nu=datetime(2026, 1, 1, 12, 0))
    r = _kilder(db.connect())["kalender"]
    assert date.fromisoformat(r["data_til"]) > idag()  # seneste begivenhed ligger fremme
    assert r["opdateret"] == "2026-01-01T12:00:00"
    assert r["gammel"] is True  # før: alderen blev regnet fra data_til og var negativ, så aldrig gammel


def test_uaendret_kalender_beholder_tiden_og_bliver_gammel(miljoe):
    foer = datetime.now() - timedelta(days=5)
    cli.opdater(nu=foer)
    cli.opdater()  # samme indhold, hentet igen nu
    r = _kilder(db.connect())["kalender"]
    assert r["opdateret"] == foer.isoformat(timespec="seconds")
    assert r["alder_dage"] == 5 and r["gammel"] is True
    assert r["hentet"] != r["opdateret"]  # opdater kørte, men kalenderen ændrede sig ikke


def test_aendret_kalender_er_frisk(miljoe):
    cli.opdater(nu=datetime.now() - timedelta(days=5))
    g = sqlite3.connect(config.GARMIN_DB)
    g.execute("UPDATE calendar_events SET summary = 'Flyttet forelæsning' WHERE uid = 'u4'")
    g.commit()
    g.close()
    cli.opdater()
    r = _kilder(db.connect())["kalender"]
    assert r["alder_dage"] == 0 and r["gammel"] is False


def test_hentetid_fra_garmin_coach_bruges_naar_den_findes(miljoe):
    m = miljoe["mandag"]
    lav_garmin(config.GARMIN_DB, [m], [("u1", f"{(idag() + timedelta(days=20)).isoformat()}T10:00",
                                        f"{(idag() + timedelta(days=20)).isoformat()}T12:00", "Fremtid", None)],
               state={"last_calendar_sync": "2026-01-02T08:00:00"})
    cli.opdater()
    r = _kilder(db.connect())["kalender"]
    assert r["opdateret"] == "2026-01-02T08:00:00" and r["gammel"] is True


def test_status_alder_fra_data_til_uden_opdateret():
    rows = [{"kilde": "garmin", "data_til": "2026-10-01", "opdateret": None},
            {"kilde": "sure", "data_til": "2026-10-08", "opdateret": None},
            {"kilde": "kalender", "data_til": "2026-10-30", "opdateret": "2026-10-05T07:00:00"},
            {"kilde": "ny", "data_til": None, "opdateret": None}]
    s = {r["kilde"]: (r["alder_dage"], r["gammel"]) for r in kilder.status(rows, date(2026, 10, 10))}
    assert s == {"garmin": (9, True), "sure": (2, False), "kalender": (5, True), "ny": (None, False)}


def test_aeldre_liv_db_faar_de_nye_kolonner(tmp_path):
    p = tmp_path / "gammel.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE kilder (kilde TEXT PRIMARY KEY, data_til TEXT, hentet TEXT)")
    c.execute("INSERT INTO kilder VALUES ('sure', '2026-10-01', '2026-10-01T10:00:00')")
    c.commit()
    c.close()
    r = dict(db.connect(p).execute("SELECT * FROM kilder").fetchone())
    assert r == {"kilde": "sure", "data_til": "2026-10-01", "hentet": "2026-10-01T10:00:00",
                 "opdateret": None, "aftryk": None, "fejl": None}


# --- opgave 2: én kilde, der fejler, vælter ikke de andre ----------------------

def _uge_nu(conn) -> dict:
    return dict(conn.execute("SELECT * FROM uger WHERE mandag = ?",
                             [(kilder.mandag(idag()) - timedelta(days=7)).isoformat()]).fetchone())


def test_alle_kilder_ok_giver_exit_0(miljoe, capsys):
    assert cli.main(["opdater"]) == 0
    assert capsys.readouterr().err == ""
    assert all(r["fejl"] is None for r in _kilder(db.connect()).values())


def _oedelagte_eksporter():
    return {
        "ikke json": "ikke json",
        "forkert type": json.dumps({"generated_at": "2026-10-10T10:00:00", "transactions": "ikke en liste"}),
        "mangler felt": json.dumps({"last_sync": "2026-10-10T10:00:00"}),
        "mangler kategori": json.dumps({"last_sync": idag().isoformat(), "transactions": [
            {"date": idag().isoformat(), "amount": 10, "group": "Faste"}]}),
    }


def test_oedelagt_sure_eksport_isoleres(miljoe, capsys):
    assert cli.main(["opdater"]) == 0
    foer = _uge_nu(db.connect())
    assert foer["takeaway_kr"] == 80
    for navn, indhold in _oedelagte_eksporter().items():
        capsys.readouterr()
        config.SURE_JSON.write_text(indhold)
        # Ny Garmin-dag i den forrige uge, så det kan ses, at Garmin stadig gemmes
        g = sqlite3.connect(config.GARMIN_DB)
        g.execute("UPDATE daily SET sleep_s = 30600 WHERE date = ?",
                  [(kilder.mandag(idag()) - timedelta(days=7)).isoformat()])
        g.commit()
        g.close()

        assert cli.main(["opdater"]) == 1, navn
        ud = capsys.readouterr()
        assert "kilden sure fejlede" in ud.err, navn
        assert "sure       FEJL:" in ud.out and "garmin     data til" in ud.out, navn

        conn = db.connect()
        k = _kilder(conn)
        assert k["sure"]["fejl"], navn
        assert k["garmin"]["fejl"] is None and k["kalender"]["fejl"] is None, navn
        uge = _uge_nu(conn)
        assert uge["takeaway_kr"] == 80, navn  # Sures tal står som ved sidste vellykkede læsning
        assert uge["soevn_timer_snit"] > foer["soevn_timer_snit"], navn  # Garmin er opdateret
        assert uge["undervisning_timer"] == 2.0, navn  # kalenderen også


def test_fejl_ryddes_naar_kilden_virker_igen(miljoe):
    gode = config.SURE_JSON.read_text()
    config.SURE_JSON.write_text("ikke json")
    assert cli.main(["opdater"]) == 1
    config.SURE_JSON.write_text(gode)
    assert cli.main(["opdater"]) == 0
    assert _kilder(db.connect())["sure"]["fejl"] is None


def test_fejl_i_garmin_isoleres_ogsaa(miljoe, monkeypatch, capsys):
    def fejler(fra):
        raise sqlite3.OperationalError("no such table: daily")
    monkeypatch.setitem(kilder.KILDER, "garmin", fejler)
    assert cli.main(["opdater"]) == 1
    assert "kilden garmin fejlede" in capsys.readouterr().err
    conn = db.connect()
    k = _kilder(conn)
    assert k["garmin"]["fejl"] == "OperationalError: no such table: daily"
    assert k["sure"]["fejl"] is None and k["kalender"]["fejl"] is None
    assert _uge_nu(conn)["takeaway_kr"] == 80


def test_rapport_opdater_giver_rapporten_med_fejlen_i_kilder(miljoe, capsys):
    config.SURE_JSON.write_text("ikke json")
    assert cli.main(["rapport", "--opdater"]) == 0
    ud = capsys.readouterr()
    assert "kilden sure fejlede" in ud.err
    r = json.loads(ud.out)
    assert {k["kilde"]: bool(k["fejl"]) for k in r["kilder"]} == {"garmin": False, "kalender": False, "sure": True}


def test_tilbagebetaling_trækkes_kun_fra_op_til_ugens_køb(tmp_path, monkeypatch):
    """Take-away og café/bar er netto, men en refusion større end ugens køb gør ikke ugen negativ."""
    from conftest import lav_sure
    monkeypatch.setattr(config, "SURE_JSON", tmp_path / "data.json")
    m = date(2026, 10, 19)
    t = lambda dag, kr, kat: {"date": (m + timedelta(days=dag)).isoformat(), "amount": kr,
                              "group": "Variable udgifter", "category": kat}
    lav_sure(config.SURE_JSON, [
        t(0, 40, "Take-away og mad ude"), t(4, -300, "Take-away og mad ude"),   # mere tilbage end ugens køb
        t(1, -40, "Café, bar og byture"),                                        # kun tilbagebetaling
        t(7, 300, "Take-away og mad ude"), t(8, -150, "Take-away og mad ude"),   # en ven betaler sin del: netto
        t(2, 400, "Dagligvarer"), t(3, -500, "Dagligvarer"),                     # dagligvarer er netto uden grænse
    ], "2026-11-01")
    ud, _ = kilder.oekonomi(m)
    u1, u2 = ud["2026-10-19"], ud["2026-10-26"]
    assert (u1["takeaway_kr"], u1["cafe_bar_kr"], u1["takeaway_koeb"]) == (0, 0, 1)
    assert u2["takeaway_kr"] == 150 and u2["takeaway_koeb"] == 1
    assert u1["dagligvarer_kr"] == -100
    assert u1["variabelt_kr"] == 440  # kun køb, uændret

