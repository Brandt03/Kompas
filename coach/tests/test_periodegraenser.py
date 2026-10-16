"""Opg. 4: en periode lørdag–fredag har natten til den første lørdag med, ikke natten til lørdagen efter.

Garmin gemmer søvnen på den dato, man vågner, så natten til lørdag S står på S."""

from datetime import date, timedelta

from garmin_coach.db import upsert
from garmin_coach.metrics import periode_rapport

S, E = date(2026, 9, 26), date(2026, 10, 9)  # lørdag og fredag


def _nat(conn, d: date, timer: float, score: int = 70) -> None:
    upsert(conn, "daily", {"date": d.isoformat(), "sleep_s": timer * 3600, "sleep_score": score,
                           "hrv_last_night": 60, "resting_hr": 48}, pk=["date"])


def test_datoerne_er_loerdag_og_fredag():
    assert S.weekday() == 5 and E.weekday() == 4 and (E - S).days + 1 == 14


def test_natten_til_foerste_loerdag_er_med_og_natten_efter_ikke(conn):
    _nat(conn, S - timedelta(days=1), 3)   # natten til fredagen før: forrige periode
    _nat(conn, S, 9)                        # natten til periodens første lørdag
    for i in range(1, 14):
        _nat(conn, S + timedelta(days=i), 7)
    _nat(conn, E + timedelta(days=1), 3)   # natten til lørdagen efter: næste periode
    conn.commit()

    sundhed = periode_rapport(conn, S.isoformat(), E.isoformat())["sundhed"]
    assert sundhed["sovn_t"] == round((9 + 13 * 7) / 14, 2)
    assert sundhed["naetter_u7"] == 0  # de to korte nætter uden for perioden tæller ikke


def test_to_perioder_i_traek_deler_ingen_nat(conn):
    S2, E2 = E + timedelta(days=1), E + timedelta(days=14)
    for i in range((E2 - S).days + 1):
        _nat(conn, S + timedelta(days=i), 6 if S + timedelta(days=i) <= E else 8)
    conn.commit()
    foerste = periode_rapport(conn, S.isoformat(), E.isoformat())
    anden = periode_rapport(conn, S2.isoformat(), E2.isoformat())
    assert foerste["sundhed"]["sovn_t"] == 6 and foerste["sundhed"]["naetter_u7"] == 14
    assert anden["sundhed"]["sovn_t"] == 8 and anden["sundhed"]["naetter_u7"] == 0
    assert not any("Wellness-data" in f for f in foerste["forbehold"] + anden["forbehold"])
