"""Coachens beregninger med kendte svar: TRIMP, ACWR, afvigelse fra grundniveauet og huller, der forbliver huller.
python -m unittest discover -s tests"""
from __future__ import annotations

import math
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

# Faste pulstal, så belastningen ikke afhænger af data; sættes før garmin_coach læser miljøet
os.environ.update({"GC_HR_MAX": "190", "GC_HR_REST": "50", "GC_SEX": "m",
                   "GC_DB": os.path.join(tempfile.mkdtemp(), "ubrugt.db")})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "coach"))
from garmin_coach import db, metrics  # noqa: E402

I_DAG = date.today()
I_GAAR = I_DAG - timedelta(days=1)
# 45 min med snitpuls 140 ved makspuls 190 og hvilepuls 50: Banister-TRIMP 63,6
PAS_TRIMP = 63.6


class Base(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(Path(tempfile.mkdtemp()) / "test.db")

    def tearDown(self):
        self.conn.close()

    def dag(self, d: date, **kol):
        db.upsert(self.conn, "daily", {"date": d.isoformat(), "resting_hr": 50, **kol}, pk=["date"])

    def pas(self, d: date, nr: int = 0):
        db.upsert(self.conn, "activities", {
            "activity_id": f"{d.isoformat()}-{nr}", "start_local": f"{d.isoformat()} 17:00:00", "date": d.isoformat(),
            "sport": "running", "name": "Tur", "duration_s": 45 * 60, "avg_hr": 140}, pk=["activity_id"])


class Trimp(unittest.TestCase):
    def test_kendte_vaerdier(self):
        ath = metrics.Athlete(hr_max=190, hr_rest=50, sex="m")
        self.assertEqual(metrics.banister_trimp(3600, 150, ath), 108.1)
        self.assertEqual(metrics.banister_trimp(3600, 150, metrics.Athlete(hr_max=190, hr_rest=50, sex="f")), 121.5)
        self.assertEqual(metrics.banister_trimp(45 * 60, 140, ath), PAS_TRIMP)

    def test_ingen_puls_giver_ingen_belastning(self):
        ath = metrics.Athlete(hr_max=190, hr_rest=50, sex="m")
        self.assertEqual(metrics.banister_trimp(3600, None, ath), 0.0)
        self.assertEqual(metrics.banister_trimp(3600, 45, ath), 0.0)   # under hvilepulsen
        self.assertEqual(metrics.banister_trimp(0, 150, ath), 0.0)


class Acwr(Base):
    def byg(self, sidste_dag: date, dobbelt_sidste_uge: bool = False):
        for i in range(35):
            d = sidste_dag - timedelta(days=i)
            self.dag(d)
            self.pas(d)
            if dobbelt_sidste_uge and i < 7:
                self.pas(d, 1)

    def test_jaevn_belastning_giver_1(self):
        self.byg(I_GAAR)
        self.dag(I_DAG)
        r = metrics.training_load(self.conn)
        self.assertEqual(r["beregnet_til_og_med"], I_GAAR.isoformat())
        self.assertEqual(r["akut_7d"], round(7 * PAS_TRIMP))
        self.assertEqual(r["acwr"], 1.0)

    def test_dobbelt_sidste_uge(self):
        # Akut 14 pas mod (21 + 14) / 4 pas pr. uge: 1,6. Den akutte uge indgår selv i de 28 dage.
        self.byg(I_GAAR, dobbelt_sidste_uge=True)
        self.dag(I_DAG)
        self.assertEqual(metrics.training_load(self.conn)["acwr"], 1.6)

    def test_gamle_data_giver_intet_tal(self):
        # Manglende dage ville ligne hviledage, så ACWR beregnes ikke
        self.byg(I_DAG - timedelta(days=5))
        r = metrics.training_load(self.conn)
        self.assertIsNone(r["acwr"])
        self.assertIsNone(r["kronisk_uge_snit_28d"])
        self.assertIn("sync", r["acwr_fortolkning"])

    def test_for_lidt_historik(self):
        for i in range(10):
            self.dag(I_GAAR - timedelta(days=i))
            self.pas(I_GAAR - timedelta(days=i))
        self.assertIsNone(metrics.training_load(self.conn)["acwr"])


class Grundniveau(Base):
    def byg_grundniveau(self):
        # 53 dage før de seneste 7: skiftevis 50 og 70 ms og én dag med 60, så snittet er 60
        for i in range(7, 60):
            n = i - 7
            self.dag(I_DAG - timedelta(days=i), hrv_last_night=60 if n == 52 else (50 if n % 2 else 70))

    def test_afvigelse_i_standardafvigelser(self):
        self.byg_grundniveau()
        for i in range(7):
            self.dag(I_DAG - timedelta(days=i), hrv_last_night=65)
        hrv = metrics.recovery(self.conn)["hrv"]
        self.assertEqual(hrv["baseline"], 60.0)
        self.assertEqual(hrv["baseline_datapunkter"], 53)
        self.assertEqual(hrv["afvigelse_sd"], round(5 / math.sqrt(5200 / 53), 2))

    def test_huller_er_huller_ikke_nul(self):
        # To nætter uden måling trækker ikke snittet ned: de er None, ikke 0
        self.byg_grundniveau()
        for i in range(7):
            self.dag(I_DAG - timedelta(days=i), hrv_last_night=None if i in (1, 4) else 65)
        hrv = metrics.recovery(self.conn)["hrv"]
        self.assertEqual(hrv["aktuel"], 65.0)
        self.assertEqual(hrv["aktuelle_datapunkter"], 5)

    def test_for_faa_maalinger_giver_ingen_afvigelse(self):
        self.byg_grundniveau()
        self.dag(I_DAG, hrv_last_night=80)
        self.dag(I_DAG - timedelta(days=1), hrv_last_night=80)
        hrv = metrics.recovery(self.conn)["hrv"]
        self.assertEqual(hrv["aktuelle_datapunkter"], 2)
        self.assertIsNone(hrv["afvigelse_sd"])


if __name__ == "__main__":
    unittest.main()
