"""Demodata for Kompas' egen side Forbindelser (/kompas/forbindelser.json).

Den rigtige status skrives af bin/forbindelser.py, som undersøger maskinen (tidsstempler, servere, værktøjer).
Det må demoen ikke gøre på en fremmeds maskine, så her er et opdigtet statusbillede i samme form, med tider
omkring demoens "nu". Én forbindelse har en advarsel, så siden også viser, hvordan et problem ser ud.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

UGEDAGE = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _plan(nu: datetime, dage: list[int], time: int, minut: int, retning: int) -> datetime:
    """Seneste (retning=-1) eller næste (retning=1) gang på ugedagene `dage` (mandag = 0) kl. time:minut."""
    for n in range(0, 8):
        d = (nu + timedelta(days=retning * n)).date()
        t = datetime(d.year, d.month, d.day, time, minut).astimezone()
        if d.weekday() in dage and ((retning < 0 and t <= nu) or (retning > 0 and t > nu)):
            return t
    raise ValueError("ingen tid i planen")


def _punkt(navn, type_, projekt, status, tekst, sidst=None, naeste=None, hjaelp=None, link=None) -> dict:
    p = {"navn": navn, "type": type_, "projekt": projekt, "status": status, "tekst": tekst}
    p |= {k: v for k, v in (("sidst", sidst and _iso(sidst)), ("naeste", naeste and _iso(naeste)),
                            ("hjaelp", hjaelp), ("link", link)) if v}
    return p


def lav(ud: Path, idag: date) -> None:
    nu = datetime.now().astimezone()
    if nu.date() != idag:
        nu = datetime(idag.year, idag.month, idag.day, 10, 30).astimezone()
    for_ = lambda **kw: nu - timedelta(**kw)  # noqa: E731
    sidste_halve = nu.replace(minute=15 if nu.minute >= 15 else 45, second=4, microsecond=0)
    if sidste_halve > nu:
        sidste_halve -= timedelta(minutes=30)

    kilder = [
        _punkt("Garmin Connect", "API (uofficielt)", "Form & fokus", "ok", "hentes højst hver 3. time", for_(hours=1, minutes=40),
               link="https://connect.garmin.com"),
        _punkt("Hevy", "API-nøgle", "Form & fokus", "ok", "styrkepas hentes med Garmin", for_(hours=1, minutes=40),
               link="https://hevy.com/settings?developer"),
        _punkt("Kalendere", "iCal", "Form & fokus · Studie", "advarsel", "1 af 2 feeds kunne ikke hentes", sidste_halve,
               hjaelp="Se `~/.kompas/opdater.log`. Er en adresse udløbet, så kopiér en ny hemmelig iCal-adresse ind i "
                      "`GC_ICS_URLS` i `~/kompas/coach/.env`."),
        _punkt("Banken", "via Sure", "Økonomi", "ok", "bankerne synkroniseres, når Sure kører", for_(hours=7, minutes=12), link="/okonomi"),
        _punkt("Jobindex", "RSS", "Karriere", "ok", "hentes, når rutinen Karriere kører",
               _plan(nu, [0, 3], 12, 0, -1) + timedelta(minutes=6), link="/karriere/"),
        _punkt("Canvas", "downloads", "Studie", "info", "sorteres, når du kører scriptet", for_(days=3, hours=2),
               hjaelp="Flyt Canvas-downloads til fagmapperne: `node Scripts/canvas-sortering.js --kør` "
                      "(uden `--kør` er det en prøvekørsel)."),
    ]

    rutiner = [("Studie", "køreplan for næste uge", "Studie", [6], 18, 0),
               ("Træning", "14-dages rapport", "Form & fokus", [5], 10, 0),
               ("Overblik", "ugereview", "I dag · Form & fokus", [0], 7, 0),
               ("Karriere", "nye jobmatch", "Karriere", [0, 3], 12, 0)]
    claude = [_punkt("garmin-coach", "MCP-server", "Form & fokus", "ok", "svarer med 12 værktøjer · i Claude-appen (Chat og Code)")]
    for navn, skriver, projekt, dage, t, m in rutiner:
        hvornaar = (UGEDAGE[dage[0]] if len(dage) == 1 else " og ".join(UGEDAGE[d] for d in dage)) + f" kl. {t:02d}.{m:02d}"
        claude.append(_punkt(navn, "Claude-rutine", projekt, "ok", f"{skriver} · hver {hvornaar}",
                             _plan(nu, dage, t, m, -1) + timedelta(minutes=9), _plan(nu, dage, t, m, 1)))

    drift = [
        _punkt("Caddy", "webserver", "Kompas", "ok", "serverer kompas.localhost"),
        _punkt("Opdatering", "LaunchAgent", "Kompas", "ok", "henter og bygger hver halve time", sidste_halve),
        _punkt("Karriere-server", "LaunchAgent", "Karriere", "ok", "svarer på 127.0.0.1:8766"),
        _punkt("Studie-server", "LaunchAgent", "Studie", "ok", "svarer på 127.0.0.1:8767"),
        _punkt("Sure", "Docker (Colima)", "Økonomi", "info", "lukket, startes af Kompas-appen",
               hjaelp="Åbn Kompas-appen. Det tager ca. 30 sekunder."),
        _punkt("Tailscale", "VPN", "Studie", "ok", "På farten er tilgængelig på telefonen"),
        _punkt("Backup", "mappe i skyen", "Kompas", "ok", "coach.db og liv.db, 14 dage tilbage", for_(hours=9, minutes=3)),
    ]

    vaerktoejer = [
        ("Homebrew", "installerer resten", "4.6.3", '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'),
        ("Caddy", "kompas.localhost", "2.10.0", "brew install caddy"),
        ("Colima", "Docker-maskinen til Sure", "0.8.1", "brew install colima"),
        ("Docker", "Sure", "28.3.2", "brew install docker docker-compose"),
        ("Node.js", "Studie", "22.18.0", "brew install node"),
        ("Python", "Form & fokus, Karriere", "3.13.5", "brew install python"),
        ("SQLite", "backup", "3.50.2", "brew install sqlite"),
        ("Git", "projekterne", "2.50.1", "xcode-select --install"),
        ("Tailscale", "telefonen (valgfri)", "1.86.2", "https://tailscale.com/download"),
        ("GitHub CLI", "GitHub (valgfri)", None, "brew install gh"),
    ]

    data = {
        "genereret": _iso(sidste_halve + timedelta(seconds=2)),
        "kilde": "kompas/bin/forbindelser.py (via opdater.sh) · demodata",
        "grupper": [
            {"id": "kilder", "titel": "Datakilder", "undertitel": "Hvor tallene kommer fra", "punkter": kilder},
            {"id": "claude", "titel": "Claude", "undertitel": "MCP-server og planlagte rutiner", "punkter": claude},
            {"id": "drift", "titel": "Kører i baggrunden", "undertitel": "Servere, baggrundsjob og backup", "punkter": drift},
        ],
        "vaerktoejer": [{"navn": n, "til": til, "version": v, "installeret": v is not None,
                         "status": "ok" if v else ("info" if "valgfri" in til else "fejl"), "kommando": k}
                        for n, til, v, k in vaerktoejer],
        "mcp": {"navn": "garmin-coach", "command": "/Users/alex/kompas/coach/.venv/bin/python",
                "args": ["-m", "garmin_coach.server"],
                "env": {"GC_DB": "/Users/alex/.garmin-coach/coach.db", "GARMINTOKENS": "/Users/alex/.garminconnect",
                        "GC_TZ": "Europe/Copenhagen"},
                "desktop": True, "code": False},
    }
    mappe = ud / "kompas"
    mappe.mkdir(parents=True, exist_ok=True)
    (mappe / "forbindelser.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
