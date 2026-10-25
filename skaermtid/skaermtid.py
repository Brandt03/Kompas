#!/usr/bin/python3
"""Skærmtid: hvor tiden går hen på Mac, stationær, bærbar og telefon, regnet ud fra ActivityWatch.

    /usr/bin/python3 skaermtid.py byg [--ud ~/.kompas/skaermtid] [--server http://localhost:5600] [--dage 56]
    /usr/bin/python3 skaermtid.py rapport      # byg, og skriv ugens tal til rutinen Kompas · Skærmtid som JSON

Læser alle enheders begivenheder fra den lokale ActivityWatch-server (de andre enheders ligger dér efter aw-sync),
sorterer dem i kategorier efter `regler.json` og skriver `skaermtid.json`, `kompas.json` og siden til mappen. En enhed
kan have flere værtsnavne (`vaert` som liste), fordi aw-sync giver en enheds vinduer dens værtsnavn, men dens
browserfaner og telefonens app dens enheds-id; de lægges sammen pr. enhed, før der regnes.
Alt regnes forfra hver gang, så en rettet regel gælder bagud. Kun standardbiblioteket (macOS' /usr/bin/python3).

Kun summer forlader ActivityWatch: tid pr. dag, enhed, kategori og program (eller hjemmesidens vært). Vinduestitler
bruges alene til at matche en regel og skrives aldrig.

Døgnet skifter kl. `doegn_skifter` (06:00), så en nat kl. 01 hører til aftenens dag, og "sen skærmtid" er tiden fra
`sen_fra` (23:00) til døgnet skifter. På computerne tæller kun tid, hvor aw-watcher-afk siger, at du er aktiv;
telefonen har ingen afk-måler, så dér tæller tiden med skærmen tændt.

Svarer ActivityWatch ikke, skrives intet: de gamle filer bliver stående, og kommandoen slutter med exit 1.
"""
from __future__ import annotations

import argparse
import os
import bisect
import json
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HER = Path(__file__).resolve().parent
# Dine enheder, kategorier og regler. regler.json er personlig og ligger ikke i git; uden den bruges eksemplet
REGLER = HER / "regler.json" if (HER / "regler.json").exists() else HER / "regler.example.json"
# Dine valg fra siden (kategori eller "tæller ikke" for ét bestemt program eller én side). Skrives kun af
# server.py; regler.json skrives aldrig af et program. Valg går forud for reglerne. Uden valg.json (og uden
# SKAERMTID_VALG) læses valg.example.json, så eksemplet viser formatet; det første valg på siden skriver valg.json.
VALG = Path(os.environ.get("SKAERMTID_VALG") or HER / "valg.json")
VALG_EKSEMPEL = HER / "valg.example.json"
SIDE = HER / "side"
RAPPORTER = HER / "rapporter"  # rutinen Kompas · Skærmtid gemmer ugens gennemgang her (<uge>.md og <uge>.json)
UD = Path.home() / ".kompas" / "skaermtid"
SERVER = "http://localhost:5600"
DK = ZoneInfo("Europe/Copenhagen")
DAGE = 56  # 8 uger, samme sammenligningsgrundlag som Overblik
UKATEGORISERET = "Ukategoriseret"
# Kører vinduerne mere end så længe efter den sidste afk-måling, er afk-måleren holdt op (se beregn)
AFK_STOPPET_EFTER = timedelta(hours=1)
FANE_MAKS = timedelta(minutes=30)  # en browserfane gælder højst så længe efter, at den blev set
FORELOEBIG_UNDER = 7  # dage: tal pr. enhed, der bygger på færre dage, er foreløbige
# Dagens forløb (dage[].forloeb): kvarterer med mindst så meget skærmtid står med deres største kategori, de seneste
# FORLOEB_DAGE dage. Det er stadig kun summer, ikke titler; Overblik lægger dem ved siden af kalenderen.
KVARTER = timedelta(minutes=15)
KVARTER_MIN = 300  # sekunder
FORLOEB_DAGE = 28

# I menuen står siden under Form & fokus, som coach også skriver sine sider til; Kompas lægger dem i samme mappe
KOMPAS = {
    "omraade": "Form & fokus", "ikon": "clock", "raekkefoelge": 45,
    "kilde": "skaermtid (python3 skaermtid.py byg)",
    "sider": [{"titel": "Skærmtid", "ikon": "clock", "sti": "/skaermtid/"}],
}


# --- regler -------------------------------------------------------------------

def laes_regler(sti: Path = REGLER, valg_sti: Path | None = None) -> dict:
    cfg = json.loads(sti.read_text())
    for k in cfg["kategorier"]:
        for r in k["regler"]:
            r["_re"] = {felt: re.compile(r[felt], re.I) for felt in ("app", "domaene", "sti", "titel") if felt in r}
    cfg["_browser"] = re.compile(cfg["browsere"], re.I)
    cfg["_ignorer"] = re.compile(cfg["ignorer"], re.I) if cfg.get("ignorer") else None
    cfg["_gruppe"] = {k: g["navn"] for g in cfg.get("grupper", []) for k in g["kategorier"]}
    saet_valg(cfg, laes_valg(valg_sti or VALG))
    return cfg


def laes_valg(sti: Path = VALG) -> list[dict]:
    """valg.json: [{"app": "dk.dba.android", "kategori": "Økonomi"}, {"domaene": "www.dr.dk", "ignorer": true}, …].
    `app` er pakkenavnet på telefonen og programmets navn på computerne; `domaene` er hjemmesidens vært, præcis."""
    sti = Path(sti)
    if not sti.exists() and sti == HER / "valg.json" and not os.environ.get("SKAERMTID_VALG"):
        sti = VALG_EKSEMPEL
    try:
        d = json.loads(sti.read_text())
    except FileNotFoundError:
        return []
    return d.get("valg", []) if isinstance(d, dict) else []


def saet_valg(cfg: dict, valg: list[dict]) -> None:
    cfg["valg"] = valg
    cfg["_valg"] = {("domaene" if "domaene" in v else "app", (v.get("domaene") or v.get("app") or "").lower()): v
                    for v in valg if v.get("domaene") or v.get("app")}


def valgt(cfg: dict, app: str | None, pakke: str | None, domaene: str | None) -> dict | None:
    """Dit valg for netop dette: siden går forud for programmet, pakkenavnet for programmets navn."""
    vs = cfg.get("_valg") or {}
    if domaene and ("domaene", domaene.lower()) in vs:
        return vs[("domaene", domaene.lower())]
    for a in (pakke, app):
        if a and ("app", a.lower()) in vs:
            return vs[("app", a.lower())]
    return None


def _klokken(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def kategoriser(cfg: dict, app: str | None, pakke: str | None, domaene: str | None, sti: str | None,
                titel: str | None) -> str:
    return kategori_og_kilde(cfg, app, pakke, domaene, sti, titel)[0]


def kategori_og_kilde(cfg: dict, app: str | None, pakke: str | None, domaene: str | None, sti: str | None,
                      titel: str | None) -> tuple[str, str | None]:
    """Kategorien og hvorfor: "valg" (dit valg på siden), "domaene", "titel" eller "app" (reglens stærkeste
    mønster), None for ukategoriseret. Dit valg går forud. Reglerne prøves i to gennemløb: først alle regler med
    program, side eller sti, i rækkefølge; så reglerne med titel alene, og kun når der ikke er et domæne. Så kan en
    svag titelregel i en tidlig kategori aldrig slå en programregel i en senere (Mail med "Moodle" i titlen er
    Kommunikation, ikke Studie), og en kendt adresse overtrumfes aldrig af fanens titel. `app` prøves mod
    programmets navn og pakkenavn."""
    v = valgt(cfg, app, pakke, domaene)
    if v and v.get("kategori"):
        return v["kategori"], "valg"
    apps = [a for a in (app, pakke) if a]

    def passer(rx: dict) -> bool:
        if "app" in rx and not any(rx["app"].search(a) for a in apps):
            return False
        if "domaene" in rx and not (domaene and rx["domaene"].search(domaene)):
            return False
        if "sti" in rx and not (sti is not None and rx["sti"].search(sti)):
            return False
        # Med en side i samme regel skal begge passe (YouTube-videoer om CS50 er Studie)
        return "titel" not in rx or bool(titel and rx["titel"].search(titel))

    for kun_titel in (False, True):
        if kun_titel and domaene:
            break
        for k in cfg["kategorier"]:
            for r in k["regler"]:
                rx = r["_re"]
                if (set(rx) == {"titel"}) != kun_titel or not passer(rx):
                    continue
                return k["navn"], ("domaene" if "domaene" in rx else "titel" if "titel" in rx else "app")
    return UKATEGORISERET, None


def domaene_og_sti(url: str | None) -> tuple[str | None, str | None]:
    """Værten og resten af adressen ("/#/studie/"); None uden adresse. Kun værten skrives ud. Telefonens browser
    sender kun værten ("github.com") og nogle gange søgefeltets tekst; det første tælles, det andet ikke."""
    if not url:
        return None, None
    url = url.strip()
    if "://" not in url:
        if " " in url or "." not in url.split("/")[0]:
            return None, None
        url = "https://" + url
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return None, None
    if not u.hostname or ("." not in u.hostname and u.hostname != "localhost"):
        return None, None
    sti = u.path or "/"
    if u.query:
        sti += "?" + u.query
    if u.fragment:
        sti += "#" + u.fragment
    return u.hostname.lower(), sti


# --- tid ----------------------------------------------------------------------

def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def stykker(start: datetime, slut: datetime, cfg: dict):
    """Deler [start, slut) ved døgnskiftet og ved `sen_fra` i lokal tid: (start, slut, dato, sen)."""
    skift, sen_fra = _klokken(cfg["doegn_skifter"]), _klokken(cfg["sen_fra"])
    t = start
    while t < slut:
        lokal = t.astimezone(DK)
        dato = lokal.date() - timedelta(days=1) if lokal.time() < skift else lokal.date()
        sen = lokal.time() >= sen_fra or lokal.time() < skift
        graenser = [datetime.combine(d, k, tzinfo=DK) for d in (lokal.date(), lokal.date() + timedelta(days=1))
                    for k in (skift, sen_fra)]
        naeste = min(g for g in graenser if g > t)
        stop = min(slut, naeste)
        yield t, stop, dato, sen
        t = stop


def _intervaller(events: list[dict], filt=lambda e: True) -> tuple[list[datetime], list[tuple[datetime, datetime, dict]]]:
    xs = []
    for e in events:
        if not filt(e):
            continue
        s = _dt(e["timestamp"])
        xs.append((s, s + timedelta(seconds=e.get("duration") or 0), e.get("data") or {}))
    xs.sort(key=lambda x: x[0])
    return [x[0] for x in xs], xs


def _overlap(starter: list[datetime], xs: list, s: datetime, e: datetime):
    """De intervaller i xs (sorteret), der overlapper [s, e), klippet til."""
    i = bisect.bisect_right(starter, s) - 1
    i = max(i, 0)
    while i < len(xs) and xs[i][0] < e:
        a, b, data = xs[i]
        if b > s:
            yield max(a, s), min(b, e), data
        i += 1


# --- beregning ----------------------------------------------------------------

def _vaerter(en: dict) -> list[str]:
    """`vaert` i regler.json er ét værtsnavn eller en liste: aw-sync giver en synkroniseret enheds vinduer dens
    værtsnavn (små bogstaver, punktum bliver til _), men dens browserfaner og telefonens app dens enheds-id."""
    v = en.get("vaert")
    return [v] if isinstance(v, str) else list(v or [])


def _enhed(cfg: dict, vaert: str) -> str:
    for en in cfg["enheder"]:
        if any(x.lower() == vaert.lower() for x in _vaerter(en)):
            return en["navn"]
    return vaert


def telefoner(samlet: dict, cfg: dict) -> set[str]:
    """Enhederne, der tæller som telefon (ingen afk-måler: tiden med skærmen tændt tæller, korte tjek tælles).
    `slags` i regler.json afgør det ("telefon" eller "computer"); en enhed uden slags, fx en ukendt vært, er telefon,
    når den ingen afk-bucket har. Så bliver en computer, hvis afk-data mangler, aldrig talt som telefon."""
    slags = {en["navn"]: en.get("slags") for en in cfg["enheder"]}
    return {e for e, b in samlet.items()
            if (slags.get(e) == "telefon" if slags.get(e) in ("telefon", "computer") else b.get("afk") is None)}


def saml(raa: dict, cfg: dict) -> dict:
    """Lægger værter, der er samme enhed, sammen: {enhed: {"window", "afk", "web", "sidst", "vaerter"}}. Så kan
    Stationærs browserfaner (under dens enheds-id) klippes mod dens vinduer (under værtsnavnet)."""
    ud: dict = {}
    for vaert, b in raa.items():
        s = ud.setdefault(_enhed(cfg, vaert), {"window": [], "afk": None, "web": [], "unlock": [], "sidst": None, "vaerter": []})
        s["window"] += b.get("window") or []
        s["web"] += b.get("web") or []
        s["unlock"] += b.get("unlock") or []
        if b.get("afk") is not None:
            s["afk"] = (s["afk"] or []) + b["afk"]
        if b.get("sidst") and (s["sidst"] is None or _dt(b["sidst"]) > _dt(s["sidst"])):
            s["sidst"] = b["sidst"]
        s["vaerter"].append(vaert)
    return ud


def beregn(raa: dict, cfg: dict, fra: date, til: date, nu: datetime) -> dict:
    """raa: {vaert: {"window": [events], "afk": [events] | None, "web": [events], "sidst": iso | None}}.
    Giver dokumentet, siden viser. Dage er lokale døgn (skifter kl. doegn_skifter) fra `fra` til og med `til`."""
    kategorier = [k["navn"] for k in cfg["kategorier"]] + [UKATEGORISERET]
    # sek[dato][enhed] -> {"total", "sen", "kat": {navn: sek}, "apps": {(app, domaene): {"sek", "kat"}}}
    sek: dict = defaultdict(lambda: defaultdict(lambda: {"total": 0.0, "sen": 0.0, "kat": defaultdict(float),
                                                          "apps": defaultdict(lambda: {"sek": 0.0}),
                                                          "time": defaultdict(float)}))
    # De talte stykker pr. enhed (start, slut, gruppe, dato), så siden kan vise telefon samtidig med computer
    stykliste: dict = defaultdict(list)
    # Alle talte stykker (start, slut, enhed, dato, sen, kategori, programnøgle), før overlap mellem enheder fordeles
    stk: list = []
    samlet = saml(raa, cfg)
    telefon = telefoner(samlet, cfg)
    # Computere med vinduer, men uden afk-data i perioden: deres tid tæller ikke (aktiv tid kan ikke afgøres), og
    # siden siger det, så en afk-måler, der ikke kører eller ikke synkes, bliver opdaget
    afk_mangler = {e for e, b in samlet.items() if e not in telefon and not b.get("afk") and b.get("window")}
    # Computere, hvis afk-måler er holdt op, mens vinduerne fortsætter (dør aw-qt, tager den afk-måleren med sig,
    # mens serveren og vinduerne kører videre): {enhed: sidste afk-måling}. Tiden derefter tæller ikke.
    slut = lambda evs: max((_dt(e["timestamp"]) + timedelta(seconds=e.get("duration") or 0) for e in evs), default=None)
    afk_stoppet = {}
    for e, b in samlet.items():
        if e in telefon or not b.get("afk") or not b.get("window"):
            continue
        a, w = slut(b["afk"]), slut(b["window"])
        if w - a > AFK_STOPPET_EFTER:
            afk_stoppet[e] = a.astimezone(DK).isoformat(timespec="seconds")
    for enhed, b in samlet.items():
        aktiv = None
        if enhed not in telefon:
            aktiv = _intervaller(b.get("afk") or [], lambda e: (e.get("data") or {}).get("status") == "not-afk")
        web = _intervaller(b.get("web") or [])
        if aktiv is None:  # telefonen: fanerne er kun øjebliksbilleder
            web = _forlaeng(web)
        for e in b.get("window") or []:
            d = e.get("data") or {}
            s = _dt(e["timestamp"])
            slut = s + timedelta(seconds=e.get("duration") or 0)
            if slut <= s:
                continue
            app, pakke, titel = d.get("app"), d.get("package"), d.get("title")
            # Låseskærm, notifikationer og startmenu er ikke skærmtid, og det er det heller ikke, du har sagt ikke tæller
            if cfg["_ignorer"] and any(cfg["_ignorer"].search(a) for a in (app, pakke) if a):
                continue
            browser = bool(app and cfg["_browser"].search(app) or pakke and cfg["_browser"].search(pakke))
            v = valgt(cfg, app, pakke, None)
            if v and v.get("ignorer") and not browser:
                continue
            # Kun aktiv tid på computere: klip vinduet til afk-målerens "not-afk"
            aktive = list(_overlap(*aktiv, s, slut)) if aktiv is not None else [(s, slut, None)]
            for a, z, _ in aktive:
                dele = []
                if browser:
                    # Browseren: del efter den fane, udvidelsen så samtidig; resten står uden adresse
                    t = a
                    for ws, we, wd in _overlap(*web, a, z):
                        if ws > t:
                            dele.append((t, ws, None, None))
                        dele.append((ws, we, wd.get("url"), wd.get("title")))
                        t = we
                    if t < z:
                        dele.append((t, z, None, None))
                else:
                    dele.append((a, z, None, None))
                for ds, de, url, fanetitel in dele:
                    dom, sti = domaene_og_sti(url)
                    v = valgt(cfg, app, pakke, dom) if dom else None
                    if v and v.get("ignorer"):
                        continue
                    kat, kilde = kategori_og_kilde(cfg, app, pakke, dom, sti, fanetitel or titel)
                    for ps, pe, dato, sen in stykker(ds, de, cfg):
                        if not (fra <= dato <= til):
                            continue
                        # Kategorien med i nøglen: Edge uden adresse kan være både YouTube (titlen) og ukategoriseret.
                        # Et valg på siden gælder siden (domænet), ellers pakkenavnet og ellers programmets navn.
                        nøgle = (app or pakke or "?", "domaene" if dom else "app", dom or pakke or app or "?", dom,
                                 kat, kilde, browser and not dom)
                        stk.append((ps, pe, enhed, dato, sen, kat, nøgle))

    # Hver enhed får sin fulde tid (sek, brutto: "Mac 4,2 t"). I alt, kategorier og programmer bygger på netsek, hvor
    # tid på flere enheder på én gang kun tæller én gang (_fordel), så de lægges sammen til I alt.
    net, samtidig = _fordel(stk, telefon)
    netsek: dict = defaultdict(lambda: defaultdict(lambda: {"total": 0.0, "sen": 0.0, "kat": defaultdict(float),
                                                            "apps": defaultdict(lambda: {"sek": 0.0})}))
    for (ps, pe, enhed, dato, sen, kat, nøgle), n_net in zip(stk, net):
        for mål, n in ((sek[dato][enhed], (pe - ps).total_seconds()), (netsek[dato][enhed], n_net)):
            mål["total"] += n
            mål["kat"][kat] += n
            mål["apps"][nøgle]["sek"] += n
            if sen:
                mål["sen"] += n
        for time_, m in _pr_time(ps, pe):
            sek[dato][enhed]["time"][time_] += m
        stykliste[enhed].append((ps, pe, cfg["_gruppe"].get(kat, UKATEGORISERET), dato))

    tjek = _tjek(samlet, cfg, fra, til, telefon)
    forloeb_fra = max(fra, til - timedelta(days=FORLOEB_DAGE - 1))
    forloeb = _forloeb(stk, net, cfg, forloeb_fra)

    timer = lambda s: round(s / 3600, 2)
    grupper = [g["navn"] for g in cfg.get("grupper", [])]
    dage = []
    d = fra
    while d <= til:
        # Enhederne brutto; i alt, sen tid, kategorier og grupper netto
        enheder = {}
        for enhed, v in sek.get(d, {}).items():
            enheder[enhed] = {"timer": timer(v["total"]), "sen_timer": timer(v["sen"]),
                              "kategorier": {k: timer(v["kat"][k]) for k in kategorier if v["kat"].get(k)}}
        kat_sum = defaultdict(float)
        for v in netsek.get(d, {}).values():
            for k, n in v["kat"].items():
                kat_sum[k] += n
        grp_sum = defaultdict(float)
        for k, n in kat_sum.items():
            grp_sum[cfg["_gruppe"].get(k, UKATEGORISERET)] += n
        dage.append({"dato": d.isoformat(),
                     "timer": timer(sum(v["total"] for v in netsek.get(d, {}).values())),
                     "sen_timer": timer(sum(v["sen"] for v in netsek.get(d, {}).values())),
                     "samtidig_timer": timer(samtidig.get(d, 0)),
                     "kategorier": {k: timer(kat_sum[k]) for k in kategorier if kat_sum.get(k)},
                     "grupper": {g: timer(grp_sum[g]) for g in grupper + [UKATEGORISERET] if grp_sum.get(g)},
                     "tjek": tjek.get(d),
                     "enheder": enheder,
                     # null før de seneste FORLOEB_DAGE dage; en tom liste er en dag uden skærmtid
                     "forloeb": forloeb.get(d, []) if d >= forloeb_fra else None})
        d += timedelta(days=1)
    # Dagene før den første dag med data står ikke med: uden data er tiden ukendt, ikke 0 timer. Siden og Overblik
    # læser en dag, der mangler, som "ingen data"
    dage = dage[next((i for i, x in enumerate(dage) if x["enheder"] or x["tjek"]), len(dage)):]

    uger: dict = {}
    for dag in dage:
        dd = date.fromisoformat(dag["dato"])
        m = dd - timedelta(days=dd.weekday())
        u = uger.setdefault(m, {"uge": f"{dd.isocalendar()[0]}-W{dd.isocalendar()[1]:02d}", "mandag": m.isoformat(),
                                "timer": 0.0, "sen_timer": 0.0, "dage_med_data": 0, "kategorier": defaultdict(float),
                                "enheder": defaultdict(float)})
        u["timer"] += dag["timer"]
        u["sen_timer"] += dag["sen_timer"]
        u["dage_med_data"] += 1 if dag["enheder"] else 0
        for k, t in dag["kategorier"].items():
            u["kategorier"][k] += t
        for en, v in dag["enheder"].items():
            u["enheder"][en] += v["timer"]
    for u in uger.values():
        u["timer"], u["sen_timer"] = round(u["timer"], 2), round(u["sen_timer"], 2)
        u["kategorier"] = {k: round(t, 2) for k, t in u["kategorier"].items()}
        u["enheder"] = {k: round(t, 2) for k, t in u["enheder"].items()}

    # Siden viser perioderne, som de står her, og lægger ikke selv dage sammen
    denne_uge = til - timedelta(days=til.weekday())
    # forrige_uge og ugen_foer er de to sidste hele uger (mandag–søndag); dem gennemgår rutinen
    spaend = {"idag": (til, til), "uge": (denne_uge, til), "fire_uger": (til - timedelta(days=27), til),
              "forrige_uge": (denne_uge - timedelta(days=7), denne_uge - timedelta(days=1)),
              "ugen_foer": (denne_uge - timedelta(days=14), denne_uge - timedelta(days=8))}
    perioder = {navn: _periode(dage, pf, pt, kategorier, grupper) for navn, (pf, pt) in spaend.items()}

    # Hvad der tæller i hver kategori pr. periode (siden folder kategorierne ud med dem), og det største
    # ukategoriserede og de største programmer de seneste 14 dage, så en manglende kategori er til at se
    for navn, (pf, pt) in spaend.items():
        perioder[navn]["programmer"] = _programmer(netsek, pf, pt)
    nylig = _programmer(netsek, til - timedelta(days=13), til)
    enhedsside = _enhedsside(sek, stykliste, telefon, grupper, dage, uger, cfg, spaend)
    # Browsertid uden adresse kan ikke få én kategori (kun de enkelte sider kan), så den står ikke i listen over det,
    # der mangler en kategori, men for sig pr. enhed (enhedens fulde tid), og siden viser den ved enheden
    ukat_alle = [a for a in nylig if a["kategori"] == UKATEGORISERET and not a["browser"]]
    ukat = ukat_alle[:30]
    browser_uden: dict = defaultdict(list)
    for a in _programmer(sek, til - timedelta(days=13), til):
        if a["kategori"] == UKATEGORISERET and a["browser"]:
            for en, t in a["enheder"].items():
                browser_uden[en].append({"program": a["app"], "timer": t})
    browser_uden_adresse = {en: sorted(xs, key=lambda x: -x["timer"]) for en, xs in browser_uden.items()}
    stoerste = nylig[:20]

    enheder = []
    kendte = set()
    for en in cfg["enheder"]:
        b = samlet.get(en["navn"]) if _vaerter(en) else None
        kendte.add(en["navn"])
        enheder.append({"navn": en["navn"], "vaert": en.get("vaert"), "slags": en.get("slags"), "sjaelden": bool(en.get("sjaelden")),
                        "sidst": b["sidst"] if b else None, "kendt": True, "afk_mangler": en["navn"] in afk_mangler,
                        "afk_stoppet": afk_stoppet.get(en["navn"])})
    for navn, b in samlet.items():
        if navn not in kendte:
            enheder.append({"navn": navn, "vaert": navn, "slags": None, "sidst": b.get("sidst"), "kendt": False,
                            "afk_mangler": navn in afk_mangler, "afk_stoppet": afk_stoppet.get(navn)})

    return {
        "genereret": nu.astimezone(DK).isoformat(timespec="seconds"),
        "fra": fra.isoformat(), "til": til.isoformat(),
        "doegn_skifter": cfg["doegn_skifter"], "sen_fra": cfg["sen_fra"],
        "kategorier": kategorier,
        "grupper": [{"navn": g["navn"], "kategorier": g["kategorier"]} for g in cfg.get("grupper", [])],
        "korte_tjek_sek": (cfg.get("korte_tjek") or {}).get("under_sek"),
        "enheder": enheder,
        "dage": dage,
        "uger": [uger[m] for m in sorted(uger)],
        "perioder": perioder,
        "ukategoriseret": ukat,
        "ukategoriseret_antal": len(ukat_alle),
        "browser_uden_adresse": browser_uden_adresse,
        "stoerste": stoerste,
        "enhedsside": enhedsside,
        "regler": [{"kategori": k["navn"], **{f: r[f] for f in ("app", "domaene", "sti", "titel") if f in r}}
                   for k in cfg["kategorier"] for r in k["regler"]],
        "valg": cfg.get("valg", []),
    }


def _pr_time(start: datetime, slut: datetime):
    """[start, slut) delt på lokale klokketimer: (time 0–23, sekunder)."""
    t = start
    while t < slut:
        lokal = t.astimezone(DK)
        naeste = (lokal.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).astimezone(timezone.utc)
        stop = min(slut, naeste)
        yield lokal.hour, (stop - t).total_seconds()
        t = stop


def _forloeb(stk: list, net: list[float], cfg: dict, fra: date) -> dict:
    """Dagens forløb fra dato `fra`: {dato: [{"start", "slut", "kategori", "gruppe"}]}. Hvert kvarter får den kategori,
    der fik mest tid i det (netto, så tid på flere enheder på én gang tæller én gang), når det har mindst KVARTER_MIN
    sekunder; nabokvarterer med samme kategori lægges sammen. Kvartererne regnes i UTC, så sommertid ikke giver huller."""
    pr_kvarter: dict = defaultdict(lambda: defaultdict(float))
    for (ps, pe, _enhed, dato, _sen, kat, _nøgle), n in zip(stk, net):
        varighed = (pe - ps).total_seconds()
        if dato < fra or n <= 0 or varighed <= 0:
            continue
        andel, a, z = n / varighed, ps.astimezone(timezone.utc), pe.astimezone(timezone.utc)
        k = a.replace(minute=a.minute - a.minute % 15, second=0, microsecond=0)
        while k < z:
            overlap = (min(z, k + KVARTER) - max(a, k)).total_seconds()
            if overlap > 0:
                pr_kvarter[(dato, k)][kat] += overlap * andel
            k += KVARTER
    ud: dict = defaultdict(list)
    for (dato, k) in sorted(pr_kvarter):
        kat = pr_kvarter[(dato, k)]
        if sum(kat.values()) < KVARTER_MIN:
            continue
        størst = max(kat, key=kat.get)
        blokke = ud[dato]
        if blokke and blokke[-1]["kategori"] == størst and blokke[-1]["_slut"] == k:
            blokke[-1]["_slut"] = k + KVARTER
        else:
            blokke.append({"kategori": størst, "gruppe": cfg["_gruppe"].get(størst, UKATEGORISERET), "_start": k, "_slut": k + KVARTER})
    lokal = lambda t: t.astimezone(DK).isoformat(timespec="minutes")
    return {d: [{"start": lokal(b["_start"]), "slut": lokal(b["_slut"]), "kategori": b["kategori"], "gruppe": b["gruppe"]}
                for b in bs] for d, bs in ud.items()}


def _fordel(stk: list, telefon: set) -> tuple[list[float], dict]:
    """Fordeler tid, hvor flere enheder var i brug på én gang, så den kun tæller én gang i alt. Giver nettosekunderne
    for hvert stykke i `stk` (samme rækkefølge) og {dato: sekunder, hvor mere end én enhed var i brug}.

    - Er telefonens skærm tændt, kigger du på den: telefonen får tiden, og computerne intet. Computerens "aktive" tid
      er dér som regel bare de 3 minutter, afk-måleren venter, før den regner dig som væk.
    - Ellers deles tiden ligeligt mellem computerne i brug. afk-måleren kan ikke se, hvilken skærm du kigger på,
      når du skifter frem og tilbage.
    Overlapper en enheds egne stykker (det bør de ikke), deler de enhedens andel."""
    net = [0.0] * len(stk)
    samtidig: dict = defaultdict(float)
    hændelser = sorted([(s[0], 1, i) for i, s in enumerate(stk)] + [(s[1], 0, i) for i, s in enumerate(stk)])
    aktive: set = set()
    forrige = None
    for t, er_start, i in hændelser:
        if aktive and forrige is not None and t > forrige:
            n = (t - forrige).total_seconds()
            pr_enhed: dict = defaultdict(list)
            for j in aktive:
                pr_enhed[stk[j][2]].append(j)
            vindere = [e for e in pr_enhed if e in telefon] or list(pr_enhed)
            for e in vindere:
                for j in pr_enhed[e]:
                    net[j] += n / len(vindere) / len(pr_enhed[e])
            if len(pr_enhed) > 1:
                samtidig[stk[next(iter(aktive))][3]] += n
        forrige = t
        (aktive.add if er_start else aktive.discard)(i)
    return net, samtidig


def _samtidig(stykliste: dict, telefon: set) -> dict:
    """Telefonens tid, mens en computer samtidig var i aktiv brug: {dato: {(telefonens gruppe, computerens gruppe):
    sek}}. Dato er telefonstykkets dag."""
    comp = sorted(x for e, xs in stykliste.items() if e not in telefon for x in xs)
    starter = [x[0] for x in comp]
    ud: dict = defaultdict(lambda: defaultdict(float))
    for e in telefon:
        for ps, pe, pg, dato in stykliste.get(e, []):
            i = max(bisect.bisect_right(starter, ps) - 1, 0)
            # computerstykker er korte; gå tilbage, til ingen kan nå ind i telefonstykket
            while i > 0 and comp[i - 1][1] > ps:
                i -= 1
            while i < len(comp) and comp[i][0] < pe:
                cs, ce, cg, _ = comp[i]
                o = (min(pe, ce) - max(ps, cs)).total_seconds()
                if o > 0:
                    ud[dato][(pg, cg)] += o
                i += 1
    return ud


def _enhedsside(sek: dict, stykliste: dict, telefon: set, grupper: list, dage: list, uger: dict, cfg: dict,
                perioder: dict) -> dict:
    """Tallene pr. enhed på siden (feltet enhedsside). Enhederne har data fra forskellige dage, så hver enhed måles
    pr. hel dag med data, og alt, der sammenligner enhederne, bygger kun på fælles hele dage (telefon og mindst én
    computer har data). En
    hel dag er ikke i dag (den er ikke slut) og ikke en enheds første dag, hvis dens første data kom mere end fire timer
    efter døgnskiftet (den blev sat op midt på dagen). Under FORELOEBIG_UNDER hele dage er et tal foreløbigt; siden siger det."""
    t = lambda x: round(x / 3600, 2)
    alle = sorted({e for d in sek.values() for e in d})
    rækkefølge = [e["navn"] for e in cfg["enheder"]]
    alle.sort(key=lambda e: rækkefølge.index(e) if e in rækkefølge else 99)
    idag = perioder["idag"][1]
    dage_med = {e: sorted(d for d in sek if e in sek[d] and sek[d][e]["total"] > 0) for e in alle}
    første_data = {e: min(x[0] for x in xs).astimezone(DK) for e, xs in stykliste.items() if xs}

    def hel(e: str, d: date) -> bool:
        if d >= idag:
            return False
        f = første_data.get(e)
        døgnstart = datetime.combine(d, _klokken(cfg["doegn_skifter"]), tzinfo=DK)
        return not (dage_med[e] and d == dage_med[e][0] and f and f - døgnstart > timedelta(hours=4))

    hele = {e: [d for d in dage_med[e] if hel(e, d)] for e in alle}
    samtidig = _samtidig(stykliste, telefon)
    gr = lambda k: cfg["_gruppe"].get(k, UKATEGORISERET)
    alle_grupper = list(grupper) + [UKATEGORISERET]

    enheder = []
    for e in alle:
        pr = {}
        for navn, (pf, pt) in perioder.items():
            ds = [d for d in dage_med[e] if pf <= d <= pt]
            hd = [d for d in hele[e] if pf <= d <= pt]
            total, grp, katsum, apps = 0.0, defaultdict(float), defaultdict(float), defaultdict(float)
            for d in ds:
                v = sek[d][e]
                total += v["total"]
                for k, n in v["kat"].items():
                    grp[gr(k)] += n
                    katsum[k] += n
                for (app, _, _, dom, kat, _, _), a in v["apps"].items():
                    apps[(dom or app, kat)] += a["sek"]
            top = sorted(apps.items(), key=lambda x: -x[1])[:5]
            hel_total = sum(sek[d][e]["total"] for d in hd)
            hel_grp, hel_kat = defaultdict(float), defaultdict(float)
            for d in hd:
                for k, n in sek[d][e]["kat"].items():
                    hel_grp[gr(k)] += n
                    hel_kat[k] += n
            pr[navn] = {"dage": len(ds), "hele_dage": len(hd), "timer": t(total),
                        "pr_dag": t(hel_total / len(hd)) if hd else None,
                        "grupper": {g: t(grp[g]) for g in alle_grupper if grp.get(g)},
                        "grupper_pr_dag": {g: t(hel_grp[g] / len(hd)) for g in alle_grupper if hel_grp.get(g)} if hd else {},
                        # Kategorierne inden for grupperne (siden viser dem, når man peger på en gruppe i en bjælke)
                        "kategorier": {k: t(n) for k, n in sorted(katsum.items(), key=lambda x: -x[1]) if t(n)},
                        "kategorier_pr_dag": {k: t(n / len(hd)) for k, n in sorted(hel_kat.items(), key=lambda x: -x[1]) if t(n / len(hd))} if hd else {},
                        "andele": {g: round(grp[g] / total, 3) for g in alle_grupper if grp.get(g)} if total else {},
                        "top": [{"navn": n, "kategori": k, "timer": t(x)} for (n, k), x in top]}
        # Døgnrytme de seneste 28 dage: minutter pr. klokketime i gennemsnit pr. dag med data
        pf, pt = perioder["fire_uger"]
        ds = [d for d in hele[e] if pf <= d <= pt]
        pr_time = [0.0] * 24
        for d in ds:
            for h, n in sek[d][e]["time"].items():
                pr_time[h] += n
        enheder.append({"navn": e, "telefon": e in telefon, "foerste": dage_med[e][0].isoformat() if dage_med[e] else None,
                        "dage": len(dage_med[e]), "hele_dage": len(hele[e]), "perioder": pr,
                        "doegn": {"dage": len(ds), "min_pr_time": [round(x / 60 / len(ds), 1) if ds else None for x in pr_time],
                                  "min_pr_dag": round(sum(pr_time) / 60 / len(ds)) if ds else None,
                                  "travleste": [{"time": h, "min": round(pr_time[h] / 60 / len(ds), 1)}
                                                for h in sorted(range(24), key=lambda h: -pr_time[h])[:3] if pr_time[h]] if ds else []}})

    faelles = {}
    for navn, (pf, pt) in perioder.items():
        # I dag med, når den er perioden; ellers kun hele dage, så en halv opsætningsdag ikke skævvrider andelene
        ok = (lambda e, d: d in dage_med[e]) if navn == "idag" else (lambda e, d: d in hele[e])
        ds = [d for d in sek if pf <= d <= pt and any(e in telefon and ok(e, d) for e in sek[d])
              and any(e not in telefon and ok(e, d) for e in sek[d])]
        enh = defaultdict(float)
        for d in ds:
            for e, v in sek[d].items():
                enh[e] += v["total"]
        total = sum(enh.values())
        sam, pr_tel, pr_comp = 0.0, defaultdict(float), defaultdict(float)
        for d in ds:
            for (pg, cg), n in samtidig.get(d, {}).items():
                sam += n
                pr_tel[pg] += n
                pr_comp[cg] += n
        tel = sum(enh[e] for e in telefon)
        faelles[navn] = {"dage": len(ds), "dage_liste": [d.isoformat() for d in sorted(ds)],
                         "enheder": {e: t(enh[e]) for e in alle if enh.get(e)},
                         "andele": {e: round(enh[e] / total, 3) for e in alle if enh.get(e)} if total else {},
                         "samtidig": {"timer": t(sam), "andel_af_telefon": round(sam / tel, 3) if tel else None,
                                      "telefonens_grupper": {g: t(pr_tel[g]) for g in alle_grupper if pr_tel.get(g)},
                                      "telefonens_andele": {g: round(pr_tel[g] / sam, 3) for g in alle_grupper if pr_tel.get(g)},
                                      "computerens_grupper": {g: t(pr_comp[g]) for g in alle_grupper if pr_comp.get(g)},
                                      "computerens_andele": {g: round(pr_comp[g] / sam, 3) for g in alle_grupper if pr_comp.get(g)}}}

    # Uge for uge pr. enhed, de seneste 8 uger: timer pr. dag med data (None uden data den uge)
    ugeliste = []
    for m in sorted(uger)[-8:]:
        u = uger[m]
        felt = {}
        for e in alle:
            ds = [d for d in hele[e] if m <= d <= m + timedelta(days=6)]
            felt[e] = {"hele_dage": len(ds), "timer": t(sum(sek[d][e]["total"] for d in ds)),
                       "pr_dag": t(sum(sek[d][e]["total"] for d in ds) / len(ds)) if ds else None}
        ugeliste.append({"uge": u["uge"], "mandag": u["mandag"], "enheder": felt})

    return {"enheder": enheder, "faelles": faelles, "uger": ugeliste, "foreloebig_under": FORELOEBIG_UNDER,
            "grupper": alle_grupper, "doegn_skifter_time": _klokken(cfg["doegn_skifter"]).hour}


def _tjek(samlet: dict, cfg: dict, fra: date, til: date, telefon: set | None = None) -> dict:
    """Telefonens tjek pr. dag: åbninger af apps i `korte_tjek.kategorier` (sammenhængende tid i samme app; et skift
    til en anden app, også hjemmeskærmen, afslutter åbningen), hvor mange af dem der var korte (under
    `korte_tjek.under_sek`), og oplåsninger. Kun telefonerne (se telefoner()); {} uden telefon."""
    if telefon is None:
        telefon = telefoner(samlet, cfg)
    kt = cfg.get("korte_tjek") or {}
    kats, graense = set(kt.get("kategorier", [])), kt.get("under_sek", 60)
    skift = _klokken(cfg["doegn_skifter"])
    dato = lambda t: (lambda l: l.date() - timedelta(days=1) if l.time() < skift else l.date())(t.astimezone(DK))
    ud: dict = {}
    for enhed, b in samlet.items():
        if enhed not in telefon:
            continue
        evs = sorted((_dt(e["timestamp"]), e.get("duration") or 0, e.get("data") or {}) for e in b.get("window") or [])
        if not evs:
            continue
        dage_med = {dato(t) for t, _, _ in evs}
        for d in dage_med:
            if fra <= d <= til:
                ud.setdefault(d, {"aabninger": 0, "korte": 0, "oplaasninger": 0})
        sessioner, cur = [], None
        for t, n, data in evs:
            nøgle = data.get("package") or data.get("app")
            if cur and cur[0] == nøgle and (t - cur[2]).total_seconds() <= 10:
                cur[2] = max(cur[2], t + timedelta(seconds=n))
            else:
                if cur:
                    sessioner.append(cur)
                cur = [nøgle, t, t + timedelta(seconds=n), data]
        if cur:
            sessioner.append(cur)
        for nøgle, start, slut, data in sessioner:
            d = dato(start)
            if d not in ud:
                continue
            if kategoriser(cfg, data.get("app"), data.get("package"), None, None, data.get("title")) in kats:
                ud[d]["aabninger"] += 1
                if (slut - start).total_seconds() < graense:
                    ud[d]["korte"] += 1
        for e in b.get("unlock") or []:
            d = dato(_dt(e["timestamp"]))
            if d in ud:
                ud[d]["oplaasninger"] += 1
    return ud


def _forlaeng(web: tuple[list, list]) -> tuple[list, list]:
    """Telefonens browser melder kun et øjeblik, når fanen skifter (sekunder ad gangen). En fane gælder derfor, til
    den næste kommer, højst FANE_MAKS efter; browserens vinduestid klipper den bagefter. Kun telefonen: på
    computerne melder udvidelsen løbende, og et hul betyder, at fanen ikke var i brug."""
    starter, xs = web
    ud = []
    for i, (s, e, d) in enumerate(xs):
        naeste = xs[i + 1][0] if i + 1 < len(xs) else s + FANE_MAKS
        ud.append((s, max(e, min(naeste, s + FANE_MAKS)), d))
    return starter, ud


def _programmer(sek: dict, fra: date, til: date, maks: int = 300) -> list[dict]:
    """Programmer og sider fra `fra` til og med `til`, lagt sammen på tværs af enheder: navn, nøgle (det, et valg
    på siden gælder), kategori, hvorfor (kilde), om det er browsertid uden adresse, timer i alt og pr. enhed."""
    samlet: dict = {}
    d = fra
    while d <= til:
        for enhed, v in sek.get(d, {}).items():
            for (navn, typ, nøgle, dom, kat, kilde, browser), a in v["apps"].items():
                x = samlet.setdefault((typ, nøgle.lower(), kat), {
                    "navn": dom or navn, "app": navn, "type": typ, "noegle": nøgle, "domaene": dom, "kategori": kat,
                    "kilde": kilde, "browser": browser, "sek": 0.0, "enheder": defaultdict(float)})
                x["sek"] += a["sek"]
                x["enheder"][enhed] += a["sek"]
        d += timedelta(days=1)
    ud = []
    for x in sorted(samlet.values(), key=lambda x: -x["sek"])[:maks]:
        if x["sek"] < 30:
            break
        ud.append({k: x[k] for k in ("navn", "app", "type", "noegle", "domaene", "kategori", "kilde", "browser")}
                  | {"timer": round(x["sek"] / 3600, 2),
                     "enheder": {e: round(n / 3600, 2) for e, n in sorted(x["enheder"].items(), key=lambda y: -y[1])}})
    return ud


def _periode(dage: list[dict], fra: date, til: date, kategorier: list[str], grupper: list[str] = ()) -> dict:
    """Summen af dagene fra `fra` til og med `til`: timer, sen tid, kategorier, grupper, enheder, hvor stor en del,
    der er ukategoriseret (None uden tid), og telefonens tjek (i alt og pr. dag med telefondata)."""
    valgte = [d for d in dage if fra.isoformat() <= d["dato"] <= til.isoformat()]
    kat: dict = defaultdict(float)
    grp: dict = defaultdict(float)
    enh: dict = defaultdict(float)
    tj: dict = defaultdict(int)
    tjek_dage = [d["tjek"] for d in valgte if d.get("tjek")]
    for t in tjek_dage:
        for k, n in t.items():
            tj[k] += n or 0
    for d in valgte:
        for k, t in d["kategorier"].items():
            kat[k] += t
        for g, t in d.get("grupper", {}).items():
            grp[g] += t
        for en, v in d["enheder"].items():
            enh[en] += v["timer"]
    timer = round(sum(d["timer"] for d in valgte), 2)
    return {"fra": fra.isoformat(), "til": til.isoformat(), "timer": timer,
            "sen_timer": round(sum(d["sen_timer"] for d in valgte), 2),
            "samtidig_timer": round(sum(d.get("samtidig_timer", 0) for d in valgte), 2),
            "dage_med_data": sum(1 for d in valgte if d["enheder"]),
            "kategorier": {k: round(kat[k], 2) for k in kategorier if kat.get(k)},
            "grupper": {g: round(grp[g], 2) for g in list(grupper) + [UKATEGORISERET] if grp.get(g)},
            "tjek": ({"dage": len(tjek_dage), **dict(tj),
                      **{f"{k}_pr_dag": round(tj[k] / len(tjek_dage), 1) for k in ("aabninger", "korte", "oplaasninger")}}
                     if tjek_dage else None),
            "enheder": {en: round(t, 2) for en, t in enh.items()},
            "ukategoriseret_andel": round(kat.get(UKATEGORISERET, 0) / timer, 3) if timer else None}


# --- ActivityWatch ------------------------------------------------------------

def _get(server: str, sti: str, **params) -> object:
    url = f"{server}/api/0/{sti}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())


def _vaert(bid: str, b: dict, lokal: str | None) -> str:
    """Bucketens vært. Browserudvidelsen og aw-stopwatch skriver `unknown`; ligger bucketen her på Mac'en selv (ikke
    hentet med aw-sync, som sætter `$aw.sync.origin`), er det Mac'en. Hentede buckets beholder det, aw-sync gav dem."""
    vaert = b.get("hostname")
    if (not vaert or vaert == "unknown") and lokal and not (b.get("data") or {}).get("$aw.sync.origin"):
        return lokal
    return vaert or bid.split("_", 1)[-1]


def hent(server: str, fra_utc: datetime, til_utc: datetime) -> dict:
    """Alle buckets på serveren, grupperet efter vært: vinduer, afk, browserfaner og seneste begivenhed."""
    lokal = (_get(server, "info") or {}).get("hostname")
    buckets = _get(server, "buckets/")
    raa: dict = {}
    for bid, b in buckets.items():
        vaert = _vaert(bid, b, lokal)
        slags = {"currentwindow": "window", "afkstatus": "afk", "web.tab.current": "web",
                 "os.lockscreen.unlocks": "unlock"}.get(b.get("type"))
        if not slags:
            continue
        r = raa.setdefault(vaert, {"window": [], "afk": None, "web": [], "unlock": [], "sidst": None})
        events = _get(server, f"buckets/{urllib.parse.quote(bid, safe='')}/events", limit=-1,
                      start=fra_utc.isoformat(), end=til_utc.isoformat())
        if slags == "afk":
            r["afk"] = (r["afk"] or []) + events
        else:
            r[slags] += events
        nyeste = _get(server, f"buckets/{urllib.parse.quote(bid, safe='')}/events", limit=1)
        if nyeste:
            e = nyeste[0]
            t = _dt(e["timestamp"]) + timedelta(seconds=e.get("duration") or 0)
            # Lokal tid, så siden kan læse datoen direkte ("i dag kl. 00.47")
            if r["sidst"] is None or t > _dt(r["sidst"]):
                r["sidst"] = t.astimezone(DK).isoformat(timespec="seconds")
    return raa


def byg(ud: Path = UD, server: str = SERVER, dage: int = DAGE, nu: datetime | None = None) -> dict:
    cfg = laes_regler()
    nu = nu or datetime.now(timezone.utc)
    lokal = nu.astimezone(DK)
    skift = _klokken(cfg["doegn_skifter"])
    idag = lokal.date() - timedelta(days=1) if lokal.time() < skift else lokal.date()
    fra = idag - timedelta(days=dage - 1)
    # Hent fra døgnskiftet før `fra` (en begivenhed kan begynde før og række ind) til nu
    fra_utc = (datetime.combine(fra - timedelta(days=1), skift, tzinfo=DK)).astimezone(timezone.utc)
    try:
        raa = hent(server, fra_utc, nu)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise SystemExit(f"ActivityWatch svarer ikke på {server}: {e}") from e
    doc = beregn(raa, cfg, fra, idag, nu)
    doc["rapport"] = seneste_rapport()
    ud.mkdir(parents=True, exist_ok=True)
    _skriv(ud / "skaermtid.json", json.dumps(doc, ensure_ascii=False))
    for f in SIDE.iterdir():
        if f.is_file() and not f.name.startswith("."):
            shutil.copyfile(f, ud / f.name)
    # Manifestet til sidst, når siden og tallene er på plads
    _skriv(ud / "kompas.json", json.dumps(KOMPAS | {"opdateret": nu.astimezone(timezone.utc).isoformat(timespec="seconds")
                                                      .replace("+00:00", "Z")}, ensure_ascii=False))
    return doc


def seneste_rapport(mappe: Path = RAPPORTER) -> dict | None:
    """Den nyeste gennemgang fra rutinen (rapporter/<uge>.json), som siden viser; None, hvis der ingen er."""
    filer = sorted(mappe.glob("*-W*.json")) if mappe.is_dir() else []
    if not filer:
        return None
    try:
        r = json.loads(filer[-1].read_text())
    except ValueError:
        return None
    if not isinstance(r, dict):
        return None
    # Ugens mandag, så siden kan skrive "uge 42 · 12.–18. okt."
    aar, uge = (int(x) for x in filer[-1].stem.split("-W"))
    return {"mandag": date.fromisocalendar(aar, uge, 1).isoformat()} | r | {"uge": filer[-1].stem}


def rapport(doc: dict) -> dict:
    """Ugens tal til rutinen, færdigregnede: den sidste hele uge mod ugen før, delt på grupper, kategorier og enheder,
    korte tjek, telefonen samtidig med computer, de største programmer, det ukategoriserede, kategorier sat kun ud fra
    en vinduestitel (til at tjekke), enhedernes seneste data og dine valg. Rutinen skal ikke selv lægge tal sammen."""
    p, f = doc["perioder"]["forrige_uge"], doc["perioder"]["ugen_foer"]
    mandag = date.fromisoformat(p["fra"])
    uden = lambda x: {k: v for k, v in x.items() if k != "programmer"}
    return {
        "uge": f"{mandag.isocalendar()[0]}-W{mandag.isocalendar()[1]:02d}", "mandag": p["fra"], "soendag": p["til"],
        "genereret": doc["genereret"], "doegn_skifter": doc["doegn_skifter"], "sen_fra": doc["sen_fra"],
        "forrige_uge": uden(p), "ugen_foer": uden(f),
        "stoerste": p["programmer"][:15],
        "kun_titel": [x for x in p["programmer"] if x["kilde"] == "titel"][:15],
        "faelles": doc["enhedsside"]["faelles"]["forrige_uge"],
        "enheder_pr_dag": {e["navn"]: {k: e["perioder"]["forrige_uge"][k] for k in ("pr_dag", "hele_dage", "grupper_pr_dag")}
                           for e in doc["enhedsside"]["enheder"]},
        "ukategoriseret": doc["ukategoriseret"], "ukategoriseret_antal": doc["ukategoriseret_antal"],
        "browser_uden_adresse": doc["browser_uden_adresse"],
        "enheder": doc["enheder"], "kategorier": doc["kategorier"], "valg": doc["valg"],
    }


def _skriv(sti: Path, tekst: str) -> None:
    tmp = sti.with_suffix(sti.suffix + ".tmp")
    tmp.write_text(tekst)
    tmp.replace(sti)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Skærmtid fra ActivityWatch til Kompas")
    sub = p.add_subparsers(dest="kommando", required=True)
    b = sub.add_parser("byg", help="skriv skaermtid.json, kompas.json og siden")
    b.add_argument("--ud", type=Path, default=UD)
    b.add_argument("--server", default=SERVER)
    b.add_argument("--dage", type=int, default=DAGE)
    r = sub.add_parser("rapport", help="byg og skriv ugens tal til rutinen som JSON (den sidste hele uge mod ugen før)")
    r.add_argument("--ud", type=Path, default=UD)
    r.add_argument("--server", default=SERVER)
    a = p.parse_args(argv)
    if a.kommando == "rapport":
        print(json.dumps(rapport(byg(a.ud, a.server)), ensure_ascii=False, indent=1))
        return 0
    doc = byg(a.ud, a.server, a.dage)
    sidste = doc["dage"][-1] if doc["dage"] else {"timer": 0}
    print(f"{a.ud}: {len(doc['dage'])} dage fra den første med data, i dag {sidste['timer']} t, "
          f"{len([e for e in doc['enheder'] if e['sidst']])} enheder med data")
    return 0


if __name__ == "__main__":
    sys.exit(main())
