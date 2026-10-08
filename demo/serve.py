"""Kompas med opdigtede data på http://localhost:8000, uden Caddy, Sure, Garmin eller andet.

    python3 demo/serve.py            laver demodata for i dag og starter serveren
    python3 demo/serve.py --port 8080

Serveren gør det samme som Caddyfile'en, bare med demodata: hver sti slås først op i demo/ud (skrevet af lav.py),
derefter i projektets egne sider. Et API-kald uden filendelse (fx /studie/api/repetition) besvares med den
tilsvarende .json-fil. Demoen gemmer intet: skrivninger får 403. Sure (Oversigt, Transaktioner, Rapporter, Plan)
er et selvstændigt open source-program og er ikke med; dens stier viser en side, der forklarer det.
Kun standardbiblioteket, og serveren lytter kun på denne maskine.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlsplit

import lav

ROD = Path(__file__).resolve().parent.parent
UD = lav.UD

# Sti → mapper, der slås op i rækkefølge (demodata først, så projektets egne sider)
MONTERINGER = {
    "/kompas/": [UD / "kompas", ROD / "public"],
    "/form/": [UD / "form", ROD / "coach" / "site"],
    "/studie/": [UD / "studie", ROD / "studie" / "Scripts" / "kompas"],
    "/karriere/": [UD / "karriere", ROD / "karriere" / "kompas"],
    "/forbrug/": [UD / "forbrug", ROD / "okonomi" / "dashboard" / "public"],
}
TYPER = {".webmanifest": "application/manifest+json", ".js": "text/javascript", ".mjs": "text/javascript",
         ".woff2": "font/woff2", ".md": "text/markdown; charset=utf-8", ".json": "application/json"}

SURE = """<!doctype html>
<html lang="da"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sure</title>
<link rel="stylesheet" href="/kompas/assets/tokens.css"><link rel="stylesheet" href="/kompas/assets/page.css">
</head><body><div class="wrap" style="max-width:640px">
<section class="card panel">
  <div class="panel-head"><h2>Sure er ikke med i demoen</h2></div>
  <p>Oversigt, Transaktioner, Rapporter, Plan og indstillingerne er
  <a href="https://github.com/we-promise/sure" target="_blank" rel="noopener">Sure</a>, et open source-budgetprogram,
  der kører i Docker ved siden af Kompas. Kompas viser Sure i sin ramme, skjuler Sures egen menu og bruger
  Sures farver og skrift i resten af siderne.</p>
  <p>Kompas' egne økonomisider er <a href="/#/forbrug/" target="_top">Forbrug</a>,
  <a href="/#/forbrug/scenarier/" target="_top">Scenarier</a> og <a href="/#/forbrug/su/" target="_top">SU-vagt</a>,
  som bygger på et udtræk fra Sure. De er med i demoen med opdigtede tal.</p>
</section></div></body></html>"""


class Demo(BaseHTTPRequestHandler):
    server_version = "KompasDemo"

    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _redirect(self, to: str) -> None:
        self._send(302, b"", "text/plain", {"Location": to})

    def _file(self, path: Path) -> None:
        ctype = TYPER.get(path.suffix) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") and "charset" not in ctype:
            ctype += "; charset=utf-8"
        self._send(200, path.read_bytes(), ctype)

    def _find(self, path: str, query: str) -> Path | None:
        for prefix, roots in MONTERINGER.items():
            if not path.startswith(prefix):
                continue
            rest = path[len(prefix):]
            if rest == "" or rest.endswith("/"):
                rest += "index.html"
            # Et API-kald med query slås først op som en fil pr. svar: /karriere/api/opslag?id=d1001 som
            # api/opslag/d1001, og /studie/api/facit?nr=7&fag=is som api/facit/fag=is&nr=7.json
            par = sorted(parse_qsl(query, keep_blank_values=True))
            pr_svar = []
            if par and "/api/" in path:
                if len(par) == 1 and "/" not in par[0][1]:
                    pr_svar.append(f"{rest}/{par[0][1]}")
                pr_svar.append(f"{rest}/" + "&".join(f"{k}={quote(v, safe='')}" for k, v in par))
            kandidater = [k + e for k in pr_svar + [rest] for e in ("", ".json")]
            for root in roots:
                for kandidat in kandidater:
                    f = (root / kandidat).resolve()
                    # Kun filer inde i den monterede mappe (ingen ../)
                    if f.is_file() and root.resolve() in f.parents:
                        return f
            return None
        return None

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        path = unquote(url.path)
        if path == "/":
            return self._file(ROD / "public" / "shell.html")
        if path == "/up":  # Shell'en spørger, om Sure kører
            return self._send(503, b"Sure er ikke med i demoen", "text/plain; charset=utf-8")
        if path.rstrip("/") in (p.rstrip("/") for p in MONTERINGER) and not path.endswith("/"):
            return self._redirect(path + "/")
        f = self._find(path, url.query)
        if f:
            return self._file(f)
        if any(path.startswith(p) for p in MONTERINGER):
            if "/api/" in path:
                return self._send(404, json.dumps({"fejl": "Findes ikke i demoen."}).encode(), "application/json")
            return self._send(404, b"Findes ikke i demoen", "text/plain; charset=utf-8")
        # Alt andet er Sures stier
        return self._send(200, SURE.encode(), "text/html; charset=utf-8")

    do_HEAD = do_GET

    def _skriv(self) -> None:
        self._send(403, json.dumps({"fejl": "Demoen gemmer ikke noget."}, ensure_ascii=False).encode(),
                   "application/json")

    do_POST = do_PUT = do_PATCH = do_DELETE = _skriv

    def log_message(self, fmt: str, *args) -> None:
        pass


def main() -> None:
    p = argparse.ArgumentParser(description="Kompas med opdigtede data")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--dato", help="lad som om det er en anden dag (ÅÅÅÅ-MM-DD)")
    a = p.parse_args()
    from datetime import date
    lav.lav(idag=date.fromisoformat(a.dato) if a.dato else None)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Demo)
    print(f"Kompas-demoen kører på http://localhost:{a.port}  (Ctrl+C stopper)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
