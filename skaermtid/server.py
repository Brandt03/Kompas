#!/usr/bin/python3
"""Skærmtid-serveren: det eneste sted, Skærmtid-siden kan skrive (https://kompas.localhost/skaermtid/).

Den kan kun én ting: gemme dit valg for ét program eller én side i valg.json (en kategori, "tæller ikke", eller
fjerne valget igen) og så bygge siden forfra med skaermtid.byg(), så valget ses med det samme og gælder bagud.
regler.json skriver den aldrig; dine håndskrevne regler bliver stående, som de er.

    /usr/bin/python3 server.py      # lytter på 127.0.0.1:8770; Caddy sender /skaermtid/api/* hertil

    GET  /skaermtid/api/valg        dine valg
    POST /skaermtid/api/valg        {"type": "app" | "domaene", "noegle": …, "navn": …,
                                     "kategori": … | "ignorer": true | "fjern": true}

Kører altid i baggrunden som LaunchAgent local.kompas.skaermtid; log i ~/.kompas/skaermtid-server.log. Telefonen
når den gennem Tailscale (Caddy 127.0.0.1:8768); dens adresse står i SKAERMTID_ORIGINS (bin/tailscale.sh).
Test mod en kopi: SKAERMTID_PORT, SKAERMTID_VALG (valg-filen) og SKAERMTID_UD (hvor siden bygges til).
Kun standardbiblioteket; macOS' egen /usr/bin/python3.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skaermtid  # noqa: E402  (læser SKAERMTID_VALG ved import)

PORT = int(os.environ.get("SKAERMTID_PORT", "8770"))
UD = Path(os.environ.get("SKAERMTID_UD") or skaermtid.UD)
# Kompas på Mac'en, og telefonen gennem Tailscale (https://<mac>.<tailnet>.ts.net), som bin/tailscale.sh
# sætter i LaunchAgent'en som SKAERMTID_ORIGINS
TILLADTE_ORIGINS = ["https://kompas.localhost"] + [o.strip() for o in os.environ.get("SKAERMTID_ORIGINS", "").split(",") if o.strip()]
# Kun de navne, Kompas selv bruger (mod DNS rebinding), som de andre servere. 8768 er Caddys blok til telefonen.
TILLADTE_VAERTER = {"kompas.localhost", f"127.0.0.1:{PORT}", f"localhost:{PORT}", "127.0.0.1:8768", "localhost:8768",
                    *(urlparse(o).netloc for o in TILLADTE_ORIGINS)}
# Én skrivning og ét byg ad gangen: valg.json læses, ændres og skrives hel
SKRIVELAAS = threading.Lock()


def log(tekst: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {tekst}", flush=True)


def gem_valg(krop: dict) -> dict:
    """Gemmer, ændrer eller fjerner ét valg i valg.json og bygger siden igen. ValueError ved ugyldigt input."""
    typ = krop.get("type")
    nøgle = krop.get("noegle")
    if typ not in ("app", "domaene"):
        raise ValueError("type skal være app eller domaene")
    if not isinstance(nøgle, str) or not 0 < len(nøgle.strip()) <= 200 or re.search(r"[\x00-\x1f]", nøgle):
        raise ValueError("ugyldigt program eller side")
    nøgle = nøgle.strip()
    # Navnet vises på siden (escapet) og står i valg.json; kun tekst, uden styretegn
    navn = krop.get("navn")
    navn = re.sub(r"[\x00-\x1f\x7f]", "", navn).strip()[:200] if isinstance(navn, str) else ""
    navn = navn or nøgle
    cfg = skaermtid.laes_regler()
    kategorier = [k["navn"] for k in cfg["kategorier"]]
    if typ == "app" and cfg["_browser"].search(nøgle):
        raise ValueError("En browser kan ikke få én kategori. Vælg i stedet for den enkelte side.")

    fjern, ignorer, kategori = bool(krop.get("fjern")), bool(krop.get("ignorer")), krop.get("kategori")
    if fjern + ignorer + bool(kategori) != 1:
        raise ValueError("vælg én af: kategori, ignorer eller fjern")
    if kategori and (not isinstance(kategori, str) or kategori not in kategorier):
        raise ValueError("ukendt kategori")

    valg = [v for v in skaermtid.laes_valg(skaermtid.VALG)
            if (v.get(typ) or "").lower() != nøgle.lower()]
    if not fjern:
        nyt = {typ: nøgle, "navn": navn}
        nyt |= {"ignorer": True} if ignorer else {"kategori": kategori}
        nyt["valgt"] = datetime.now().date().isoformat()
        valg.append(nyt)
    valg.sort(key=lambda v: (v.get("kategori") or "~", (v.get("navn") or "").lower()))
    sti = Path(skaermtid.VALG)
    tmp = sti.with_suffix(".tmp")
    tmp.write_text(json.dumps({"_om": "Dine valg fra Skærmtid-siden. Skrives af server.py; går forud for "
                                      "regler.json og gælder præcis ét program (app: pakkenavn eller programnavn) "
                                      "eller én side (domaene: værten).", "valg": valg},
                              ensure_ascii=False, indent=1) + "\n")
    tmp.replace(sti)
    hvad = "fjernet" if fjern else "tæller ikke" if ignorer else kategori
    log(f"valg: {typ} {nøgle} → {hvad}")

    try:
        doc = skaermtid.byg(UD)
    except SystemExit as e:  # ActivityWatch svarer ikke: valget er gemt og gælder ved næste byg
        log(f"byg fejlede: {e}")
        return {"gemt": True, "bygget": False, "fejl": str(e), "valg": valg}
    return {"gemt": True, "bygget": True, "genereret": doc["genereret"], "valg": valg}


class Handler(BaseHTTPRequestHandler):
    server_version = "Skaermtid/1"

    def log_message(self, fmt, *args):  # stille; fejl og valg logges selv
        pass

    def _json(self, kode: int, obj) -> None:
        krop = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(kode)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(krop)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(krop)

    def _kendt_vaert(self) -> bool:
        vaert = re.sub(r":(443|80)$", "", (self.headers.get("Host") or "").lower())
        if vaert in TILLADTE_VAERTER:
            return True
        log(f"afvist vært: {vaert[:80]}")
        self._json(403, {"fejl": "ukendt vært"})
        return False

    def do_GET(self):
        if not self._kendt_vaert():
            return
        sti = urlparse(self.path).path
        if sti in ("/", "/skaermtid/api/"):
            return self._json(200, {"tjeneste": "skaermtid", "ok": True})
        if sti == "/skaermtid/api/valg":
            return self._json(200, {"valg": skaermtid.laes_valg(skaermtid.VALG)})
        return self._json(404, {"fejl": "ikke fundet"})

    def do_POST(self):
        if not self._kendt_vaert():
            return
        # Kun Kompas må skrive: en fremmed side kan ikke sende JSON på tværs af origins uden en CORS-preflight,
        # som serveren aldrig godkender, og Origin-tjekket fanger resten.
        if self.headers.get("Origin") not in TILLADTE_ORIGINS or not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._json(403, {"fejl": "kun fra Kompas"})
        if urlparse(self.path).path != "/skaermtid/api/valg":
            return self._json(404, {"fejl": "ikke fundet"})
        try:
            rå = (self.headers.get("Content-Length") or "0").strip()
            if not rå.isdigit() or int(rå) > 10_000:
                return self._json(400, {"fejl": "ugyldig længde"})
            krop = json.loads(self.rfile.read(int(rå)) or b"{}")
            if not isinstance(krop, dict):
                raise ValueError("forventede et JSON-objekt")
            with SKRIVELAAS:
                return self._json(200, gem_valg(krop))
        except (ValueError, TypeError) as e:
            return self._json(400, {"fejl": str(e)})
        except Exception as e:  # noqa: BLE001
            # Detaljen (fx en sti) står kun i loggen, ikke i svaret
            log(f"POST: {type(e).__name__}: {e}")
            return self._json(500, {"fejl": "intern fejl; se skaermtid-server.log"})


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    log(f"Skærmtid på http://127.0.0.1:{PORT} (valg: {skaermtid.VALG}, byg til: {UD})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
