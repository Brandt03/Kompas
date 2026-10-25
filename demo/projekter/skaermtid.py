"""Demodata for Skærmtid (/skaermtid/): seks uger på fire opdigtede enheder.

Modulet laver rå ActivityWatch-begivenheder (vinduer, afk, browserfaner og oplåsninger) for Mac, Stationær, Telefon
og Bærbar og regner dem om med projektets egen beregning (skaermtid.beregn) og regler.example.json og
valg.example.json, så tallene på siden er regnet af den rigtige kode. Skriver:

  ud/skaermtid/skaermtid.json   det, `skaermtid.py byg` skriver, inkl. ugens gennemgang fra rutinen
  ud/skaermtid/kompas.json      menuen (skaermtid.KOMPAS)

Enhederne, programmerne, siderne og tiderne er opdigtede: en studerende med forelæsninger om formiddagen, egne
projekter om eftermiddagen, telefonen spredt over dagen og stationæren til spil et par aftener om ugen. Kun
begivenhederne og ugens gennemgang er opdigtet her; teksten i gennemgangen bygger på de tal, koden har regnet.
Samme dato giver samme data. Kun standardbiblioteket; intet rammer nettet.
"""
from __future__ import annotations

import importlib.util
import json
import random
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROD = Path(__file__).resolve().parents[2]
PROJEKT = ROD / "skaermtid"
DK = ZoneInfo("Europe/Copenhagen")
DAGE = 42
UGEDAGE = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]

# Værterne i regler.example.json. Stationær og Bærbar sender (som med aw-sync) vinduer og afk under værtsnavnet, men
# browserfanerne under enheds-id'et, så beregningen skal lægge dem sammen.
MAC, PC, PC_ID, TLF, BAERBAR, BAERBAR_ID = ("macbook.local", "pc-stue", "00000000-0000-4000-8000-0000000000a1",
                                            "telefon", "baerbar", "00000000-0000-4000-8000-0000000000b2")


def _projekt():
    """skaermtid.py fra projektet (under et andet navn end dette modul, som også hedder skaermtid)."""
    spec = importlib.util.spec_from_file_location("skaermtid_projekt", PROJEKT / "skaermtid.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Enhed:
    """Rå begivenheder for én vært i ActivityWatch' form."""

    def __init__(self, telefon: bool = False):
        self.window, self.web, self.unlock = [], [], []
        self.afk = None if telefon else []

    @staticmethod
    def _ev(start: datetime, sek: float, data: dict) -> dict:
        return {"timestamp": start.astimezone(timezone.utc).isoformat(), "duration": round(sek, 3), "data": data}

    def vindue(self, start: datetime, sek: float, app: str, titel: str = "", pakke: str | None = None) -> None:
        data = {"app": app, "title": titel} if pakke is None else {"app": app, "package": pakke}
        self.window.append(self._ev(start, sek, data))

    def fane(self, start: datetime, sek: float, url: str, titel: str = "") -> None:
        self.web.append(self._ev(start, sek, {"url": url, "title": titel}))

    def aktiv(self, start: datetime, sek: float) -> None:
        self.afk.append(self._ev(start, sek, {"status": "not-afk"}))

    def oplaas(self, t: datetime) -> None:
        self.unlock.append(self._ev(t, 0, {}))

    def raa(self, nu: datetime) -> dict:
        """Som ActivityWatch svarer kl. `nu`: kun det, der er begyndt, og klippet til nu."""
        def klip(xs):
            if xs is None:
                return None
            ud = []
            for e in xs:
                s = datetime.fromisoformat(e["timestamp"])
                if s < nu:
                    ud.append({**e, "duration": min(e["duration"], (nu - s).total_seconds())})
            return ud
        b = {"window": klip(self.window), "afk": klip(self.afk), "web": klip(self.web), "unlock": klip(self.unlock)}
        slut = [datetime.fromisoformat(e["timestamp"]) + timedelta(seconds=e["duration"])
                for k in ("window", "web", "unlock") for e in b[k]]
        b["sidst"] = max(slut).astimezone(DK).isoformat(timespec="seconds") if slut else None
        return b


# ── computerne: blokke af programmer og faner ─────────────────────────────────
# (minutter fra–til, program eller BROWSER, adresse eller None, titel). Først i listen er oftest.
STUDIE = [
    ((15, 40), "Goodnotes", None, "Forelæsning 7 – noter"),
    ((8, 20), "BROWSER", "https://canvas.instructure.com/courses/2048/modules", "Moduler: Alfa – Canvas"),
    ((10, 25), "BROWSER", "https://www.youtube.com/watch?v=k1", "StatQuest: Linear Regression, Clearly Explained - YouTube"),
    ((5, 12), "Zotero", None, "Mit bibliotek"),
    ((6, 15), "BROWSER", "https://moodle.example.edu/course/view.php?id=31", "Beta: Uge 7 – Moodle"),
    ((3, 10), "BROWSER", "https://scholar.google.com/scholar?q=technology+acceptance", "Google Scholar"),
    ((4, 12), "BROWSER", "https://kompas.localhost/#/studie/", "Studie – Kompas"),
    ((2, 6), "BROWSER", "https://www.wolframalpha.com/input", "Wolfram|Alpha"),
    ((3, 8), "BROWSER", "https://translate.google.com/", "Google Oversæt"),
    ((2, 5), "Mail", None, "Indbakke"),
]
PROJEKTER = [
    ((25, 55), "Code", None, "skaermtid.py — kompas"),
    ((8, 20), "Terminal", None, "zsh — kompas"),
    ((8, 20), "Claude", None, "Claude"),
    ((5, 15), "BROWSER", "https://github.com/alex/kompas/pulls", "Pull requests · alex/kompas"),
    ((3, 10), "BROWSER", "https://stackoverflow.com/questions/1", "python - zoneinfo og sommertid - Stack Overflow"),
    ((3, 8), "BROWSER", "https://developer.mozilla.org/en-US/docs/Web/CSS/grid", "grid - CSS | MDN"),
    ((2, 6), "Slack", None, "Slack | studiegruppe"),
    ((2, 6), "BROWSER", "https://kompas.localhost/#/form/uge.html", "Ugereview – Kompas"),
    ((2, 6), "BROWSER", "https://www.notion.so/alex/Projektplan", "Projektplan"),
    ((2, 5), "BROWSER", "https://open.spotify.com/", "Spotify – Web Player"),
    ((1, 4), "Forhåndsvisning", None, "opgave.pdf"),
]
AFTEN = [
    ((15, 45), "BROWSER", "https://www.youtube.com/watch?v=a1", "Vlog: tre dage i Lissabon - YouTube"),
    ((8, 25), "BROWSER", "https://www.reddit.com/r/dataisbeautiful/", "dataisbeautiful"),
    ((25, 50), "BROWSER", "https://www.netflix.com/watch/1", "Netflix"),
    ((4, 12), "BROWSER", "https://www.dr.dk/nyheder/indland", "Nyheder – DR"),
    ((3, 8), "BROWSER", "https://www.dba.dk/cykler/", "Cykler – DBA"),
    ((3, 10), "BROWSER", "https://www.wikipedia.org/wiki/Lissabon", "Lissabon – Wikipedia"),
    ((2, 6), "BROWSER", None, "Ny fane"),
]
SPIL = [
    ((40, 90), "javaw.exe", None, "Minecraft 1.21"),
    ((15, 40), "Discord.exe", None, "#generelt - Discord"),
    ((5, 20), "steam.exe", None, "Steam"),
    ((10, 30), "BROWSER", "https://www.youtube.com/watch?v=g1", "Byggeguide: automatisk farm - YouTube"),
    ((1, 4), "explorer.exe", None, "Stifinder"),
]
BAERBAR_STUDIE = [
    ((20, 45), "obsidian", None, "Alfa · forelæsning 8 - Obsidian"),
    ((10, 25), "BROWSER", "https://moodle.example.edu/mod/resource/view.php?id=7", "Beta: slides uge 8 – Moodle"),
    ((10, 30), "Code", None, "opgave2.py - Visual Studio Code"),
    ((5, 15), "Alacritty", None, "python opgave2.py"),
    ((3, 10), "BROWSER", "https://github.com/alex/opgaver", "alex/opgaver"),
    ((2, 6), "Slack", None, "Slack | studiegruppe"),
]


def _blok(rng: random.Random, en: Enhed, start: datetime, slut: datetime, liste: list, browser: str,
          faner: Enhed | None = None) -> None:
    """Fylder [start, slut) med programmer fra listen og små pauser; afk-måleren siger aktiv i hvert stykke."""
    faner = faner or en
    t = start
    vaegte = [len(liste) - i for i in range(len(liste))]
    while t < slut:
        (lo, hi), app, url, titel = rng.choices(liste, weights=vaegte)[0]
        sek = min(rng.uniform(lo, hi) * 60, (slut - t).total_seconds())
        if sek < 30:
            break
        er_browser = app == "BROWSER"
        en.vindue(t, sek, browser if er_browser else app, titel)
        if er_browser and url:
            # Udvidelsen melder fanen løbende; et lille hul først, som på en rigtig maskine
            faner.fane(t + timedelta(seconds=2), sek - 2, url, titel)
        en.aktiv(t, sek)
        t += timedelta(seconds=sek)
        if rng.random() < 0.35:
            t += timedelta(minutes=rng.uniform(1, 8))  # væk fra skærmen


def _kl(d: date, h: float) -> datetime:
    """Klokken h (timer, også over 24) på døgnet d, lokal tid."""
    return datetime.combine(d, time(0), tzinfo=DK) + timedelta(hours=h)


def _computere(rng: random.Random, d: date, idx: int, mac: Enhed, pc: Enhed, pc_web: Enhed, lap: Enhed,
               lap_web: Enhed, baerbar_fra: int) -> None:
    hverdag = d.weekday() < 5
    j = lambda: rng.uniform(-0.3, 0.3)  # noqa: E731
    # Mac'en: forelæsninger og læsning om formiddagen, egne projekter om eftermiddagen, lidt om aftenen
    if hverdag and d.weekday() not in (1, 3):
        _blok(rng, mac, _kl(d, 8.8 + j()), _kl(d, 11.7 + j()), STUDIE, "Microsoft Edge")
    if hverdag:
        _blok(rng, mac, _kl(d, 12.7 + j()), _kl(d, 15.4 + j()), PROJEKTER, "Microsoft Edge")
        if rng.random() < 0.5:
            _blok(rng, mac, _kl(d, 16 + j()), _kl(d, 17 + j()), STUDIE, "Microsoft Edge")
    elif rng.random() < 0.7:
        _blok(rng, mac, _kl(d, 10.5 + j()), _kl(d, 12.5 + j()), PROJEKTER, "Microsoft Edge")
    if rng.random() < (0.55 if hverdag else 0.75):
        _blok(rng, mac, _kl(d, 20 + j()), _kl(d, 21.6 + j()), AFTEN, "Microsoft Edge")
    if rng.random() < 0.22:
        _blok(rng, mac, _kl(d, 23.1 + j() / 3), _kl(d, 24.2 + j()), AFTEN[:3], "Microsoft Edge")
    # Bærbaren: med på studiet tirsdag og torsdag (fra den dag, den blev sat op)
    if idx >= baerbar_fra and d.weekday() in (1, 3):
        _blok(rng, lap, _kl(d, 9.2 + j()), _kl(d, 11.8 + j()), BAERBAR_STUDIE, "chromium", lap_web)
        _blok(rng, lap, _kl(d, 12.8 + j()), _kl(d, 14.6 + j()), BAERBAR_STUDIE, "chromium", lap_web)
    # Stationæren: spil et par aftener om ugen
    if d.weekday() in (4, 5) and rng.random() < 0.8 or d.weekday() == 2 and rng.random() < 0.35:
        _blok(rng, pc, _kl(d, 19.5 + j()), _kl(d, 22.4 + j()), SPIL, "msedge.exe", pc_web)


# ── telefonen: korte og lange åbninger spredt over dagen ──────────────────────
# (navn, pakke, vægt, minutter fra–til, andel korte tjek under et minut)
APPS = [
    ("Instagram", "com.instagram.android", 16, (1.5, 8), 0.55),
    ("Reddit", "com.reddit.frontpage", 9, (2, 12), 0.25),
    ("Messenger", "com.facebook.orca", 10, (0.5, 4), 0.0),
    ("WhatsApp", "com.whatsapp", 8, (0.5, 3), 0.0),
    ("Spotify", "com.spotify.music", 6, (0.3, 1.5), 0.0),
    ("DR Nyheder", "dk.dr.drnyheder", 5, (1, 6), 0.45),
    ("Chrome", "com.android.chrome", 5, (1, 8), 0.0),
    ("YouTube", "com.google.android.youtube", 4, (4, 20), 0.0),
    ("Gmail", "com.google.android.gm", 3, (0.5, 3), 0.0),
    ("Maps", "com.google.android.apps.maps", 2, (1, 5), 0.0),
    ("Kalender", "com.google.android.calendar", 2, (0.3, 1.5), 0.0),
    ("Google Keep", "com.google.android.keep", 2, (0.5, 3), 0.0),
    ("MobilePay", "dk.danskebank.mobilepay", 1, (0.5, 1.5), 0.0),
    ("Lommeregner", "com.android.calculator2", 1, (0.2, 1), 0.0),
    ("Bus & tog", "com.example.rejseplan", 1, (0.5, 2), 0.0),
    ("Strava", "com.strava", 1, (1, 4), 0.0),
]
DUOLINGO = ("Duolingo", "com.duolingo", 0, (7, 14), 0.0)
TELEFON_SIDER = ["www.dr.dk", "www.wikipedia.org", "www.dmi.dk", "github.com", "www.reddit.com", "www.dba.dk"]
STARTER = ("Pixel Launcher", "com.android.launcher3")


def _telefon(rng: random.Random, d: date, tlf: Enhed, idx: int) -> None:
    vaagen, seng = 7.2 + rng.uniform(0, 1.2), 23.2 + rng.uniform(-0.6, 1.4)
    # Lidt færre åbninger uge for uge, så ugerne ikke ligner hinanden
    antal = rng.randint(42, 64) - idx // 7 * 2
    aabninger = [(vaagen + 0.25, DUOLINGO)]  # sprog hver morgen
    aabninger += [(rng.uniform(vaagen, seng), rng.choices(APPS, weights=[a[2] for a in APPS])[0]) for _ in range(antal)]
    slut_forrige = _kl(d, 0)
    for h, (navn, pakke, _, (lo, hi), kort) in sorted(aabninger, key=lambda x: x[0]):
        t = max(_kl(d, h), slut_forrige + timedelta(seconds=20))
        lang = 1.5 if h > 20 and navn in ("YouTube", "Reddit") else 1
        sek = rng.uniform(8, 50) if rng.random() < kort else rng.uniform(lo, hi) * 60 * lang
        if rng.random() < 0.85:
            tlf.oplaas(t - timedelta(seconds=3))
        tlf.vindue(t - timedelta(seconds=2), 2, STARTER[0], pakke=STARTER[1])
        tlf.vindue(t, sek, navn, pakke=pakke)
        if navn == "Chrome" and rng.random() < 0.8:
            # Telefonens browser melder kun værten, et øjeblik, når fanen skifter
            tlf.fane(t + timedelta(seconds=1), 3, rng.choice(TELEFON_SIDER))
        slut_forrige = t + timedelta(seconds=sek)
        tlf.vindue(slut_forrige, 2, STARTER[0], pakke=STARTER[1])


# ── ugens gennemgang (rutinen Kompas · Skærmtid), skrevet ud fra de regnede tal ─
def _k(x: float, n: int = 1) -> str:
    return f"{x:.{n}f}".replace(".", ",")


def _t(x: float | None) -> str:
    if x is None:
        return "–"
    return f"{round(x * 60)} min" if x < 1 else f"{_k(x)} t"


def _gennemgang(r: dict, dage: list) -> dict:
    p, f = r["forrige_uge"], r["ugen_foer"]
    prod, prod_f = p["grupper"].get("Produktiv", 0), f["grupper"].get("Produktiv", 0)
    pas, pas_f = p["grupper"].get("Passiv", 0), f["grupper"].get("Passiv", 0)
    tj, tj_f = p.get("tjek") or {}, f.get("tjek") or {}
    tal = [f"Produktiv {_t(prod)} mod {_t(prod_f)} ugen før; passiv {_t(pas)} mod {_t(pas_f)}.",
           f"Korte tjek {_k(tj.get('korte_pr_dag', 0))} pr. dag mod {_k(tj_f.get('korte_pr_dag', 0))}; "
           f"oplåsninger {_k(tj.get('oplaasninger_pr_dag', 0), 0)} pr. dag mod {_k(tj_f.get('oplaasninger_pr_dag', 0), 0)}.",
           f"Sen skærmtid {_t(p['sen_timer'])} mod {_t(f['sen_timer'])}."]
    fl = r.get("faelles") or {}
    if fl.get("dage"):
        tal.append(f"Telefonen samtidig med en computer: {_t(fl['samtidig']['timer'])} på {fl['dage']} fælles hele dage.")
    enh = max(p["enheder"].items(), key=lambda x: x[1], default=None)
    if enh:
        tal.append(f"{enh[0]} fyldte mest med {_t(enh[1])}.")
    forslag = {"Alacritty": "Egne projekter", "Forhåndsvisning": "Studie", "translate.google.com": "Sprog",
               "www.notion.so": "Egne projekter"}
    vedl = [f"Forslag: {x['navn']} ({_t(x['timer'])} de seneste 14 dage) under {forslag[x['navn']]}."
            for x in r["ukategoriseret"] if x["navn"] in forslag][:2]
    vedl.append("Stationær har ikke sendt data i nogle dage; den bruges sjældent, så det er forventet.")
    # Dagen i ugen med flest korte tjek
    ugens = [d for d in dage if p["fra"] <= d["dato"] <= p["til"] and d.get("tjek")]
    top = max(ugens, key=lambda d: d["tjek"]["korte"], default=None)
    en_ting = (f"Telefonen i tasken under formiddagens læsning om {UGEDAGE[date.fromisoformat(top['dato']).weekday()]}en, "
               f"hvor de korte tjek toppede med {top['tjek']['korte']}." if top else "")
    retning = "mere" if prod > prod_f else "mindre"
    tjek = "færre" if tj.get("korte_pr_dag", 0) < tj_f.get("korte_pr_dag", 0) else "flere"
    return {"saetning": f"{retning.capitalize()} produktiv tid end ugen før ({_t(prod)}) og {tjek} korte tjek på telefonen.",
            "tal": tal, "vedligehold": vedl, "en_ting": en_ting, "forbehold": []}


def lav(ud: Path, idag: date) -> None:
    st = _projekt()
    cfg = st.laes_regler(PROJEKT / "regler.example.json", valg_sti=PROJEKT / "valg.example.json")
    # Bygget "nu", når demoen laves i dag efter kl. 8; ellers om aftenen den dag
    nu = datetime.now(DK)
    if nu.date() != idag or nu.time() < time(8, 0):
        nu = datetime.combine(idag, time(20, 15), tzinfo=DK)
    fra = idag - timedelta(days=DAGE - 1)

    mac, pc, pc_web, tlf, lap, lap_web = Enhed(), Enhed(), Enhed(), Enhed(telefon=True), Enhed(), Enhed()
    baerbar_fra = DAGE - 24  # bærbaren kom med for 24 dage siden
    for i in range(DAGE):
        d = fra + timedelta(days=i)
        rng = random.Random(f"skaermtid-{d.isoformat()}")
        _computere(rng, d, i, mac, pc, pc_web, lap, lap_web, baerbar_fra)
        _telefon(rng, d, tlf, i)
    # Stationæren bruges sjældent (sjaelden i regler.example.json): den sidste spilleaften var for fire dage siden,
    # som Forbindelser i demoen (demo/projekter/kompas.py) siger
    graense = _kl(idag - timedelta(days=3), 6).astimezone(timezone.utc).isoformat()
    for xs in (pc.window, pc.afk, pc_web.web):
        xs[:] = [e for e in xs if e["timestamp"] < graense]
    for_fire = _kl(idag - timedelta(days=4), 6).astimezone(timezone.utc).isoformat()
    if not any(e["timestamp"] >= for_fire for e in pc.window):
        rng = random.Random(f"skaermtid-pc-{idag.isoformat()}")
        _blok(rng, pc, _kl(idag - timedelta(days=4), 19.6), _kl(idag - timedelta(days=4), 22.2), SPIL, "msedge.exe", pc_web)
    # Bærbaren har altid data fra i går eller i dag, så den ikke ser ud til at være faldet ud
    i_gaar = _kl(idag - timedelta(days=1), 6)
    if not any(e["timestamp"] >= i_gaar.astimezone(timezone.utc).isoformat() for e in lap.window):
        rng = random.Random(f"skaermtid-baerbar-{idag.isoformat()}")
        _blok(rng, lap, i_gaar + timedelta(hours=7), i_gaar + timedelta(hours=8.5), BAERBAR_STUDIE, "chromium", lap_web)

    raa = {MAC: mac.raa(nu), PC: pc.raa(nu), PC_ID: pc_web.raa(nu), TLF: tlf.raa(nu),
           BAERBAR: lap.raa(nu), BAERBAR_ID: lap_web.raa(nu)}
    doc = st.beregn(raa, cfg, fra, idag, nu)

    # Ugens gennemgang, som rutinen gemmer i rapporter/<uge>.json mandag morgen, og som byg lægger i doc["rapport"]
    r = st.rapport(doc)
    mandag = date.fromisoformat(r["mandag"]) + timedelta(days=7)
    doc["rapport"] = {"mandag": r["mandag"], **_gennemgang(r, doc["dage"]),
                      "genereret": datetime.combine(mandag, time(6, 34)).isoformat(timespec="minutes"), "uge": r["uge"]}

    mappe = ud / "skaermtid"
    mappe.mkdir(parents=True, exist_ok=True)
    (mappe / "skaermtid.json").write_text(json.dumps(doc, ensure_ascii=False))
    opdateret = nu.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    (mappe / "kompas.json").write_text(json.dumps({**st.KOMPAS, "opdateret": opdateret}, ensure_ascii=False))
