"""Opgave 3: reviewet regnes ud fra rapportens mandag, ikke fra dagen, rutinen kører."""

from __future__ import annotations

import json
from datetime import date, timedelta

from overblik import cli, kilder, rapport


def test_sidste_hele_uge_er_den_samme_hele_ugen():
    # Uge 41 i 2026 er mandag 5/10 til søndag 11/10; sidste hele uge er uge 40 fra mandag 28/9
    for i in range(7):
        assert kilder.sidste_hele_uge(date(2026, 10, 5) + timedelta(days=i)) == date(2026, 9, 28)
    assert kilder.sidste_hele_uge(date(2026, 10, 12)) == date(2026, 10, 5)


def test_kommende_uge_foelger_rapportens_mandag():
    m = date(2026, 9, 28)
    mandag = rapport.kommende_uge(m, date(2026, 10, 5))
    onsdag = rapport.kommende_uge(m, date(2026, 10, 7))
    # Kørt onsdag er den kommende uge stadig mandag–søndag, ikke de syv dage fra onsdag
    for k in (mandag, onsdag):
        assert (k["uge"], k["mandag"], k["soendag"]) == ("2026-W41", "2026-10-05", "2026-10-11")
    assert mandag["kalender_dage_frem"] == 7
    assert onsdag["kalender_dage_frem"] == 5  # onsdag til og med søndag
    assert rapport.kommende_uge(m, date(2026, 10, 12))["kalender_dage_frem"] is None  # ugen er forbi


def test_kommende_uge_over_aarsskiftet():
    k = rapport.kommende_uge(date(2026, 12, 28), date(2026, 12, 30))  # 2026 har 53 uger
    assert (k["uge"], k["mandag"], k["soendag"]) == ("2027-W01", "2027-01-04", "2027-01-10")


def test_rapport_kommende_uge_kommer_fra_uge_argumentet(miljoe, capsys):
    cli.opdater()
    m = miljoe["mandag"]
    assert cli.main(["rapport", "--uge", m.isoformat()]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["mandag"] == m.isoformat()
    assert r["kommende_uge"]["mandag"] == (m + timedelta(days=7)).isoformat()
