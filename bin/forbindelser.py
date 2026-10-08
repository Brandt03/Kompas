#!/usr/bin/env python3
"""Status for alt, Kompas henter fra og kører på, til siden Forbindelser (/kompas/forbindelser.html).

Køres af opdater.sh hvert 30. minut og skriver public/forbindelser.json (ikke i git). Læser kun: tidsstempler,
logs og om noget er sat op. Hemmeligheder (kalender-URL'er, API-nøgler, tokens) læses aldrig ud; der tjekkes kun,
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
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HJEM = Path.home()
KOMPAS = HJEM / "kompas"
UD = KOMPAS / "public" / "forbindelser.json"
STATE = HJEM / ".kompas"
COACH = KOMPAS / "coach"
COACH_DB = HJEM / ".garmin-coach" / "coach.db"
SURE_DATA = KOMPAS / "okonomi" / "dashboard" / "public" / "data.json"
KARRIERE = KOMPAS / "karriere"
SEMESTER = Path(os.environ.get("KOMPAS_SEMESTER", KOMPAS / "studie"))
BACKUP = Path(os.environ.get("KOMPAS_BACKUP", HJEM / "Backup" / "kompas"))  # som backup-data.sh
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


# opdater.sh's fejllinjer → faste navne. Rå loglinjer vises aldrig: kalenderens fejl indeholder starten af en
# hemmelig iCal-adresse.
TRIN = {"Garmin fejlede": "garmin", "kalenderen fejlede": "kalender", "Form & Fokus-byg fejlede": "Form & fokus-byg",
        "overblik fejlede": "Overblik", "studie-eksporten fejlede": "studie-eksporten", "forbindelser fejlede": "Forbindelser"}


def seneste_koersel():
    """Sidste kørsel af opdater.sh: tidspunkt, de trin der fejlede, og (fejlede, i alt) kalenderfeeds."""
    try:
        linjer = (STATE / "opdater.log").read_text(errors="ignore").splitlines()
    except OSError:
        return None, set(), None
    ok = [i for i, l in enumerate(linjer) if re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ok$", l)]
    if not ok:
        return None, set(), None
    start = ok[-2] + 1 if len(ok) > 1 else 0
    t = datetime.strptime(linjer[ok[-1]][:19], "%Y-%m-%d %H:%M:%S").astimezone(timezone.utc)
    koersel = linjer[start:ok[-1]]
    fejl = {navn for l in koersel for moenster, navn in TRIN.items() if moenster in l}
    feeds = next(((int(m.group(1)), int(m.group(2))) for l in koersel
                  for m in [re.search(r"(\d+) af (\d+) kalenderfeeds fejlede", l)] if m), None)
    return t, fejl, feeds


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


def cron_tider(udtryk, retning):
    """Seneste (retning=-1) eller næste (retning=1) tidspunkt, cron-udtrykket rammer, i UTC."""
    try:
        mi, ti, dag, md, ug = udtryk.split()
        M, T, D, MD = _felt(mi, 0, 59), _felt(ti, 0, 23), _felt(dag, 1, 31), _felt(md, 1, 12)
        UG = {u % 7 for u in _felt(ug, 0, 7)}  # 0 og 7 er søndag
    except ValueError:
        return None
    nu = datetime.now().astimezone()
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
    """Claude-appens egne planlagte opgaver: id → navn, tidsplan, slået til, seneste kørsel. Kun de felter."""
    for fil in sorted(APP_SESSIONER.glob("*/*/scheduled-tasks.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            opgaver = json.loads(fil.read_text()).get("scheduledTasks", [])
        except (OSError, ValueError):
            continue
        return {o.get("id"): {"navn": o.get("displayName") or o.get("id"), "cron": o.get("cronExpression"),
                              "slaaet_til": o.get("enabled", True), "sidst": tid(o.get("lastRunAt"))} for o in opgaver}
    return None


def punkt(navn, type_, projekt, status, tekst, sidst=None, hjaelp=None, link=None, naeste=None):
    return {k: v for k, v in dict(navn=navn, type=type_, projekt=projekt, status=status, tekst=tekst, sidst=iso(sidst),
                                   naeste=iso(naeste), hjaelp=hjaelp, link=link).items() if v is not None}


# ── datakilder ────────────────────────────────────────────────────────────────
def datakilder(koersel, fejl, feeds, karriere_rutine):
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
            s, tekst = ("fejl" if feeds[0] >= feeds[1] else "advarsel"), f"{feeds[0]} af {feeds[1]} feeds kunne ikke hentes"
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
                        hjaelp="Åbn Kompas-appen, så laves udtrækket (`sure/dashboard/export.sh`)."))

    t = mtime(KARRIERE / "data" / "set.json")
    kr = karriere_rutine or {}
    plan = f"hentes, når rutinen {kr['navn']} kører" if kr.get("navn") else "hentes af jobagentens rutine"
    s, tekst = frisk(t, 8 * 24 * TIME, plan, "ikke hentet i over en uge")
    # Kørte rutinen, uden at hent_jobs.py nåede at hente, så fejlede hentningen
    if t and kr.get("sidst") and (kr["sidst"] - t).total_seconds() > 6 * TIME:
        s, tekst = "advarsel", f"rutinen {kr['navn']} kørte, men hentede ikke nye opslag"
    ud.append(punkt("Jobindex", "RSS", "Karriere", s, tekst, t,
                    hjaelp=None if s == "ok" else "Se rutinens seneste kørsel under Planlagte opgaver i Claude-appen.",
                    link="/karriere/"))

    log = SEMESTER / "Scripts" / "canvas-log.txt"
    t = None
    try:
        sidste = log.read_text(errors="ignore").strip().splitlines()[-1]
        t = tid(sidste[:16])
    except (OSError, IndexError):
        pass
    ud.append(punkt("Canvas", "downloads", "Studie", "info", "sorteres, når du kører scriptet", t,
                    hjaelp="Flyt Canvas-downloads til fagmapperne: `node Scripts/canvas-sortering.js --kør` "
                    "(uden `--kør` er det en prøvekørsel)."))
    return ud


# ── Claude ────────────────────────────────────────────────────────────────────
MCP_ENV = ("GC_DB", "GARMINTOKENS", "GC_TZ")  # stier og tidszone, aldrig hemmeligheder
# Rutinerne, Kompas viser: id på den planlagte opgave i Claude-appen → hvad den skriver, og hvilket område.
# Ret id'erne, så de passer til dine egne planlagte opgaver.
RUTINE_INFO = {
    "studie-koereplan": ("køreplan for næste uge", "Studie"),
    "traening-rapport": ("14-dages rapport", "Form & fokus"),
    "overblik-ugereview": ("ugereview", "I dag · Form & fokus"),
    "jobagent-studiejob": ("nye jobmatch", "Karriere"),
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
    try:
        r = subprocess.run(kommando, input="".join(json.dumps(b) + "\n" for b in beskeder), capture_output=True,
                           text=True, timeout=timeout, cwd=str(COACH),
                           env={**os.environ, "PATH": PATH, **{k: str(v) for k, v in (cfg.get("env") or {}).items()}})
        ud = r.stdout
    except subprocess.TimeoutExpired as e:
        ud = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
    except OSError as e:
        return None, f"kunne ikke starte ({e.strerror})"
    for linje in ud.splitlines():
        try:
            svar = json.loads(linje)
        except ValueError:
            continue
        if svar.get("id") == 2:
            if "result" in svar:
                return len(svar["result"].get("tools", [])), None
            return None, "svarede med en fejl på tools/list"
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


def claude(cfg, rutiner):
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
        ud.append(punkt("Rutiner", "Claude-rutine", "Kompas", "info", "kan ikke læse Claude-appens planlagte opgaver",
                        hjaelp="Se dem under Planlagte opgaver i Claude-appen."))
        return ud
    for rid, (skriver, projekt) in RUTINE_INFO.items():
        r = rutiner.get(rid)
        if not r:
            ud.append(punkt(rid, "Claude-rutine", projekt, "fejl", "findes ikke i Claude-appen",
                            hjaelp=f"Instruktionerne ligger i `~/.claude/scheduled-tasks/{rid}/SKILL.md`. Opret rutinen igen."))
            continue
        forrige, naeste = cron_tider(r["cron"], -1), cron_tider(r["cron"], 1)
        hvornaar = plan_tekst(r["cron"]) or "uden fast tid"
        # Sprunget over = den forrige planlagte kørsel kom ikke, og der er gået mindst en halv periode siden sidste
        # kørsel. Det sidste krav undgår falske advarsler lige efter, at tidsplanen er ændret.
        periode = (naeste - forrige) if forrige and naeste else None
        sprunget = bool(forrige and periode and (not r["sidst"] or (
            r["sidst"] < forrige - timedelta(minutes=1) and forrige - r["sidst"] >= periode / 2)))
        if not r["slaaet_til"]:
            s, tekst = "advarsel", f"{skriver} · slået fra"
        elif not sprunget:
            s, tekst = "ok", f"{skriver} · hver {hvornaar}"
        elif alder(forrige) < 3 * TIME:  # appen lægger op til et kvarter til tidsplanen
            s, tekst = "ok", f"{skriver} · kører om lidt"
        else:
            l = forrige.astimezone()
            s, tekst = "advarsel", f"{skriver} · skulle have kørt {UGEDAGE[l.weekday()]} kl. {l:%H.%M}"
        ud.append(punkt(r["navn"], "Claude-rutine", projekt, s, tekst, r["sidst"], naeste=naeste if r["slaaet_til"] else None,
                        hjaelp=None if s == "ok" else "Rutiner kører kun, mens Claude-appen er åben, og en glemt kørsel "
                        f"tages, næste gang appen åbnes. Du kan også køre den nu under Planlagte opgaver ({r['navn']})."))
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
    andre = sorted(fejl - {"garmin", "kalender"})
    if andre:
        s, tekst = "advarsel", "sidste kørsel: " + ", ".join(andre) + " fejlede"
    ud.append(punkt("Opdatering", "LaunchAgent", "Kompas", s, tekst, koersel,
                    hjaelp=None if s == "ok" else "Den er slået fra, når Kompas er lukket. Åbn Kompas-appen. "
                    "Log: `~/.kompas/opdater.log`"))

    for navn, port, label, projekt in [("Karriere-server", 8766, "karriere", "Karriere"), ("Studie-server", 8767, "studie", "Studie")]:
        oppe = http(f"http://127.0.0.1:{port}/") is not None
        ud.append(punkt(navn, "LaunchAgent", projekt, "ok" if oppe else "fejl",
                        f"svarer på 127.0.0.1:{port}" if oppe else "svarer ikke",
                        hjaelp=None if oppe else f"`launchctl kickstart -k gui/$(id -u)/local.kompas.{label}` "
                        f"(log: `~/.kompas/{label}{'-server' if label == 'studie' else ''}.log`)"))

    oppe = http("http://127.0.0.1:3000/up") == 200
    ud.append(punkt("Sure", "Docker (Colima)", "Økonomi", "ok" if oppe else "info",
                    "kører" if oppe else "lukket, startes af Kompas-appen",
                    hjaelp=None if oppe else "Åbn Kompas-appen. Det tager ca. 30 sekunder."))

    ts = TAILSCALE if os.access(TAILSCALE, os.X_OK) else shutil.which("tailscale", path=PATH)
    if not ts:
        ud.append(punkt("Tailscale", "VPN", "Studie", "info", "ikke installeret (kun til telefonen)",
                        link="https://tailscale.com/download"))
    else:
        rc, ud_json = koer(ts, "status", "--json")
        try:
            koerer = rc == 0 and json.loads(ud_json).get("BackendState") == "Running"
        except ValueError:
            koerer = False
        rc, serve = koer(ts, "serve", "status", "--json")
        deler = "127.0.0.1:8768" in serve
        s = "ok" if koerer and deler else "advarsel" if koerer else "info"
        ud.append(punkt("Tailscale", "VPN", "Studie", s,
                        "På farten er tilgængelig på telefonen" if s == "ok" else
                        "kører, men deler ikke På farten" if koerer else "ikke forbundet",
                        hjaelp=None if s == "ok" else "`~/kompas/bin/tailscale-mobil.sh`" if koerer
                        else "Åbn Tailscale og log ind, hvis du vil bruge På farten."))

    filer = sorted(BACKUP.glob("*.db.gz"), key=lambda p: p.stat().st_mtime) if BACKUP.is_dir() else []
    t = mtime(filer[-1]) if filer else None
    s, tekst = frisk(t, 2 * 24 * TIME, "coach.db og liv.db, 14 dage tilbage", "ingen backup de sidste to dage")
    ud.append(punkt("Backup", "mappe i skyen", "Kompas", s, tekst, t,
                    hjaelp=None if s == "ok" else "`~/kompas/bin/backup-data.sh --tving`"))
    return ud


# ── værktøjer ─────────────────────────────────────────────────────────────────
VAERKTOEJER = [
    # navn, kommando(er), versionsflag, bruges til, installation
    ("Homebrew", ["brew"], "--version", "installerer resten", "/bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""),
    ("Caddy", ["caddy"], "version", "kompas.localhost", "brew install caddy"),
    ("Colima", ["colima"], "version", "Docker-maskinen til Sure", "brew install colima"),
    ("Docker", ["docker"], "--version", "Sure", "brew install docker docker-compose"),
    ("Node.js", ["node"], "--version", "Studie", "brew install node"),
    ("Python", ["python3"], "--version", "Form & fokus, Karriere", "brew install python"),
    ("SQLite", ["sqlite3"], "--version", "backup", "brew install sqlite"),
    ("Git", ["git"], "--version", "projekterne", "xcode-select --install"),
    ("Tailscale", [TAILSCALE, "tailscale"], "version", "telefonen (valgfri)", "https://tailscale.com/download"),
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


def main():
    koersel, fejl, feeds = seneste_koersel()
    cfg, rutiner = mcp_konfig(), app_rutiner()
    grupper = [
        {"id": "kilder", "titel": "Datakilder", "undertitel": "Hvor tallene kommer fra",
         "punkter": datakilder(koersel, fejl, feeds, (rutiner or {}).get("jobagent-studiejob"))},
        {"id": "claude", "titel": "Claude", "undertitel": "MCP-server og planlagte rutiner", "punkter": claude(cfg, rutiner)},
        {"id": "drift", "titel": "Kører i baggrunden", "undertitel": "Servere, baggrundsjob og backup", "punkter": drift(koersel, fejl)},
    ]
    data = {"genereret": iso(NU), "kilde": "kompas/bin/forbindelser.py (via opdater.sh)", "grupper": grupper,
            "vaerktoejer": vaerktoejer(), "mcp": mcp_guide(cfg)}
    UD.parent.mkdir(parents=True, exist_ok=True)
    tmp = UD.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.replace(UD)


if __name__ == "__main__":
    main()
