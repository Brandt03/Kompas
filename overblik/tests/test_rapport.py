"""Låser afvigelses- og korrelationsfunktionernes nuværende opførsel fast. Testene beskriver det, koden gør nu, ikke
nødvendigvis det, den bør gøre: metoden afventer en beslutning, og en ændring skal kunne ses her."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from overblik import db, rapport


# --- rang og korrelation ------------------------------------------------------

def test_rang_giver_ens_vaerdier_gennemsnitsrang():
    assert rapport._rang([3, 1, 2, 2]) == [4.0, 1.0, 2.5, 2.5]


def test_pearson():
    assert rapport._pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert rapport._pearson([1, 1, 1], [1, 2, 3]) == 0.0  # ingen spredning: 0, ikke division med 0


def test_spearman_er_deterministisk_med_blok_permutation():
    rho, p = rapport.spearman(list(range(18)), list(range(18)))
    assert rho == pytest.approx(1.0)
    assert p == pytest.approx(0.001999600079984003)  # (1 + 9) / 5001 med seed 0

    rho, p = rapport.spearman(list(range(18)), [x if x % 2 else -x for x in range(18)])
    assert rho == pytest.approx(0.08359133126934984)
    assert p == pytest.approx(0.6644671065786842)


def test_spearman_med_to_blokke_kan_ikke_blive_signifikant():
    rho, p = rapport.spearman([1, 2, 3, 4, 5, 6], [6, 5, 4, 3, 2, 1])
    assert rho == pytest.approx(-1.0)
    assert p == pytest.approx(0.5036992601479704)


# --- afvigelser ---------------------------------------------------------------

def test_afvigelse_kraever_fire_ugers_historik_og_en_vaerdi():
    assert rapport._afvigelse("hrv_snit", 40, [60, 62, 58]) is None
    assert rapport._afvigelse("hrv_snit", None, [60, 62, 58, 61]) is None


def test_afvigelse_robust_z():
    assert rapport._afvigelse("hrv_snit", 40, [60, 62, 58, 61, 59, 60, 63, 57]) == {
        "vaerdi": 40, "normal": 60.0, "normal_interval": [57, 63], "robust_z": -8.99, "retning": "under",
        "tydelig": True, "vurdering": "skidt"}
    assert rapport._afvigelse("traening_pas", 5, [2, 3, 4, 2, 3, 4, 2, 4]) == {
        "vaerdi": 5, "normal": 3.0, "normal_interval": [2, 4], "robust_z": 1.35, "retning": "over",
        "tydelig": False, "vurdering": None}
    assert rapport._afvigelse("skridt_snit", 9000, [8000, 8500, 9000, 9500, 10000]) == {
        "vaerdi": 9000, "normal": 9000, "normal_interval": [8000, 10000], "robust_z": 0.0, "retning": "som",
        "tydelig": False, "vurdering": None}


def test_afvigelse_naar_mad_er_nul():
    # 900 kr. efter otte uger med 0 kr.: uden for alle uger og over minimumsforskellen
    assert rapport._afvigelse("takeaway_kr", 900, [0] * 8) == {
        "vaerdi": 900, "normal": 0.0, "normal_interval": [0, 0], "robust_z": None, "retning": "over",
        "tydelig": True, "vurdering": "skidt"}
    # 899 kr. efter uger med 900 kr.: uden for, men under minimumsforskellen
    assert rapport._afvigelse("cafe_bar_kr", 899, [900] * 8)["tydelig"] is False
    # inden for intervallet: ikke tydelig, selv om MAD er 0
    assert rapport._afvigelse("takeaway_kr", 50, [0, 0, 0, 0, 0, 0, 10, 20]) == {
        "vaerdi": 50, "normal": 0.0, "normal_interval": [0, 20], "robust_z": None, "retning": "over",
        "tydelig": False, "vurdering": None}
    # kolonne uden minimumsforskel og uden vurdering: blot uden for alle uger
    assert rapport._afvigelse("traening_pas", 5, [3, 3, 3, 3, 3, 2, 4, 3]) == {
        "vaerdi": 5, "normal": 3.0, "normal_interval": [2, 4], "robust_z": None, "retning": "over",
        "tydelig": True, "vurdering": None}


# --- afvigelse fra de nærmeste uger -------------------------------------------

def test_fra_normalen_lige_mange_naboer_paa_hver_side():
    alle = [{"x": v} for v in range(1, 11)]
    assert rapport._fra_normalen(alle, "x") == [None, None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, None, None]


def test_fra_normalen_springer_huller_over():
    alle = [{"x": v} for v in [5, 5, 9, 5, 5, None, 5, 1, 5, 5, 5]]
    assert rapport._fra_normalen(alle, "x") == [None, None, 4.0, 0, 0, None, 0, -4, 0.0, None, None]


# --- hele rapporten -------------------------------------------------------------

def _uger(n: int):
    conn = db.connect(":memory:")
    start = date(2026, 1, 5)
    for i in range(n):
        m = start + timedelta(days=7 * i)
        iso = m.isocalendar()
        soevn = 7 + ((i * 7) % 5) * 0.2
        db.gem_uge(conn, f"{iso.year}-W{iso.week:02d}", m.isoformat(), {
            "garmin_dage": 7, "soevn_timer_snit": round(soevn, 2),
            "takeaway_kr": round(1000 - 100 * soevn + (i % 3) * 10),
            "stress_snit": 25 + (i % 4), "traening_timer": 3 + (i % 2), "cafe_bar_kr": 0 if i != n - 1 else 900,
        })
    return conn, start + timedelta(days=7 * (n - 1))


def test_lav_afvigelser_og_sammenhaenge():
    conn, sidste = _uger(30)
    r = rapport.lav(conn, sidste)
    assert (r["uge"], r["mandag"], r["baseline"]) == ("2026-W31", "2026-07-27", "de 8 foregående uger")
    assert set(r["afvigelser"]) == {"garmin_dage", "traening_timer", "soevn_timer_snit", "stress_snit",
                                    "takeaway_kr", "cafe_bar_kr"}
    assert r["afvigelser"]["cafe_bar_kr"]["tydelig"] is True
    assert r["afvigelser"]["takeaway_kr"]["robust_z"] == -0.22
    s = {(h["x"], h["y"]): h for h in r["sammenhaenge"]}
    assert len(s) == len(rapport.HYPOTESER) == 11
    assert {k: s[("soevn_timer_snit", "takeaway_kr")][k] for k in ("n_uger", "rho", "p", "status")} == \
        {"n_uger": 26, "rho": -0.96, "p": 0.0002, "status": "stærk"}
    assert {k: s[("traening_timer", "stress_snit")][k] for k in ("rho", "p", "status")} == \
        {"rho": 0.41, "p": 0.0182, "status": "antydning"}
    assert s[("stress_snit", "takeaway_kr")]["status"] == "ingen sammenhæng"
    assert s[("cafe_bar_kr", "hrv_snit")]["status"] == "for få uger (0 af 18)"
    assert len(r["seneste_uger"]) == 8


def test_lav_med_for_faa_uger():
    conn, sidste = _uger(12)
    r = rapport.lav(conn, sidste)
    assert all(h["status"] == f"for få uger ({h['n_uger']} af 18)" for h in r["sammenhaenge"])


def test_lav_uden_data_for_ugen():
    conn, _ = _uger(3)
    assert rapport.lav(conn, date(2025, 1, 6)) == {"fejl": "ingen data for ugen der starter 2025-01-06"}
