#!/usr/bin/env python3
"""Status for alt, Kompas henter fra og kører på, til siden Forbindelser (/kompas/forbindelser.html).

Køres af opdater.sh hvert 30. minut og skriver public/forbindelser.json (ikke i git). Læser kun: tidsstempler,
opdater.sh's statusfil og om noget er sat op. Hemmeligheder (kalender-URL'er, API-nøgler, tokens) læses aldrig ud; der tjekkes kun,
om de findes. Status regnes her, så siden kun viser den:
  ok        virker og er frisk
  advarsel  virker, men er gammel eller har fejlet én gang
  fejl      virker ikke
  info      ikke en fejl (lukket med vilje, manuel, ikke sat op)

    /usr/bin/python3 bin/forbindelser.py        (standardbiblioteket, Python 3.9+)
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HJEM = Path.home()
KOMPAS = HJEM / "kompas"
UD = KOMPAS / "public" / "forbindelser.json"
STATE = HJEM / ".kompas"
KOPI = HJEM / "KompasKopi"  # kopien til bærbaren (bin/kopi.py)
COACH = KOMPAS / "coach"
COACH_DB = HJEM / ".garmin-coach" / "coach.db"
SURE_DATA = KOMPAS / "okonomi" / "dashboard" / "public" / "data.json"
SKAERMTID = STATE / "skaermtid" / "skaermtid.json"
SEMESTER = Path(os.environ.get("KOMPAS_SEMESTER", KOMPAS / "studie"))
CLAUDE_DESKTOP = HJEM / "Library/Application Support/Claude/claude_desktop_config.json"
CLAUDE_CODE = HJEM / ".claude.json"
APP_SESSIONER = HJEM / "Library/Application Support/Claude/claude-code-sessions"
TAILSCALE = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
NU = datetime.now(timezone.utc)
TIME = 3600


# ── små hjælpere ──────────────────────────────────────────────────────────────
def iso(t):
    return t.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z") if t else None


def mtime(p):
    try:
        return datetime.fromtimestamp(Path(p).stat().st_mtime, timezone.utc)
    except OSError:
        return None


def tid(s):
    """ISO-tekst (med eller uden zone; uden zone er lokal tid) → datetime i UTC."""
    if not s:
        return None
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.astimezone(timezone.utc) if t.tzinfo else t.astimezone().astimezone(timezone.utc)


def alder(t):
    return (NU - t).total_seconds() if t else None


def frisk(t, graense, ok_tekst, gammel_tekst):
    """ok, hvis t er nyere end graense sekunder, ellers advarsel. Ingen tid er en fejl."""
    if not t:
        return "fejl", "ingen kørsel fundet"
    return ("ok", ok_tekst) if alder(t) <= graense else ("advarsel", gammel_tekst)


def koer(*cmd, timeout=5):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env={**os.environ, "PATH": PATH})
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def http(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def env_noegler(fil):
    """Kun navnene på nøgler med en værdi; værdierne forlader aldrig funktionen."""
    ud = {}
    try:
        for linje in Path(fil).read_text().splitlines():
            m = re.match(r"\s*([A-Z0-9_]+)\s*=\s*(.*)$", linje)
            if m:
                ud[m.group(1)] = bool(m.group(2).strip().strip('"\''))
    except OSError:
        pass
    return ud


def env_antal(fil, noegle):
    """Antal komma-adskilte værdier i en nøgle (fx kalender-feeds), uden at give værdierne videre."""
    try:
        for linje in Path(fil).read_text().splitlines():
            m = re.match(rf"\s*{noegle}\s*=\s*(.*)$", linje)
            if m:
                return len([x for x in m.group(1).strip().strip('"\'').split(",") if x.strip()])
    except OSError:
        pass
    return 0


def db_vaerdi(db, sql, *args):
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
        try:
            row = con.execute(sql, args).fetchone()
        finally:
            con.close()
        return row[0] if row else None
    except sqlite3.Error:
        return None


# opdater.sh's trin (id'erne i dens statusfil) → navne på siden. Et ukendt id vises, som det er.
TRIN = {"garmin": "garmin", "kalender": "kalender", "form-byg": "Form & fokus-byg", "overblik": "Overblik",
        "studie-eksport": "studie-eksporten", "aw-sync": "aw-sync", "skaermtid": "Skærmtid",
        "kopi": "kopien til bærbaren"}


def seneste_koersel(fil=STATE / "opdater-status.json"):
    """Sidste fuldførte kørsel af opdater.sh: tidspunkt, id'erne på de trin der fejlede, og antal kalenderfeeds,
    der ikke kunne hentes (None, når kalenderen ikke nåede at svare)."""
    try:
        d = json.loads(Path(fil).read_text())
    except (OSError, ValueError):
        return None, set(), None
    fejl = {i for i, udfald in (d.get("trin") or {}).items() if udfald != "ok"}
    return tid(d.get("slut")), fejl, d.get("kalenderfeeds_fejlede")


# ── cron (rutinernes tidsplaner, lokal tid) ───────────────────────────────────
def _felt(s, lav, hoej):
    ud = set()
    for del_ in s.split(","):
        trin = 1
        if "/" in del_:
            del_, t = del_.split("/")
            trin = int(t)
        if del_ == "*":
            a, b = lav, hoej
        elif "-" in del_:
            a, b = map(int, del_.split("-"))
        else:
            a = b = int(del_)
        ud.update(range(a, b + 1, trin))
    return ud


def cron_tider(udtryk, retning, nu=None):
    """Seneste (retning=-1) eller næste (retning=1) tidspunkt før/efter nu, cron-udtrykket rammer, i UTC."""
    try:
        mi, ti, dag, md, ug = udtryk.split()
        M, T, D, MD = _felt(mi, 0, 59), _felt(ti, 0, 23), _felt(dag, 1, 31), _felt(md, 1, 12)
        UG = {u % 7 for u in _felt(ug, 0, 7)}  # 0 og 7 er søndag
    except ValueError:
        return None
    nu = (nu or NU).astimezone()
    for n in range(0, 62):
        d = (nu + timedelta(days=retning * n)).date()
        if d.month not in MD or d.day not in D or (d.isoweekday() % 7) not in UG:
            continue
        tider = sorted((datetime(d.year, d.month, d.day, t, m).astimezone() for t in T for m in M), reverse=retning < 0)
        for t in tider:
            if (retning < 0 and t <= nu) or (retning > 0 and t > nu):
                return t.astimezone(timezone.utc)
    return None


def app_rutiner():
    """Claude-appens egne rutiner: id → navn, tidsplan, slået til, seneste kørsel, oprettet. Kun de felter."""
    for fil in sorted(APP_SESSIONER.glob("*/*/scheduled-tasks.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            opgaver = json.loads(fil.read_text()).get("scheduledTasks", [])
        except (OSError, ValueError):
            continue
        # Rutinerne hedder "Kompas · Studie" osv. i appen; inde i Kompas er forstavelsen overflødig
        return {o.get("id"): {"navn": (o.get("displayName") or o.get("id")).removeprefix("Kompas · "), "cron": o.get("cronExpression"),
                              "slaaet_til": o.get("enabled", True), "sidst": tid(o.get("lastRunAt")),
                              "oprettet": datetime.fromtimestamp(o["createdAt"] / 1000, timezone.utc)
                              if isinstance(o.get("createdAt"), (int, float)) else None} for o in opgaver}
    return None


def punkt(navn, type_, projekt, status, tekst, sidst=None, hjaelp=None, link=None, naeste=None):
    return {k: v for k, v in dict(navn=navn, type=type_, projekt=projekt, status=status, tekst=tekst, sidst=iso(sidst),
                                   naeste=iso(naeste), hjaelp=hjaelp, link=link).items() if v is not None}


# ── datakilder ────────────────────────────────────────────────────────────────
def datakilder(koersel, fejl, feeds):
    ud = []
    env = env_noegler(COACH / ".env")
    aaben = "Den hentes, når Kompas kører. Åbn Kompas-appen."

    t = mtime(STATE / "garmin-sidst")
    s, tekst = frisk(t, 26 * TIME, "hentes højst hver 3. time", "ikke hentet i over et døgn")
    if "garmin" in fejl:
        s, tekst = "fejl", "sidste hentning fejlede"
    ud.append(punkt("Garmin Connect", "API (uofficielt)", "Form & fokus", s, tekst, t,
                    hjaelp=None if s == "ok" else f"{aaben} Fejler den igen, så log ind på ny: "
                    "`cd ~/kompas/coach && .venv/bin/python -m garmin_coach.ingest_garmin --login`",
                    link="https://connect.garmin.com"))

    if env.get("HEVY_API_KEY") or os.environ.get("HEVY_API_KEY"):
        t = tid(db_vaerdi(COACH_DB, "SELECT value FROM sync_state WHERE key = 'last_hevy_sync'"))
        s, tekst = frisk(t, 26 * TIME, "styrkepas hentes med Garmin", "ikke hentet i over et døgn")
        if db_vaerdi(COACH_DB, "SELECT value FROM sync_state WHERE key = 'last_hevy_error'"):
            s, tekst = "fejl", "sidste hentning fejlede"
        ud.append(punkt("Hevy", "API-nøgle", "Form & fokus", s, tekst, t,
                        hjaelp=None if s == "ok" else aaben, link="https://hevy.com/settings?developer"))
    else:
        ud.append(punkt("Hevy", "API-nøgle", "Form & fokus", "info", "ikke sat op",
                        hjaelp="Sæt `HEVY_API_KEY` i `~/kompas/coach/.env` (Hevy Pro → Settings → Developer).",
                        link="https://hevy.com/settings?developer"))

    n = env_antal(COACH / ".env", "GC_ICS_URLS")
    if not n:
        ud.append(punkt("Kalendere", "iCal", "Form & fokus · Studie", "fejl", "ingen kalender sat op",
                        hjaelp="Sæt `GC_ICS_URLS` i `~/kompas/coach/.env`: hemmelige iCal-adresser, adskilt med komma."))
    else:
        s, tekst = frisk(koersel, 2 * TIME, f"{n} feed{'s' if n != 1 else ''}, hentes hver halve time",
                         f"{n} feed{'s' if n != 1 else ''}, ikke hentet i over to timer")
        if "kalender" in fejl:
            s, tekst = "fejl", "sidste hentning fejlede"
        elif feeds:
            s, tekst = ("fejl" if feeds >= n else "advarsel"), f"{feeds} af {n} feeds kunne ikke hentes"
        ud.append(punkt("Kalendere", "iCal", "Form & fokus · Studie", s, tekst, koersel,
                        hjaelp=None if s == "ok" else "Se `~/.kompas/opdater.log`. Er en adresse udløbet, så kopiér "
                        "en ny hemmelig iCal-adresse ind i `GC_ICS_URLS` i `~/kompas/coach/.env`."))

    try:
        d = json.loads(SURE_DATA.read_text())
        t = tid(d.get("last_sync"))
        s, tekst = frisk(t, 3 * 24 * TIME, "bankerne synkroniseres, når Sure kører", "ikke synkroniseret i over tre dage")
        ud.append(punkt("Banken", "via Sure", "Økonomi", s, tekst, t,
                        hjaelp=None if s == "ok" else "Sure synkroniserer kun, mens den kører. Åbn Kompas-appen.",
                        link="/okonomi"))
    except (OSError, ValueError):
        ud.append(punkt("Banken", "via Sure", "Økonomi", "fejl", "Sures udtræk mangler",
                        hjaelp="Åbn Kompas-appen, så laves udtrækket (`okonomi/dashboard/export.sh`)."))

    # Filens tid, ikke dens indhold: under launchd må python stat'e filer i OneDrive, men ikke læse dem
    t = mtime(SEMESTER / "Scripts" / "canvas-log.txt")
    ud.append(punkt("Canvas", "downloads", "Studie", "info", "sorteres, når du kører scriptet", t,
                    hjaelp="Flyt Canvas-downloads til fagmapperne: `node Scripts/canvas-sortering.js --kør` "
                    "(uden `--kør` er det en prøvekørsel)."))
    return ud + skaermtid_enheder()


def skaermtid_enheder(fil=SKAERMTID, nu=None):
    """Ét punkt pr. enhed i Skærmtid: hvornår ActivityWatch dér sidst sendte data (`enheder[].sidst`, som
    skaermtid.py skriver). Samme grænse som Skærmtid-siden: to hele dage uden data er en advarsel, undtagen for en
    enhed med `sjaelden` i regler.json, som du sjældent bruger; den står som info."""
    nu = (nu or NU).astimezone()
    try:
        enheder = json.loads(Path(fil).read_text()).get("enheder") or []
    except (OSError, ValueError):
        return [punkt("ActivityWatch", "enheder", "Skærmtid", "fejl", "Skærmtid er ikke bygget",
                      hjaelp="Se linjerne med `skaermtid` i `~/.kompas/opdater.log`.")]
    ud = []
    for e in enheder:
        navn, t = e.get("navn") or "?", tid(e.get("sidst"))
        if not e.get("kendt"):
            ud.append(punkt(f"Skærmtid · {navn}", "ActivityWatch", "Skærmtid", "info", "ukendt enhed sender data", t,
                            hjaelp="Giv værtsnavnet et navn i `~/kompas/skaermtid/regler.json`.", link="/skaermtid/"))
            continue
        dage = (nu.date() - t.astimezone().date()).days if t else None
        if e.get("sjaelden") and (dage is None or dage >= 2):
            s, tekst = "info", "bruges sjældent" + (f" · ingen data i {dage} dage" if dage is not None else "")
        elif dage is None:
            s, tekst = "advarsel", "har aldrig sendt data"
        elif dage >= 2:
            s, tekst = "advarsel", f"ingen data i {dage} dage"
        else:
            s, tekst = "ok", "sender data"
        ud.append(punkt(f"Skærmtid · {navn}", "ActivityWatch", "Skærmtid", s, tekst, t, link="/skaermtid/",
                        hjaelp=None if s in ("ok", "info") else "Tjek, at ActivityWatch kører på enheden, og at Syncthing har sendt "
                        "`~/ActivityWatchSync` til Mac'en (se `skaermtid/OPSAETNING.md`)."))
    return ud


# ── Claude ────────────────────────────────────────────────────────────────────
MCP_ENV = ("GC_DB", "GARMINTOKENS", "GC_TZ")  # stier og tidszone, aldrig hemmeligheder
# Rutinerne, Kompas viser: id på den planlagte opgave i Claude-appen → hvad den skriver, og hvilket område.
# Ret id'erne, så de passer til dine egne planlagte opgaver.
RUTINE_INFO = {
    "studie-koereplan": ("køreplan for næste uge", "Studie"),
    "traening-rapport": ("vurdering af perioden", "Form & fokus"),
    "overblik-ugereview": ("ugereview", "I dag · Form & fokus"),
    "sprog-ugen": ("nye sprogkort og ugens tekst", "Sprog"),
    "skaermtid-ugen": ("ugens gennemgang og kategorierne", "Skærmtid"),
}
UGEDAGE = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]


def mcp_konfig():
    """garmin-coach fra Claude-appens konfiguration. Den fulde env bruges kun til at starte serveren i testen."""
    try:
        cfg = json.loads(CLAUDE_DESKTOP.read_text()).get("mcpServers", {}).get("garmin-coach", {})
    except (OSError, ValueError):
        cfg = {}
    return cfg


def i_claude_code(navn):
    try:
        d = json.loads(CLAUDE_CODE.read_text())
    except (OSError, ValueError):
        return False
    return navn in d.get("mcpServers", {}) or any(navn in p.get("mcpServers", {}) for p in d.get("projects", {}).values())


def mcp_haandtryk(cfg, timeout=20):
    """Starter serveren, som Claude gør, og laver MCP-håndtrykket (initialize + tools/list).
    Svarer (antal værktøjer, None) eller (None, kort fejl). Kalder aldrig selv et værktøj."""
    kommando = [cfg.get("command") or str(COACH / ".venv/bin/python")] + list(cfg.get("args") or ["-m", "garmin_coach.server"])
    beskeder = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "kompas-forbindelser", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    # stdin holdes åben, til svaret på tools/list er kommet: lukkes den straks, stopper serveren ved EOF,
    # før den når at svare på andet end initialize.
    try:
        p = subprocess.Popen(kommando, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             text=True, cwd=str(COACH),
                             env={**os.environ, "PATH": PATH, **{k: str(v) for k, v in (cfg.get("env") or {}).items()}})
    except OSError as e:
        return None, f"kunne ikke starte ({e.strerror})"
    vagt = threading.Timer(timeout, p.kill)
    vagt.start()
    try:
        p.stdin.write("".join(json.dumps(b) + "\n" for b in beskeder))
        p.stdin.flush()
        for linje in p.stdout:
            try:
                svar = json.loads(linje)
            except ValueError:
                continue
            if svar.get("id") == 2:
                if "result" in svar:
                    return len(svar["result"].get("tools", [])), None
                return None, "svarede med en fejl på tools/list"
    except OSError:
        pass
    finally:
        vagt.cancel()
        p.kill()
        p.wait()
    return None, "svarede ikke på håndtrykket"


def plan_tekst(cron):
    """'0 12 * * 1,4' → 'mandag og torsdag kl. 12.00'."""
    try:
        mi, ti, _, _, ug = cron.split()
        dage = sorted({(u - 1) % 7 for u in _felt(ug, 0, 7)})  # mandag = 0
        t, m = _felt(ti, 0, 23), _felt(mi, 0, 59)
    except (ValueError, AttributeError):
        return None
    navne = [UGEDAGE[d] for d in dage]
    dagtekst = "dag" if len(dage) == 7 else navne[0] if len(navne) == 1 else ", ".join(navne[:-1]) + " og " + navne[-1]
    kl = f" kl. {min(t):02d}.{min(m):02d}" if len(t) == 1 and len(m) == 1 else ""
    return dagtekst + kl


def claude(cfg, rutiner, nu=NU):
    ud = []
    if not cfg:
        ud.append(punkt("garmin-coach", "MCP-server", "Form & fokus", "info", "ikke sat op i Claude-appen",
                        hjaelp="Se guiden nedenfor."))
    else:
        antal, fejl = mcp_haandtryk(cfg)
        ud.append(punkt("garmin-coach", "MCP-server", "Form & fokus", "ok" if antal else "fejl",
                        f"svarer med {antal} værktøjer · i Claude-appen (Chat og Code)" if antal else fejl,
                        hjaelp=None if antal else "Prøv selv: `cd ~/kompas/coach && .venv/bin/python -c \"import garmin_coach.server\"`. "
                        "Virker det, så genstart Claude-appen."))

    if rutiner is None:
        ud.append(punkt("Rutiner", "Claude-rutine", "Kompas", "info", "kan ikke læse Claude-appens rutiner",
                        hjaelp="Se dem under Rutiner i Claude-appen."))
        return ud
    for rid, (skriver, projekt) in RUTINE_INFO.items():
        r = rutiner.get(rid)
        if not r:
            ud.append(punkt(rid, "Claude-rutine", projekt, "fejl", "findes ikke i Claude-appen",
                            hjaelp=f"Instruktionerne ligger i `~/.claude/scheduled-tasks/{rid}/SKILL.md`. Opret rutinen igen."))
            continue
        forrige, naeste = cron_tider(r["cron"], -1, nu), cron_tider(r["cron"], 1, nu)
        hvornaar = plan_tekst(r["cron"]) or "uden fast tid"
        # Sprunget over = den forrige planlagte kørsel kom ikke, og der er gået mindst en halv periode siden sidste
        # kørsel. Det sidste krav undgår falske advarsler lige efter, at tidsplanen er ændret. En rutine oprettet efter
        # det forrige tidspunkt har ikke sprunget noget over.
        periode = (naeste - forrige) if forrige and naeste else None
        oprettet = r.get("oprettet")
        sprunget = bool(forrige and periode and not (oprettet and oprettet > forrige) and (not r["sidst"] or (
            r["sidst"] < forrige - timedelta(minutes=1) and forrige - r["sidst"] >= periode / 2)))
        if not r["slaaet_til"]:
            s, tekst = "advarsel", f"{skriver} · slået fra"
        elif not sprunget:
            s, tekst = "ok", f"{skriver} · hver {hvornaar}"
        elif (nu - forrige).total_seconds() < 3 * TIME:  # appen lægger op til et kvarter til tidsplanen
            s, tekst = "ok", f"{skriver} · kører om lidt"
        else:
            l = forrige.astimezone()
            s, tekst = "advarsel", f"{skriver} · skulle have kørt {UGEDAGE[l.weekday()]} kl. {l:%H.%M}"
        if s == "ok":
            hjaelp = None
        elif not r["slaaet_til"]:
            hjaelp = (f"Rutinen er slået fra i Claude-appen. Slå den til under Rutiner (Kompas · {r['navn']}), "
                      "eller lad den være, hvis det er med vilje.")
        else:
            hjaelp = ("Rutiner kører kun, mens Claude-appen er åben, og en glemt kørsel tages, næste gang appen åbnes. "
                      f"Du kan også køre den nu under Rutiner ({r['navn']}).")
        ud.append(punkt(r["navn"], "Claude-rutine", projekt, s, tekst, r["sidst"], naeste=naeste if r["slaaet_til"] else None,
                        hjaelp=hjaelp))
    return ud


def mcp_guide(cfg):
    """Konfigurationen til guiden: kommandoen, de faste argumenter og kun de kendte, ufarlige env-værdier.
    Argumenterne fra Claudes konfiguration vises aldrig, for en hemmelighed kan stå dér (fx --token …), og
    kommandoen kun, når den er stien til en fil."""
    env = {k: v for k, v in (cfg.get("env") or {}).items() if k in MCP_ENV}
    env.setdefault("GC_DB", str(COACH_DB))
    env.setdefault("GARMINTOKENS", str(HJEM / ".garminconnect"))
    kommando = cfg.get("command")
    if not (isinstance(kommando, str) and Path(kommando).is_absolute() and Path(kommando).is_file()):
        kommando = str(COACH / ".venv/bin/python")
    return {"navn": "garmin-coach", "command": kommando, "args": ["-m", "garmin_coach.server"], "env": env,
            "desktop": bool(cfg), "code": i_claude_code("garmin-coach")}


# ── drift ─────────────────────────────────────────────────────────────────────
def drift(koersel, fejl):
    ud = []
    caddy_koerer = koer("pgrep", "-x", "caddy")[0] == 0
    ud.append(punkt("Caddy", "webserver", "Kompas", "ok" if caddy_koerer else "fejl",
                    "serverer kompas.localhost" if caddy_koerer else "kører ikke",
                    hjaelp=None if caddy_koerer else "`brew services start caddy`"))

    s, tekst = frisk(koersel, 45 * 60, "henter og bygger hver halve time", "har ikke kørt den sidste halve time")
    andre = sorted(TRIN.get(i, i) for i in fejl - {"garmin", "kalender"})
    hjaelp = None if s == "ok" else "Den er slået fra, når Kompas er lukket. Åbn Kompas-appen. Log: `~/.kompas/opdater.log`"
    if andre:
        # Opdateringen kørte; det er et af dens trin, der fejlede. Trinnet står med sin egen linje i loggen.
        s, tekst = "advarsel", "sidste kørsel: " + ", ".join(andre) + " fejlede"
        hjaelp = "Se, hvad der fejlede, i `~/.kompas/opdater.log` (de sidste linjer før \"færdig med fejl\")."
    ud.append(punkt("Opdatering", "LaunchAgent", "Kompas", s, tekst, koersel, hjaelp=hjaelp))

    for navn, port, label, projekt, log in [("Studie-server", 8767, "studie", "Studie", "studie-server.log"),
                                            ("Sprog-server", 8769, "sprog", "Sprog", "sprog-server.log"),
                                            ("Skærmtid-server", 8770, "skaermtid", "Skærmtid", "skaermtid-server.log")]:
        oppe = http(f"http://127.0.0.1:{port}/") is not None
        ud.append(punkt(navn, "LaunchAgent", projekt, "ok" if oppe else "fejl",
                        f"svarer på 127.0.0.1:{port}" if oppe else "svarer ikke",
                        hjaelp=None if oppe else f"`launchctl kickstart -k gui/$(id -u)/local.kompas.{label}` "
                        f"(log: `~/.kompas/{log}`)"))

    oppe = http("http://127.0.0.1:3000/up") == 200
    ud.append(punkt("Sure", "Docker (Colima)", "Økonomi", "ok" if oppe else "info",
                    "kører" if oppe else "lukket, startes af Kompas-appen",
                    hjaelp=None if oppe else "Åbn Kompas-appen. Det tager ca. 30 sekunder."))

    ts = TAILSCALE if os.access(TAILSCALE, os.X_OK) else shutil.which("tailscale", path=PATH)
    if not ts:
        ud.append(punkt("Tailscale", "VPN", "Kompas", "info", "ikke installeret (kun til telefonen og bærbaren)",
                        link="https://tailscale.com/download"))
    else:
        rc, ud_json = koer(ts, "status", "--json")
        try:
            koerer = rc == 0 and json.loads(ud_json).get("BackendState") == "Running"
        except ValueError:
            koerer = False
        rc, serve = koer(ts, "serve", "status", "--json")
        # 8768 er Caddys blok til telefonen (På farten), 8771 hele Kompas til bærbaren (se bin/tailscale.sh)
        mangler = [hvad for hvad, port in (("telefonen", "8768"), ("bærbaren", "8771")) if f"127.0.0.1:{port}" not in serve]
        s = "ok" if koerer and not mangler else "advarsel" if koerer else "info"
        ud.append(punkt("Tailscale", "VPN", "Kompas", s,
                        "På farten på telefonen og hele Kompas på bærbaren" if s == "ok" else
                        f"kører, men deler ikke Kompas med {' og '.join(mangler)}" if koerer else "ikke forbundet",
                        hjaelp=None if s == "ok" else "`~/kompas/bin/tailscale.sh`" if koerer
                        else "Åbn Tailscale og log ind, hvis du vil bruge Kompas på telefonen eller bærbaren."))

    ud.append(kopi_punkt(fejl))

    # backup-data.sh noterer dagens backup; backupmappen i skyen kan ikke listes, når launchd starter os
    t = mtime(STATE / "backup-sidst")
    s, tekst = frisk(t, 2 * 24 * TIME, "coach.db, liv.db, Sprogs data og ActivityWatch, 14 dage tilbage", "ingen backup de sidste to dage")
    ud.append(punkt("Backup", "mappe i skyen", "Kompas", s, tekst, t,
                    hjaelp=None if s == "ok" else "`~/kompas/bin/backup-data.sh --tving`"))
    return ud


def kopi_punkt(fejl, fil=KOPI / "site" / "kompas" / "kopi.json", nu=None):
    """Kopien til bærbaren. bin/kopi.py skriver kopi.json til sidst i hver kørsel, også når noget ikke kunne
    hentes, så filens alder siger kun, at kopien er bygget. Om det lykkedes, står i opdateringens trin `kopi`;
    ellers ville punktet sige ok, mens Opdatering siger, at kopien fejlede."""
    t = mtime(fil)
    if not t:
        s, tekst = "fejl", "ingen kørsel fundet"
    elif ((nu or NU) - t).total_seconds() > 45 * 60:
        s, tekst = "advarsel", "ikke bygget den sidste halve time"
    elif "kopi" in fejl:
        s, tekst = "advarsel", "bygget, men sidste kørsel fejlede"
    else:
        s, tekst = "ok", "bygget den sidste halve time; Syncthing sender den til bærbaren"
    if s == "ok":
        hjaelp = None
    elif "kopi" in fejl:
        hjaelp = ("Linjerne med `kopi:` i `~/.kompas/opdater.log` siger, hvad der ikke kunne hentes; resten af kopien "
                  "er bygget. Byg igen: `/usr/bin/python3 ~/kompas/bin/kopi.py`")
    else:
        hjaelp = ("Den bygges af opdateringen. Log: `~/.kompas/opdater.log` (linjerne med `kopi:`). "
                  "Byg nu: `/usr/bin/python3 ~/kompas/bin/kopi.py`")
    return punkt("Kopi til bærbaren", "Syncthing", "Kompas", s, tekst, t, hjaelp=hjaelp)


# ── værktøjer ─────────────────────────────────────────────────────────────────
VAERKTOEJER = [
    # navn, kommando(er), versionsflag, bruges til, installation
    ("Homebrew", ["brew"], "--version", "Caddy, Colima, Docker, gh", "/bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""),
    ("Caddy", ["caddy"], "version", "kompas.localhost", "brew install caddy"),
    ("Colima", ["colima"], "version", "Docker-maskinen til Sure", "brew install colima"),
    ("Docker", ["docker"], "--version", "Sure", "brew install docker docker-compose"),
    # Node og Python kan komme fra Homebrew eller fra installerne på nodejs.org og python.org. Installernes faste
    # stier prøves først, fordi Studie-serveren og opdater.sh kører /usr/local/bin/node, og LaunchAgents ikke har
    # Homebrews PATH; ellers bruges den, der ligger på PATH.
    ("Node.js", ["/usr/local/bin/node", "node"], "--version", "Studie, Sprog, opdater.sh", "https://nodejs.org/en/download"),
    ("Python", ["/Library/Frameworks/Python.framework/Versions/Current/bin/python3", "python3"], "--version",
     "Form & fokus, Overblik, Excel", "https://www.python.org/downloads/macos/"),
    ("SQLite", ["sqlite3"], "--version", "backup", "brew install sqlite"),
    ("Git", ["git"], "--version", "projekterne", "xcode-select --install"),
    ("Tailscale", [TAILSCALE, "tailscale"], "version", "telefonen og bærbaren (valgfri)", "https://tailscale.com/download"),
    ("GitHub CLI", ["gh"], "--version", "GitHub (valgfri)", "brew install gh"),
]


def vaerktoejer():
    ud = []
    for navn, cmds, flag, til, install in VAERKTOEJER:
        sti = next((c if os.path.isabs(c) and os.access(c, os.X_OK) else shutil.which(c, path=PATH)
                    for c in cmds if (os.path.isabs(c) and os.access(c, os.X_OK)) or shutil.which(c, path=PATH)), None)
        version = None
        if sti:
            _, out = koer(sti, flag)
            m = re.search(r"\d+\.\d+(\.\d+)?", out)
            version = m.group(0) if m else None
        valgfri = "valgfri" in til
        ud.append({"navn": navn, "til": til, "version": version, "installeret": bool(sti),
                   "status": "ok" if sti else "info" if valgfri else "fejl", "kommando": install})
    return ud


# ── projekter på pause ────────────────────────────────────────────────────────
def pausede(fil=KOMPAS / "public" / "projekter.json"):
    """Projekterne under `pause` i projekter.json: {projekt: {siden, hvorfor}}. Ingen fil eller ingen pause giver {}."""
    try:
        return {p["projekt"]: p for p in json.loads(fil.read_text()).get("pause", []) if p.get("projekt")}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def paa_pause(grupper, pause):
    """Et projekt på pause er det med vilje: dets punkter (rutinen, datakilden, serveren) vises ikke. Siden nævner i stedet
    pausen én gang (feltet `pause` i forbindelser.json), så det er tydeligt, at de mangler med vilje."""
    for g in grupper:
        g["punkter"] = [p for p in g["punkter"] if p.get("projekt") not in pause]
    return [g for g in grupper if g["punkter"]]


def main():
    koersel, fejl, feeds = seneste_koersel()
    cfg, rutiner = mcp_konfig(), app_rutiner()
    grupper = [
        {"id": "kilder", "titel": "Datakilder", "undertitel": "Hvor tallene kommer fra",
         "punkter": datakilder(koersel, fejl, feeds)},
        {"id": "claude", "titel": "Claude", "undertitel": "MCP-server og planlagte rutiner", "punkter": claude(cfg, rutiner)},
        {"id": "drift", "titel": "Kører i baggrunden", "undertitel": "Servere, baggrundsjob og backup", "punkter": drift(koersel, fejl)},
    ]
    pause = pausede()
    grupper = paa_pause(grupper, pause)
    data = {"genereret": iso(NU), "kilde": "kompas/bin/forbindelser.py (via opdater.sh)", "grupper": grupper,
            "pause": [{"projekt": n, "siden": pp.get("siden"), "hvorfor": pp.get("hvorfor")} for n, pp in pause.items()],
            "vaerktoejer": vaerktoejer(), "mcp": mcp_guide(cfg)}
    UD.parent.mkdir(parents=True, exist_ok=True)
    tmp = UD.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.replace(UD)


if __name__ == "__main__":
    main()
