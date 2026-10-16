"""Et gemt review får tidspunkt med tidszone og metoden, tallene er regnet efter. Ældre reviews røres ikke."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

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
