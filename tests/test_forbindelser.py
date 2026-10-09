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
KARRIERE = "0 12 * * 1,4"  # mandag og torsdag kl. 12


def kl(dag, t, m=0):
    """Lokal tid i oktober 2026 (torsdag den 8. er en kørselsdag for KARRIERE)."""
    return datetime(2026, 10, dag, t, m, tzinfo=DK)


def rutine(sidst, cron=KARRIERE, slaaet_til=True):
    return {"jobagent-studiejob": {"navn": "Karriere", "cron": cron, "slaaet_til": slaaet_til,
                                   "sidst": sidst.astimezone(timezone.utc) if sidst else None}}


def status(rutiner, nu):
    punkter = forbindelser.claude({}, rutiner, nu=nu.astimezone(timezone.utc))
    return next(p for p in punkter if p["type"] == "Claude-rutine" and p["projekt"] == "Karriere")


class Rutinestatus(unittest.TestCase):
    def test_koerte_til_tiden(self):
        p = status(rutine(kl(8, 12, 5)), nu=kl(8, 15))
        self.assertEqual(p["status"], "ok")
        self.assertEqual(p["tekst"], "nye jobmatch · hver mandag og torsdag kl. 12.00")
        self.assertEqual(p["naeste"], "2026-10-12T10:00:00Z")

    def test_sprunget_over_advarer_med_den_glemte_tid(self):
        p = status(rutine(kl(5, 12, 3)), nu=kl(8, 16))
        self.assertEqual(p["status"], "advarsel")
        self.assertEqual(p["tekst"], "nye jobmatch · skulle have kørt torsdag kl. 12.00")

    def test_lige_over_tiden_koerer_om_lidt(self):
        p = status(rutine(kl(5, 12, 3)), nu=kl(8, 13))
        self.assertEqual(p["status"], "ok")
        self.assertEqual(p["tekst"], "nye jobmatch · kører om lidt")

    def test_ny_tidsplan_giver_ingen_falsk_advarsel(self):
        # Kørte onsdag efter den gamle plan; den nye plan havde sit første tidspunkt torsdag kl. 12
        p = status(rutine(kl(7, 9)), nu=kl(8, 16))
        self.assertEqual(p["status"], "ok")
        self.assertEqual(p["tekst"], "nye jobmatch · hver mandag og torsdag kl. 12.00")

    def test_slaaet_fra_viser_ingen_naeste_koersel(self):
        p = status(rutine(kl(5, 12, 3), slaaet_til=False), nu=kl(8, 16))
        self.assertEqual(p["status"], "advarsel")
        self.assertEqual(p["tekst"], "nye jobmatch · slået fra")
        self.assertNotIn("naeste", p)

    def test_mangler_i_appen(self):
        p = status({}, nu=kl(8, 16))
        self.assertEqual(p["status"], "fejl")
        self.assertEqual(p["tekst"], "findes ikke i Claude-appen")


if __name__ == "__main__":
    unittest.main()
