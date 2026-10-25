"""Tests af bin/kopi.py: kopien til bærbaren. Kører mod midlertidige mapper og en lille testserver, aldrig mod
~/KompasKopi eller Kompas' rigtige servere.

    python -m unittest discover -s tests
"""
import importlib.util
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parent.parent / "bin"


class Svar(BaseHTTPRequestHandler):
    svar = {}       # sti -> bytes; mangler stien, svarer serveren 500
    vaerter = []    # Host-headere, serveren har fået
    kald = []

    def do_GET(self):
        from urllib.parse import unquote
        sti = unquote(self.path)
        Svar.vaerter.append(self.headers.get("Host"))
        Svar.kald.append(sti)
        data = Svar.svar.get(sti)
        self.send_response(200 if data is not None else 500)
        self.end_headers()
        self.wfile.write(data if data is not None else b"fejl")

    def log_message(self, *a):
        pass


class Kopi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Svar)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        with mock.patch.dict(os.environ, {"KOPI_KILDE": f"http://127.0.0.1:{cls.srv.server_port}"}):
            spec = importlib.util.spec_from_file_location("kopi_test", BIN / "kopi.py")
            cls.k = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.k)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kopi-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        kompas = self.tmp / "kompas"
        for f, tekst in {"public/shell.html": "ramme", "public/assets/tokens.css": "css", "public/.skjult": "x",
                         "studie/studie.json": json.dumps({"fag": [{"id": "alfa", "status": {"pensum": {
                             "forelaesninger": [{"mappe": "Forelæsninger", "fil": "Uge 1.pdf"},
                                                {"mappe": "..", "fil": "ude.pdf"}], "oevelser": []}}}]}),
                         "sprog/index.html": "sprog", "sprog/regler.html": "regler",
                         "baerbar/Caddyfile": "reverse_proxy {{OPSTROEM}} {\n\theader_up Host {{MAC}}\n}\n",
                         "baerbar/opsaet.sh": "echo hej\n"}.items():
            (kompas / f).parent.mkdir(parents=True, exist_ok=True)
            (kompas / f).write_text(tekst, encoding="utf-8")
        Svar.svar = {"/studie/api/pensum/alfa/Forelæsninger/Uge 1.pdf": b"%PDF",
                     "/studie/api/pensum/alfa/../ude.pdf": b"ude",
                     "/sprog/": b"sprog", "/sprog/regler.html": b"regler"}
        Svar.svar.update({sti: json.dumps({"sti": sti}).encode() for sti in self.k.API})
        Svar.vaerter, Svar.kald = [], []
        self.ud = self.tmp / "KompasKopi"
        for navn, vaerdi in {"KOMPAS": kompas, "STATISKE": {"kompas": kompas / "public", "studie": kompas / "studie"},
                             "SERVER_SIDER": {"sprog": kompas / "sprog"}}.items():
            p = mock.patch.object(self.k, navn, vaerdi)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(self.k, "mac_navn", return_value="mac.tailnet.ts.net")
        p.start()
        self.addCleanup(p.stop)

    def byg(self):
        with mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            return self.k.byg(self.ud)

    def tekst(self, rel):
        return (self.ud / rel).read_text(encoding="utf-8")

    def test_kopien_har_Kompas_stier_som_filer(self):
        self.assertTrue(self.byg())
        site = self.ud / "site"
        self.assertEqual(self.tekst("site/kompas/shell.html"), "ramme")
        self.assertEqual(self.tekst("site/kompas/assets/tokens.css"), "css")
        self.assertFalse((site / "kompas" / ".skjult").exists())
        self.assertEqual(json.loads(self.tekst("site/studie/api/genkald")), {"sti": "/studie/api/genkald"})
        self.assertEqual(self.tekst("site/sprog/index.html"), "sprog")
        self.assertEqual((site / "studie/api/pensum/alfa/Forelæsninger/Uge 1.pdf").read_bytes(), b"%PDF")
        info = json.loads(self.tekst("site/kompas/kopi.json"))
        self.assertEqual(info["mac"], "mac.tailnet.ts.net")
        self.assertIn("T", info["bygget"])
        # Hentet med Kompas' eget navn, som serverne kender
        self.assertEqual(set(Svar.vaerter), {"kompas.localhost"})

    def test_baerbarens_filer_faar_Macens_adresse(self):
        self.byg()
        self.assertEqual(self.tekst("baerbar/Caddyfile"),
                         "reverse_proxy https://mac.tailnet.ts.net:8443 {\n\theader_up Host mac.tailnet.ts.net:8443\n}\n")
        self.assertEqual(self.tekst("baerbar/opsaet.sh"), "echo hej\n")

    def test_uden_tailscale_bliver_den_gamle_Caddyfile_staaende(self):
        self.byg()
        with mock.patch.object(self.k, "mac_navn", return_value=None):
            self.assertFalse(self.byg())
        self.assertIn("mac.tailnet.ts.net", self.tekst("baerbar/Caddyfile"))

    def test_uaendrede_filer_skrives_ikke_igen(self):
        self.byg()
        site = self.ud / "site"
        foer = {p: p.stat().st_mtime_ns for p in site.rglob("*") if p.is_file()}
        time.sleep(1.1)  # kopi.json har tid i hele sekunder
        Svar.kald = []
        self.byg()
        efter = {p: p.stat().st_mtime_ns for p in site.rglob("*") if p.is_file()}
        aendret = sorted(str(p.relative_to(site)) for p in efter if efter[p] != foer.get(p))
        self.assertEqual(aendret, ["kompas/kopi.json"])
        # Pensum hentes kun første gang
        self.assertNotIn("/studie/api/pensum/alfa/Forelæsninger/Uge 1.pdf", Svar.kald)
        self.assertEqual(list(site.rglob("*.tmp")) + list(site.rglob(".*.tmp")), [])

    def test_det_der_er_vaek_paa_Macen_forsvinder_fra_kopien(self):
        self.byg()
        (self.k.KOMPAS / "public/assets/tokens.css").unlink()
        self.byg()
        self.assertFalse((self.ud / "site/kompas/assets").exists())
        self.assertTrue((self.ud / "site/kompas/kopi.json").exists())

    def test_fejlet_kald_beholder_den_gamle_fil(self):
        self.byg()
        del Svar.svar["/sprog/api/pakke"]
        self.assertFalse(self.byg())
        self.assertEqual(json.loads(self.tekst("site/sprog/api/pakke")), {"sti": "/sprog/api/pakke"})

    def test_projekt_paa_pause_kommer_ikke_med(self):
        self.byg()
        (self.k.KOMPAS / "public/projekter.json").write_text(json.dumps(
            {"manifester": [], "pause": [{"projekt": "Sprog", "manifest": "/sprog/kompas.json"}]}), encoding="utf-8")
        Svar.kald = []
        self.assertTrue(self.byg())
        self.assertFalse((self.ud / "site/sprog").exists())
        self.assertFalse(any(str(k).startswith("/sprog/") for k in Svar.kald), Svar.kald)
        self.assertTrue((self.ud / "site/studie/api/genkald").exists())

    def test_pensum_kan_ikke_skrive_uden_for_kopien(self):
        self.assertTrue(self.byg())
        self.assertFalse((self.ud / "site/studie/api/pensum/ude.pdf").exists())
        self.assertNotIn("/studie/api/pensum/alfa/../ude.pdf", Svar.kald)


if __name__ == "__main__":
    unittest.main()
