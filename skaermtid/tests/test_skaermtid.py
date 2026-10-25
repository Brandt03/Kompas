"""Tests for beregningen i skaermtid.py, uden ActivityWatch:

    python3 -m unittest discover -s tests      (fra skaermtid/)

Begivenhederne er lavet her; tiderne er lokal dansk tid, skrevet som UTC i oktober 2026 (UTC+2).
"""
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import skaermtid  # noqa: E402

DK = ZoneInfo("Europe/Copenhagen")
# Eksemplets regler (regler.example.json), ikke dine egne i regler.json og ikke dine valg i valg.json, så testene
# ikke afhænger af, hvad der står i dine regler eller er valgt på siden
EKSEMPEL = skaermtid.HER / "regler.example.json"
CFG = skaermtid.laes_regler(EKSEMPEL, valg_sti=Path("/findes/ikke"))
# Testene er skrevet til døgnskifte kl. 4 og sen skærmtid fra kl. 23; de holder, uanset hvad regler.json står på
CFG["doegn_skifter"], CFG["sen_fra"] = "04:00", "23:00"
NU = datetime(2026, 10, 18, 12, 0, tzinfo=DK)


def kl(dag, t, m=0):
    return datetime(2026, 10, dag, t, m, tzinfo=DK).astimezone(timezone.utc)


def ev(start, minutter, **data):
    return {"timestamp": start.isoformat(), "duration": minutter * 60, "data": data}


def vindue(start, minutter, app, title=""):
    return ev(start, minutter, app=app, title=title)


def aktiv(start, minutter):
    return ev(start, minutter, status="not-afk")


def dag(doc, d):
    return next(x for x in doc["dage"] if x["dato"] == d)


class Kategorier(unittest.TestCase):
    def k(self, app=None, pakke=None, dom=None, sti=None, titel=None):
        return skaermtid.kategoriser(CFG, app, pakke, dom, sti, titel)

    def test_app_paa_mac_windows_og_android(self):
        self.assertEqual(self.k(app="Goodnotes"), "Studie")
        self.assertEqual(self.k(app="Instagram", pakke="com.instagram.android"), "Sociale medier")
        self.assertEqual(self.k(app="Discord"), "Spil")
        self.assertEqual(self.k(app="Claude"), "Egne projekter")
        self.assertEqual(self.k(app="Lommeregner"), "Ukategoriseret")

    def test_nyheder_indkoeb_og_hverdag(self):
        self.assertEqual(self.k(app="DR Nyheder", pakke="dk.dr.drnyheder"), "Nyheder")
        self.assertEqual(self.k(app="Microsoft Edge", dom="www.dr.dk", sti="/nyheder/indland"), "Nyheder")
        self.assertEqual(self.k(app="Microsoft Edge", dom="www.dr.dk", sti="/drtv/serie/1"), "Video & streaming")
        self.assertEqual(self.k(app="DBA", pakke="dk.dba.android"), "Indkøb")
        self.assertEqual(self.k(app="Maps", pakke="com.google.android.apps.maps"), "Hverdag")
        # "arc" i searchbox og "hbo" i googlequicksearchbox må ikke gøre Google-appen til browser eller video
        self.assertEqual(self.k(app="Google", pakke="com.google.android.googlequicksearchbox"), "Ukategoriseret")
        self.assertIsNone(CFG["_browser"].search("com.google.android.googlequicksearchbox"))

    def test_domaene_slaar_browserens_navn(self):
        self.assertEqual(self.k(app="Microsoft Edge", dom="www.youtube.com", sti="/watch"), "Video & streaming")
        self.assertEqual(self.k(app="msedge.exe", dom="www.reddit.com", sti="/"), "Sociale medier")
        self.assertEqual(self.k(app="Microsoft Edge", dom="kompas.localhost", sti="/#/studie/"), "Studie")
        self.assertEqual(self.k(app="Microsoft Edge", dom="kompas.localhost", sti="/#/form/uge.html"), "Form & fokus")
        self.assertEqual(self.k(app="Microsoft Edge", dom="kompas.localhost", sti="/"), "Egne projekter")

    def test_titel_kun_uden_adresse(self):
        self.assertEqual(self.k(app="Microsoft Edge", titel="Katte - YouTube"), "Video & streaming")
        # En kendt adresse overtrumfer titlen, også når titlen nævner YouTube
        self.assertEqual(self.k(app="Microsoft Edge", dom="canvas.instructure.com", sti="/", titel="YouTube"), "Studie")
        self.assertEqual(self.k(app="Microsoft Edge", titel="Ny fane"), "Ukategoriseret")

    def test_programregel_slaar_titelregel_i_tidligere_kategori(self):
        # Titel alene er den svageste slags regel og prøves først, når ingen regel med program, side eller sti passer,
        # uanset kategoriernes rækkefølge: Mail med "Moodle" i titlen er Kommunikation (app), ikke Studie (titel)
        self.assertEqual(self.k(app="Mail", titel="Besked fra Moodle"), "Kommunikation")
        self.assertEqual(self.k(app="Terminal", titel="make sure tests pass"), "Egne projekter")
        self.assertEqual(self.k(app="Claude", titel="duolingo-eksport"), "Egne projekter")
        # Uden en programregel gælder titlen stadig, og en side med titel i samme regel kræver begge
        self.assertEqual(self.k(app="Finder", titel="Canvas uploads"), "Studie")
        self.assertEqual(self.k(app="Microsoft Edge", titel="Katte - YouTube"), "Video & streaming")
        self.assertEqual(skaermtid.kategori_og_kilde(CFG, "Mail", None, None, None, "Moodle")[1], "app")
        self.assertEqual(skaermtid.kategori_og_kilde(CFG, "Finder", None, None, None, "Moodle")[1], "titel")

    def test_domaene_og_sti(self):
        self.assertEqual(skaermtid.domaene_og_sti("https://kompas.localhost/#/studie/"), ("kompas.localhost", "/#/studie/"))
        self.assertEqual(skaermtid.domaene_og_sti("https://WWW.YouTube.com/watch?v=1"), ("www.youtube.com", "/watch?v=1"))
        self.assertEqual(skaermtid.domaene_og_sti(None), (None, None))
        self.assertEqual(skaermtid.domaene_og_sti("about:blank"), (None, None))


class Doegn(unittest.TestCase):
    def test_nat_hoerer_til_aftenens_dag_og_er_sen(self):
        dele = list(skaermtid.stykker(kl(17, 22, 30), kl(18, 1, 0), CFG))
        self.assertEqual([(d.isoformat(), sen, round((b - a).total_seconds() / 60)) for a, b, d, sen in dele],
                         [("2026-10-17", False, 30), ("2026-10-17", True, 120)])

    def test_doegnet_skifter_kl_4(self):
        dele = list(skaermtid.stykker(kl(18, 3, 30), kl(18, 4, 30), CFG))
        self.assertEqual([(d.isoformat(), sen) for _, _, d, sen in dele], [("2026-10-17", True), ("2026-10-18", False)])


class Beregning(unittest.TestCase):
    def test_kun_aktiv_tid_paa_computer(self):
        raa = {"macbook.local": {"window": [vindue(kl(17, 10), 60, "Goodnotes")],
                                 "afk": [aktiv(kl(17, 10), 20), aktiv(kl(17, 10, 40), 10)], "web": [], "sidst": None}}
        doc = skaermtid.beregn(raa, CFG, date(2026, 10, 17), date(2026, 10, 18), NU)
        d = dag(doc, "2026-10-17")
        self.assertEqual(d["timer"], 0.5)
        self.assertEqual(d["enheder"]["Mac"]["kategorier"], {"Studie": 0.5})
        self.assertEqual(dag(doc, "2026-10-18")["timer"], 0)

    def test_telefon_uden_afk_taeller_alt(self):
        raa = {"Pixel": {"window": [ev(kl(17, 20), 30, app="Instagram", package="com.instagram.android")],
                           "afk": None, "web": [], "sidst": "2026-10-17T20:30:00+02:00"}}
        doc = skaermtid.beregn(raa, CFG, date(2026, 10, 17), date(2026, 10, 17), NU)
        self.assertEqual(dag(doc, "2026-10-17")["enheder"]["Pixel"]["kategorier"], {"Sociale medier": 0.5})
        # En vært, der ikke står i regler.json, vises som ukendt enhed med sit værtsnavn
        ukendt = next(e for e in doc["enheder"] if e["navn"] == "Pixel")
        self.assertFalse(ukendt["kendt"])
        self.assertEqual([e["navn"] for e in doc["enheder"]][:3], ["Mac", "Stationær", "Telefon"])

    def test_slags_afgoer_telefon_og_computer_uden_afk_advarer(self):
        # Stationær er computer i regler.json: uden afk-data tæller dens vinduer ikke, og siden får besked.
        # Pixel står ikke i regler.json og har ingen afk-bucket, så den er telefon: alt tæller, også korte tjek.
        raa = {"pc-stue": {"window": [vindue(kl(17, 10), 60, "Goodnotes")], "afk": None, "web": [], "sidst": None},
               "Pixel": {"window": [ev(kl(17, 20), 0.5, app="Instagram", package="com.instagram.android")],
                           "afk": None, "web": [], "sidst": None}}
        doc = skaermtid.beregn(raa, CFG, date(2026, 10, 17), date(2026, 10, 17), NU)
        d = dag(doc, "2026-10-17")
        self.assertNotIn("Stationær", d["enheder"])
        self.assertEqual(d["enheder"]["Pixel"]["kategorier"], {"Sociale medier": 0.01})
        self.assertEqual(d["tjek"], {"aabninger": 1, "korte": 1, "oplaasninger": 0})
        e = {x["navn"]: x for x in doc["enheder"]}
        self.assertTrue(e["Stationær"]["afk_mangler"])
        self.assertFalse(e["Pixel"]["afk_mangler"])
        self.assertEqual([x["navn"] for x in doc["enhedsside"]["enheder"] if x["telefon"]], ["Pixel"])
        # En telefon med slags i regler.json er telefon, selv om der skulle ligge en afk-bucket
        raa = {"telefon": {"window": [vindue(kl(17, 10), 30, "Instagram")], "afk": [], "web": [], "sidst": None}}
        doc = skaermtid.beregn(raa, CFG, date(2026, 10, 17), date(2026, 10, 17), NU)
        self.assertEqual(dag(doc, "2026-10-17")["enheder"]["Telefon"]["timer"], 0.5)
        self.assertFalse(next(x for x in doc["enheder"] if x["navn"] == "Telefon")["afk_mangler"])

    def test_forloeb_i_kvarterer_med_stoerste_kategori(self):
        # Instagram 17.10–17.40 rammer kvartererne 17.00 (5 min), 17.15 og 17.30; 2 min kl. 18 er under grænsen
        raa = {"telefon": {"window": [vindue(kl(17, 17, 10), 30, "Instagram"), vindue(kl(17, 18, 0), 2, "Instagram")],
                              "afk": [], "web": [], "sidst": None}}
        doc = skaermtid.beregn(raa, CFG, date(2026, 10, 16), date(2026, 10, 17), NU)
        self.assertEqual(dag(doc, "2026-10-17")["forloeb"], [{"start": "2026-10-17T17:00+02:00", "slut": "2026-10-17T17:45+02:00",
                                                                "kategori": "Sociale medier", "gruppe": "Passiv"}])
        # Den 16. er før de første data og står derfor ikke med
        self.assertEqual([x["dato"] for x in doc["dage"]], ["2026-10-17"])

    def test_to_computere_samtidig_taeller_en_gang(self):
        # Som mandag morgen: Mac og bærbar i brug 10.00–11.00 på samme tid, Mac alene 11.00–11.30.
        # I alt er 1,5 t, ikke 2,5; den fælles time deles ligeligt; hver enhed beholder sin fulde tid
        raa = {"macbook.local": {"window": [vindue(kl(17, 10), 90, "Goodnotes")], "afk": [aktiv(kl(17, 10), 90)],
                                 "web": [], "sidst": None},
               "baerbar": {"window": [vindue(kl(17, 10), 60, "Claude")], "afk": [aktiv(kl(17, 10), 60)],
                           "web": [], "sidst": None}}
        doc = skaermtid.beregn(raa, CFG, date(2026, 10, 17), date(2026, 10, 17), NU)
        d = dag(doc, "2026-10-17")
        self.assertEqual((d["timer"], d["samtidig_timer"]), (1.5, 1.0))
        self.assertEqual(d["kategorier"], {"Studie": 1.0, "Egne projekter": 0.5})
        self.assertEqual({e: v["timer"] for e, v in d["enheder"].items()}, {"Mac": 1.5, "Bærbar": 1.0})
        self.assertEqual(sum(d["grupper"].values()), d["timer"])
        p = doc["perioder"]["idag"]
        self.assertEqual((p["timer"], p["samtidig_timer"]), (1.5, 1.0))
        self.assertEqual({a["app"]: a["timer"] for a in p["programmer"]}, {"Goodnotes": 1.0, "Claude": 0.5})

    def test_telefon_vinder_over_computer(self):
        # Instagram på telefonen 10.10–10.20, mens Goodnotes er aktiv på Mac'en 10.00–10.30: de ti minutter er
        # Instagram, ikke begge dele. Den samtidige tid står stadig under enhederne
        raa = {"macbook.local": {"window": [vindue(kl(17, 10), 30, "Goodnotes")], "afk": [aktiv(kl(17, 10), 30)],
                                 "web": [], "sidst": None},
               "telefon": {"window": [ev(kl(17, 10, 10), 10, app="Instagram", package="com.instagram.android")],
                              "afk": None, "web": [], "sidst": None}}
        doc = skaermtid.beregn(raa, CFG, date(2026, 10, 17), date(2026, 10, 17), NU)
        d = dag(doc, "2026-10-17")
        self.assertEqual((d["timer"], d["samtidig_timer"]), (0.5, 0.17))
        self.assertEqual(d["kategorier"], {"Studie": 0.33, "Sociale medier": 0.17})
        self.assertEqual({e: v["timer"] for e, v in d["enheder"].items()}, {"Mac": 0.5, "Telefon": 0.17})

    def test_afk_maaler_der_stopper_advarer(self):
        # afk-måleren dør kl. 22.30, vinduerne kører videre. Tiden derefter tæller ikke, og siden får
        # tidspunktet; en halv times forskel er normal og advarer ikke
        raa = {"macbook.local": {"window": [vindue(kl(17, 22), 30, "Goodnotes"), vindue(kl(18, 10), 60, "Goodnotes")],
                                 "afk": [aktiv(kl(17, 22), 30)], "web": [], "sidst": None}}
        doc = skaermtid.beregn(raa, CFG, date(2026, 10, 17), date(2026, 10, 18), NU)
        mac = next(x for x in doc["enheder"] if x["navn"] == "Mac")
        self.assertEqual(mac["afk_stoppet"], "2026-10-17T22:30:00+02:00")
        self.assertFalse(mac["afk_mangler"])
        self.assertEqual(dag(doc, "2026-10-18")["timer"], 0)
        raa["macbook.local"]["window"] = [vindue(kl(17, 22), 60, "Goodnotes")]
        doc = skaermtid.beregn(raa, CFG, date(2026, 10, 17), date(2026, 10, 18), NU)
        self.assertIsNone(next(x for x in doc["enheder"] if x["navn"] == "Mac")["afk_stoppet"])

    def test_browser_deles_efter_faner(self):
        raa = {"macbook.local": {
            "window": [vindue(kl(17, 10), 30, "Microsoft Edge", "Katte - YouTube")],
            "afk": [aktiv(kl(17, 10), 30)],
            "web": [ev(kl(17, 10), 10, url="https://www.youtube.com/watch?v=1"),
                    ev(kl(17, 10, 10), 10, url="https://canvas.instructure.com/courses/1")],
            "sidst": None}}
        doc = skaermtid.beregn(raa, CFG, date(2026, 10, 17), date(2026, 10, 17), NU)
        k = dag(doc, "2026-10-17")["enheder"]["Mac"]["kategorier"]
        # 10 min YouTube, 10 min Canvas, 10 min uden adresse -> titlen siger YouTube
        self.assertEqual(k, {"Studie": 0.17, "Video & streaming": 0.33})
        apps = {(a["app"], a["domaene"]): a["kategori"] for a in doc["stoerste"]}
        self.assertEqual(apps[("Microsoft Edge", "www.youtube.com")], "Video & streaming")
        self.assertEqual(apps[("Microsoft Edge", None)], "Video & streaming")

    def test_browser_uden_adresse_deles_efter_kategori(self):
        # Samme program uden adresse i to kategorier: YouTube efter titlen og en ny fane uden regel
        raa = {"macbook.local": {
            "window": [vindue(kl(17, 10), 10, "Microsoft Edge", "Katte - YouTube"), vindue(kl(17, 10, 10), 20, "Microsoft Edge", "Ny fane")],
            "afk": [aktiv(kl(17, 10), 30)], "web": [], "sidst": None}}
        doc = skaermtid.beregn(raa, CFG, date(2026, 10, 17), date(2026, 10, 17), NU)
        self.assertEqual([(a["app"], a["kategori"], a["timer"]) for a in doc["stoerste"]],
                         [("Microsoft Edge", "Ukategoriseret", 0.33), ("Microsoft Edge", "Video & streaming", 0.17)])
        # Browsertid uden adresse kan ikke vælges, så den står for sig pr. enhed og ikke under Mangler en kategori
        self.assertEqual(doc["ukategoriseret"], [])
        self.assertEqual(doc["ukategoriseret_antal"], 0)
        self.assertEqual(doc["browser_uden_adresse"], {"Mac": [{"program": "Microsoft Edge", "timer": 0.33}]})

    def test_browser_uden_adresse_er_enhedens_fulde_tid(self):
        # Telefonens Edge uden adresse samtidig med Mac'ens: hver enhed står med sin fulde tid, også når telefonen får
        # den samtidige tid i alt
        c = dict(CFG)
        c["enheder"] = [{"navn": "Mac", "vaert": "macbook.local", "slags": "computer"},
                        {"navn": "Telefon", "vaert": ["telefon"], "slags": "telefon"}]
        raa = {"macbook.local": {"window": [vindue(kl(17, 10), 30, "Microsoft Edge", "Ny fane"), vindue(kl(17, 10, 30), 10, "Lommeregner")],
                                 "afk": [aktiv(kl(17, 10), 40)], "web": [], "sidst": None},
               "telefon": {"window": [ev(kl(17, 10), 15, app="Edge", package="com.microsoft.emmx")],
                              "afk": None, "web": [], "sidst": None}}
        doc = skaermtid.beregn(raa, c, date(2026, 10, 17), date(2026, 10, 17), NU)
        self.assertEqual(doc["browser_uden_adresse"], {"Mac": [{"program": "Microsoft Edge", "timer": 0.5}],
                                                       "Telefon": [{"program": "Edge", "timer": 0.25}]})
        self.assertEqual([a["app"] for a in doc["ukategoriseret"]], ["Lommeregner"])
        self.assertFalse(any(a["browser"] for a in doc["ukategoriseret"]))

    def test_sen_skaermtid_og_uger(self):
        raa = {"macbook.local": {"window": [vindue(kl(17, 22, 30), 120, "Lommeregner")],
                                 "afk": [aktiv(kl(17, 22, 30), 120)], "web": [], "sidst": None}}
        doc = skaermtid.beregn(raa, CFG, date(2026, 10, 12), date(2026, 10, 18), NU)
        d = dag(doc, "2026-10-17")
        self.assertEqual((d["timer"], d["sen_timer"]), (2.0, 1.5))
        self.assertEqual(dag(doc, "2026-10-18")["timer"], 0)
        # Dagene før den første dag med data står ikke med (uden data er tiden ukendt, ikke 0)
        self.assertEqual([x["dato"] for x in doc["dage"]], ["2026-10-17", "2026-10-18"])
        self.assertEqual(len(doc["uger"]), 1)
        self.assertEqual(doc["uger"][0]["uge"], "2026-W42")
        self.assertEqual(doc["uger"][0]["sen_timer"], 1.5)
        self.assertEqual(doc["ukategoriseret"][0]["app"], "Lommeregner")
        p = doc["perioder"]
        self.assertEqual((p["idag"]["timer"], p["uge"]["timer"], p["fire_uger"]["timer"]), (0, 2.0, 2.0))
        self.assertEqual(p["uge"]["ukategoriseret_andel"], 1.0)
        self.assertIsNone(p["idag"]["ukategoriseret_andel"])
        self.assertEqual(p["uge"]["enheder"], {"Mac": 2.0})

    def test_laaseskaerm_taeller_ikke(self):
        raa = {"macbook.local": {"window": [vindue(kl(17, 10), 10, "loginwindow"), vindue(kl(17, 10, 10), 5, "UserNotificationCenter"),
                                            vindue(kl(17, 10, 15), 5, "Lommeregner")],
                                 "afk": [aktiv(kl(17, 10), 20)], "web": [], "sidst": None}}
        doc = skaermtid.beregn(raa, CFG, date(2026, 10, 17), date(2026, 10, 17), NU)
        self.assertEqual(dag(doc, "2026-10-17")["timer"], 0.08)
        self.assertEqual([a["app"] for a in doc["stoerste"]], ["Lommeregner"])

    def test_titler_skrives_aldrig(self):
        raa = {"macbook.local": {"window": [vindue(kl(17, 10), 10, "Microsoft Edge", "HEMMELIG TITEL")],
                                 "afk": [aktiv(kl(17, 10), 10)], "web": [], "sidst": None}}
        doc = skaermtid.beregn(raa, CFG, date(2026, 10, 17), date(2026, 10, 17), NU)
        self.assertNotIn("HEMMELIG", __import__("json").dumps(doc))



class Enheder(unittest.TestCase):
    def cfg(self):
        c = dict(CFG)
        c["enheder"] = [{"navn": "Mac", "vaert": "macbook.local", "slags": "computer"},
                        {"navn": "Stationær", "vaert": ["desktop-alex", "aaaa-bbbb"], "slags": "computer"},
                        {"navn": "Telefon", "vaert": None, "slags": "telefon"}]
        return c

    def test_vaert_kan_vaere_liste(self):
        c = self.cfg()
        self.assertEqual(skaermtid._enhed(c, "macbook.local"), "Mac")
        self.assertEqual(skaermtid._enhed(c, "DESKTOP-ALEX"), "Stationær")
        self.assertEqual(skaermtid._enhed(c, "aaaa-bbbb"), "Stationær")
        self.assertEqual(skaermtid._enhed(c, "1234-ukendt"), "1234-ukendt")

    def test_faner_under_enheds_id_klippes_mod_vinduerne(self):
        # Vinduer og afk under værtsnavnet, browserfanerne under enheds-id'et: samme enhed, så YouTube findes
        c = self.cfg()
        raa = {"desktop-alex": {"window": [vindue(kl(17, 20), 60, "msedge.exe", "Ny fane")],
                                "afk": [aktiv(kl(17, 20), 60)], "web": [], "sidst": kl(17, 21).isoformat()},
               "aaaa-bbbb": {"window": [], "afk": None, "sidst": kl(17, 20, 30).isoformat(),
                             "web": [ev(kl(17, 20), 30, url="https://www.youtube.com/watch?v=1")]}}
        doc = skaermtid.beregn(raa, c, date(2026, 10, 17), date(2026, 10, 17), NU)
        d = dag(doc, "2026-10-17")
        self.assertEqual(d["enheder"], {"Stationær": {"timer": 1.0, "sen_timer": 0.0,
                                                      "kategorier": {"Video & streaming": 0.5, "Ukategoriseret": 0.5}}})
        st = next(e for e in doc["enheder"] if e["navn"] == "Stationær")
        self.assertEqual((st["sidst"], st["kendt"], st["vaert"]), (kl(17, 21).isoformat(), True, ["desktop-alex", "aaaa-bbbb"]))
        self.assertEqual([e["navn"] for e in doc["enheder"] if not e["kendt"]], [])

    def test_sjaelden_fra_regler_kommer_med_i_enheder(self):
        c = self.cfg()
        c["enheder"][1] = {**c["enheder"][1], "sjaelden": True}
        doc = skaermtid.beregn({}, c, date(2026, 10, 17), date(2026, 10, 17), NU)
        self.assertEqual({e["navn"]: e["sjaelden"] for e in doc["enheder"]}, {"Mac": False, "Stationær": True, "Telefon": False})

    def test_ukendt_vaert_vises_som_ukendt_enhed(self):
        raa = {"1ec2-telefon": {"window": [vindue(kl(17, 20), 10, "Instagram")], "afk": None, "web": [],
                                "sidst": kl(17, 20, 10).isoformat()}}
        doc = skaermtid.beregn(raa, self.cfg(), date(2026, 10, 17), date(2026, 10, 17), NU)
        ukendt = [e for e in doc["enheder"] if not e["kendt"]]
        self.assertEqual([(e["navn"], e["vaert"], e["sidst"]) for e in ukendt], [("1ec2-telefon", "1ec2-telefon", kl(17, 20, 10).isoformat())])

    def test_unknown_er_maskinen_selv_medmindre_hentet(self):
        self.assertEqual(skaermtid._vaert("aw-watcher-web-chrome", {"hostname": "unknown", "data": {}}, "macbook.local"), "macbook.local")
        self.assertEqual(skaermtid._vaert("aw-watcher-web-edge-synced-from-aaaa", {"hostname": "aaaa", "data": {"$aw.sync.origin": "aaaa"}},
                                          "macbook.local"), "aaaa")
        self.assertEqual(skaermtid._vaert("aw-watcher-window_desktop-alex-synced-from-desktop-alex",
                                          {"hostname": "desktop-alex", "data": {"$aw.sync.origin": "desktop-alex"}}, "macbook.local"), "desktop-alex")
        self.assertEqual(skaermtid._vaert("aw-watcher-window_X", {}, None), "X")



class Valg(unittest.TestCase):
    """Dine valg fra siden (valg.json) går forud for reglerne og gælder præcis ét program eller én side."""

    def cfg(self, valg):
        c = skaermtid.laes_regler(EKSEMPEL, valg_sti=Path("/findes/ikke"))
        skaermtid.saet_valg(c, valg)
        return c

    def test_valg_slaar_reglen_og_siger_hvorfor(self):
        c = self.cfg([{"app": "com.reddit.frontpage", "kategori": "Studie"}, {"domaene": "www.dba.dk", "kategori": "Økonomi"}])
        self.assertEqual(skaermtid.kategori_og_kilde(c, "Reddit", "com.reddit.frontpage", None, None, None), ("Studie", "valg"))
        self.assertEqual(skaermtid.kategori_og_kilde(c, "Microsoft Edge", None, "www.dba.dk", "/", None), ("Økonomi", "valg"))
        # Uden valg: reglens stærkeste mønster
        self.assertEqual(skaermtid.kategori_og_kilde(c, "Instagram", None, None, None, None), ("Sociale medier", "app"))
        self.assertEqual(skaermtid.kategori_og_kilde(c, "Microsoft Edge", None, "www.youtube.com", "/", None), ("Video & streaming", "domaene"))
        self.assertEqual(skaermtid.kategori_og_kilde(c, "Microsoft Edge", None, None, None, "Katte - YouTube"), ("Video & streaming", "titel"))
        self.assertEqual(skaermtid.kategori_og_kilde(c, "Lommeregner", None, None, None, None), ("Ukategoriseret", None))

    def test_taeller_ikke_fjerner_tiden(self):
        c = self.cfg([{"app": "com.android.deskclock", "ignorer": True}, {"domaene": "www.dr.dk", "ignorer": True}])
        raa = {"telefon": {"window": [ev(kl(17, 20), 10, app="Ur", package="com.android.deskclock"),
                                         ev(kl(17, 21), 10, app="Noter", package="com.example.noter")],
                              "afk": None, "web": [], "sidst": None},
               "macbook.local": {"window": [vindue(kl(17, 10), 20, "Microsoft Edge")], "afk": [aktiv(kl(17, 10), 20)],
                                 "web": [ev(kl(17, 10), 10, url="https://www.dr.dk/nyheder")], "sidst": None}}
        c["enheder"] = [{"navn": "Mac", "vaert": "macbook.local"}, {"navn": "Telefon", "vaert": ["telefon"]}]
        d = dag(skaermtid.beregn(raa, c, date(2026, 10, 17), date(2026, 10, 17), NU), "2026-10-17")
        # Uret og dr.dk er væk; Noter og Edge uden adresse står tilbage
        self.assertEqual({e: v["timer"] for e, v in d["enheder"].items()}, {"Telefon": 0.17, "Mac": 0.17})


class Telefonbrowser(unittest.TestCase):
    def test_kun_vaerten_uden_skema(self):
        self.assertEqual(skaermtid.domaene_og_sti("github.com"), ("github.com", "/"))
        self.assertEqual(skaermtid.domaene_og_sti("amazon.de/dp/1"), ("amazon.de", "/dp/1"))
        self.assertEqual(skaermtid.domaene_og_sti("Søg efter eller spørg om hvad som helst"), (None, None))
        self.assertEqual(skaermtid.domaene_og_sti("q"), (None, None))

    def test_fanen_gaelder_til_den_naeste(self):
        # Telefonens browser melder kun i et øjeblik; fanen gælder til næste fane, højst 30 minutter
        raa = {"telefon": {"window": [ev(kl(17, 20), 60, app="Edge", package="com.microsoft.emmx")], "afk": None,
                              "web": [ev(kl(17, 20), 0.05, url="www.youtube.com"), ev(kl(17, 20, 10), 0.05, url="www.reddit.com")],
                              "sidst": None}}
        c = dict(CFG)
        c["enheder"] = [{"navn": "Telefon", "vaert": ["telefon"]}]
        doc = skaermtid.beregn(raa, c, date(2026, 10, 17), date(2026, 10, 17), NU)
        self.assertEqual(dag(doc, "2026-10-17")["kategorier"],
                         {"Sociale medier": 0.5, "Video & streaming": 0.17, "Ukategoriseret": 0.33})


class Programmer(unittest.TestCase):
    def test_lagt_sammen_paa_tvaers_af_enheder_med_noegle_og_kilde(self):
        raa = {"macbook.local": {"window": [vindue(kl(17, 10), 30, "Claude")], "afk": [aktiv(kl(17, 10), 30)], "web": [], "sidst": None},
               "telefon": {"window": [ev(kl(17, 20), 15, app="Claude", package="com.anthropic.claude"),
                                         ev(kl(17, 21), 6, app="Lommeregner", package="com.android.calculator2")], "afk": None, "web": [], "sidst": None}}
        c = dict(CFG)
        c["enheder"] = [{"navn": "Mac", "vaert": "macbook.local"}, {"navn": "Telefon", "vaert": ["telefon"]}]
        doc = skaermtid.beregn(raa, c, date(2026, 10, 17), date(2026, 10, 17), NU)
        p = {(x["type"], x["noegle"]): x for x in doc["perioder"]["idag"]["programmer"]}
        # Mac'ens Claude har programnavnet som nøgle, telefonens pakkenavnet; begge Egne projekter fra en app-regel
        self.assertEqual((p[("app", "Claude")]["timer"], p[("app", "Claude")]["kilde"], p[("app", "Claude")]["enheder"]),
                         (0.5, "app", {"Mac": 0.5}))
        self.assertEqual(p[("app", "com.anthropic.claude")]["navn"], "Claude")
        self.assertEqual((p[("app", "com.android.calculator2")]["kategori"], p[("app", "com.android.calculator2")]["kilde"]), ("Ukategoriseret", None))
        self.assertEqual([x["noegle"] for x in doc["ukategoriseret"]], ["com.android.calculator2"])


class Grupper(unittest.TestCase):
    def test_hver_kategori_i_praecis_en_gruppe(self):
        i_grupper = [k for g in CFG["grupper"] for k in g["kategorier"]]
        self.assertEqual(sorted(i_grupper), sorted(k["navn"] for k in CFG["kategorier"]))

    def test_youtube_med_laerende_titel_er_studie(self):
        k = lambda titel: skaermtid.kategoriser(CFG, "Microsoft Edge", None, "www.youtube.com", "/watch?v=1", titel)
        self.assertEqual(k("CS50 2024 - Lecture 0 - Scratch - YouTube"), "Studie")
        self.assertEqual(k("Katte der falder ned - YouTube"), "Video & streaming")
        self.assertEqual(k(None), "Video & streaming")
        # En titel-regel uden side gælder stadig kun uden adresse
        self.assertEqual(skaermtid.kategoriser(CFG, "Microsoft Edge", None, "canvas.instructure.com", "/", "YouTube"), "Studie")

    def test_fanens_titel_og_grupper_pr_dag(self):
        raa = {"macbook.local": {"window": [vindue(kl(17, 10), 30, "Microsoft Edge", "YouTube")], "afk": [aktiv(kl(17, 10), 30)],
                                 "web": [ev(kl(17, 10), 20, url="https://www.youtube.com/watch?v=1", title="CS50 Lecture 3 - YouTube"),
                                         ev(kl(17, 10, 20), 10, url="https://www.youtube.com/watch?v=2", title="Katte - YouTube")],
                                 "sidst": None}}
        c = dict(CFG); c["enheder"] = [{"navn": "Mac", "vaert": "macbook.local"}]
        doc = skaermtid.beregn(raa, c, date(2026, 10, 17), date(2026, 10, 17), NU)
        self.assertEqual(dag(doc, "2026-10-17")["grupper"], {"Produktiv": 0.33, "Passiv": 0.17})
        self.assertEqual(doc["perioder"]["idag"]["grupper"], {"Produktiv": 0.33, "Passiv": 0.17})


class KorteTjek(unittest.TestCase):
    def test_aabninger_korte_og_oplaasninger(self):
        app = lambda start, sek, navn, pakke: {"timestamp": start.isoformat(), "duration": sek, "data": {"app": navn, "package": pakke}}
        t = kl(17, 20)
        s = timedelta(seconds=1)
        window = [
            app(t, 20, "Instagram", "com.instagram.android"),            # kort tjek
            app(t + 20 * s, 2, "Starter", "com.android.launcher"),
            app(t + 22 * s, 30, "Instagram", "com.instagram.android"),   # ny åbning efter hjemmeskærmen, …
            app(t + 53 * s, 40, "Instagram", "com.instagram.android"),   # … samme åbning (1 s pause): 71 s, ikke kort
            app(t + 100 * s, 10, "Messenger", "com.facebook.orca"),      # Kommunikation tæller ikke som tjek
        ]
        raa = {"telefon": {"window": window, "afk": None, "web": [], "sidst": None,
                              "unlock": [{"timestamp": t.isoformat(), "duration": 0, "data": {}},
                                         {"timestamp": (t + 90 * s).isoformat(), "duration": 0, "data": {}}]}}
        c = dict(CFG); c["enheder"] = [{"navn": "Telefon", "vaert": ["telefon"]}]
        doc = skaermtid.beregn(raa, c, date(2026, 10, 16), date(2026, 10, 17), NU)
        self.assertEqual(dag(doc, "2026-10-17")["tjek"], {"aabninger": 2, "korte": 1, "oplaasninger": 2})
        self.assertNotIn("2026-10-16", [x["dato"] for x in doc["dage"]])
        self.assertEqual(doc["perioder"]["fire_uger"]["tjek"]["korte_pr_dag"], 1.0)


class Enhedsside(unittest.TestCase):
    """Enhederne på siden (enhedsside): pr. hel dag med data, fælles dage og telefon samtidig med computer."""

    def doc(self):
        c = dict(CFG)
        c["enheder"] = [{"navn": "Mac", "vaert": "macbook.local", "slags": "computer"},
                        {"navn": "Telefon", "vaert": ["telefon"], "slags": "telefon"}]
        tlf = lambda dag, t, m, minutter, navn, pakke: ev(kl(dag, t, m), minutter, app=navn, package=pakke)
        raa = {
            # Mac'en sættes op den 16. kl. 15 (halv dag) og bruges hele den 17.
            "macbook.local": {"window": [vindue(kl(16, 15), 60, "Claude"), vindue(kl(17, 10), 60, "Claude")],
                              "afk": [aktiv(kl(16, 15), 60), aktiv(kl(17, 10), 60)], "web": [], "sidst": None},
            # Telefonen har data fra den 15. kl. 7; den 17. kl. 10.30–10.50 Reddit, mens Mac'en er i brug
            "telefon": {"window": [tlf(15, 7, 0, 30, "Reddit", "com.reddit.frontpage"),
                                      tlf(16, 9, 0, 30, "Reddit", "com.reddit.frontpage"),
                                      tlf(17, 10, 30, 20, "Reddit", "com.reddit.frontpage")],
                           "afk": None, "web": [], "sidst": None}}
        return skaermtid.beregn(raa, c, date(2026, 10, 15), date(2026, 10, 18), NU)["enhedsside"]

    def test_hele_dage(self):
        e = {x["navn"]: x for x in self.doc()["enheder"]}
        # Mac'ens første dag (sat op kl. 15) og i dag (den 18.) er ikke hele dage; telefonens første data kl. 7 er
        self.assertEqual((e["Mac"]["dage"], e["Mac"]["hele_dage"]), (2, 1))
        self.assertEqual((e["Telefon"]["dage"], e["Telefon"]["hele_dage"]), (3, 3))
        self.assertEqual(e["Mac"]["perioder"]["fire_uger"]["pr_dag"], 1.0)
        self.assertEqual(e["Mac"]["perioder"]["fire_uger"]["grupper_pr_dag"], {"Produktiv": 1.0})
        self.assertEqual(e["Mac"]["perioder"]["fire_uger"]["kategorier_pr_dag"], {"Egne projekter": 1.0})
        self.assertEqual(e["Telefon"]["perioder"]["fire_uger"]["kategorier"], {"Sociale medier": 1.33})
        self.assertEqual(e["Mac"]["perioder"]["fire_uger"]["grupper"], {"Produktiv": 2.0})  # også den halve dag
        self.assertEqual(e["Telefon"]["perioder"]["fire_uger"]["andele"], {"Passiv": 1.0})
        self.assertEqual(e["Mac"]["doegn"]["min_pr_time"][10], 60.0)
        self.assertEqual((e["Mac"]["doegn"]["min_pr_dag"], e["Mac"]["doegn"]["travleste"]), (60, [{"time": 10, "min": 60.0}]))

    def test_faelles_dage_og_samtidig(self):
        f = self.doc()["faelles"]["fire_uger"]
        self.assertEqual(f["dage_liste"], ["2026-10-17"])  # den 16. er Mac'ens halve opsætningsdag
        self.assertEqual(f["enheder"], {"Mac": 1.0, "Telefon": 0.33})
        self.assertEqual(f["samtidig"]["timer"], 0.33)
        self.assertEqual(f["samtidig"]["telefonens_grupper"], {"Passiv": 0.33})
        self.assertEqual(f["samtidig"]["computerens_grupper"], {"Produktiv": 0.33})
        self.assertEqual(f["samtidig"]["andel_af_telefon"], 1.0)


class Rapport(unittest.TestCase):
    def test_seneste_rapport_og_ugens_tal(self):
        import tempfile, json as js
        with tempfile.TemporaryDirectory() as t:
            m = Path(t)
            self.assertIsNone(skaermtid.seneste_rapport(m))
            (m / "2026-W41.json").write_text(js.dumps({"saetning": "a"}))
            (m / "2026-W42.json").write_text(js.dumps({"saetning": "b"}))
            self.assertEqual(skaermtid.seneste_rapport(m), {"saetning": "b", "uge": "2026-W42", "mandag": "2026-10-12"})
        raa = {"macbook.local": {"window": [vindue(kl(13, 10), 60, "Claude"), vindue(kl(8, 10), 30, "Claude")],
                                 "afk": [aktiv(kl(13, 10), 60), aktiv(kl(8, 10), 30)], "web": [], "sidst": None}}
        c = dict(CFG); c["enheder"] = [{"navn": "Mac", "vaert": "macbook.local"}]
        doc = skaermtid.beregn(raa, c, date(2026, 9, 28), date(2026, 10, 19), NU)
        r = skaermtid.rapport(doc)
        # Mandag den 19. kører rutinen: den sidste hele uge er 12.–18. oktober (uge 42), ugen før 5.–11.
        self.assertEqual((r["uge"], r["mandag"], r["soendag"]), ("2026-W42", "2026-10-12", "2026-10-18"))
        self.assertEqual((r["forrige_uge"]["grupper"], r["ugen_foer"]["grupper"]), ({"Produktiv": 1.0}, {"Produktiv": 0.5}))
        self.assertNotIn("programmer", r["forrige_uge"])
        self.assertIn("browser_uden_adresse", r)
        # Dagene starter med den første dag med data (den 8.), ikke med perioden (28. sep.)
        self.assertEqual(doc["dage"][0]["dato"], "2026-10-08")
        self.assertEqual([u["uge"] for u in doc["uger"]], ["2026-W41", "2026-W42", "2026-W43"])
        self.assertEqual([u["uge"] for u in doc["enhedsside"]["uger"]], ["2026-W41", "2026-W42", "2026-W43"])

    def test_uden_data_ingen_dage(self):
        doc = skaermtid.beregn({}, CFG, date(2026, 10, 12), date(2026, 10, 18), NU)
        self.assertEqual((doc["dage"], doc["uger"]), ([], []))
        self.assertEqual(doc["perioder"]["uge"]["timer"], 0)
        self.assertEqual(doc["browser_uden_adresse"], {})



class Server(unittest.TestCase):
    """server.py: det eneste, der skriver (valg.json). Testene skriver i en midlertidig mappe og bygger aldrig."""

    def setUp(self):
        import tempfile
        import server
        self.server = server
        self.tmp = tempfile.TemporaryDirectory()
        self.gammel = (skaermtid.VALG, skaermtid.REGLER, skaermtid.byg)
        skaermtid.VALG = Path(self.tmp.name) / "valg.json"
        skaermtid.REGLER = EKSEMPEL
        # laes_regler har REGLER som standardværdi fra importen; gem_valg kalder den uden argument
        skaermtid.laes_regler.__defaults__ = (EKSEMPEL, None)
        skaermtid.byg = lambda ud: {"genereret": "nu"}
        self.gammel_log = server.log
        server.log = lambda tekst: None

    def tearDown(self):
        skaermtid.VALG, skaermtid.REGLER, skaermtid.byg = self.gammel
        skaermtid.laes_regler.__defaults__ = (self.gammel[1], None)
        self.server.log = self.gammel_log
        self.tmp.cleanup()

    def test_gemmer_fjerner_og_afviser(self):
        import json
        gem = self.server.gem_valg
        svar = gem({"type": "app", "noegle": "com.example.noter", "navn": "Noter\x00<b>", "kategori": "Studie"})
        self.assertTrue(svar["gemt"])
        v = json.loads(skaermtid.VALG.read_text())["valg"]
        self.assertEqual([(x["app"], x["navn"], x["kategori"]) for x in v], [("com.example.noter", "Noter<b>", "Studie")])
        # Navnet er kun tekst; ellers bruges nøglen
        gem({"type": "domaene", "noegle": "www.example.org", "navn": {"x": 1}, "ignorer": True})
        self.assertEqual(json.loads(skaermtid.VALG.read_text())["valg"][-1]["navn"], "www.example.org")
        gem({"type": "app", "noegle": "com.example.noter", "fjern": True})
        self.assertEqual([x.get("app") for x in json.loads(skaermtid.VALG.read_text())["valg"]], [None])
        for krop in ({"type": "sti", "noegle": "x", "kategori": "Studie"},
                     {"type": "app", "noegle": "", "kategori": "Studie"},
                     {"type": "app", "noegle": "a" * 201, "kategori": "Studie"},
                     {"type": "app", "noegle": "x\ny", "kategori": "Studie"},
                     {"type": "app", "noegle": "x", "kategori": "Findes ikke"},
                     {"type": "app", "noegle": "x", "kategori": ["Studie"]},
                     {"type": "app", "noegle": "x", "kategori": "Studie", "ignorer": True},
                     {"type": "app", "noegle": "x"},
                     {"type": "app", "noegle": "Microsoft Edge", "kategori": "Studie"}):
            with self.assertRaises(ValueError, msg=krop):
                gem(krop)

    def test_kun_kompas_og_kendte_vaerter(self):
        import http.client
        import json
        import threading
        from http.server import ThreadingHTTPServer
        srv = ThreadingHTTPServer(("127.0.0.1", 0), self.server.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)

        def post(host, origin, krop, ctype="application/json"):
            c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
            c.request("POST", "/skaermtid/api/valg", body=json.dumps(krop),
                      headers={"Host": host, "Origin": origin, "Content-Type": ctype})
            r = c.getresponse()
            return r.status, json.loads(r.read())

        krop = {"type": "app", "noegle": "com.example.noter", "kategori": "Studie"}
        self.assertEqual(post("evil.example", "https://kompas.localhost", krop)[0], 403)
        self.assertEqual(post("kompas.localhost", "https://evil.example", krop)[0], 403)
        self.assertEqual(post("kompas.localhost", "https://kompas.localhost", krop, "text/plain")[0], 403)
        self.assertEqual(post("kompas.localhost", "https://kompas.localhost", {**krop, "kategori": "x"})[0], 400)
        status, svar = post("kompas.localhost", "https://kompas.localhost", krop)
        self.assertEqual((status, svar["gemt"]), (200, True))


class Eksempel(unittest.TestCase):
    def test_uden_egne_filer_bruges_eksemplerne(self):
        # I et frisk klon findes regler.json og valg.json ikke; så læses eksemplerne
        if not (skaermtid.HER / "regler.json").exists():
            self.assertEqual(skaermtid.REGLER, EKSEMPEL)
        if not (skaermtid.HER / "valg.json").exists() and not __import__("os").environ.get("SKAERMTID_VALG"):
            self.assertTrue(skaermtid.laes_valg(skaermtid.HER / "valg.json"))
        # En valgt sti, der ikke findes (fx en testkopi), er tom, ikke eksemplet
        self.assertEqual(skaermtid.laes_valg(Path("/findes/ikke/valg.json")), [])


if __name__ == "__main__":
    unittest.main()
