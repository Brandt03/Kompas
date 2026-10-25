"""Demodata til Form & fokus (/form/): garmin-coach og overblik.

Modulet laver en opdigtet garmin-coach-database for "Alex" i en midlertidig mappe og kører projekternes egne
byg på den, så tallene på siderne er regnet af den rigtige kode:

- overblik (`opdater`, `gem-review`, `eksport`) skriver liv.json, også nætterne, planlagt mod faktisk og studietiden,
- garmin-coach (`site.byg`) skriver coach.json, soevn.json, kroppen.json og kroppen/ (døgn for døgn og måned for
  måned til Kroppen i tal), perioder.json, oversigt.json og kompas.json.

Kun rådata (Garmin med døgnets og nattens kurver, Hevy, kalender med studieblokke, et lille Sure-udtræk og et
Skærmtid- og Studie-udtræk i samme form som de rigtige), periodernes vurderinger og ugereviewenes tekst er
opdigtet her; teksterne bygger på de tal, koden har regnet. Byg-vejen i begge projekter bruger kun
standardbiblioteket, så modulet kræver ingen af garmin-coach' tredjepartspakker (mcp, garminconnect, icalendar).
Uret fryses til `idag` kl. 7 under byg (Python og SQLite), så alt følger `idag`. Intet skrives uden for `ud` og
en midlertidig mappe, og intet rammer nettet.
"""
from __future__ import annotations

import contextlib
import json
import math
import random
import sqlite3
import sys
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

ROD = Path(__file__).resolve().parents[2]
COACH = ROD / "coach"
LIV = ROD / "overblik"
KL = time(7, 0)  # siderne er "bygget" kl. 7, når Kompas-appen åbnes om morgenen

DK = ZoneInfo("Europe/Copenhagen")
UGEDAGE = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]

# Opdigtet atlet: makspuls 196 og hvilepuls 52 giver pulszonerne nedenfor (Karvonen 50-90 %).
ZONER = {1: 124, 2: 138, 3: 153, 4: 167, 5: 182}

# Pladsholderfag i samme form som titlerne fra universitetets skema: "Alfa – lorem ipsum (A) - KURS101.A -
# Lecture (On Campus)". garmin-coach genkender dem som undervisning, og første ord bestemmer faget i Kompas.
# (navn, kode, hold, kort navn i CalTask)
FAG = [
    ("Alfa – lorem ipsum", "KURS101", "A", "Alfa"),
    ("Beta – dolor sit amet", "KURS102", "B", "Beta"),
    ("Gamma – consectetur", "KURS103", "C", "Gamma"),
]
ALFA, BETA, GAMMA = range(3)
# Ugeskema i de fire moduler 08:15–10:00, 10:15–12:00, 13:00–14:45 og 15:00–16:45:
# ugedag -> (fag, start, slut, art, form). Hver hverdag har to moduler med et hul imellem.
SKEMA = {
    0: [(BETA, "10:15", "12:00", "Lecture", "On Campus"), (GAMMA, "15:00", "16:45", "Exercise", "On Campus")],
    1: [(ALFA, "08:15", "10:00", "Lecture", "On Campus"), (ALFA, "13:00", "14:45", "Exercise", "On Campus")],
    2: [(GAMMA, "10:15", "12:00", "Lecture", "On Campus"), (BETA, "15:00", "16:45", "Exercise", "On Campus")],
    3: [(ALFA, "08:15", "10:00", "Lecture", "Online"), (BETA, "13:00", "14:45", "Lecture", "On Campus")],
    4: [(GAMMA, "08:15", "10:00", "Supervision", "On Campus"), (GAMMA, "13:00", "14:45", "Lecture", "On Campus")],
}
# Selvstudie, som CalTask logger det: ugedag -> (fag, start, varighed i timer)
SELVSTUDIE = {0: (ALFA, "08:15", 1.5), 2: (GAMMA, "12:45", 2.0), 3: (BETA, "10:30", 1.5), 6: (GAMMA, "13:00", 2.0)}
SELVSTUDIE_TUNG = {1: (BETA, "15:15", 3.0), 2: (GAMMA, "19:00", 2.0), 4: (ALFA, "10:30", 2.5), 5: (ALFA, "11:00", 3.0)}
# Studieblokke fra Kompas' studieplan (mærket #kompas-plan i kalenderen, plan_blok = 1): ugedag -> (fag, start, slut,
# hvad). Dagene uden fast selvstudie i CalTask bliver tit glippet, og de to døgn før i går er altid glippet, så I dag
# har noget at vise under Står stille.
PLAN = {0: (ALFA, "08:15", "10:00", "fagnoter"), 1: (BETA, "15:00", "16:45", "øvelser"),
        2: (GAMMA, "12:45", "14:45", "læsning"), 3: (BETA, "10:15", "12:00", "fagnoter"),
        4: (ALFA, "10:15", "12:00", "opgave"), 5: (BETA, "13:00", "14:30", "repetition"),
        6: (GAMMA, "13:00", "15:00", "opgave")}

# Hevy: to programmer, (øvelse, sæt, reps, start-kg, slut-kg, trin)
STYRKE = {
    "A": [("Squat (Barbell)", 3, 5, 72.5, 95, 2.5), ("Bench Press (Barbell)", 3, 5, 55, 70, 2.5),
          ("Bent Over Row (Barbell)", 3, 8, 45, 60, 2.5)],
    "B": [("Romanian Deadlift (Barbell)", 3, 8, 62.5, 85, 2.5), ("Overhead Press (Barbell)", 3, 6, 32.5, 42.5, 2.5),
          ("Incline Bench Press (Dumbbell)", 3, 10, 18, 24, 2), ("Bulgarian Split Squat (Dumbbell)", 3, 10, 12, 18, 2)],
}

# Alt andet i kalenderen er pladsholdere
SOCIALT = ["Tempor incididunt", "Ut labore et dolore", "Magna aliqua", "Ut enim ad minim", "Quis nostrud",
           "Exercitation ullamco"]
ANDET = {"start": "Lorem ipsum", "intro": "Dolor sit amet", "fredag": "Consectetur", "imorgen": "Adipiscing elit",
         "om2": "Sed do eiusmod"}


# --------------------------------------------------------------------------------------------------------------
# Små hjælpere
# --------------------------------------------------------------------------------------------------------------

def mandag(d: date) -> date:
    return d - timedelta(days=d.weekday())


def tal(x, d: int = 0) -> str:
    """Dansk talformat: 8.812 og 7,4."""
    if x is None:
        return "–"
    s = f"{x:,.{d}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def kl(hhmm: str) -> str:
    return hhmm.replace(":", ".")


def _klem(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _importer() -> SimpleNamespace:
    """Projekternes egne moduler. Stierne fjernes igen bagefter, så de ikke forstyrrer andre demomoduler."""
    stier = [str(COACH), str(LIV)]
    sys.path[:0] = stier
    try:
        from garmin_coach import config as gc_config, db as gc_db, kroppen, metrics, site
        from overblik import cli, config as liv_config, db as liv_db, kilder, rapport, side
    finally:
        for s in stier:
            sys.path.remove(s)
    return SimpleNamespace(gc_config=gc_config, gc_db=gc_db, kroppen=kroppen, metrics=metrics, site=site, cli=cli,
                           liv_config=liv_config, liv_db=liv_db, kilder=kilder, rapport=rapport, side=side)


@contextlib.contextmanager
def _frossent_ur(nu: datetime, moduler):
    """Erstat `date`/`datetime` i modulerne med udgaver, hvor i dag og nu er `nu` (som smoke_test.py gør)."""

    class Dato(date):
        @classmethod
        def today(cls):
            return cls(nu.year, nu.month, nu.day)

    class Tid(datetime):
        @classmethod
        def now(cls, tz=None):
            t = cls(nu.year, nu.month, nu.day, nu.hour, nu.minute)
            return t if tz is None else t.astimezone(tz)

        @classmethod
        def today(cls):
            return cls.now()

    with contextlib.ExitStack() as stak:
        for m in moduler:
            if hasattr(m, "date"):
                stak.enter_context(mock.patch.object(m, "date", Dato))
            if hasattr(m, "datetime"):
                stak.enter_context(mock.patch.object(m, "datetime", Tid))
        yield


def _sql_date(idag: date):
    """SQLites date() med `idag` som 'now'. Dækker de former, garmin-coach bruger: date(kolonne) og
    date('now', 'localtime', '-N days')."""
    def date_(v, *mods):
        if v is None:
            return None
        d = idag if v == "now" else date.fromisoformat(str(v)[:10])
        for m in mods:
            if str(m).endswith(("day", "days")):
                d += timedelta(days=int(str(m).split()[0]))
        return d.isoformat()
    return date_


def _utc(lokal: datetime) -> str:
    return lokal.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _hm(d: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(d, time(h, m))


# --------------------------------------------------------------------------------------------------------------
# Rådata: Garmin, Hevy, kalender og et Sure-udtræk
# --------------------------------------------------------------------------------------------------------------

class Tidslinje:
    """Datoerne demoen hænger på, alle regnet fra idag."""

    def __init__(self, idag: date):
        self.idag = idag
        self.denne = mandag(idag)
        self.start = self.denne - timedelta(weeks=34)          # første dag med data (en mandag)
        self.semester = self.denne - timedelta(weeks=6)        # første undervisningsuge
        self.selvstudie_fra = self.semester + timedelta(weeks=1)
        self.tung = self.denne - timedelta(weeks=1)            # ugen reviewet handler om: afleveringsuge
        self.kalender_til = self.denne + timedelta(days=20)    # kalenderen rækker tre uger frem
        self.hul = self.idag - timedelta(days=71)              # en dag, hvor uret lå i skuffen
        self.plan_fra = self.denne - timedelta(weeks=3)        # studieplanens blokke i kalenderen
        self.skaerm_fra = self.idag - timedelta(days=56)       # Skærmtid har målt i otte uger
        self.kurver_fra = self.idag - timedelta(days=60)       # døgnets kurver er hentet for de seneste 60 dage
        self._faktorer: dict = {}
        # Fyldes, mens databasen bygges, og bruges af Skærmtid-udtrækket: (seng, op) pr. dag og dagens pas
        self.soevn: dict = {}
        self.pas: dict = {}
        self.kalender: list = []

    def sen(self, aften: date) -> float | None:
        """Sen skærmtid (efter kl. 23) aftenen `aften` i timer, som Skærmtid måler den; None før Skærmtid kom med
        og i aften, som ikke er kommet endnu."""
        if aften < self.skaerm_fra or aften >= self.idag:
            return None
        rng = random.Random(aften.toordinal() * 7 + 3)
        f = self.ugefaktor(aften)
        base = 0.2 + (0.45 if aften.weekday() in (4, 5) else 0) + (0.5 if mandag(aften) == self.tung else 0) \
            - 0.8 * f["soevn"]
        return round(_klem(base + rng.expovariate(2.4) - 0.2, 0, 2.5) * 4) / 4

    def ugefaktor(self, d: date) -> dict:
        """Ugens fælles udsving (søvn, HRV, stress, take-away …), ens for alle dage i ugen."""
        m = mandag(d)
        if m not in self._faktorer:
            self._faktorer[m] = self._ny_faktor(m, random.Random(m.toordinal()))
        return self._faktorer[m]

    def _ny_faktor(self, m: date, rng: random.Random) -> dict:
        if m == self.tung:
            return {"soevn": -0.6, "hrv": -2.5, "rhr": 0.8, "stress": 7, "takeaway": 2.0}
        if m == self.denne:
            return {"soevn": 0.25, "hrv": 3.0, "rhr": -0.8, "stress": -2, "takeaway": 0.8}
        f = {"soevn": rng.gauss(0, 0.12), "hrv": rng.gauss(0, 1.6), "rhr": rng.gauss(0, 0.5),
             "stress": rng.gauss(0, 2.0), "takeaway": 1.0}
        if m >= self.semester:  # undervisningen koster lidt søvn og giver lidt mere stress
            f["soevn"] -= 0.15
            f["stress"] += 3
        # Kortere nætter går sammen med mere take-away og mere stress, så overblik har noget at finde
        f["takeaway"] = _klem(1.0 - 3.5 * f["soevn"] + rng.gauss(0, 0.15), 0.3, 2.0)
        f["stress"] += -6 * f["soevn"]
        return f


def _undervisning_og_kalender(tl: Tidslinje, rng: random.Random) -> list[tuple]:
    """Kalenderbegivenheder: (uid, start_lokal, slut_lokal, titel, heldag)."""
    ev = []

    def tilfoej(uid, s: datetime, e: datetime, titel: str, heldag: bool = False):
        ev.append((uid, s, e, titel, heldag))

    # Undervisning fra semesterstart og tre uger frem. En weekend-idag får en hverdags skema, så I dag-siden
    # altid har en dag at vise.
    d = tl.semester
    while d <= tl.kalender_til:
        skema = SKEMA.get(d.weekday()) or (SKEMA[2] if d == tl.idag else [])
        for i, (fag, a, b, art, form) in enumerate(skema):
            navn, kode, hold, _ = FAG[fag]
            titel = f"{navn} ({hold}) - {kode}.{hold} - {art} ({form})"
            tilfoej(f"skema-{d}-{i}", _hm(d, a), _hm(d, b), titel)
        d += timedelta(days=1)

    # Selvstudie logget i CalTask: kun sessioner, der er slut, når siden bygges
    nu = datetime.combine(tl.idag, KL)
    d = tl.selvstudie_fra
    while d <= tl.idag:
        plan = dict(SELVSTUDIE)
        if mandag(d) == tl.tung:
            plan.update(SELVSTUDIE_TUNG)
        if d == tl.idag - timedelta(days=1) and d.weekday() not in plan:  # i går blev der studeret i blokken
            fag, a, b, _ = PLAN[d.weekday()]
            plan[d.weekday()] = (fag, a, (_hm(d, b) - _hm(d, a)).seconds / 3600)
        glippet = d in (tl.idag - timedelta(days=2), tl.idag - timedelta(days=3))
        if d.weekday() in plan and not glippet and (rng.random() < 0.85 or mandag(d) == tl.tung or d == tl.idag - timedelta(days=1)):
            fag, a, t = plan[d.weekday()]
            s = _hm(d, a)
            e = s + timedelta(hours=t + rng.choice((-0.5, -0.25, 0, 0, 0.25)))
            if e <= nu:
                tilfoej(f"caltask-{d}", s, e, f"Selvstudie · {FAG[fag][3]}")
        d += timedelta(days=1)

    # Andet: en aftale den første dag (så kalenderen dækker hele historikken), en aften ude hver anden lørdag,
    # tre heldage før semesterstart, noget hver anden fredag og et par ting de kommende dage.
    tilfoej("start", _hm(tl.start, "08:30"), _hm(tl.start, "09:15"), ANDET["start"])
    d, i = tl.start + timedelta(days=5), 0
    while d < tl.idag:
        if mandag(d) != tl.tung:
            tilfoej(f"social-{d}", _hm(d, "19:00"), _hm(d, "23:30"), SOCIALT[i % len(SOCIALT)])
        d, i = d + timedelta(days=14), i + 1
    intro = tl.semester - timedelta(days=7)
    tilfoej("intro", datetime.combine(intro, time()), datetime.combine(intro + timedelta(days=3), time()),
            ANDET["intro"], heldag=True)
    d = tl.semester + timedelta(days=4)
    while d <= tl.kalender_til:
        if (d - tl.semester).days % 14 == 4:
            tilfoej(f"fredag-{d}", _hm(d, "15:00"), _hm(d, "18:00"), ANDET["fredag"])
        d += timedelta(days=7)
    imorgen = tl.idag + timedelta(days=1)
    tilfoej("imorgen", _hm(imorgen, "18:00"), _hm(imorgen, "20:30"), ANDET["imorgen"])
    om2 = tl.idag + timedelta(days=2)
    tilfoej("om2", datetime.combine(om2, time()), datetime.combine(om2 + timedelta(days=1), time()),
            ANDET["om2"], heldag=True)

    # Studieplanens blokke de seneste tre uger og frem (uid "plan-…" bliver plan_blok = 1)
    d = tl.plan_fra
    while d <= tl.kalender_til:
        if d.weekday() in PLAN:
            fag, a, b, hvad = PLAN[d.weekday()]
            # I dag har altid en blok, der er i gang om formiddagen (I dag viser det faktiske under den)
            if d == tl.idag and not any(s.date() == d and s.hour < 9 for _, s, _, _, heldag in ev if not heldag):
                fag, a, b, hvad = ALFA, "08:15", "10:00", "fagnoter"
            tilfoej(f"plan-{d}", _hm(d, a), _hm(d, b), f"{FAG[fag][3]} · {hvad}")
        d += timedelta(days=1)
    return ev


def _traeningsplan(tl: Tidslinje, d: date, rng: random.Random) -> list[tuple]:
    """Dagens pas: (type, start). Typer: A/B (styrke), rolig, lang, interval, boulder, svoem (morgensvømning)."""
    wd, pas = d.weekday(), []
    foer_semester = mandag(d) < tl.semester
    tung = mandag(d) == tl.tung
    if wd in (2, 4) and not tung and rng.random() < (0.55 if wd == 2 else 0.3):
        pas.append(("svoem", "06:45"))
    if wd == 0:
        pas.append(("A", "17:15"))
    elif wd == 1 and not tung and rng.random() < 0.9:
        pas.append(("rolig", "17:00"))
    elif wd == 2 and foer_semester and rng.random() < 0.7:
        pas.append(("rolig", "18:00"))
    elif wd == 3:
        pas.append(("B", "16:00"))
    elif wd == 5 and rng.random() < 0.92:
        pas.append(("interval", "10:00"))
    elif wd == 6 and not tung:
        x = rng.random()
        if x < (0.6 if foer_semester else 0.45):
            pas.append(("boulder", "16:00"))
        elif x < 0.9:
            pas.append(("lang", "10:00"))
    return pas


def _zonetid(kind: str, sek: float, rng: random.Random) -> list[float]:
    andele = {"svoem": [0.22, 0.58, 0.16, 0.04, 0.0], "rolig": [0.14, 0.74, 0.10, 0.02, 0.0], "lang": [0.12, 0.78, 0.09, 0.01, 0.0],
              "interval": [0.10, 0.42, 0.14, 0.21, 0.13], "boulder": [0.62, 0.30, 0.08, 0.0, 0.0]}[kind]
    a = [max(0.0, x + rng.gauss(0, 0.03)) for x in andele]
    s = sum(a)
    return [round(sek * x / s) for x in a]


def _byg_coach_db(conn: sqlite3.Connection, tl: Tidslinje, rng: random.Random) -> None:
    kalender = _undervisning_og_kalender(tl, rng)
    social_naetter = {s.date() + timedelta(days=1) for _, s, _, titel, heldag in kalender
                      if not heldag and s.hour >= 18 and titel != ANDET["imorgen"]}
    # Som kalenderhentningen: fag-felterne fra garmin-coachs egen tolkning af titlen og kalenderens navn
    from garmin_coach.skema import fag_kolonner
    kalendernavn = lambda uid: "Skema" if uid.startswith("skema-") else "Selvstudie" if uid.startswith("caltask-") else "Privat"
    conn.executemany(
        "INSERT INTO calendar_events (uid, start_local, end_local, start_utc, end_utc, summary, all_day, "
        "fag_navn, fag_kode, fag_art, fag_form, kalender, plan_blok) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(uid, s.strftime("%Y-%m-%dT%H:%M"), e.strftime("%Y-%m-%dT%H:%M"),
          None if heldag else _utc(s), None if heldag else _utc(e), titel, int(heldag),
          *fag_kolonner(titel).values(), kalendernavn(uid), int(uid.startswith("plan-")))
         for uid, s, e, titel, heldag in kalender])
    tl.kalender = kalender

    alle_dage = (tl.idag - tl.start).days + 1
    dage, natdata, pas_i_gaar = [], {}, 0.0
    for i in range(alle_dage):
        d = tl.start + timedelta(days=i)
        f = tl.ugefaktor(d)
        p = i / alle_dage  # fremgang fra 0 til 1 over hele perioden

        # --- træning (i dag er ikke trænet endnu kl. 7)
        belastning_i_dag, pas = 0.0, []
        if d < tl.idag and d != tl.hul:
            for n, (kind, kl_) in enumerate(_traeningsplan(tl, d, rng)):
                a = _gem_pas(conn, d, kind, kl_, n, p, rng)
                belastning_i_dag += a["belastning"]
                pas.append(a)
        tl.pas[d] = pas

        # --- søvn og restitution (natten til d)
        if d == tl.hul:
            pas_i_gaar = belastning_i_dag
            continue
        weekend = d.weekday() in (5, 6)
        sen = tl.sen(d - timedelta(days=1)) or 0.0
        # Sengetid i timer efter midnat aftenen før (over 24 er efter midnat); sen skærmtid skubber den
        seng_t = 23.0 - 1.5 * f["soevn"] + rng.gauss(0, 0.35) + (1.7 if d in social_naetter else 0) \
            + (0.4 if d.weekday() in (5, 6) else 0)
        if sen:
            seng_t = max(seng_t, 23.0 + sen + rng.uniform(0.1, 0.4))
        if any(a["kind"] == "svoem" for a in pas):
            op_t = 24 + 6.1
        else:
            op_t = 24 + (8.5 + rng.gauss(0, 0.4) if weekend else 7.0 + rng.gauss(0, 0.2))
        if d == tl.idag:
            seng_t, op_t = 23.1, 30.75
        nul = datetime.combine(d - timedelta(days=1), time())
        seng, op = nul + timedelta(hours=seng_t), nul + timedelta(hours=op_t)
        faser = _soevnfaser(seng, op, rng)
        tid = {n: sum((b - a).total_seconds() for a, b, x in faser if x == n) for n in range(4)}
        soevn = (tid[0] + tid[1] + tid[2]) / 3600
        tl.soevn[d] = (seng, op)
        natdata[d] = faser

        hrv = 55 + f["hrv"] + 3.5 * (soevn - 7.3) + rng.gauss(0, 4.5) - (5 if d in social_naetter else 0) \
            - 0.03 * pas_i_gaar
        rhr = 53 + f["rhr"] - 0.6 * (soevn - 7.3) + rng.gauss(0, 1.4) + (1.5 if d in social_naetter else 0)
        if d == tl.idag:
            hrv, rhr = 60.0, 51.0
        score = _klem(round(76 + 8 * (soevn - 7.3) + 0.3 * (hrv - 55) - 5 * sen + rng.gauss(0, 4)), 38, 95)
        readiness = _klem(round(64 + 9 * (soevn - 7.3) + 1.1 * (hrv - 55) - 1.4 * (rhr - 53)
                                - 0.08 * pas_i_gaar + rng.gauss(0, 6)), 8, 99)
        if d == tl.idag:
            score, readiness = 84, 79
        bb = _klem(round(68 + 6 * (soevn - 7.3) + 0.6 * (hrv - 55) + rng.gauss(0, 5)), 25, 100)
        stress = round(_klem(28 + f["stress"] + rng.gauss(0, 4), 12, 60))
        skridt = round(_klem(rng.gauss(8600 if d.weekday() < 5 else 7400, 2100), 2500, 19000))
        dage.append({
            "date": d.isoformat(), "resting_hr": round(rhr), "hrv_last_night": round(hrv),
            "sleep_s": round(soevn * 3600), "deep_s": round(tid[0]), "rem_s": round(tid[2]),
            "light_s": round(tid[1]), "awake_s": round(tid[3]),
            "sleep_score": score, "stress_avg": 22 if d == tl.idag else stress,
            "bb_high": 88 if d == tl.idag else bb, "bb_low": None if d == tl.idag else max(5, bb - rng.randint(45, 62)),
            "steps": 640 if d == tl.idag else skridt, "training_readiness": readiness,
            "vo2max": round(47.2 + 2.3 * p + rng.gauss(0, 0.15), 1) if d.weekday() in (1, 5) else None,
            "weight_kg": round(75.6 - 1.9 * p + rng.gauss(0, 0.3), 1) if d.weekday() in (0, 3, 6) else None,
            "_bb_start": max(5, (88 if d == tl.idag else bb) - rng.randint(38, 58)),
        })
        pas_i_gaar = belastning_i_dag

    # HRV-status som Garmins: 7-dages snit holdt op mod niveauet
    grund = sum(x["hrv_last_night"] for x in dage) / len(dage)
    for j, x in enumerate(dage):
        uge = [y["hrv_last_night"] for y in dage[max(0, j - 6): j + 1]]
        x["hrv_status"] = "UNBALANCED" if sum(uge) / len(uge) < grund - 6 else "BALANCED"

    # Garmins rådata pr. døgn (daily.raw), som Kroppen i tal og overblik læser: døgnets tal (stats), natten (sleep)
    # og for de seneste 60 dage døgnets kurver (puls, stress, body battery og skridt)
    pr_dag = {date.fromisoformat(x["date"]): x for x in dage}
    for x in dage:
        d = date.fromisoformat(x["date"])
        raw = {"sleep": _nat_raw(tl.soevn[d], natdata[d], x, rng)}
        if d >= tl.kurver_fra:
            raw.update(_doegn_kurver(tl, d, x, pr_dag.get(d + timedelta(days=1)), natdata, rng))
        raw["stats"] = _stats(tl, d, x, rng)
        x["raw"] = json.dumps(raw)
    kol = [k for k in dage[0] if not k.startswith("_")]
    conn.executemany(f"INSERT INTO daily ({', '.join(kol)}) VALUES ({', '.join('?' * len(kol))})",
                     [[x[k] for k in kol] for x in dage])

    for k, v in {"zone_max_hr": "196", "zone_method": "HR_RESERVE",
                 "zone_floors": json.dumps({f"zone{z}": b for z, b in ZONER.items()}),
                 "last_calendar_sync": tl.idag.isoformat()}.items():
        conn.execute("INSERT INTO sync_state (key, value) VALUES (?, ?)", (k, v))
    conn.commit()


# --------------------------------------------------------------------------------------------------------------
# Garmins rådata: natten, døgnets kurver og døgnets tal, i Garmins egne feltnavne
# --------------------------------------------------------------------------------------------------------------

def _ms(t: datetime) -> int:
    """Lokal tid (dansk) som Garmins epoke i millisekunder (GMT)."""
    return int(t.replace(tzinfo=DK).timestamp() * 1000)


def _gmt(t: datetime) -> str:
    return t.replace(tzinfo=DK).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0")


def _tider(fra: datetime, til: datetime, minutter: int):
    """Lokale tidspunkter fra `fra` til `til` med fast skridt i virkelig tid, så døgnet, hvor uret stilles, hverken får
    et hul eller en dobbelt time (fold bevares, så _ms rammer den rigtige af de to kl. 2.30)."""
    t, z = fra.replace(tzinfo=DK).astimezone(timezone.utc), til.replace(tzinfo=DK).astimezone(timezone.utc)
    while t < z:
        yield t.astimezone(DK).replace(tzinfo=None)
        t += timedelta(minutes=minutter)


def _soevnfaser(seng: datetime, op: datetime, rng: random.Random) -> list[tuple]:
    """Nattens faser som Garmins sleepLevels: (fra, til, niveau), 0 dyb, 1 let, 2 REM, 3 vågen. Cyklusser på ca.
    90 minutter, med mest dyb søvn først og mest REM til sidst."""
    faser, t, cyklus = [], seng, 0

    def laeg(n: int, minutter: float):
        nonlocal t
        s = min(op, t + timedelta(minutes=minutter))
        if s > t:
            if faser and faser[-1][2] == n:
                faser[-1] = (faser[-1][0], s, n)
            else:
                faser.append((t, s, n))
            t = s

    laeg(3, rng.uniform(3, 12))  # falder i søvn
    while t < op:
        m = rng.uniform(80, 100)
        dyb, rem = max(0.04, 0.32 - 0.08 * cyklus), min(0.38, 0.14 + 0.07 * cyklus)
        let = (1 - dyb - rem) / 2
        for n, andel in ((1, let), (0, dyb), (1, let), (2, rem)):
            laeg(n, m * andel)
        if rng.random() < 0.3:
            laeg(3, rng.uniform(2, 9))
        cyklus += 1
    return faser


def _fase(faser: list, t: datetime) -> int | None:
    return next((n for a, b, n in faser if a <= t < b), None)


def _bb_nat(x: dict, seng: datetime, op: datetime, t: datetime) -> float:
    """Body battery i løbet af natten: lades op fra aftenens niveau til dagens top, hurtigst først."""
    frac = _klem((_ms(t) - _ms(seng)) / max(1, _ms(op) - _ms(seng)), 0, 1)
    return x["_bb_start"] + (x["bb_high"] - x["_bb_start"]) * (1 - math.exp(-3 * frac)) / (1 - math.exp(-3))


def _nat_raw(tider: tuple, faser: list, x: dict, rng: random.Random) -> dict:
    """Garmins sleep-objekt: dailySleepDTO med tiderne og nattens kurver (puls, HRV, SpO2, åndedræt, stress og body
    battery) i de felter, garmin-coach henter."""
    seng, op = tider
    rhr, hrv = x["resting_hr"], x["hrv_last_night"]
    timer = lambda t: (t - seng).total_seconds() / 3600  # noqa: E731
    fase = lambda t: _fase(faser, t)  # noqa: E731
    puls = [{"value": round(rhr + 3 + 7 * math.exp(-timer(t) / 1.2) + {0: -2, 2: 3, 3: 9}.get(fase(t), 0)
                            + rng.gauss(0, 1.3)), "startGMT": _ms(t)} for t in _tider(seng, op, 2)]
    hrvd = [{"value": round(max(15, hrv + {0: 7, 2: -6, 3: -10}.get(fase(t), 0) + rng.gauss(0, 7))),
             "startGMT": _ms(t)} for t in _tider(seng, op, 5)]
    spo2 = [{"epochTimestamp": _gmt(t), "spo2Reading": round(_klem(95.5 + rng.gauss(0, 1.3), 87, 100))}
            for t in _tider(seng, op, 5)]
    aand = [{"respirationValue": round(14.2 + (0.9 if fase(t) == 2 else 0) + rng.gauss(0, 0.6), 1),
             "startTimeGMT": _ms(t)} for t in _tider(seng, op, 4)]
    stress = [{"value": round(_klem(11 + (14 if fase(t) == 3 else 0) + 6 * math.exp(-timer(t)) + rng.gauss(0, 3), 1, 60)),
               "startGMT": _ms(t)} for t in _tider(seng, op, 3)]
    bb = [{"value": round(_bb_nat(x, seng, op, t)), "startGMT": _ms(t)} for t in _tider(seng, op, 3)]
    x["_spo2"] = [s["spo2Reading"] for s in spo2]
    return {
        "dailySleepDTO": {
            "sleepStartTimestampGMT": _ms(seng), "sleepEndTimestampGMT": _ms(op),
            # Garmins "lokale" tidsstempler er vægtiden skrevet som om den var GMT
            "sleepStartTimestampLocal": int(seng.replace(tzinfo=timezone.utc).timestamp() * 1000),
            "sleepEndTimestampLocal": int(op.replace(tzinfo=timezone.utc).timestamp() * 1000),
            "avgSleepStress": round(sum(s["value"] for s in stress) / len(stress), 1),
            "averageRespirationValue": round(sum(a["respirationValue"] for a in aand) / len(aand), 1),
        },
        "sleepLevels": [{"startGMT": _gmt(a), "endGMT": _gmt(b), "activityLevel": float(n)} for a, b, n in faser],
        "sleepHeartRate": puls, "hrvData": hrvd, "wellnessEpochSPO2DataDTOList": spo2,
        "wellnessEpochRespirationDataDTOList": aand, "sleepStress": stress, "sleepBodyBattery": bb,
    }


def _undervisning_paa(tl: Tidslinje, d: date) -> list[tuple]:
    if mandag(d) < tl.semester or d.weekday() not in SKEMA:
        return []
    return [(_hm(d, a), _hm(d, b)) for _, a, b, _, _ in SKEMA[d.weekday()]]


def _doegn_kurver(tl: Tidslinje, d: date, x: dict, naeste: dict | None, natdata: dict, rng: random.Random) -> dict:
    """Døgnets kurver, som garmin-coach henter dem: puls hvert 2. min, stress og body battery hvert 3. min og skridt
    pr. kvarter, fra midnat til midnat (i dag kun til kl. 7). Retter døgnets skridt, stress og body battery-bund i `x`,
    så døgnets tal og kurverne passer sammen."""
    midnat = datetime.combine(d, time())
    slut = datetime.combine(d, KL) if d == tl.idag else midnat + timedelta(days=1)
    seng, op = tl.soevn[d]
    nat_naeste = tl.soevn.get(d + timedelta(days=1)) if naeste else None
    seng2 = nat_naeste[0] if nat_naeste else midnat + timedelta(hours=23)
    pas = tl.pas.get(d, [])
    timer = _undervisning_paa(tl, d)
    rhr, niveau = x["resting_hr"], x["stress_avg"]
    bb_slut = naeste["_bb_start"] if naeste else max(5, x["bb_high"] - 55)

    def i_pas(t):
        return next((a for a in pas if a["start"] <= t < a["slut"]), None)

    def sover(t):
        return seng <= t < op or (nat_naeste is not None and nat_naeste[0] <= t < nat_naeste[1])

    def efter_pas(t):
        return any(a["slut"] <= t < a["slut"] + timedelta(minutes=25) for a in pas)

    i_timen = lambda t: any(a <= t < b for a, b in timer)  # noqa: E731
    # Gåture: til og fra undervisningen og et par tilfældige kvarterer
    gaa = set()
    if timer:
        gaa |= {timer[0][0] - timedelta(minutes=30), timer[-1][1]}
    for q in _tider(midnat, slut, 15):
        if not sover(q) and not i_pas(q) and 8 <= q.hour < 21 and rng.random() < (0.06 if d.weekday() >= 5 else 0.03):
            gaa.add(q)
    gaar = lambda t: any(q <= t < q + timedelta(minutes=15) for q in gaa)  # noqa: E731

    puls = []
    for t in _tider(midnat, slut, 2):
        a = i_pas(t)
        if sover(t):
            v = rhr + 3 + rng.gauss(0, 1.5)
        elif a:
            ind = (t - a["start"]).total_seconds() / 60
            v = min(a["snit"], 95 + 8 * ind) + rng.gauss(0, 5) + (0.5 * (a["maks"] - a["snit"]) if a["kind"] == "interval"
                                                                  and int(ind / 4) % 2 else 0)
        else:
            v = rhr + 22 + rng.gauss(0, 5) + (32 if gaar(t) else 0) + (18 if efter_pas(t) else 0)
        puls.append([_ms(t), round(_klem(v, 38, 200))])

    # Body battery: natten som i _nat_raw; vågen tømmes den fra dagens top mod aftenens niveau, hurtigst under pas
    vaagen = list(_tider(op, seng2, 3))
    vaegt = [1 + (4 if i_pas(t) else 0) + (0.6 if i_timen(t) else 0) for t in vaagen]
    i_alt, akk, bb_vaagen = sum(vaegt) or 1, 0.0, {}
    for t, w in zip(vaagen, vaegt):
        akk += w
        bb_vaagen[t] = x["bb_high"] - (x["bb_high"] - bb_slut) * akk / i_alt
    stress, bbv = [], []
    for t in _tider(midnat, slut, 3):
        if seng <= t < op:
            s, b = _klem(12 + rng.gauss(0, 3), 1, 40), _bb_nat(x, seng, op, t)
        elif nat_naeste and t >= nat_naeste[0]:
            s, b = _klem(14 + rng.gauss(0, 3), 1, 40), _bb_nat(naeste, nat_naeste[0], nat_naeste[1], t)
        elif t < seng:  # før natten til i dag: aftenen før
            s, b = _klem(niveau - 5 + rng.gauss(0, 6), 1, 99), x["_bb_start"] + (seng - t).total_seconds() / 3600 * 3
        else:
            s = -2 if i_pas(t) else _klem(niveau + (10 if i_timen(t) else 0) - (6 if t.hour >= 20 else 0)
                                         + rng.gauss(0, 9), 1, 99)
            b = bb_vaagen.get(t, bb_slut)
        stress.append([_ms(t), round(s)])
        bbv.append([_ms(t), "MEASURED", round(_klem(b, 5, 100)), 1.0])

    skridt, i_alt = [], 0
    for q in _tider(midnat, slut, 15):
        a = i_pas(q + timedelta(minutes=7))
        if sover(q + timedelta(minutes=7)):
            n, lvl = 0, "sleeping"
        elif a and a["sport"] == "running":
            n, lvl = round(rng.uniform(2300, 2600)), "highlyActive"
        elif a:
            n, lvl = round(rng.uniform(0, 250) if a["kind"] != "svoem" else 0), "generic"
        elif q in gaa:
            n, lvl = round(rng.uniform(1100, 1600)), "active"
        else:
            n, lvl = round(max(0, rng.gauss(45, 45))), "sedentary"
        i_alt += n
        skridt.append({"startGMT": _gmt(q), "endGMT": _gmt(q + timedelta(minutes=15)), "steps": n,
                       "primaryActivityLevel": lvl})

    x["steps"] = i_alt
    vaagne = [s for _, s in stress if s > 0 and not sover(datetime.fromtimestamp(_ / 1000, DK).replace(tzinfo=None))]
    if vaagne and d != tl.idag:
        x["stress_avg"] = round(sum(vaagne) / len(vaagne))
    if d != tl.idag:
        x["bb_low"] = min(b[2] for b in bbv)
    x["_puls"] = [v for _, v in puls]
    return {"heart_rates": {"heartRateValues": puls}, "all_day_stress": {"stressValuesArray": stress,
                                                                         "bodyBatteryValuesArray": bbv},
            "steps_day": skridt}


def _stats(tl: Tidslinje, d: date, x: dict, rng: random.Random) -> dict:
    """Garmins døgntal (stats) i Garmins feltnavne. I dag er kun til kl. 7."""
    pas = tl.pas.get(d, [])
    seng, op = tl.soevn[d]
    midnat = datetime.combine(d, time())
    dag_s = 7 * 3600 if d == tl.idag else 86400
    sov = max(0.0, (op - max(seng, midnat)).total_seconds())
    akt_s = sum((a["slut"] - a["start"]).total_seconds() for a in pas)
    vaagen = max(0.0, dag_s - sov - akt_s)
    hoej = _klem(0.03 + (x["stress_avg"] - 25) * 0.006, 0.01, 0.2)
    puls = x.pop("_puls", None)
    spo2 = x.pop("_spo2", None) or [95]
    loeb_min = sum((a["slut"] - a["start"]).total_seconds() / 60 for a in pas if a["sport"] == "running")
    andet_min = sum((a["slut"] - a["start"]).total_seconds() / 60 for a in pas if a["sport"] != "running")
    lav = x["bb_low"] if x["bb_low"] is not None else x["_bb_start"]
    return {
        "includesWellnessData": True, "totalSteps": x["steps"], "dailyStepGoal": 8000,
        "totalDistanceMeters": round(x["steps"] * 0.76), "bmrKilocalories": round(1790 * dag_s / 86400),
        "activeKilocalories": round(x["steps"] * 0.04 + sum(a["kcal"] for a in pas)),
        "floorsAscended": round(max(0.0, rng.gauss(9, 4)) * dag_s / 86400, 1),
        "minHeartRate": min(puls) if puls else x["resting_hr"] - 3,
        "maxHeartRate": max(puls) if puls else round(max([a["maks"] for a in pas] + [118 + rng.uniform(0, 20)])),
        "averageStressLevel": x["stress_avg"],
        "restStressDuration": round(vaagen * (0.45 - hoej / 2) + sov * 0.9), "lowStressDuration": round(vaagen * 0.3),
        "mediumStressDuration": round(vaagen * (0.25 - hoej / 2)), "highStressDuration": round(vaagen * hoej),
        "activityStressDuration": round(akt_s), "uncategorizedStressDuration": round(rng.uniform(300, 1500) * dag_s / 86400),
        "sleepingSeconds": round(sov), "sedentarySeconds": round(vaagen * 0.82), "activeSeconds": round(vaagen * 0.15 + akt_s * 0.4),
        "highlyActiveSeconds": round(vaagen * 0.03 + akt_s * 0.6),
        "moderateIntensityMinutes": round(andet_min * 0.5 + (rng.uniform(10, 35) if d != tl.idag else 0)),
        "vigorousIntensityMinutes": round(loeb_min * 0.7),
        "bodyBatteryHighestValue": x["bb_high"], "bodyBatteryLowestValue": lav,
        "bodyBatteryChargedValue": x["bb_high"] - x["_bb_start"], "bodyBatteryDrainedValue": x["bb_high"] - lav,
        "averageSpo2": round(sum(spo2) / len(spo2)), "lowestSpo2": min(spo2),
        "avgWakingRespirationValue": round(15.4 + rng.gauss(0, 0.5), 1),
    }


STED = {"rolig": "Byparken", "lang": "Søstien", "interval": "Atletikbanen", "boulder": "Klatrehallen",
        "svoem": "Svømmehallen", "A": "Fitnesscentret", "B": "Fitnesscentret"}


def _gem_pas(conn, d: date, kind: str, kl_: str, n: int, p: float, rng: random.Random) -> dict:
    """Ét pas i activities (og Hevy for styrke) med Garmins nøgletal i raw. Returnerer passet med tider, puls og en
    grov belastning til restitutionen."""
    start = _hm(d, kl_) + timedelta(minutes=rng.choice((-10, -5, 0, 5, 10, 15)))
    aid = f"demo-{d.isoformat()}-{n}"
    raw: dict = {"startTimeGMT": start.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "locationName": STED[kind]}
    meter = None
    if kind in ("A", "B"):
        minutter = rng.uniform(58, 72)
        snit, maks, sport, navn, last = rng.uniform(104, 114), rng.uniform(140, 156), "strength_training", \
            f"Styrke {kind}", None
        saet = _gem_hevy(conn, aid, kind, start, minutter, p, rng)
        raw.update({"activeSets": saet[0], "totalReps": saet[1], "trainingEffectLabel": "ANAEROBIC_CAPACITY"})
    else:
        minutter = {"rolig": rng.uniform(36, 52), "lang": rng.uniform(62, 80), "interval": rng.uniform(40, 52),
                    "boulder": rng.uniform(75, 100), "svoem": rng.uniform(35, 46)}[kind]
        snit = {"rolig": rng.uniform(137, 144), "lang": rng.uniform(139, 145), "interval": rng.uniform(153, 160),
                "boulder": rng.uniform(116, 126), "svoem": rng.uniform(126, 136)}[kind]
        maks = {"rolig": rng.uniform(154, 164), "lang": rng.uniform(158, 168), "interval": rng.uniform(177, 186),
                "boulder": rng.uniform(150, 162), "svoem": rng.uniform(150, 166)}[kind]
        sport = {"boulder": "bouldering", "svoem": "lap_swimming"}.get(kind, "running")
        navn = {"rolig": "Rolig løbetur", "lang": "Langtur", "interval": "Intervaller 5 × 4 min",
                "boulder": "Bouldering", "svoem": "Svømning i bassin"}[kind]
        last = {"rolig": rng.uniform(52, 72), "lang": rng.uniform(85, 115), "interval": rng.uniform(105, 150),
                "boulder": rng.uniform(38, 60), "svoem": rng.uniform(40, 62)}[kind]
        zt = _zonetid(kind, minutter * 60, rng)
        raw.update({f"hrTimeInZone_{z}": s for z, s in enumerate(zt, 1)})
        conn.executemany("INSERT INTO activity_zones (activity_id, zone, seconds, low_bpm) VALUES (?, ?, ?, ?)",
                         [(aid, z, s, ZONER[z]) for z, s in enumerate(zt, 1)])
        raw["trainingEffectLabel"] = {"rolig": "AEROBIC_BASE", "lang": "AEROBIC_BASE", "interval": "VO2MAX",
                                      "boulder": "ANAEROBIC_CAPACITY", "svoem": "AEROBIC_BASE"}[kind]
    km = {"rolig": 5.9 + 0.6 * p, "lang": 6.1 + 0.6 * p, "interval": 7.2 + 0.5 * p}.get(kind)
    if km is not None:
        meter = round(km * minutter / 45 * 1000)
        bevaeg = minutter * 60 * (0.93 if kind == "interval" else 0.98)
        tempo = bevaeg / (meter / 1000)  # sekunder pr. km
        kadence = rng.uniform(162, 168) + (6 if kind == "interval" else 0)
        raw.update({"averageSpeed": round(meter / bevaeg, 3), "movingDuration": round(bevaeg),
                    "averageRunningCadenceInStepsPerMinute": round(kadence, 1),
                    "avgStrideLength": round(100000 / tempo / kadence * 60, 1), "steps": round(kadence * bevaeg / 60),
                    "fastestSplit_1000": round(tempo * (0.86 if kind == "interval" else 0.95) + rng.gauss(0, 4), 1),
                    "vO2MaxValue": round(47.2 + 2.3 * p)})
        if meter >= 5000:
            raw["fastestSplit_5000"] = round(5 * tempo * 0.98 + rng.gauss(0, 10), 1)
    elif kind == "svoem":
        meter = round((1500 + 400 * p + rng.uniform(-150, 150)) / 50) * 50
        bevaeg = minutter * 60 * 0.82
        baner = meter // 25
        raw.update({"averageSpeed": round(meter / bevaeg, 3), "movingDuration": round(bevaeg), "poolLength": 2500,
                    "activeLengths": baner, "averageSwolf": round(44 - 4 * p + rng.gauss(0, 1.2)),
                    "averageSwimCadenceInStrokesPerMinute": round(rng.uniform(25, 29)),
                    "strokes": round(baner * rng.uniform(16, 19))})
    aerob = round(rng.uniform(2.2, 3.8), 1)
    anaerob = round(rng.uniform(0.2, 2.8 if kind == "interval" else 1.2), 1)
    kcal = round(minutter * snit * 0.075)
    raw.update({"duration": round(minutter * 60), "aerobicTrainingEffect": aerob, "anaerobicTrainingEffect": anaerob,
                "differenceBodyBattery": -round(minutter / 4 + (snit - 100) / 6),
                "moderateIntensityMinutes": round(minutter * (0.5 if snit < 140 else 0.25)),
                "vigorousIntensityMinutes": round(minutter * (0.1 if snit < 140 else 0.6)),
                "waterEstimated": round(minutter * 9)})
    if last is not None:
        raw["activityTrainingLoad"] = round(last)
    if kind not in ("svoem", "A", "B", "boulder"):
        raw["elevationGain"] = round(rng.uniform(15, 60))
    conn.execute(
        "INSERT INTO activities (activity_id, start_local, date, sport, name, duration_s, distance_m, avg_hr, "
        "max_hr, elev_gain_m, calories, garmin_load, aerobic_te, anaerobic_te, raw) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (aid, start.strftime("%Y-%m-%d %H:%M:%S"), d.isoformat(), sport, navn, round(minutter * 60),
         meter, round(snit), round(maks), raw.get("elevationGain"), kcal,
         None if last is None else round(last), aerob, anaerob, json.dumps(raw)))
    return {"kind": kind, "sport": sport, "start": start, "slut": start + timedelta(minutes=minutter),
            "snit": snit, "maks": maks, "kcal": kcal,
            "belastning": {"A": 40, "B": 40, "rolig": 60, "lang": 85, "interval": 95, "boulder": 70, "svoem": 55}[kind]}


def _gem_hevy(conn, aid: str, program: str, start: datetime, minutter: float, p: float,
              rng: random.Random) -> tuple[int, int]:
    """Gemmer passet i Hevy og svarer (arbejdssæt, gentagelser) til Garmins nøgletal."""
    wid = "hevy-" + aid
    conn.execute(
        "INSERT INTO hevy_workouts (workout_id, activity_id, title, start_utc, end_utc, updated_at, raw) "
        "VALUES (?, ?, ?, ?, ?, ?, '{}')",
        (wid, aid, f"Styrke {program}", start.astimezone(timezone.utc).isoformat(),
         (start + timedelta(minutes=minutter)).astimezone(timezone.utc).isoformat(),
         start.astimezone(timezone.utc).isoformat()))
    saet = []
    for ei, (oevelse, antal, reps, fra, til, trin) in enumerate(STYRKE[program]):
        kg = fra + round((til - fra) * p / trin + rng.uniform(-0.6, 0.4)) * trin
        kg = _klem(kg, fra, til)
        saet.append((wid, ei, 0, oevelse, "warmup", round(kg * 0.6 / trin) * trin, reps, None))
        for si in range(1, antal + 1):
            r = reps + rng.choice((0, 0, 0, 1, -1)) if si == antal else reps
            rpe = (rng.choice((9, 9, 9.5, 8.5)) if si == antal else rng.choice((7.5, 8, 8, 8.5)))
            saet.append((wid, ei, si, oevelse, "normal", kg, r, None if rng.random() < 0.12 else rpe))
    conn.executemany(
        "INSERT INTO hevy_sets (workout_id, exercise_index, set_index, exercise, set_type, weight_kg, reps, rpe) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", saet)
    arbejde = [s for s in saet if s[4] == "normal"]
    return len(arbejde), sum(s[6] for s in arbejde)


def _sure_udtraek(sti: Path, tl: Tidslinje, rng: random.Random) -> None:
    """Et lille Sure-udtræk med de felter overblik læser (date, amount, group, category)."""
    tx = []

    def koeb(d: date, beloeb: float, kategori: str, gruppe: str = "Variable udgifter"):
        tx.append({"date": d.isoformat(), "amount": round(beloeb, 2), "group": gruppe, "category": kategori})

    d = tl.start
    while d < tl.idag:
        f = tl.ugefaktor(d)  # samme ugefaktor som Garmin-dataene
        wd = d.weekday()
        if wd in (0, 3, 5):
            koeb(d, rng.uniform(160, 290), "Dagligvarer")
        if rng.random() < 0.24 * f["takeaway"]:
            koeb(d, rng.uniform(85, 165), "Take-away og mad ude")
        if wd in (4, 5) and rng.random() < 0.45:
            koeb(d, rng.uniform(60, 240), "Café, bar og byture")
        if wd == 2:
            koeb(d, rng.uniform(40, 160), "Transport")
        if rng.random() < 0.05:
            koeb(d, rng.uniform(250, 650), "Tøj og sko")
        if rng.random() < 0.04:
            koeb(d, rng.uniform(80, 300), "Deling med venner")
        if d.day == 1:
            koeb(d, 4200, "Husleje", "Faste udgifter")
        d += timedelta(days=1)
    sti.write_text(json.dumps({"generated_at": f"{tl.idag}T06:55:00Z", "last_sync": f"{tl.idag}T06:55:00Z",
                               "transactions": tx}, ensure_ascii=False))


# Skærmtids grupper og kategorier, som i skaermtid/regler.example.json
GRUPPE = {"Studie": "Produktiv", "Sprog": "Produktiv", "Egne projekter": "Produktiv", "Form & fokus": "Produktiv",
          "Økonomi": "Produktiv", "Sociale medier": "Passiv", "Video & streaming": "Passiv", "Nyheder": "Passiv",
          "Spil": "Gaming", "Kommunikation": "Praktisk", "Hverdag": "Praktisk", "Indkøb": "Praktisk"}
FORLOEB_DAGE = 28


def _vaelg(rng: random.Random, valg: list[tuple]) -> str | None:
    """Første kategori, hvis tærskel slaget er under; None er et kvarter uden skærm."""
    x = rng.random()
    return next((k for graense, k in valg if x < graense), None)


def _skaermtid_udtraek(sti: Path, tl: Tidslinje, rng: random.Random) -> None:
    """Et Skærmtid-udtræk (skaermtid.json) med de felter overblik læser: pr. døgn (kl. 6 til kl. 6) den sene skærmtid
    efter kl. 23 og, de seneste 28 døgn, dagens forløb som Skærmtids største kategori pr. kvarter. Kvartererne følger
    den opdigtede kalender, søvnen og passene, så planlagt mod faktisk har noget at vise."""
    undervisning = [(s, e) for uid, s, e, _, heldag in tl.kalender if uid.startswith("skema-")]
    studie = [(s, e) for uid, s, e, _, heldag in tl.kalender if uid.startswith(("plan-", "caltask-"))]
    aftaler = [(s, e) for uid, s, e, _, heldag in tl.kalender
               if not heldag and not uid.startswith(("skema-", "plan-", "caltask-"))]
    i = lambda t, xs: any(a <= t < b for a, b in xs)  # noqa: E731
    soevn = list(tl.soevn.values())
    pas = [(a["start"], a["slut"]) for xs in tl.pas.values() for a in xs]
    nu = datetime.combine(tl.idag, time(9, 30))  # Skærmtid opdateres hver halve time; i dag er med til formiddagen
    dage, d = [], tl.skaerm_fra
    while d <= tl.idag:
        sen = tl.sen(d) or 0.0
        forloeb, sen_kvarterer = [], round(sen * 4)
        start = datetime.combine(d, time(6))
        for q in _tider(start, min(start + timedelta(days=1), nu), 15):
            m = q + timedelta(minutes=7)
            if i(m, soevn) or i(m, pas):
                continue
            if q.hour >= 23 or q.hour < 6:  # sent: telefonen i sengen, så længe den sene skærmtid rækker
                kat = None
                if sen_kvarterer > 0:
                    sen_kvarterer -= 1
                    kat = _vaelg(rng, [(0.5, "Video & streaming"), (0.9, "Sociale medier"), (1, "Kommunikation")])
            elif i(m, aftaler):  # ude blandt andre: telefonen er mest i lommen
                kat = _vaelg(rng, [(0.12, "Sociale medier"), (0.2, "Kommunikation")])
            elif i(m, undervisning):
                kat = _vaelg(rng, [(0.35, "Studie"), (0.45, "Kommunikation"), (0.5, "Sociale medier")])
            elif i(m, studie):
                kat = _vaelg(rng, [(0.62, "Studie"), (0.76, "Sociale medier"), (0.82, "Kommunikation")])
            elif q.hour < 9:
                kat = _vaelg(rng, [(0.25, "Nyheder"), (0.4, "Sociale medier"), (0.5, "Kommunikation")])
            elif q.hour >= 18:
                spil = 0.12 if d.weekday() >= 5 else 0.04
                kat = _vaelg(rng, [(0.28, "Video & streaming"), (0.42, "Sociale medier"), (0.5, "Kommunikation"),
                                   (0.5 + spil, "Spil"), (0.56 + spil, "Sprog"), (0.62 + spil, "Egne projekter"),
                                   (0.64 + spil, "Økonomi")])
            else:
                kat = _vaelg(rng, [(0.1, "Sociale medier"), (0.18, "Kommunikation"), (0.23, "Hverdag"),
                                   (0.26, "Indkøb"), (0.3, "Form & fokus")])
            if kat is None:
                continue
            slut = q + timedelta(minutes=15)
            if forloeb and forloeb[-1]["kategori"] == kat and forloeb[-1]["_slut"] == q:
                forloeb[-1]["_slut"] = slut
            else:
                forloeb.append({"kategori": kat, "gruppe": GRUPPE[kat], "_start": q, "_slut": slut})
        timer = sum((b["_slut"] - b["_start"]).total_seconds() for b in forloeb) / 3600
        # Tider med zone, som Skærmtid skriver dem (overblik læser dem som lokal tid)
        forloeb = [{"start": b["_start"].astimezone().isoformat(timespec="minutes"),
                    "slut": b["_slut"].astimezone().isoformat(timespec="minutes"),
                    "kategori": b["kategori"], "gruppe": b["gruppe"]} for b in forloeb]
        dage.append({"dato": d.isoformat(), "timer": round(timer, 2), "sen_timer": sen,
                     "enheder": {"Mac": {"timer": round(timer * 0.55, 2)}, "Telefon": {"timer": round(timer * 0.45, 2)}},
                     "forloeb": forloeb if d > tl.idag - timedelta(days=FORLOEB_DAGE) else None})
        d += timedelta(days=1)
    sti.write_text(json.dumps({"dage": dage}, ensure_ascii=False))


def _studie_udtraek(sti: Path, tl: Tidslinje, rng: random.Random) -> None:
    """Et Studie-udtræk (studie.json) med det, overblik læser: svar pr. dag i Træning og På farten pr. fag."""
    fag = []
    for _ in FAG:
        dage = {}
        for n in range(1, 29):
            d = tl.idag - timedelta(days=n)
            if rng.random() < (0.6 if d.weekday() < 5 else 0.35):
                dage[d.isoformat()] = rng.randint(4, 24)
        fag.append({"status": {"rytme": {"dage": dage}}})
    sti.write_text(json.dumps({"fag": fag}))


# --------------------------------------------------------------------------------------------------------------
# Periodernes vurderinger (det, Træning-rutinen ellers skriver)
# --------------------------------------------------------------------------------------------------------------

def _hent(o, sti: str):
    for k in sti.split("."):
        o = None if o is None else o.get(k)
    return o


def _lavpct(p: dict):
    z = p["traening"].get("intensitet_min")
    t = sum(z.values()) if z else 0
    return round(100 * z["lav"] / t) if t else None


SAMMENLIGN = [  # (sti, navn, enhed, decimaler, op er godt, mindste ændring der nævnes)
    ("sundhed.sovn_t", "Søvnen", " t pr. nat", 1, True, 0.12),
    ("sundhed.hrv", "HRV om natten", " ms", 0, True, 1.5),
    ("sundhed.hvilepuls", "Hvilepulsen", " bpm", 1, False, 0.6),
    ("sundhed.readiness", "Readiness", "", 0, True, 3),
    ("sundhed.stress", "Stress", "", 0, False, 2),
    ("sundhed.skridt", "Skridt pr. dag", "", 0, True, 500),
    ("traening.timer", "Træningstiden", " t", 1, True, 0.6),
    ("styrke.haarde_saet", "Arbejdssæt", "", 0, True, 4),
]
# Træningsmålet, som rutinen Træning måler perioden mod (se coach/RUTINE.md, 2b): gulvet er to styrkepas om ugen,
# konditionen ét løb eller én cykeltur, og svømning om morgenen er bonus.
GULV = 2


def _dm(d: date) -> str:
    return f"{d.day}/{d.month}"


def _maal(conn: sqlite3.Connection, start: date, slut: date) -> list[dict]:
    """Målet pr. uge (lørdag til fredag): styrkepas, løb/cykling og morgensvømning før kl. 10."""
    uger = []
    for a in (start, start + timedelta(days=7)):
        b = min(slut, a + timedelta(days=6))
        r = conn.execute(
            "SELECT sum(sport = 'strength_training') s, sum(sport IN ('running', 'road_biking')) k, "
            "sum(sport = 'lap_swimming' AND time(start_local) < '10:00') m FROM activities WHERE date BETWEEN ? AND ?",
            (a.isoformat(), b.isoformat())).fetchone()
        uger.append({"styrke": r[0] or 0, "kondition": r[1] or 0, "svoem": r[2] or 0})
    return uger


def _fokus(p: dict, maal: list[dict], slut: date, fase: str) -> list[tuple]:
    """Fokus er handlinger med dag og tid i de næste 14 dage (F er lørdagen efter perioden), ikke tærskler."""
    F = slut + timedelta(days=1)
    efter = " lige efter undervisningen" if fase != "foer" else ""
    lav = _lavpct(p)
    ud = [("styrke", f"Styrke mandag {_dm(F + timedelta(days=2))} og torsdag {_dm(F + timedelta(days=5))}{efter}, "
                     f"ca. kl. 17, og igen {_dm(F + timedelta(days=9))} og {_dm(F + timedelta(days=12))}")]
    if lav is not None and lav < 80:
        ud.append(("let", f"Rolig løbetur tirsdag {_dm(F + timedelta(days=3))} kl. 17 med pulsen under {ZONER[3]} bpm "
                          "hele vejen, også op ad bakke"))
    if min(u["kondition"] for u in maal) < 1 or len(ud) < 2:
        ud.append(("kondition", f"Intervaller lørdag {_dm(F + timedelta(days=7))} kl. 10, hvis readiness er over 60; "
                                "ellers en rolig tur samme tid"))
    return ud[:3]


HANDLING = {
    "styrke": "Læg styrkepassene som faste aftaler i kalenderen, så de ikke skal findes plads til hver uge.",
    "let": f"Løb de rolige ture under {ZONER[3]} bpm (grænsen til zone 3), også op ad bakke.",
    "kondition": "Pak løbetøjet fredag aften, så lørdagens tur ikke afhænger af morgenformen.",
    "rpe": "Udfyld RPE i Hevy lige efter sættet i stedet for bagefter.",
}


def _opfoelgning(art: str, tekst: str, p: dict, maal: list[dict]) -> dict:
    st = p["styrke"]
    if art == "styrke":
        n = [u["styrke"] for u in maal]
        status = "naaet" if min(n) >= GULV else "delvist" if sum(n) >= GULV else "ikke"
        note = f"{n[0]} og {n[1]} styrkepas i de to uger."
        if st["rpe_daekning_pct"] is not None:
            note = note[:-1] + f", {st['rpe_daekning_pct']} % af sættene med RPE."
    elif art == "let":
        v = _lavpct(p) or 0
        status, note = ("naaet" if v >= 75 else "delvist" if v >= 70 else "ikke"), f"{v} % af konditionstiden i zone 1–2."
    else:
        n = sum(u["kondition"] for u in maal)
        status, note = ("naaet" if n >= 2 else "delvist" if n == 1 else "ikke"), f"{n} løbeture i perioden."
    return {"fokus": tekst, "status": status, "note": note}


AABNING = {
    "foer": ["En stabil periode uden undervisning, hvor træningen fik god plads.",
             "Endnu en rolig periode med lange nætter og en jævn træningsrytme.",
             "Ferierytmen holdt: mere bevægelse i hverdagen og ingen tidlige morgener.",
             "Sidste hele periode før studiestart, med fokus på at holde fast i rytmen."],
    "start": ["Studiestarten fyldte: nye skemaer, tidlige morgener og lidt kortere nætter."],
    "under": ["Undervisningen kører nu i fast rytme, og træningen har fundet sin plads omkring den.",
              "Anden periode med undervisning. Selvstudiet logges nu i CalTask, så studietiden kan ses ved siden "
              "af træning og søvn."],
}


def _vurdering(p: dict, forrige: dict | None, fase: str, nr: int, forrige_fokus: list, maal: list[dict],
               slut: date) -> tuple[dict, list]:
    s, t, st = p["sundhed"], p["traening"], p["styrke"]
    godt, skidt = [], []
    if forrige:
        for sti, navn, enhed, dec, op, mindst in SAMMENLIGN:
            a, b = _hent(forrige, sti), _hent(p, sti)
            if a is None or b is None or abs(b - a) < mindst:
                continue
            tekst = f"{navn} {'steg' if b > a else 'faldt'} fra {tal(a, dec)} til {tal(b, dec)}{enhed}."
            ((godt if (b > a) == op else skidt)).append((abs(b - a) / mindst, tekst))
        for noegle in ("squat_barbell", "bench_press_barbell", "romanian_deadlift_barbell"):
            a, b = (forrige["styrke"]["e1rm"] or {}).get(noegle), (st["e1rm"] or {}).get(noegle)
            if a and b and b - a >= 1.5:
                l = st["loeft"][noegle]
                godt.append((2.5, f"{l['navn']}: e1RM op fra {tal(a, 1)} til {tal(b, 1)} kg "
                                  f"(bedste sæt {l['bedste_saet']})."))
    for n, u in enumerate(maal, 1):
        if u["styrke"] < GULV:
            skidt.append((4, f"Gulvet blev ikke nået i uge {n} af perioden: {u['styrke']} af {GULV} styrkepas."))
    if all(u["styrke"] >= GULV for u in maal):
        godt.append((1.6, f"Gulvet holdt i begge uger: {st['pas']} styrkepas med {st['haarde_saet']} arbejdssæt i alt."))
    if sum(u["svoem"] for u in maal):
        n = sum(u["svoem"] for u in maal)
        godt.append((1.0, f"Bonus: {n} morgensvømning{'er' if n > 1 else ''} før kl. 10."))
    lav = _lavpct(p)
    if lav is not None:
        (godt if lav >= 75 else skidt).append(
            (1.2, f"{lav} % af konditionstiden lå i zone 1–2" + (", som det skal." if lav >= 75 else
                                                                  ", så de rolige ture er blevet for hårde.")))
    if st["rpe_daekning_pct"] is not None:
        (godt if st["rpe_daekning_pct"] >= 85 else skidt).append(
            (1.0, f"RPE er udfyldt på {st['rpe_daekning_pct']} % af arbejdssættene."))
    godt = [x for _, x in sorted(godt, key=lambda g: -g[0])[:4]]
    skidt = [x for _, x in sorted(skidt, key=lambda g: -g[0])[:3]]

    fokus = _fokus(p, maal, slut, fase)
    opf = [_opfoelgning(art, tekst, p, maal) for art, tekst in forrige_fokus]
    naaet = sum(1 for o in opf if o["status"] == "naaet")
    resume = (f"Målet: styrke {maal[0]['styrke']} og {maal[1]['styrke']} pas, løb/cykling {maal[0]['kondition']} og "
              f"{maal[1]['kondition']}, morgensvømning {maal[0]['svoem']} og {maal[1]['svoem']}. "
              f"{AABNING[fase][nr % len(AABNING[fase])]} Søvnen lå på {tal(s['sovn_t'], 1)} t pr. nat og HRV på "
              f"{tal(s['hrv'])} ms, og du nåede {t['pas']} pas på {tal(t['timer'], 1)} t.")
    if opf:
        resume += f" {naaet} af {len(opf)} fokus fra perioden før blev nået."
    forbedring = [HANDLING[art] for art, _ in fokus]
    if st["rpe_daekning_pct"] is not None and st["rpe_daekning_pct"] < 85:
        forbedring.append(HANDLING["rpe"])
    vurdering = {
        "resume": resume, "gaar_godt": godt, "gaar_daarligt": skidt, "forbedring": forbedring[:4],
        "fokus": [x for _, x in fokus], "opfoelgning": opf,
    }
    return vurdering, fokus


def _perioder(m, conn: sqlite3.Connection, tl: Tidslinje) -> None:
    sidste_slut = tl.idag - timedelta(days=(tl.idag.weekday() - 4) % 7 or 7)  # seneste fredag før i dag
    forrige, forrige_fokus, taellere = None, [], {"foer": 0, "start": 0, "under": 0}
    for k in range(6, -1, -1):
        slut = sidste_slut - timedelta(days=14 * k)
        start = slut - timedelta(days=13)
        fase = "foer" if slut < tl.semester else "start" if start <= tl.semester else "under"
        p = m.metrics.periode_rapport(conn, start.isoformat(), slut.isoformat())
        maal = _maal(conn, start, slut)
        vurdering, fokus = _vurdering(p, forrige, fase, taellere[fase], forrige_fokus, maal, slut)
        taellere[fase] += 1
        m.site.ny_periode(conn, start.isoformat(), slut.isoformat(), vurdering)
        forrige, forrige_fokus = p, fokus


# --------------------------------------------------------------------------------------------------------------
# Ugereviews (det, rutinen "overblik-ugereview" ellers skriver)
# --------------------------------------------------------------------------------------------------------------

NAVN = {  # kolonne -> (navn, enhed, decimaler), i den rækkefølge reviewet nævner dem
    "soevn_timer_snit": ("søvn pr. nat", " t", 1), "selvstudie_timer": ("selvstudie", " t", 1),
    "takeaway_kr": ("take-away", " kr.", 0), "traening_timer": ("træning", " t", 1),
    "stress_snit": ("stress", "", 0), "hrv_snit": ("HRV", " ms", 0), "hvilepuls_snit": ("hvilepuls", " bpm", 1),
    "soevnscore_snit": ("søvnscore", "", 0), "skridt_snit": ("skridt pr. dag", "", 0),
    "variabelt_kr": ("variable køb", " kr.", 0), "cafe_bar_kr": ("café og bar", " kr.", 0),
    "dagligvarer_kr": ("dagligvarer", " kr.", 0), "traening_pas": ("træningspas", "", 0),
    "belastning": ("belastning", "", 0), "takeaway_koeb": ("take-away-køb", "", 0),
    "undervisning_timer": ("undervisning", " t", 1), "selvstudie_dage": ("dage med selvstudie", "", 0),
    "garmin_dage": ("dage med Garmin-data", "", 0),
}
FRASE = {
    ("soevn_timer_snit", "under"): "kortere nætter", ("soevn_timer_snit", "over"): "længere nætter",
    ("takeaway_kr", "over"): "mere take-away", ("takeaway_kr", "under"): "mindre take-away",
    ("takeaway_koeb", "over"): "flere take-away-køb", ("selvstudie_timer", "over"): "mere selvstudie",
    ("selvstudie_dage", "over"): "flere dage med selvstudie", ("traening_timer", "under"): "mindre træning",
    ("traening_timer", "over"): "mere træning", ("traening_pas", "under"): "færre træningspas",
    ("stress_snit", "over"): "højere stress", ("stress_snit", "under"): "lavere stress",
    ("hrv_snit", "under"): "lavere HRV", ("hrv_snit", "over"): "højere HRV",
    ("variabelt_kr", "over"): "flere variable køb", ("variabelt_kr", "under"): "færre variable køb",
    ("soevnscore_snit", "under"): "lavere søvnscore", ("soevnscore_snit", "over"): "højere søvnscore",
    ("hvilepuls_snit", "under"): "lavere hvilepuls", ("hvilepuls_snit", "over"): "højere hvilepuls",
    ("skridt_snit", "under"): "færre skridt", ("skridt_snit", "over"): "flere skridt",
    ("selvstudie_timer", "under"): "mindre selvstudie", ("traening_pas", "over"): "flere træningspas",
    ("cafe_bar_kr", "over"): "mere café og bar", ("cafe_bar_kr", "under"): "mindre café og bar",
    ("dagligvarer_kr", "over"): "mere brugt på dagligvarer", ("dagligvarer_kr", "under"): "mindre brugt på dagligvarer",
    ("belastning", "over"): "højere belastning", ("belastning", "under"): "lavere belastning",
    ("undervisning_timer", "over"): "mere undervisning", ("undervisning_timer", "under"): "mindre undervisning",
}
# Kolonner, der siger det samme som en anden; nævnes kun, hvis den anden ikke skiller sig ud
DUBLET = {"selvstudie_dage": "selvstudie_timer", "takeaway_koeb": "takeaway_kr", "traening_pas": "traening_timer",
          "soevnscore_snit": "soevn_timer_snit"}
EN_TING = {
    "soevn_timer_snit": "Gå i seng senest 23.30 de aftener, hvor undervisningen starter kl. 8.15 næste morgen.",
    "soevnscore_snit": "Gå i seng senest 23.30 de aftener, hvor undervisningen starter kl. 8.15 næste morgen.",
    "takeaway_kr": "Lav madpakke søndag aften til mandag og tirsdag, så de lange dage på campus ikke ender med "
                   "take-away.",
    "takeaway_koeb": "Lav madpakke søndag aften til mandag og tirsdag, så de lange dage på campus ikke ender med "
                     "take-away.",
    "stress_snit": "Hold én hverdagsaften helt fri for skole og skærm, og læg den i kalenderen nu.",
    "traening_timer": "Hold fast i de to styrkepas, også i travle uger; de tager kun en time.",
    "traening_pas": "Hold fast i de to styrkepas, også i travle uger; de tager kun en time.",
    "hrv_snit": "Læg intervallerne efter en nat med mindst 7 timers søvn, ikke efter en kort.",
}


def _vaerdi(k: str, v) -> str:
    _, enhed, dec = NAVN.get(k, (k, "", 1))
    return f"{tal(v, dec)}{enhed}"


def _review_tekst(snap: dict, uger_med_selvstudie: int) -> dict:
    r = snap["rapport"]
    af = r["afvigelser"]
    # Vurderede afvigelser (godt/skidt) før de blot usædvanlige, og i fast rækkefølge efter emne. Ikke efter z:
    # robust_z er None, når de fleste baseline-uger var ens
    tydelige = sorted(((k, a) for k, a in af.items() if a["tydelig"] and k in NAVN),
                      key=lambda x: (x[1]["vurdering"] is None, list(NAVN).index(x[0])))
    tydelige = [(k, a) for k, a in tydelige if not (k in DUBLET and DUBLET[k] in dict(tydelige))]
    dele = [FRASE.get((k, a["retning"]), f"{'mere' if a['retning'] == 'over' else 'mindre'} {NAVN[k][0]}")
            for k, a in tydelige]
    dele = list(dict.fromkeys(dele))[:4]
    if not dele:
        saetning = "En helt almindelig uge: alle tal lå inden for det normale."
    elif len(dele) == 1:
        saetning = f"Ugen skilte sig kun ud på ét punkt: {dele[0]}. Resten lå inden for det normale."
    else:
        saetning = f"Ugen skilte sig ud med {', '.join(dele[:-1])} og {dele[-1]}; resten lå inden for det normale."

    udskilte = []
    for k, a in tydelige[:6]:
        vurd = {"godt": " – bedre end normalt", "skidt": " – dårligere end normalt"}.get(a["vurdering"], "")
        linje = f"{NAVN[k][0][0].upper()}{NAVN[k][0][1:]}: {_vaerdi(k, a['vaerdi'])} mod normalt {_vaerdi(k, a['normal'])}{vurd}"
        udskilte.append(linje if linje.endswith(".") else linje + ".")
    if not udskilte:
        udskilte = ["Ingen tal skilte sig tydeligt ud."]

    samm = []
    for h in r["sammenhaenge"]:
        if h.get("status") in ("stærk", "antydning"):
            samm.append(f"{h['spoergsmaal']} Der er en {'stærk sammenhæng' if h['status'] == 'stærk' else 'antydning'}"
                        f" (rho {tal(h['rho'], 2)} over {h['n_uger']} uger). Korrelation er ikke årsag, men mønsteret "
                        "er værd at holde øje med.")
    venter = [h for h in r["sammenhaenge"] if h["x"] == "selvstudie_timer" and h.get("rho") is None]
    if venter:
        samm.append(f"Hypoteserne om selvstudie venter stadig: der er {venter[0]['n_uger']} af "
                    "12 uger med logget selvstudie.")

    skidt = [k for k, a in tydelige if a["vurdering"] == "skidt" and k in EN_TING]
    en_ting = EN_TING[skidt[0]] if skidt else ("Fortsæt rytmen fra denne uge, og læg den hårde løbetur om lørdagen "
                                                "igen.")
    forbehold = []
    if (snap.get("dage") and sum(1 for d in snap["dage"] if "soevn_t" in d) < 7):
        forbehold.append(f"Garmin har kun data for {sum(1 for d in snap['dage'] if 'soevn_t' in d)} af 7 dage.")
    if "selvstudie_timer" in af and uger_med_selvstudie < 8:
        forbehold.append(f"Selvstudie er kun logget i {uger_med_selvstudie} uger før denne, så normalen for "
                         "selvstudie er usikker.")
    return {"saetning": saetning, "udskilte": udskilte, "sammenhaenge": samm,
            "kommende_uge": _kommende_uge(snap.get("kommende") or []), "en_ting": en_ting, "forbehold": forbehold}


def _kommende_uge(kal: list[dict]) -> list[str]:
    """Plan for ugen efter ud fra dens kalender: træning efter undervisningen, selvstudie i hullerne."""
    slut = {}
    for e in kal:
        if e["type"] == "undervisning" and e["slut"]:
            wd = date.fromisoformat(e["dato"]).weekday()
            slut[wd] = max(slut.get(wd, "00:00"), e["slut"])
    plan = []
    if 0 in slut and 3 in slut:
        plan.append(f"Mandag og torsdag: styrke lige efter undervisningen, som slutter {kl(slut[0])} og {kl(slut[3])}.")
    if 1 in slut:
        plan.append(f"Tirsdag: rolig løbetur sidst på eftermiddagen; undervisningen slutter allerede {kl(slut[1])}.")
    if 2 in slut:
        plan.append("Onsdag: selvstudie i hullet mellem de to moduler, og ingen træning.")
    for e in kal:
        if e["type"] == "andet" and " · " not in e["titel"]:  # studieplanens blokke er ikke aftaler
            d = date.fromisoformat(e["dato"])
            hvornaar = "hele dagen" if e["heldag"] else f"{kl(e['start'])}–{kl(e['slut'])}"
            plan.append(f"{UGEDAGE[d.weekday()].capitalize()}: {e['titel']} ({hvornaar}), så dagen efter er en let dag.")
            break
    plan.append("Lørdag: intervaller om formiddagen, hvis readiness er over 60.")
    return plan


def _reviews(m, liv: sqlite3.Connection, tl: Tidslinje) -> None:
    for k in (3, 2, 1):
        uge = tl.denne - timedelta(weeks=k)
        with _frossent_ur(datetime.combine(uge + timedelta(days=7), KL), [m.kilder, m.rapport, m.side, m.cli]):
            snap = m.side.snapshot(liv, uge)
            uger = (uge - mandag(tl.selvstudie_fra)).days // 7
            m.side.gem_review(liv, uge, _review_tekst(snap, uger))


# --------------------------------------------------------------------------------------------------------------

def lav(ud: Path, idag: date) -> None:
    """Skriver Form & fokus' demodata under ud/form."""
    m = _importer()
    tl = Tidslinje(idag)
    rng = random.Random(30)
    mappe = ud / "form"
    mappe.mkdir(parents=True, exist_ok=True)
    nu = datetime.combine(idag, KL)

    with tempfile.TemporaryDirectory(prefix="kompas-demo-form-") as tmp:
        tmp = Path(tmp)
        coach_db = tmp / "coach.db"
        cfg = m.gc_config.CONFIG
        with contextlib.ExitStack() as stak:
            # Ingen af brugerens egne indstillinger (.env, miljøet) må sive ind i demoen
            for felt, v in {"hr_max": None, "hr_rest": None, "sex": None, "ics_sources": ["demo.ics"],
                            "timezone": "Europe/Copenhagen", "min_training_window_min": 60}.items():
                stak.enter_context(mock.patch.object(cfg, felt, v))
            stak.enter_context(_frossent_ur(nu, [m.metrics, m.site, m.kroppen]))

            conn = m.gc_db.connect(coach_db)
            conn.create_function("date", -1, _sql_date(idag))
            _byg_coach_db(conn, tl, rng)
            _perioder(m, conn, tl)

            # garmin-coach regner træningsbelastningen, og overblik læser den (samme rækkefølge som opdater.sh)
            mappe.mkdir(parents=True, exist_ok=True)
            m.site._write(mappe / "belastning.json", json.dumps(m.site.belastning(conn), ensure_ascii=False))

            # overblik: ugetabel, tre reviews og liv.json, læst fra den opdigtede database
            sure = tmp / "sure.json"
            _sure_udtraek(sure, tl, rng)
            skaerm, studie = tmp / "skaermtid.json", tmp / "studie.json"
            _skaermtid_udtraek(skaerm, tl, rng)
            _studie_udtraek(studie, tl, rng)
            for mod, felt, v in ((m.liv_config, "GARMIN_DB", coach_db), (m.liv_config, "SURE_JSON", sure),
                                 (m.liv_config, "SITE_DIR", mappe),
                                 (m.liv_config, "SKAERMTID_JSON", skaerm), (m.liv_config, "STUDIE_JSON", studie), (m.liv_config, "BELASTNING_JSON", mappe / "belastning.json"),
                                 (m.liv_config, "FOERSTE_UGE", tl.start.isoformat()),
                                 (m.liv_config, "SELVSTUDIE_FRA", tl.selvstudie_fra.isoformat()),
                                 (m.liv_config, "SELVSTUDIE_PRAEFIKS", "Selvstudie ·"),
                                 (m.liv_db, "DB_PATH", tmp / "liv.db")):
                stak.enter_context(mock.patch.object(mod, felt, v))
            with _frossent_ur(nu, [m.kilder, m.rapport, m.side, m.cli]):
                m.cli.opdater()
            liv = m.liv_db.connect(tmp / "liv.db")
            _reviews(m, liv, tl)
            with _frossent_ur(nu, [m.kilder, m.rapport, m.side, m.cli]):
                m.side.eksport(liv, mappe)
            liv.close()

            # garmin-coach' eget byg; kompas.json får "nyt" på Ugereview fra liv.json ovenfor
            m.site.byg(conn, mappe)
            conn.close()

    # byg kopierer også siderne; dem leverer demoserveren fra coach/site
    for navn in ("index.html", *m.site.EKSTRA_SIDER):
        (mappe / navn).unlink(missing_ok=True)


if __name__ == "__main__":
    ud = Path(sys.argv[1]) if len(sys.argv) > 1 else ROD / "demo" / "ud"
    lav(ud, date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date.today())
    print(f"Skrev {ud / 'form'}")
