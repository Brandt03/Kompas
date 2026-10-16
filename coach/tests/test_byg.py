"""Opg. 6: ét defekt periode-dokument vælter ikke byggeriet, og kompas.json skrives først til sidst."""

import json
import logging

import pytest

from garmin_coach import site

GOD = {"start": "2026-09-26", "slut": "2026-10-09", "status": "endelig", "vurdering": {"resume": "God."}}


def _defekte(conn) -> None:
    conn.executemany("INSERT INTO perioder (start, doc) VALUES (?, ?)", [
        ("2026-08-01", "{ikke json"),
        ("2026-08-15", json.dumps(["en", "liste"])),
        ("2026-08-29", json.dumps({"start": "2026-08-29", "status": "endelig"})),  # mangler slut
        ("2026-09-12", json.dumps({"start": "2026-09-12", "slut": None, "status": "endelig"})),
    ])
    conn.commit()


def test_defekte_perioder_springes_over_med_advarsel(conn, tmp_path, caplog):
    site.gem(conn, GOD)
    _defekte(conn)
    with caplog.at_level(logging.WARNING, logger="garmin_coach.site"):
        res = site.byg(conn, tmp_path / "site")
    assert res["perioder"] == 1
    assert res["sprunget_over"] == ["2026-08-01", "2026-08-15", "2026-08-29", "2026-09-12"]
    assert json.loads((tmp_path / "site" / "perioder.json").read_text()) == [GOD]
    advarsler = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert sum("Springer periode" in a for a in advarsler) == 4
    assert any("2026-08-29" in a and "mangler 'slut'" in a for a in advarsler)
    sider = {s["sti"]: s for s in json.loads((tmp_path / "site" / "kompas.json").read_text())["sider"]}
    assert sider["/form/perioder.html"]["nyt"] == "2026-09-26"
    coach = json.loads((tmp_path / "site" / "coach.json").read_text())
    assert coach["periode"]["start"] == "2026-09-26"


def test_perioder_kommandoen_taaler_defekte(conn):
    _defekte(conn)
    assert site.perioder(conn) == []


def test_kompas_json_skrives_sidst(conn, tmp_path, monkeypatch):
    site.gem(conn, GOD)
    raekkefoelge = []
    skriv = site._write
    monkeypatch.setattr(site, "_write", lambda path, text: (raekkefoelge.append(path.name), skriv(path, text)))
    site.byg(conn, tmp_path / "site")
    assert raekkefoelge[-1] == "kompas.json"
    assert {"perioder.json", "maaneder.json", "oversigt.json", "soevn.json", "coach.json"} <= set(raekkefoelge[:-1])


def test_fejl_undervejs_lader_det_gamle_manifest_staa(conn, tmp_path, monkeypatch):
    out = tmp_path / "site"
    out.mkdir()
    (out / "kompas.json").write_text('{"gammelt": true}')

    def fejler(conn):
        raise RuntimeError("månedsoversigten fejlede")

    monkeypatch.setattr(site, "maanedsoversigt", fejler)
    with pytest.raises(RuntimeError):
        site.byg(conn, out)
    assert json.loads((out / "kompas.json").read_text()) == {"gammelt": True}
    assert not list(out.glob("*.tmp"))
