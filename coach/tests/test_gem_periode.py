"""Opg. 5: gem-periode afviser en slutdato, der ikke er en fredag, og en start, der ikke er dagen efter
forrige endelige periodes slut. Gemte perioder rettes ikke."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from garmin_coach import site

VURDERING = {"resume": "En periode."}


@pytest.fixture(autouse=True)
def hurtige_tal(monkeypatch):
    # Tallene er ikke det, der testes her; datoerne er
    monkeypatch.setattr(site, "periode_rapport", lambda conn, s, e: {"start": s, "slut": e})


def _gemt(conn) -> list[tuple[str, str, str]]:
    return [(p["start"], p["slut"], p["status"]) for p in site.perioder(conn)]


def test_slut_paa_en_loerdag_afvises(conn):
    # En slut på en lørdag gør perioden skæv: 2026-09-12 → 2026-09-26
    with pytest.raises(ValueError, match="slut skal være en fredag, men 2026-09-26 er en lørdag"):
        site.ny_periode(conn, "2026-09-12", "2026-09-26", VURDERING)
    assert _gemt(conn) == []


def test_start_skal_vaere_dagen_efter_forrige_slut(conn):
    site.ny_periode(conn, "2026-09-12", "2026-09-25", VURDERING)
    with pytest.raises(ValueError, match=r"dagen efter forrige periodes slut \(2026-09-25\), altså 2026-09-26, ikke 2026-10-03"):
        site.ny_periode(conn, "2026-10-03", "2026-10-16", VURDERING)
    doc = site.ny_periode(conn, "2026-09-26", "2026-10-09", VURDERING)
    assert doc["status"] == "endelig"
    assert _gemt(conn) == [("2026-09-12", "2026-09-25", "endelig"), ("2026-09-26", "2026-10-09", "endelig")]


def test_foerste_periode_skal_starte_en_loerdag(conn):
    with pytest.raises(ValueError, match="start skal være en lørdag, men 2026-09-13 er en søndag"):
        site.ny_periode(conn, "2026-09-13", "2026-09-25", VURDERING)


def test_eksisterende_skaev_periode_rettes_ikke_og_kaeden_fortsaetter(conn):
    # Skæve perioder gemt før valideringen: 2026-09-12 → 2026-09-26 (lørdag) og 2026-09-27 → 2026-10-09
    for s, e in (("2026-09-12", "2026-09-26"), ("2026-09-27", "2026-10-09")):
        site.gem(conn, {"start": s, "slut": e, "status": "endelig", "vurdering": VURDERING})
    foer = _gemt(conn)
    with pytest.raises(ValueError):
        site.ny_periode(conn, "2026-10-11", "2026-10-23", VURDERING)
    site.ny_periode(conn, "2026-10-10", "2026-10-23", VURDERING)
    assert _gemt(conn)[:2] == foer  # de gamle står urørt
    assert _gemt(conn)[2] == ("2026-10-10", "2026-10-23", "endelig")


def test_periode_maa_ikke_gaa_ind_i_den_naeste(conn):
    for s, e in (("2026-09-12", "2026-09-25"), ("2026-10-10", "2026-10-23")):
        site.gem(conn, {"start": s, "slut": e, "status": "endelig", "vurdering": VURDERING})
    with pytest.raises(ValueError, match="går ind i den næste, der starter 2026-10-10"):
        site.ny_periode(conn, "2026-09-26", "2026-10-16", VURDERING)


def test_slut_foer_start_og_ugyldig_dato(conn):
    with pytest.raises(ValueError, match="ligger før start"):
        site.ny_periode(conn, "2026-09-26", "2026-09-25", VURDERING)
    with pytest.raises(ValueError, match="ÅÅÅÅ-MM-DD"):
        site.ny_periode(conn, "26/9", "2026-10-09", VURDERING)


def test_foreloebig_periode_maa_slutte_midt_i_perioden(conn):
    site.ny_periode(conn, "2026-09-12", "2026-09-25", VURDERING)
    doc = site.ny_periode(conn, "2026-09-26", "2026-10-01", VURDERING, "foreløbig")  # en torsdag
    assert doc["status"] == "foreløbig"
    with pytest.raises(ValueError, match="dagen efter forrige periodes slut"):
        site.ny_periode(conn, "2026-09-27", "2026-10-01", VURDERING, "foreløbig")


def test_cli_afviser_med_tydelig_besked_og_gemmer_intet(tmp_path):
    vurdering = tmp_path / "vurdering.json"
    vurdering.write_text(json.dumps(VURDERING))
    env = {**os.environ, "GC_DB": str(tmp_path / "cli.db"), "GC_SITE": str(tmp_path / "site")}
    r = subprocess.run([sys.executable, "-m", "garmin_coach.site", "gem-periode", "2026-09-12", "2026-09-26",
                        str(vurdering)], capture_output=True, text=True, env=env,
                       cwd=Path(__file__).resolve().parent.parent)
    assert r.returncode == 1
    assert "gem-periode: intet gemt. slut skal være en fredag, men 2026-09-26 er en lørdag" in r.stderr
    assert "Traceback" not in r.stderr and r.stdout == ""
    r = subprocess.run([sys.executable, "-m", "garmin_coach.site", "perioder"], capture_output=True, text=True,
                       env=env, cwd=Path(__file__).resolve().parent.parent)
    assert json.loads(r.stdout) == []
