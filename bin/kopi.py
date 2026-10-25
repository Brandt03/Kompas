#!/usr/bin/python3
"""Kopi af Kompas til bærbaren, så den kan vise det seneste, også når Mac'en er slukket.

Køres af opdater.sh hver halve time efter de andre trin. Skriver ~/KompasKopi, som Syncthing sender til bærbaren
(mappe-ID kompas-kopi; kun send fra Mac'en, kun modtag på bærbaren). Dér serverer Caddy kopien på
http://kompas.localhost:8780 og sender alt videre til Mac'en, når den svarer (se baerbar/Caddyfile).

    site/       Kompas' stier som filer: de statiske mapper fra Caddyfile, og det, serverne svarer på læsekald
                uden parametre, hentet gennem Caddy (127.0.0.1:8771, samme stier som kompas.localhost)
    baerbar/    bærbarens Caddyfile, systemd-tjeneste og opsætning, fra ~/kompas/baerbar med Mac'ens Tailscale-navn

Kopien kan kun læses. Kald med parametre (facit, eksamenssæt) og Sures egne sider er ikke med.
Filer skrives kun, når de har ændret sig, så Syncthing kun sender det nye. Fejler et kald, bliver den gamle fil
liggende, og scriptet slutter med kode 1, så Forbindelser viser det.

    bin/kopi.py [--ud <mappe>]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

HJEM = Path.home()
KOMPAS = HJEM / "kompas"
KILDE = os.environ.get("KOPI_KILDE", "http://127.0.0.1:8771")  # Caddys blok med hele Kompas
VAERT = "kompas.localhost"
TAILSCALE = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"

# Sti i Kompas -> mappe på Mac'en, som i Caddyfile
STATISKE = {
    "kompas": KOMPAS / "public",
    "studie": HJEM / ".kompas" / "studie",
    "form": HJEM / ".garmin-coach" / "site",
    "skaermtid": HJEM / ".kompas" / "skaermtid",
    "forbrug": KOMPAS / "okonomi" / "dashboard" / "public",
}
# Serverens svar på læsekald uden parametre. Sider, som serverne selv leverer, findes ud fra deres mapper.
API = [
    "/studie/api/genkald", "/studie/api/begreber", "/studie/api/drills", "/studie/api/repetition",
    "/studie/api/laest", "/studie/api/egne-ord", "/studie/api/eksamen",
    "/sprog/kompas.json", "/sprog/api/pakke", "/sprog/api/tekster", "/sprog/api/regler",
]
SERVER_SIDER = {"sprog": KOMPAS / "sprog" / "side"}
KOPI_INFO = "kompas/kopi.json"  # findes kun i kopien; Kompas' ramme viser ud fra den, at det er kopien


def synlige(rod: Path):
    """Filerne under rod, uden skjulte filer og mapper og uden halvskrevne .tmp-filer."""
    for f in sorted(rod.rglob("*")):
        rel = f.relative_to(rod)
        if f.is_file() and not any(d.startswith(".") for d in rel.parts) and f.suffix != ".tmp":
            yield rel


def skriv(maal: Path, data: bytes) -> bool:
    """Skriver kun, hvis indholdet er nyt. Atomisk, så Syncthing aldrig sender en halv fil."""
    if maal.is_file() and maal.read_bytes() == data:
        return False
    maal.parent.mkdir(parents=True, exist_ok=True)
    tmp = maal.with_name(f".{maal.name}.tmp")
    tmp.write_bytes(data)
    tmp.replace(maal)
    return True


def kopier(kilde: Path, maal: Path) -> bool:
    st = kilde.stat()
    if maal.is_file():
        m = maal.stat()
        if m.st_size == st.st_size and int(m.st_mtime) == int(st.st_mtime):
            return False
    maal.parent.mkdir(parents=True, exist_ok=True)
    tmp = maal.with_name(f".{maal.name}.tmp")
    shutil.copy2(kilde, tmp)
    tmp.replace(maal)
    return True


def hent(sti: str, timeout=60) -> bytes:
    req = urllib.request.Request(KILDE + quote(sti, safe="/"), headers={"Host": VAERT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def filnavn(sti: str) -> str:
    """URL-sti -> fil i site/. En sti, der ender på /, er mappens index.html, som Caddy viser."""
    rel = sti.lstrip("/")
    return rel + "index.html" if rel.endswith("/") or not rel else rel


def pensum(site: Path) -> list[str]:
    """Forelæsninger og øvelser, som Fag-siden linker til (fra studie.json i kopien)."""
    try:
        S = json.loads((site / "studie" / "studie.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    ud = []
    for f in S.get("fag") or []:
        p = (f.get("status") or {}).get("pensum") or {}
        for x in (p.get("forelaesninger") or []) + (p.get("oevelser") or []):
            dele = [f.get("id"), x.get("mappe"), x.get("fil")]
            # Hver del bliver et mappe- eller filnavn i site/; "..", skjulte navne og skråstreger kunne skrive uden for den
            if all(isinstance(d, str) and d and not d.startswith(".") and "/" not in d and "\\" not in d for d in dele):
                ud.append("/studie/api/pensum/" + "/".join(dele))
    return ud


def mac_navn():
    """Mac'ens navn i tailnettet (fx <mac>.<tailnet>.ts.net), eller None uden Tailscale."""
    ts = TAILSCALE if os.access(TAILSCALE, os.X_OK) else shutil.which("tailscale")
    if not ts:
        return None
    try:
        ud = subprocess.run([ts, "status", "--json"], capture_output=True, text=True, timeout=10).stdout
        navn = json.loads(ud)["Self"]["DNSName"].rstrip(".")
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return None
    return navn if navn.endswith(".ts.net") else None


def baerbar(ud: Path, navn) -> bool:
    """Bærbarens filer med Mac'ens adresse sat ind. Uden Tailscale-navn bliver de gamle stående."""
    if not navn:
        print("kopi: fandt ikke Mac'ens Tailscale-navn; bærbarens Caddyfile er ikke opdateret", file=sys.stderr)
        return False
    for f in synlige(KOMPAS / "baerbar"):
        data = (KOMPAS / "baerbar" / f).read_bytes()
        if f.name == "Caddyfile":
            data = (data.decode("utf-8").replace("{{OPSTROEM}}", f"https://{navn}:8443")
                    .replace("{{MAC}}", f"{navn}:8443").encode("utf-8"))
        skriv(ud / "baerbar" / f, data)
    return True


def pausede_stier() -> tuple:
    """Stierne for projekter under `pause` i projekter.json (fx "/sprog/"). De kommer ikke med i kopien, og deres
    servere kaldes ikke: et læsekald kan få en server til at rydde op eller regne om, og det skal ikke ske under en pause."""
    try:
        pause = json.loads((STATISKE["kompas"] / "projekter.json").read_text(encoding="utf-8")).get("pause", [])
    except (OSError, ValueError, AttributeError):
        return ()
    return tuple(p["manifest"].rsplit("/", 1)[0] + "/" for p in pause if isinstance(p, dict) and p.get("manifest"))


def byg(ud: Path) -> bool:
    site = ud / "site"
    site.mkdir(parents=True, exist_ok=True)
    behold, ok, nye = {KOPI_INFO}, True, 0

    for prefiks, rod in STATISKE.items():
        if not rod.is_dir():
            print(f"kopi: {rod} findes ikke; /{prefiks}/ er ikke opdateret", file=sys.stderr)
            if (site / prefiks).is_dir():
                behold.update(f"{prefiks}/{rel}" for rel in synlige(site / prefiks))
            ok = False
            continue
        for rel in synlige(rod):
            behold.add(f"{prefiks}/{rel}")
            nye += kopier(rod / rel, site / prefiks / rel)

    stier = list(API)
    for prefiks, rod in SERVER_SIDER.items():
        stier += [f"/{prefiks}/"] + [f"/{prefiks}/{rel}" for rel in synlige(rod) if rel.name != "index.html"]
    pause = pausede_stier()
    stier = [s for s in stier if not s.startswith(pause)] if pause else stier
    for sti in stier:
        fil = filnavn(sti)
        behold.add(fil)
        try:
            nye += skriv(site / fil, hent(sti))
        except (urllib.error.URLError, OSError) as e:
            print(f"kopi: {sti} kunne ikke hentes ({e}); den gamle står", file=sys.stderr)
            ok = False

    # Pensum ændrer sig sjældent og fylder; en fil hentes kun, første gang den er på listen
    for sti in pensum(site):
        fil = filnavn(sti)
        behold.add(fil)
        if (site / fil).is_file():
            continue
        try:
            nye += skriv(site / fil, hent(sti, timeout=120))
        except (urllib.error.URLError, OSError) as e:
            print(f"kopi: {sti} kunne ikke hentes ({e})", file=sys.stderr)
            ok = False

    # Det, der ikke længere findes på Mac'en, forsvinder også fra kopien
    for rel in list(synlige(site)):
        if str(rel) not in behold:
            (site / rel).unlink()
            nye += 1
    for d in sorted((p for p in site.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        if not any(d.iterdir()):
            d.rmdir()

    navn = mac_navn()
    ok &= baerbar(ud, navn)
    skriv(site / KOPI_INFO, json.dumps({"bygget": datetime.now().astimezone().isoformat(timespec="seconds"),
                                        "mac": navn}, ensure_ascii=False).encode("utf-8"))
    print(f"kopi: {ud} ({nye} ændret)" + ("" if ok else ", med fejl"))
    return ok


if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--ud", type=Path, default=HJEM / "KompasKopi", help="mappen, Syncthing deler (standard ~/KompasKopi)")
    sys.exit(0 if byg(a.parse_args().ud) else 1)
