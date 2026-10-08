"""Demodata til Form & fokus (/form/): garmin-coach og overblik.

Modulet laver en opdigtet garmin-coach-database for "Alex" i en midlertidig mappe og kører projekternes egne
byg på den, så tallene på siderne er regnet af den rigtige kode:

- overblik (`opdater`, `gem-review`, `eksport`) skriver liv.json,
- garmin-coach (`site.byg`) skriver coach.json, soevn.json, perioder.json, maaneder.json, oversigt.json og
  kompas.json.

Kun rådata (Garmin, Hevy, kalender og et lille Sure-udtræk), 14-dages vurderingerne og ugereviewenes tekst er
opdigtet her; teksterne bygger på de tal, koden har regnet. Byg-vejen i begge projekter bruger kun
standardbiblioteket, så modulet kræver ingen af garmin-coach' tredjepartspakker (mcp, garminconnect, icalendar).
Uret fryses til `idag` kl. 7 under byg (Python og SQLite), så alt følger `idag`. Intet skrives uden for `ud` og
en midlertidig mappe, og intet rammer nettet.
"""
from __future__ import annotations

import contextlib
import json
import random
import sqlite3
import sys
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROD = Path(__file__).resolve().parents[2]
COACH = ROD / "coach"
LIV = ROD / "overblik"
KL = time(7, 0)  # siderne er "bygget" kl. 7, når Kompas-appen åbnes om morgenen

UGEDAGE = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]

# Opdigtet atlet: makspuls 196 og hvilepuls 52 giver pulszonerne nedenfor (Karvonen 50-90 %).
ZONER = {1: 124, 2: 138, 3: 153, 4: 167, 5: 182}

# Pladsholderfag i samme form som titlerne fra universitetets skema: "Alfa – lorem ipsum (A) - KURS101.A -
# Lecture (On Campus)". Første ord bestemmer faget i Kompas, og "KURS" gør det til undervisning i overblik.
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
        from garmin_coach import config as gc_config, db as gc_db, metrics, site
        from overblik import cli, config as liv_config, db as liv_db, kilder, rapport, side
    finally:
        for s in stier:
            sys.path.remove(s)
    return SimpleNamespace(gc_config=gc_config, gc_db=gc_db, metrics=metrics, site=site, cli=cli,
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
        self._faktorer: dict = {}

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
        if d.weekday() in plan and (rng.random() < 0.85 or mandag(d) == tl.tung):
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
    return ev


def _traeningsplan(tl: Tidslinje, d: date, rng: random.Random) -> list[tuple]:
    """Dagens pas: (type, start). Typer: A/B (styrke), rolig, lang, interval, boulder."""
    wd, pas = d.weekday(), []
    foer_semester = mandag(d) < tl.semester
    tung = mandag(d) == tl.tung
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
    andele = {"rolig": [0.14, 0.74, 0.10, 0.02, 0.0], "lang": [0.12, 0.78, 0.09, 0.01, 0.0],
              "interval": [0.10, 0.42, 0.14, 0.21, 0.13], "boulder": [0.62, 0.30, 0.08, 0.0, 0.0]}[kind]
    a = [max(0.0, x + rng.gauss(0, 0.03)) for x in andele]
    s = sum(a)
    return [round(sek * x / s) for x in a]


def _byg_coach_db(conn: sqlite3.Connection, tl: Tidslinje, rng: random.Random) -> None:
    kalender = _undervisning_og_kalender(tl, rng)
    social_naetter = {s.date() + timedelta(days=1) for _, s, _, titel, heldag in kalender
                      if not heldag and s.hour >= 18 and titel != ANDET["imorgen"]}
    conn.executemany(
        "INSERT INTO calendar_events (uid, start_local, end_local, start_utc, end_utc, summary, all_day) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(uid, s.strftime("%Y-%m-%dT%H:%M"), e.strftime("%Y-%m-%dT%H:%M"),
          None if heldag else _utc(s), None if heldag else _utc(e), titel, int(heldag))
         for uid, s, e, titel, heldag in kalender])

    alle_dage = (tl.idag - tl.start).days + 1
    dage, pas_i_gaar = [], 0.0
    for i in range(alle_dage):
        d = tl.start + timedelta(days=i)
        f = tl.ugefaktor(d)
        p = i / alle_dage  # fremgang fra 0 til 1 over hele perioden

        # --- træning (i dag er ikke trænet endnu kl. 7)
        belastning_i_dag = 0.0
        if d < tl.idag and d != tl.hul:
            for n, (kind, kl_) in enumerate(_traeningsplan(tl, d, rng)):
                belastning_i_dag += _gem_pas(conn, d, kind, kl_, n, p, rng)

        # --- søvn og restitution (natten til d)
        if d == tl.hul:
            pas_i_gaar = belastning_i_dag
            continue
        weekend = d.weekday() in (5, 6)
        soevn = 7.3 + f["soevn"] + (0.35 if weekend else 0) + rng.gauss(0, 0.5)
        if d in social_naetter:
            soevn -= 1.0
        if d == tl.idag:
            soevn = 7.6
        soevn = _klem(soevn, 4.9, 9.4)
        hrv = 55 + f["hrv"] + 3.5 * (soevn - 7.3) + rng.gauss(0, 4.5) - (5 if d in social_naetter else 0) \
            - 0.03 * pas_i_gaar
        rhr = 53 + f["rhr"] - 0.6 * (soevn - 7.3) + rng.gauss(0, 1.4) + (1.5 if d in social_naetter else 0)
        if d == tl.idag:
            hrv, rhr = 60.0, 51.0
        score = _klem(round(76 + 8 * (soevn - 7.3) + 0.3 * (hrv - 55) + rng.gauss(0, 5)), 38, 95)
        readiness = _klem(round(64 + 9 * (soevn - 7.3) + 1.1 * (hrv - 55) - 1.4 * (rhr - 53)
                                - 0.08 * pas_i_gaar + rng.gauss(0, 6)), 8, 99)
        if d == tl.idag:
            score, readiness = 84, 79
        bb = _klem(round(68 + 6 * (soevn - 7.3) + 0.6 * (hrv - 55) + rng.gauss(0, 5)), 25, 100)
        stress = round(_klem(28 + f["stress"] + rng.gauss(0, 4), 12, 60))
        skridt = round(_klem(rng.gauss(8600 if d.weekday() < 5 else 7400, 2100), 2500, 19000))
        dyb = soevn * rng.uniform(0.15, 0.21)
        rem = soevn * rng.uniform(0.19, 0.25)
        dage.append({
            "date": d.isoformat(), "resting_hr": round(rhr), "hrv_last_night": round(hrv),
            "sleep_s": round(soevn * 3600), "deep_s": round(dyb * 3600), "rem_s": round(rem * 3600),
            "light_s": round((soevn - dyb - rem) * 3600), "awake_s": round(rng.uniform(0.15, 0.6) * 3600),
            "sleep_score": score, "stress_avg": 22 if d == tl.idag else stress,
            "bb_high": 88 if d == tl.idag else bb, "bb_low": None if d == tl.idag else max(5, bb - rng.randint(45, 62)),
            "steps": 640 if d == tl.idag else skridt, "training_readiness": readiness,
            "vo2max": round(47.2 + 2.3 * p + rng.gauss(0, 0.15), 1) if d.weekday() in (1, 5) else None,
            "weight_kg": round(75.6 - 1.9 * p + rng.gauss(0, 0.3), 1) if d.weekday() in (0, 3, 6) else None,
        })
        pas_i_gaar = belastning_i_dag

    # HRV-status som Garmins: 7-dages snit holdt op mod niveauet
    grund = sum(x["hrv_last_night"] for x in dage) / len(dage)
    for j, x in enumerate(dage):
        uge = [y["hrv_last_night"] for y in dage[max(0, j - 6): j + 1]]
        x["hrv_status"] = "UNBALANCED" if sum(uge) / len(uge) < grund - 6 else "BALANCED"
    kol = list(dage[0])
    conn.executemany(f"INSERT INTO daily ({', '.join(kol)}) VALUES ({', '.join('?' * len(kol))})",
                     [[x[k] for k in kol] for x in dage])

    for k, v in {"zone_max_hr": "196", "zone_method": "HR_RESERVE",
                 "zone_floors": json.dumps({f"zone{z}": b for z, b in ZONER.items()})}.items():
        conn.execute("INSERT INTO sync_state (key, value) VALUES (?, ?)", (k, v))
    conn.commit()


def _gem_pas(conn, d: date, kind: str, kl_: str, n: int, p: float, rng: random.Random) -> float:
    """Ét pas i activities (og Hevy for styrke). Returnerer en grov belastning til restitutionen."""
    start = _hm(d, kl_) + timedelta(minutes=rng.choice((-10, -5, 0, 5, 10, 15)))
    aid = f"demo-{d.isoformat()}-{n}"
    raw: dict = {"startTimeGMT": start.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}
    if kind in ("A", "B"):
        minutter = rng.uniform(58, 72)
        snit, maks, sport, navn, last = rng.uniform(104, 114), rng.uniform(140, 156), "strength_training", \
            f"Styrke {kind}", None
        _gem_hevy(conn, aid, kind, start, minutter, p, rng)
    else:
        minutter = {"rolig": rng.uniform(36, 52), "lang": rng.uniform(62, 80), "interval": rng.uniform(40, 52),
                    "boulder": rng.uniform(75, 100)}[kind]
        snit = {"rolig": rng.uniform(137, 144), "lang": rng.uniform(139, 145), "interval": rng.uniform(153, 160),
                "boulder": rng.uniform(116, 126)}[kind]
        maks = {"rolig": rng.uniform(154, 164), "lang": rng.uniform(158, 168), "interval": rng.uniform(177, 186),
                "boulder": rng.uniform(150, 162)}[kind]
        sport = "bouldering" if kind == "boulder" else "running"
        navn = {"rolig": "Rolig løbetur", "lang": "Langtur", "interval": "Intervaller 5 × 4 min",
                "boulder": "Bouldering"}[kind]
        last = {"rolig": rng.uniform(52, 72), "lang": rng.uniform(85, 115), "interval": rng.uniform(105, 150),
                "boulder": rng.uniform(38, 60)}[kind]
        zt = _zonetid(kind, minutter * 60, rng)
        raw.update({f"hrTimeInZone_{z}": s for z, s in enumerate(zt, 1)})
        conn.executemany("INSERT INTO activity_zones (activity_id, zone, seconds, low_bpm) VALUES (?, ?, ?, ?)",
                         [(aid, z, s, ZONER[z]) for z, s in enumerate(zt, 1)])
    km = {"rolig": 5.9 + 0.6 * p, "lang": 6.1 + 0.6 * p, "interval": 7.2 + 0.5 * p}.get(kind)
    conn.execute(
        "INSERT INTO activities (activity_id, start_local, date, sport, name, duration_s, distance_m, avg_hr, "
        "max_hr, elev_gain_m, calories, garmin_load, aerobic_te, anaerobic_te, raw) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (aid, start.strftime("%Y-%m-%d %H:%M:%S"), d.isoformat(), sport, navn, round(minutter * 60),
         None if km is None else round(km * minutter / 45 * 1000), round(snit), round(maks),
         None if km is None else round(rng.uniform(15, 60)), round(minutter * snit * 0.075),
         None if last is None else round(last), round(rng.uniform(2.2, 3.8), 1),
         round(rng.uniform(0.2, 2.8 if kind == "interval" else 1.2), 1), json.dumps(raw)))
    return {"A": 40, "B": 40, "rolig": 60, "lang": 85, "interval": 95, "boulder": 70}[kind]


def _gem_hevy(conn, aid: str, program: str, start: datetime, minutter: float, p: float,
              rng: random.Random) -> None:
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


# --------------------------------------------------------------------------------------------------------------
# 14-dages vurderinger (det, rutinen "Form & Fokus" ellers skriver)
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
OPSTILLING = {
    "soevn": "Sov mindst 7 t pr. nat i snit",
    "let": "Hold mindst 75 % af konditionstiden i zone 1–2",
    "styrke": "To styrkepas om ugen med RPE på alle arbejdssæt",
    "skridt": "Mindst 8.000 skridt om dagen",
    "selvstudie": "Log selvstudie i CalTask hver undervisningsdag",
}
HANDLING = {
    "soevn": "Fast sengetid kl. 23.30 på hverdage, også aftenen før undervisning kl. 8.15.",
    "let": f"Løb de rolige ture under {ZONER[3]} bpm (grænsen til zone 3), også op ad bakke.",
    "styrke": "Udfyld RPE i Hevy lige efter sættet i stedet for bagefter.",
    "skridt": "Gå til og fra campus de dage, hvor vejret er til det.",
    "selvstudie": "Start CalTask, før bøgerne åbnes, så sessionen ikke bliver glemt.",
}


def _fokus(p: dict, fase: str) -> list[tuple]:
    s, st = p["sundhed"], p["styrke"]
    lav = _lavpct(p)
    kandidater = []
    if s["sovn_t"] is not None and s["sovn_t"] < 7.25:
        kandidater.append(("soevn", f"{OPSTILLING['soevn']} ({tal(s['sovn_t'], 1)} t i perioden)"))
    if fase != "foer" and (p.get("studie") or {}).get("selvstudie_t") is not None:
        kandidater.append(("selvstudie", f"{OPSTILLING['selvstudie']} ({tal(p['studie']['selvstudie_t'], 1)} t "
                                         f"på {p['studie']['sessioner']} sessioner)"))
    if lav is not None and lav < 80:
        kandidater.append(("let", f"{OPSTILLING['let']} ({lav} % i perioden)"))
    kandidater.append(("styrke", f"{OPSTILLING['styrke']} ({st['pas']} pas, {st['rpe_daekning_pct']} % med RPE)"))
    if s["skridt"] is not None and s["skridt"] < 9000:
        kandidater.append(("skridt", f"{OPSTILLING['skridt']} ({tal(s['skridt'])} i snit)"))
    return kandidater[:3]


def _opfoelgning(art: str, p: dict) -> dict:
    s, st, stu = p["sundhed"], p["styrke"], p.get("studie") or {}
    lav = _lavpct(p)
    if art == "soevn":
        v = s["sovn_t"] or 0
        status, note = ("naaet" if v >= 7 else "delvist" if v >= 6.8 else "ikke"), f"{tal(v, 1)} t pr. nat."
    elif art == "let":
        v = lav or 0
        status, note = ("naaet" if v >= 75 else "delvist" if v >= 70 else "ikke"), f"{v} % i zone 1–2."
    elif art == "styrke":
        status = "naaet" if st["pas"] >= 4 and (st["rpe_daekning_pct"] or 0) >= 90 else \
            "delvist" if st["pas"] >= 3 else "ikke"
        note = f"{st['pas']} pas, {st['rpe_daekning_pct']} % af sættene med RPE."
    elif art == "skridt":
        v = s["skridt"] or 0
        status, note = ("naaet" if v >= 8000 else "delvist" if v >= 7500 else "ikke"), f"{tal(v)} skridt i snit."
    else:
        n = stu.get("sessioner") or 0
        status, note = ("naaet" if n >= 7 else "delvist" if n >= 4 else "ikke"), f"{n} sessioner logget."
    return {"fokus": OPSTILLING[art], "status": status, "note": note}


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


def _vurdering(p: dict, forrige: dict | None, fase: str, nr: int, forrige_fokus: list) -> tuple[dict, list]:
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
    if st["pas"] >= 4:
        godt.append((1.1, f"Alle {st['pas']} styrkepas blev gennemført, med {st['haarde_saet']} arbejdssæt i alt."))
    if s["skridt"] is not None and s["skridt"] >= 8000:
        godt.append((0.9, f"{tal(s['skridt'])} skridt om dagen i snit."))
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

    fokus = _fokus(p, fase)
    opf = [_opfoelgning(art, p) for art, _ in forrige_fokus]
    naaet = sum(1 for o in opf if o["status"] == "naaet")
    resume = (f"{AABNING[fase][nr % len(AABNING[fase])]} Søvnen lå på {tal(s['sovn_t'], 1)} t pr. nat og HRV på "
              f"{tal(s['hrv'])} ms, og du nåede {t['pas']} pas på {tal(t['timer'], 1)} t, heraf {st['pas']} "
              f"styrkepas.")
    if opf:
        resume += f" {naaet} af {len(opf)} fokuspunkter fra perioden før blev nået."
    vurdering = {
        "resume": resume, "gaar_godt": godt, "gaar_daarligt": skidt,
        "forbedring": [HANDLING[art] for art, _ in fokus[:3]],
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
        vurdering, fokus = _vurdering(p, forrige, fase, taellere[fase], forrige_fokus)
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
        if e["type"] == "andet":
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
            stak.enter_context(_frossent_ur(nu, [m.metrics, m.site]))

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
            for mod, felt, v in ((m.liv_config, "GARMIN_DB", coach_db), (m.liv_config, "SURE_JSON", sure),
                                 (m.liv_config, "SITE_DIR", mappe), (m.liv_config, "BELASTNING_JSON", mappe / "belastning.json"),
                                 (m.liv_config, "FOERSTE_UGE", tl.start.isoformat()),
                                 (m.liv_config, "SELVSTUDIE_FRA", tl.selvstudie_fra.isoformat()),
                                 (m.liv_config, "KURSUSKODE", "KURS"), (m.liv_config, "SELVSTUDIE_PRAEFIKS", "Selvstudie ·"),
                                 (m.liv_db, "DB_PATH", tmp / "liv.db")):
                stak.enter_context(mock.patch.object(mod, felt, v))
            with _frossent_ur(nu, [m.kilder, m.rapport, m.side, m.cli]):
                m.cli.opdater()
            liv = m.liv_db.connect(tmp / "liv.db")
            _reviews(m, liv, tl)
            with _frossent_ur(nu, [m.kilder, m.rapport, m.side, m.cli]):
                m.side.eksport(liv, mappe)
            liv.close()

            # garmin-coach' eget byg; kompas.json får "nyt" på Ugen i tal fra liv.json ovenfor
            m.site.byg(conn, mappe)
            conn.close()

    # byg kopierer også siderne; dem leverer demoserveren fra coach/site
    for navn in ("index.html", *m.site.EKSTRA_SIDER):
        (mappe / navn).unlink(missing_ok=True)


if __name__ == "__main__":
    ud = Path(sys.argv[1]) if len(sys.argv) > 1 else ROD / "demo" / "ud"
    lav(ud, date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date.today())
    print(f"Skrev {ud / 'form'}")
