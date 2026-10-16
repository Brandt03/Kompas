"""Rutinestatus på siden Forbindelser: claude(cfg, rutiner, nu).   python -m unittest discover -s tests

Tidsplanerne er lokal tid, så testene kører i dansk tid uanset maskinen.
"""
import os
import sys
import time
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

os.environ["TZ"] = "Europe/Copenhagen"
time.tzset()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin"))
import forbindelser  # noqa: E402

DK = ZoneInfo("Europe/Copenhagen")
PLAN = "0 12 * * 1,4"  # en testplan: mandag og torsdag kl. 12


def kl(dag, t, m=0):
    """Lokal tid i oktober 2026 (torsdag den 8. er en kørselsdag i PLAN)."""
    return datetime(2026, 10, dag, t, m, tzinfo=DK)


def rutine(sidst, cron=PLAN, slaaet_til=True, oprettet=None):
    return {"sprog-ugen": {"navn": "Sprog", "cron": cron, "slaaet_til": slaaet_til,
                           "sidst": sidst.astimezone(timezone.utc) if sidst else None,
                           "oprettet": oprettet.astimezone(timezone.utc) if oprettet else None}}


def status(rutiner, nu):
    punkter = forbindelser.claude({}, rutiner, nu=nu.astimezone(timezone.utc))
    return next(p for p in punkter if p["type"] == "Claude-rutine" and p["projekt"] == "Sprog")


class Rutinestatus(unittest.TestCase):
    def test_koerte_til_tiden(self):
        p = status(rutine(kl(8, 12, 5)), nu=kl(8, 15))
        self.assertEqual(p["status"], "ok")
        self.assertEqual(p["tekst"], "nye sprogkort og ugens tekst · hver mandag og torsdag kl. 12.00")
        self.assertEqual(p["naeste"], "2026-10-12T10:00:00Z")

    def test_sprunget_over_advarer_med_den_glemte_tid(self):
        p = status(rutine(kl(5, 12, 3)), nu=kl(8, 16))
        self.assertEqual(p["status"], "advarsel")
        self.assertEqual(p["tekst"], "nye sprogkort og ugens tekst · skulle have kørt torsdag kl. 12.00")

    def test_lige_over_tiden_koerer_om_lidt(self):
        p = status(rutine(kl(5, 12, 3)), nu=kl(8, 13))
        self.assertEqual(p["status"], "ok")
        self.assertEqual(p["tekst"], "nye sprogkort og ugens tekst · kører om lidt")

    def test_ny_tidsplan_giver_ingen_falsk_advarsel(self):
        # Kørte onsdag efter den gamle plan; den nye plan havde sit første tidspunkt torsdag kl. 12
        p = status(rutine(kl(7, 9)), nu=kl(8, 16))
        self.assertEqual(p["status"], "ok")
        self.assertEqual(p["tekst"], "nye sprogkort og ugens tekst · hver mandag og torsdag kl. 12.00")

    def test_ny_rutine_der_ikke_har_koert_endnu(self):
        # Oprettet fredag; den forrige planlagte tid (torsdag) var før, så intet er sprunget over
        p = status(rutine(None, oprettet=kl(9, 22)), nu=kl(9, 22, 5))
        self.assertEqual(p["status"], "ok")
        # Men oprettet før torsdag og aldrig kørt: sprunget over
        p = status(rutine(None, oprettet=kl(7, 9)), nu=kl(8, 16))
        self.assertEqual(p["status"], "advarsel")

    def test_slaaet_fra_viser_ingen_naeste_koersel(self):
        p = status(rutine(kl(5, 12, 3), slaaet_til=False), nu=kl(8, 16))
        self.assertEqual(p["status"], "advarsel")
        self.assertEqual(p["tekst"], "nye sprogkort og ugens tekst · slået fra")
        self.assertNotIn("naeste", p)

    def test_mangler_i_appen(self):
        p = status({}, nu=kl(8, 16))
        self.assertEqual(p["status"], "fejl")
        self.assertEqual(p["tekst"], "findes ikke i Claude-appen")


if __name__ == "__main__":
    unittest.main()
