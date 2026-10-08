"""Karriere-serveren: Host-tjek, Origin-tjek, Content-Length og samtidige skrivninger.
Kører en kopi af serveren med eksempelfilerne i en midlertidig mappe.   python -m unittest discover -s tests"""
from __future__ import annotations

import csv
import http.client
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

KARRIERE = Path(__file__).resolve().parent.parent / "karriere"


def ledig_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class KarriereServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mappe = Path(tempfile.mkdtemp())
        shutil.copy(KARRIERE / "kompas_server.py", cls.mappe)
        shutil.copy(KARRIERE / "config.json", cls.mappe)
        shutil.copytree(KARRIERE / "kompas", cls.mappe / "kompas")
        shutil.copy(KARRIERE / "profil.example.md", cls.mappe / "profil.md")
        with open(KARRIERE / "oversigt.example.csv", encoding="utf-8") as f:
            rækker = list(csv.reader(f, delimiter=";"))
        hoved, skabelon = rækker[0], rækker[1]
        i_id = hoved.index("id")
        with open(cls.mappe / "oversigt.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter=";", lineterminator="\n")
            w.writerow(hoved)
            for n in range(30):
                række = list(skabelon)
                række[i_id] = f"t{n:03d}"
                w.writerow(række)
        cls.port = ledig_port()
        cls.proc = subprocess.Popen([sys.executable, "kompas_server.py"], cwd=cls.mappe,
                                    env={"KARRIERE_PORT": str(cls.port), "PATH": "/usr/bin:/bin"},
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", cls.port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=5)
        shutil.rmtree(cls.mappe, ignore_errors=True)

    def _req(self, metode, sti, krop=None, vaert="kompas.localhost", origin="https://kompas.localhost"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": vaert, "Content-Type": "application/json"}
        if origin:
            h["Origin"] = origin
        c.request(metode, sti, body=None if krop is None else json.dumps(krop).encode(), headers=h)
        r = c.getresponse()
        return r.status, r.read()

    def test_kendt_vaert_svarer(self):
        self.assertEqual(self._req("GET", "/kompas.json")[0], 200)

    def test_fremmed_vaert_afvises(self):
        # DNS rebinding: en fremmed side, der peger sit domæne på 127.0.0.1, sender sit eget navn som Host
        self.assertEqual(self._req("GET", "/kompas.json", vaert=f"evil.example:{self.port}")[0], 403)
        self.assertEqual(self._req("POST", "/api/status", {"id": "t000", "status": "søgt"}, vaert="evil.example")[0], 403)

    def test_skrivning_kraever_kompas_origin(self):
        self.assertEqual(self._req("POST", "/api/status", {"id": "t000", "status": "søgt"}, origin=None)[0], 403)
        self.assertEqual(self._req("POST", "/api/status", {"id": "t000", "status": "søgt"}, origin="https://evil.example")[0], 403)

    def test_negativ_content_length_afvises(self):
        with socket.create_connection(("127.0.0.1", self.port), timeout=5) as s:
            s.sendall(b"POST /api/status HTTP/1.1\r\nHost: kompas.localhost\r\nOrigin: https://kompas.localhost\r\n"
                      b"Content-Type: application/json\r\nContent-Length: -1\r\n\r\n")
            self.assertIn(b" 400 ", s.recv(200).split(b"\r\n")[0])

    def test_samtidige_statusaendringer_gaar_ikke_tabt(self):
        ids = [f"t{n:03d}" for n in range(30)]
        svar = []
        tråde = [threading.Thread(target=lambda j=j: svar.append(self._req("POST", "/api/status", {"id": j, "status": "samtale"})[0]))
                 for j in ids]
        for t in tråde:
            t.start()
        for t in tråde:
            t.join()
        self.assertEqual(svar.count(200), len(ids))
        with open(self.mappe / "oversigt.csv", encoding="utf-8") as f:
            rækker = list(csv.reader(f, delimiter=";"))
        i_id, i_st = rækker[0].index("id"), rækker[0].index("status")
        self.assertEqual(sum(1 for r in rækker[1:] if r[i_id] in ids and r[i_st] == "samtale"), len(ids))
        self.assertEqual(list(self.mappe.glob("*.tmp")) + list(self.mappe.glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
