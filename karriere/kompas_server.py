"""Karriere i Kompas (https://kompas.localhost/karriere/).

En lille lokal server, der viser jobagentens fund og lader dig beslutte, hvad der skal ske med dem.
Den er det eneste sted, siderne kan skrive, og den kan kun tre ting:

  - sætte status på et opslag i oversigt.csv (samme felt, som README'en siger, du selv opdaterer)
    og logge beslutningen med en eventuel note i data/beslutninger.jsonl
  - gemme profil.md (den gamle version gemmes først i data/profil-historik/)
  - ændre match_taerskel i config.json

Den sender, indsender eller udfylder aldrig noget udadtil. Jobopslag vises som tekst og fortolkes ikke.

    python3 kompas_server.py              # lytter på 127.0.0.1:8766; Caddy sender /karriere/* hertil

Kører altid i baggrunden som LaunchAgent local.kompas.karriere (~/Library/LaunchAgents); log i ~/.kompas/karriere.log.
Kun standardbiblioteket; virker med Pythons systemversion.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

MAPPE = Path(__file__).resolve().parent
SIDER = MAPPE / "kompas"
OVERSIGT = MAPPE / "oversigt.csv"
BESLUTNINGER = MAPPE / "data" / "beslutninger.jsonl"
PORT = int(os.environ.get("KARRIERE_PORT", "8766"))
TILLADT_ORIGIN = "https://kompas.localhost"

# Status i oversigt.csv. Agenten skriver "vurderet"; resten sætter du.
# Opslag, hvor de læser ansøgninger eller holder samtaler løbende, så stillingen kan blive besat før fristen.
# Bruges, når agentens vurdering ikke selv siger det (ældre kørsler).
LOEBENDE = re.compile(
    r"(behandl\w*|indkald\w*|inviter\w*|samtaler?|læs\w*|vurder\w*|kalder)[^.\n]{0,60}\bløbende\b"
    r"|\bløbende\b[^.\n]{0,60}(behandl|indkald|samtale|ansæt|besæt|lukket)"
    r"|on an? (ongoing|rolling) basis|(reviewed|assessed|read) continuously", re.I)

STATUS = ["vurderet", "vil søge", "fravalgt", "søgt", "samtale", "tilbud", "afslag"]

MANIFEST = {
    "omraade": "Karriere", "ikon": "briefcase", "raekkefoelge": 40,
    "kilde": "jobagent (kompas_server.py) · fund fra rutinen \"Jobagent – studiejob og praktik\"",
    "sider": [
        {"titel": "Nye match", "ikon": "sparkles", "sti": "/karriere/"},
        {"titel": "Ansøgninger", "ikon": "kanban", "sti": "/karriere/ansoegninger.html"},
        {"titel": "Profil", "ikon": "user", "sti": "/karriere/profil.html"},
    ],
}


# ── læsning ─────────────────────────────────────────────────────────

def manifest() -> dict:
    """MANIFEST med "nyt" på Nye match: en nøgle, der skifter, når agenten har tilføjet opslag til
    oversigt.csv (den tilføjer kun rækker). Så viser menuen i Kompas en prik, til siden er åbnet."""
    rækker = læs_oversigt()
    sider = [dict(s) for s in MANIFEST["sider"]]
    if rækker:
        sider[0]["nyt"] = f"{max(r.get('dato') or '' for r in rækker)} · {len(rækker)} opslag"
    return {**MANIFEST, "sider": sider, "opdateret": datetime.now().isoformat(timespec="seconds")}


def læs_oversigt() -> list[dict]:
    if not OVERSIGT.exists():
        return []
    return list(csv.DictReader(io.StringIO(OVERSIGT.read_text(encoding="utf-8")), delimiter=";"))


def id_fra_link(link: str) -> str | None:
    m = re.search(r"/vis-job/([A-Za-z0-9]+)", link or "")
    return m.group(1) if m else None


def _tabel(afsnit: str) -> list[dict]:
    rækker = [l for l in afsnit.splitlines() if l.strip().startswith("|")]
    if len(rækker) < 2:
        return []
    celler = lambda r: [c.strip() for c in r.strip().strip("|").split("|")]
    hoved = celler(rækker[0])
    return [dict(zip(hoved, celler(r))) for r in rækker[2:]]


def _tal(s: str) -> int | None:
    m = re.search(r"\d+", s or "")
    return int(m.group()) if m else None


def begrundelser(rækker: list[dict]) -> dict[str, dict]:
    """Agentens begrundelser pr. opslag-id. Findes data/vurderinger/<id>.json (nyere kørsler), bruges
    den. Ellers læses dagsrapporterne: tabellen under "Bedste match" og ###-afsnittene står i samme
    rækkefølge, og tabellen har linket; tabellen under tærsklen matches på virksomhed og score."""
    ud: dict[str, dict] = {}
    for f in sorted((MAPPE / "rapporter").glob("*.md")):
        tekst = f.read_text(encoding="utf-8")
        afsnit = {a.split("\n", 1)[0].strip(): a for a in re.split(r"^## ", tekst, flags=re.M)[1:]}
        bedste = next((a for t, a in afsnit.items() if t.startswith("Bedste match")), "")
        ids = [id_fra_link(r.get("Link", "")) for r in _tabel(bedste)]
        blokke = re.split(r"^### ", bedste, flags=re.M)[1:]
        for jid, blok in zip(ids, blokke):
            if not jid:
                continue
            hvorfor = [re.sub(r"^\*\*Hvorfor match:\*\*\s*", "", l[2:].strip()) for l in blok.splitlines() if l.startswith("- **Hvorfor")]
            huller = [re.sub(r"^\*\*Huller/risici:\*\*\s*", "", l[2:].strip()) for l in blok.splitlines() if l.startswith("- **Huller")]
            ud[jid] = {"hvorfor": hvorfor, "huller": huller, "rapport": f.stem}
        for t, a in afsnit.items():
            if t.startswith("Vurderet, men under"):
                for r in _tabel(a):
                    firma, score = (r.get("Virksomhed") or "").lower(), _tal(r.get("Score", ""))
                    kandidater = [x for x in rækker if x.get("dato") == f.stem and _tal(x.get("score", "")) == score
                                  and (firma[:12] in x.get("virksomhed", "").lower() or x.get("virksomhed", "").lower()[:12] in firma)]
                    if len(kandidater) > 1:
                        ord_ = set(re.findall(r"\w{4,}", (r.get("Stilling") or "").lower()))
                        kandidater.sort(key=lambda x: -len(ord_ & set(re.findall(r"\w{4,}", x.get("stilling", "").lower()))))
                    if kandidater:
                        ud.setdefault(kandidater[0]["id"], {"kort": r.get("Kort begrundelse", ""), "rapport": f.stem})
    for f in (MAPPE / "data" / "vurderinger").glob("*.json") if (MAPPE / "data" / "vurderinger").exists() else []:
        try:
            v = json.loads(f.read_text(encoding="utf-8"))
            ud[v.get("id") or f.stem] = {"hvorfor": v.get("hvorfor") or [], "huller": v.get("huller") or [],
                                          "kort": v.get("kort_begrundelse") or "", "sted": v.get("sted"), "timer": v.get("timer")}
            if isinstance(v.get("loebende"), bool):  # agentens eget skøn går forud for teksttjekket
                ud[v.get("id") or f.stem]["loebende"] = v["loebende"]
        except (OSError, ValueError):
            pass
    return ud


def beslutninger() -> dict[str, dict]:
    """Seneste beslutning (og note) pr. opslag."""
    ud = {}
    if BESLUTNINGER.exists():
        for linje in BESLUTNINGER.read_text(encoding="utf-8").splitlines():
            try:
                b = json.loads(linje)
                ud[b["id"]] = b
            except (ValueError, KeyError):
                pass
    return ud


def data() -> dict:
    rækker = læs_oversigt()
    begr, besl = begrundelser(rækker), beslutninger()
    # Samme opslag kan i princippet stå flere gange; den nyeste række gælder
    pr_id: dict[str, dict] = {}
    for r in rækker:
        pr_id[r["id"]] = r
    jobs = []
    for jid, r in pr_id.items():
        meta = {}
        f = MAPPE / "data" / "behandlet" / f"{jid}.json"
        if f.exists():
            try:
                m = json.loads(f.read_text(encoding="utf-8"))
                meta = {"omraade": m.get("omraade"), "indrykket": m.get("indrykket"), "har_tekst": bool(m.get("fuld_tekst")),
                        "loebende": bool(LOEBENDE.search(m.get("fuld_tekst") or ""))}
            except (OSError, ValueError):
                pass
        jobs.append({**r, "score": _tal(r.get("score", "")),
                     **meta, **begr.get(jid, {}), "note": besl.get(jid, {}).get("note"), "besluttet": besl.get(jid, {}).get("tid"),
                     "forrige": besl.get(jid, {}).get("fra")})
    rapporter = sorted((MAPPE / "rapporter").glob("*.md"))
    seneste = None
    if rapporter:
        t = rapporter[-1].read_text(encoding="utf-8")
        linjer = [l for l in t.splitlines() if l.strip() and not l.startswith("#")]
        bem = re.search(r"^## Bemærkninger\n(.*?)(?=^## |\Z)", t, re.S | re.M)
        seneste = {"dato": rapporter[-1].stem, "opsummering": linjer[0] if linjer else "", "bemaerkninger": bem.group(1).strip() if bem else ""}
    cfg = json.loads((MAPPE / "config.json").read_text(encoding="utf-8"))
    return {
        "genereret": datetime.now().isoformat(timespec="seconds"),
        "taerskel": cfg.get("match_taerskel"), "max_uafklarede": cfg.get("max_uafklarede_i_kompas"), "status": STATUS,
        "jobs": jobs, "seneste_rapport": seneste,
        "profil": (MAPPE / "profil.md").read_text(encoding="utf-8") if (MAPPE / "profil.md").exists() else "",
        "cv": (MAPPE / "cv.txt").read_text(encoding="utf-8") if (MAPPE / "cv.txt").exists() else "",
        # Kun filnavne på dokumenterne i Jobs-mappen (CV, karakterudskrifter), aldrig indholdet
        "dokumenter": sorted(f.name for f in MAPPE.parent.glob("*.pdf")),
        "soegning": {"positive_ord": cfg.get("positive_ord"), "negative_ord": cfg.get("negative_ord"),
                     "typer": list((cfg.get("employment_types") or {}).values())},
    }


# ── skrivning ───────────────────────────────────────────────────────

def _skriv_atomisk(sti: Path, tekst: str) -> None:
    tmp = sti.with_name(sti.name + ".tmp")
    tmp.write_text(tekst, encoding="utf-8")
    os.replace(tmp, sti)


def sæt_status(jid: str, status: str, note: str | None) -> dict:
    if status not in STATUS:
        raise ValueError(f"ukendt status: {status}")
    tekst = OVERSIGT.read_text(encoding="utf-8")
    læser = csv.reader(io.StringIO(tekst), delimiter=";")
    rækker = list(læser)
    hoved = rækker[0]
    i_id, i_status = hoved.index("id"), hoved.index("status")
    fundet = [n for n, r in enumerate(rækker[1:], 1) if len(r) > i_id and r[i_id] == jid]
    if not fundet:
        raise KeyError(jid)
    n = fundet[-1]
    fra = rækker[n][i_status]
    rækker[n][i_status] = status
    ud = io.StringIO()
    csv.writer(ud, delimiter=";", lineterminator="\n").writerows(rækker)
    _skriv_atomisk(OVERSIGT, ud.getvalue())
    BESLUTNINGER.parent.mkdir(parents=True, exist_ok=True)
    post = {"tid": datetime.now().isoformat(timespec="seconds"), "id": jid, "fra": fra, "til": status}
    if note:
        post["note"] = note.strip()[:500]
    with BESLUTNINGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(post, ensure_ascii=False) + "\n")
    return post


def gem_profil(tekst: str) -> dict:
    if not tekst.strip():
        raise ValueError("profilen kan ikke være tom")
    sti = MAPPE / "profil.md"
    hist = MAPPE / "data" / "profil-historik"
    hist.mkdir(parents=True, exist_ok=True)
    if sti.exists():
        (hist / f"profil-{datetime.now():%Y%m%d-%H%M%S}.md").write_text(sti.read_text(encoding="utf-8"), encoding="utf-8")
    _skriv_atomisk(sti, tekst.replace("\r\n", "\n"))
    return {"gemt": True}


def sæt_tærskel(værdi: int) -> dict:
    if not 0 <= værdi <= 100:
        raise ValueError("tærsklen skal ligge mellem 0 og 100")
    sti = MAPPE / "config.json"
    tekst = sti.read_text(encoding="utf-8")
    # Ret kun tallet, så resten af filens opsætning bevares
    ny, n = re.subn(r'("match_taerskel"\s*:\s*)\d+', rf"\g<1>{værdi}", tekst)
    if not n:
        raise ValueError("fandt ikke match_taerskel i config.json")
    json.loads(ny)
    _skriv_atomisk(sti, ny)
    return {"taerskel": værdi}


# ── http ────────────────────────────────────────────────────────────

TYPER = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8"}


class Handler(BaseHTTPRequestHandler):
    server_version = "Karriere/1"

    def log_message(self, fmt, *args):  # stille; fejl logges nedenfor
        pass

    def _send(self, kode: int, krop: bytes | str, type_: str = "application/json; charset=utf-8") -> None:
        if isinstance(krop, str):
            krop = krop.encode("utf-8")
        self.send_response(kode)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(krop)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(krop)

    def _json(self, kode: int, obj) -> None:
        self._send(kode, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        url = urlparse(self.path)
        sti, q = url.path, parse_qs(url.query)
        try:
            if sti == "/kompas.json":
                return self._json(200, manifest())
            if sti == "/api/data":
                return self._json(200, data())
            if sti == "/api/opslag":
                jid = re.sub(r"[^A-Za-z0-9]", "", (q.get("id") or [""])[0])
                f = MAPPE / "data" / "behandlet" / f"{jid}.json"
                if not jid or not f.is_file():
                    return self._json(404, {"fejl": "opslaget er ikke gemt"})
                return self._send(200, json.loads(f.read_text(encoding="utf-8")).get("fuld_tekst") or "", "text/plain; charset=utf-8")
            navn = "index.html" if sti in ("", "/") else sti.lstrip("/")
            f = (SIDER / navn).resolve()
            if SIDER.resolve() in f.parents and f.is_file():
                return self._send(200, f.read_bytes(), TYPER.get(f.suffix, "application/octet-stream"))
            return self._json(404, {"fejl": "ikke fundet"})
        except Exception as e:  # noqa: BLE001
            print(f"GET {sti}: {type(e).__name__}: {e}", file=sys.stderr)
            return self._json(500, {"fejl": str(e)})

    def do_POST(self):
        # Kun Kompas må skrive. En fremmed side kan ikke sende JSON på tværs af origins uden en CORS-preflight,
        # som serveren aldrig godkender, og Origin-tjekket fanger resten.
        if self.headers.get("Origin") != TILLADT_ORIGIN or not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._json(403, {"fejl": "kun fra Kompas"})
        try:
            længde = int(self.headers.get("Content-Length") or 0)
            if længde > 200_000:
                return self._json(413, {"fejl": "for stort"})
            krop = json.loads(self.rfile.read(længde) or b"{}")
            sti = urlparse(self.path).path
            if sti == "/api/status":
                return self._json(200, sæt_status(str(krop.get("id", "")), str(krop.get("status", "")), krop.get("note")))
            if sti == "/api/profil":
                return self._json(200, gem_profil(str(krop.get("tekst", ""))))
            if sti == "/api/taerskel":
                return self._json(200, sæt_tærskel(int(krop.get("vaerdi"))))
            return self._json(404, {"fejl": "ikke fundet"})
        except KeyError as e:
            return self._json(404, {"fejl": f"opslaget {e} står ikke i oversigt.csv"})
        except (ValueError, TypeError) as e:
            return self._json(400, {"fejl": str(e)})
        except Exception as e:  # noqa: BLE001
            print(f"POST {self.path}: {type(e).__name__}: {e}", file=sys.stderr)
            return self._json(500, {"fejl": str(e)})


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Karriere på http://127.0.0.1:{PORT} (Caddy: https://kompas.localhost/karriere/)", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
