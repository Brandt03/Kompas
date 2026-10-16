"""Overbliks statistik: afvigelser og sammenhænge.   python -m unittest discover -s tests"""
from __future__ import annotations

import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "overblik"))
from overblik import rapport  # noqa: E402


class Afvigelser(unittest.TestCase):
    def test_uge_der_skiller_sig_ud_fra_ens_uger(self):
        # Før gav MAD = 0 altid z = 0, så 900 kr. efter otte uger med 0 kr. aldrig blev markeret
        a = rapport._afvigelse("cafe_bar_kr", 900, [0] * 8)
        self.assertTrue(a["tydelig"])
        self.assertIsNone(a["robust_z"])
        self.assertEqual(a["vurdering"], "skidt")

    def test_samme_vaerdi_som_ens_uger_er_ikke_tydelig(self):
        a = rapport._afvigelse("cafe_bar_kr", 0, [0] * 8)
        self.assertFalse(a["tydelig"])
        self.assertEqual(a["robust_z"], 0.0)

    def test_uden_for_ugerne_naar_de_fleste_er_ens(self):
        a = rapport._afvigelse("cafe_bar_kr", 900, [0] * 7 + [200])
        self.assertTrue(a["tydelig"])
        self.assertIsNone(a["robust_z"])

    def test_inden_for_ugerne_er_ikke_tydelig(self):
        # Den gamle reserveskala gav 4 pas z = 3,2 efter uger med 2–4 pas
        hist = [3, 3, 3, 3, 3, 4, 2, 3]
        self.assertFalse(rapport._afvigelse("traening_pas", 4, hist)["tydelig"])
        self.assertTrue(rapport._afvigelse("traening_pas", 5, hist)["tydelig"])

    def test_lille_forskel_fra_ens_uger_er_ikke_tydelig(self):
        self.assertFalse(rapport._afvigelse("cafe_bar_kr", 899, [900] * 8)["tydelig"])
        self.assertFalse(rapport._afvigelse("cafe_bar_kr", 990, [900] * 7 + [950])["tydelig"])

    def test_almindelig_kolonne_som_foer(self):
        hist = [7.0, 7.3, 7.1, 7.4, 7.2, 6.9, 7.5, 7.2]
        self.assertTrue(rapport._afvigelse("soevn_timer_snit", 6.1, hist)["tydelig"])
        self.assertFalse(rapport._afvigelse("soevn_timer_snit", 7.25, hist)["tydelig"])

    def test_for_lidt_historik(self):
        self.assertIsNone(rapport._afvigelse("cafe_bar_kr", 900, [0, 0, 0]))


class Sammenhaenge(unittest.TestCase):
    def setUp(self):
        self.permutationer = rapport.PERMUTATIONER
        rapport.PERMUTATIONER = 400

    def tearDown(self):
        rapport.PERMUTATIONER = self.permutationer

    @staticmethod
    def _test(xs, ys):
        alle = [{"x": a, "y": b} for a, b in zip(xs, ys)]
        nx, ny = rapport._fra_normalen(alle, "x"), rapport._fra_normalen(alle, "y")
        par = [(a, b) for a, b in zip(nx, ny) if a is not None and b is not None]
        return rapport.spearman([a for a, _ in par], [b for _, b in par])

    def test_lineaer_udvikling_fjernes(self):
        alle = [{"x": 2.0 * i + 5} for i in range(20)]
        rest = [r for r in rapport._fra_normalen(alle, "x") if r is not None]
        self.assertTrue(all(abs(r) < 1e-9 for r in rest[4:-4]), "midten af en ret linje har ingen afvigelse")

    def test_faelles_saeson_er_ikke_en_sammenhaeng(self):
        # To serier, der kun deler en sæson: den gamle test kaldte det en stærk sammenhæng hver gang
        rng = random.Random(1)
        falske = 0
        for _ in range(40):
            xs = [3 * math.sin(2 * math.pi * i / 52) + rng.gauss(0, 1) for i in range(60)]
            ys = [3 * math.sin(2 * math.pi * i / 52) + rng.gauss(0, 1) for i in range(60)]
            rho, p = self._test(xs, ys)
            falske += p < 0.05 / len(rapport.HYPOTESER) and abs(rho) >= 0.3
        self.assertLessEqual(falske, 2)

    def test_aegte_sammenhaeng_findes(self):
        rng = random.Random(2)
        fundet = 0
        for _ in range(20):
            xs = [rng.gauss(0, 1) for _ in range(60)]
            ys = [0.6 * x + rng.gauss(0, 1) for x in xs]
            rho, p = self._test(xs, ys)
            fundet += p < 0.05 and rho >= 0.3
        self.assertGreaterEqual(fundet, 15)

    def test_minimum_giver_nok_blokke(self):
        self.assertGreaterEqual(rapport.MIN_UGER_KORRELATION // rapport.BLOK_UGER, 6)


if __name__ == "__main__":
    unittest.main()
