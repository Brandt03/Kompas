"""Siden Forbindelser: rutinestatus, claude(cfg, rutiner, nu), Skærmtids enheder, skaermtid_enheder(), kopien til
bærbaren, kopi_punkt(), og projekter på pause.   python -m unittest discover -s tests

Tidsplanerne er lokal tid, så testene kører i dansk tid uanset maskinen.
"""
import json
import os
import sys
import tempfile
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

    def test_slaaet_fra_har_sin_egen_hjaelp(self):
        p = status(rutine(kl(5, 12, 3), slaaet_til=False), nu=kl(8, 16))
        self.assertEqual(p["hjaelp"], "Rutinen er slået fra i Claude-appen. Slå den til under Rutiner (Kompas · Sprog), "
                                      "eller lad den være, hvis det er med vilje.")
        # Den, der skulle have kørt, beholder teksten om den glemte kørsel
        p = status(rutine(kl(5, 12, 3)), nu=kl(8, 16))
        self.assertIn("en glemt kørsel tages", p["hjaelp"])

    def test_mangler_i_appen(self):
        p = status({}, nu=kl(8, 16))
        self.assertEqual(p["status"], "fejl")
        self.assertEqual(p["tekst"], "findes ikke i Claude-appen")


class Enheder(unittest.TestCase):
    def enheder(self, enheder, nu):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"enheder": enheder}, f)
        self.addCleanup(os.unlink, f.name)
        return {p["navn"]: p for p in forbindelser.skaermtid_enheder(f.name, nu=nu.astimezone(timezone.utc))}

    def test_to_hele_dage_uden_data_advarer(self):
        p = self.enheder([{"navn": "Mac", "kendt": True, "sidst": "2026-10-21T08:00:00+02:00"},
                          {"navn": "Telefon", "kendt": True, "sidst": "2026-10-20T23:59:00+02:00"},
                          {"navn": "Stationær", "kendt": True, "sidst": "2026-10-18T20:02:45+02:00"}], kl(21, 14))
        self.assertEqual(p["Skærmtid · Mac"]["status"], "ok")
        self.assertEqual(p["Skærmtid · Telefon"]["status"], "ok")
        self.assertEqual((p["Skærmtid · Stationær"]["status"], p["Skærmtid · Stationær"]["tekst"]), ("advarsel", "ingen data i 3 dage"))

    def test_sjaelden_enhed_er_info_ikke_advarsel(self):
        p = self.enheder([{"navn": "Stationær", "kendt": True, "sjaelden": True, "sidst": "2026-10-18T20:02:45+02:00"}], kl(21, 14))
        self.assertEqual((p["Skærmtid · Stationær"]["status"], p["Skærmtid · Stationær"]["tekst"]), ("info", "bruges sjældent · ingen data i 3 dage"))
        self.assertNotIn("hjaelp", p["Skærmtid · Stationær"])

    def test_aldrig_sendt_og_ukendt(self):
        p = self.enheder([{"navn": "Bærbar", "kendt": True, "sidst": None},
                          {"navn": "ny-pc", "kendt": False, "sidst": "2026-10-21T08:00:00+02:00"}], kl(21, 14))
        self.assertEqual(p["Skærmtid · Bærbar"]["status"], "advarsel")
        self.assertEqual(p["Skærmtid · ny-pc"]["status"], "info")

    def test_mangler_filen(self):
        punkter = forbindelser.skaermtid_enheder("/findes/ikke.json", nu=kl(21, 14).astimezone(timezone.utc))
        self.assertEqual([p["status"] for p in punkter], ["fejl"])



class Kopi(unittest.TestCase):
    """kopi.json skrives også, når noget ikke kunne hentes; trinnet `kopi` i opdater-status.json afgør."""
    def kopi(self, fejl, minutter_gammel, nu=kl(21, 14)):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{}")
        self.addCleanup(os.unlink, f.name)
        t = nu.timestamp() - minutter_gammel * 60
        os.utime(f.name, (t, t))
        return forbindelser.kopi_punkt(fejl, f.name, nu=nu.astimezone(timezone.utc))

    def test_frisk_og_trinnet_lykkedes(self):
        p = self.kopi(set(), 10)
        self.assertEqual(p["status"], "ok")
        self.assertNotIn("hjaelp", p)

    def test_frisk_men_trinnet_fejlede_advarer_og_peger_paa_loggen(self):
        p = self.kopi({"kopi"}, 10)
        self.assertEqual((p["status"], p["tekst"]), ("advarsel", "bygget, men sidste kørsel fejlede"))
        self.assertIn("`kopi:`", p["hjaelp"])
        self.assertIn("~/.kompas/opdater.log", p["hjaelp"])

    def test_andre_trin_der_fejlede_roerer_ikke_kopien(self):
        self.assertEqual(self.kopi({"skaermtid", "garmin"}, 10)["status"], "ok")

    def test_gammel_kopi_advarer(self):
        p = self.kopi(set(), 60)
        self.assertEqual((p["status"], p["tekst"]), ("advarsel", "ikke bygget den sidste halve time"))

    def test_ingen_kopi(self):
        p = forbindelser.kopi_punkt(set(), "/findes/ikke/kopi.json", nu=kl(21, 14).astimezone(timezone.utc))
        self.assertEqual(p["status"], "fejl")



class Pause(unittest.TestCase):
    """Et projekt under `pause` i projekter.json: dets punkter vises ikke; en gruppe uden punkter forsvinder."""

    def test_projekt_paa_pause_vises_ikke(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            fil = Path(d) / "projekter.json"
            fil.write_text(json.dumps({"manifester": [], "pause": [{"projekt": "Sprog", "siden": "2026-10-25", "hvorfor": "Bruges ikke."}]}))
            pause = forbindelser.pausede(fil)
        self.assertEqual(pause["Sprog"]["siden"], "2026-10-25")
        grupper = [{"titel": "Claude", "punkter": [
                       forbindelser.punkt("Sprog", "Claude-rutine", "Sprog", "advarsel", "nye sprogkort og ugens tekst · slået fra"),
                       forbindelser.punkt("Studie", "Claude-rutine", "Studie", "ok", "køreplan")]},
                   {"titel": "Kun Sprog", "punkter": [forbindelser.punkt("Sprog-server", "LaunchAgent", "Sprog", "ok", "svarer")]}]
        ud = forbindelser.paa_pause(grupper, pause)
        self.assertEqual([g["titel"] for g in ud], ["Claude"])
        self.assertEqual([p["navn"] for p in ud[0]["punkter"]], ["Studie"])

    def test_ingen_fil_ingen_pause(self):
        from pathlib import Path
        self.assertEqual(forbindelser.pausede(Path("/findes/ikke.json")), {})


if __name__ == "__main__":
    unittest.main()
