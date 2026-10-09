"""Beregningslaget.

Her ligger hele pointen med opsætningen: alle tal regnes i Python, og modellen
får kun færdige aggregater at fortolke. Sprogmodeller regner upålideligt på
lange talrækker, så de skal aldrig se rå dagsdata.
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .skema import FELTER, short_title
from .config import CONFIG
from .db import get_state


# --------------------------------------------------------------------------
# Hvem er atleten? Tallene udledes frem for at blive tastet ind.
# --------------------------------------------------------------------------

@dataclass
class Athlete:
    hr_max: float
    hr_rest: float
    sex: str
    sources: dict = field(default_factory=dict)

    def hr_reserve_fraction(self, avg_hr: float) -> float:
        """Karvonen: hvor stor en del af pulsreserven en session lå på."""
        span = self.hr_max - self.hr_rest
        if span <= 0:
            return 0.0
        return max(0.0, min(1.0, (avg_hr - self.hr_rest) / span))


def _observed_hr_max(conn: sqlite3.Connection) -> float | None:
    """Tredjehøjeste registrerede makspuls det seneste år.

    Tredjehøjeste frem for højeste, fordi ét enkelt udfald fra et pulsbælte der
    mister kontakt sagtens kan vise 220 og dermed forskyde alle beregninger.
    """
    since = (date.today() - timedelta(days=365)).isoformat()
    rows = conn.execute(
        "SELECT max_hr FROM activities WHERE date >= ? AND max_hr BETWEEN 120 AND 230 "
        "ORDER BY max_hr DESC LIMIT 3",
        (since,),
    ).fetchall()
    return round(float(rows[-1]["max_hr"])) if len(rows) == 3 else None


def _observed_hr_rest(conn: sqlite3.Connection) -> float | None:
    """Median af de seneste 60 dages målte hvilepuls.

    Median frem for gennemsnit, så enkelte sygedage eller dårlige nætter ikke
    trækker niveauet op. Det her er et målt tal og dermed bedre end en statisk
    indstilling i en profil.
    """
    since = (date.today() - timedelta(days=60)).isoformat()
    rows = conn.execute(
        "SELECT resting_hr FROM daily WHERE date >= ? AND resting_hr BETWEEN 25 AND 95",
        (since,),
    ).fetchall()
    values = [float(r["resting_hr"]) for r in rows]
    return round(statistics.median(values), 1) if len(values) >= 10 else None


def _profile(conn: sqlite3.Connection, key: str) -> float | None:
    return _state_float(conn, f"profile_{key}")


def _state_float(conn: sqlite3.Connection, key: str) -> float | None:
    raw = get_state(conn, key)
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def athlete(conn: sqlite3.Connection) -> Athlete:
    """Vælg de bedste tilgængelige tal, i prioriteret rækkefølge.

    Makspuls:
    1. En værdi du selv har sat i miljøet.
    2. Garmins konfigurerede makspuls (zoneopsætningen, ellers profilen), så
       belastning og pulszoner regner med samme tal.
       Ligger din tredjehøjeste registrerede puls over, er Garmins tal bevist
       for lavt, og den registrerede bruges i stedet.
    3. Tredjehøjeste registrerede puls det seneste år. Det er et gulv, ikke en
       testet maks, og typisk for lavt.
    4. En standardværdi.

    Hvilepuls: manuelt sat, ellers median af målt hvilepuls, ellers Garmins
    profil, ellers en standardværdi. Her slår målt indstillet, for hvilepulsen
    måles faktisk hver nat.
    """
    sources: dict[str, str] = {}

    def pick(name, candidates, default):
        for value, label in candidates:
            if value:
                sources[name] = label
                return float(value)
        sources[name] = "standardværdi (upålidelig)"
        return float(default)

    observed_max = _observed_hr_max(conn)
    zone_max = _state_float(conn, "zone_max_hr")
    profile_max = _profile(conn, "hr_max")
    garmin_max, garmin_label = (
        (zone_max, "Garmins zoneopsætning") if zone_max
        else (profile_max, "Garmins profil")
    )
    observed_label = (
        "tredjehøjeste registrerede puls det seneste år — et gulv, ikke en "
        "testet makspuls, så sandsynligvis for lav"
    )
    if garmin_max and observed_max and observed_max > garmin_max:
        garmin_max = None
        observed_label = (
            f"tredjehøjeste registrerede puls det seneste år, som ligger over "
            f"{garmin_label.lower()} ({round(zone_max or profile_max)}) — "
            f"Garmins tal er dermed for lavt"
        )
    hr_max = pick("hr_max", [
        (CONFIG.hr_max, "sat manuelt"),
        (garmin_max, garmin_label),
        (observed_max, observed_label),
    ], 190)
    hr_rest = pick("hr_rest", [
        (CONFIG.hr_rest, "sat manuelt"),
        (_observed_hr_rest(conn), "median af målt hvilepuls, seneste 60 dage"),
        (_profile(conn, "hr_rest"), "Garmins profil"),
    ], 55)

    sex_raw = CONFIG.sex or get_state(conn, "profile_sex") or "m"
    sources["sex"] = "sat manuelt" if CONFIG.sex else (
        "Garmins profil" if get_state(conn, "profile_sex") else "standardværdi"
    )

    return Athlete(hr_max=hr_max, hr_rest=hr_rest, sex=sex_raw[:1].lower(), sources=sources)


# En dag tæller som målt hvis uret har leveret mindst én af de centrale værdier
_MEASURED = "(resting_hr IS NOT NULL OR sleep_s IS NOT NULL OR hrv_last_night IS NOT NULL)"


def freshness(conn: sqlite3.Connection) -> dict:
    """Hvor gamle er dataene?

    Uden det her kan et værktøj svare selvsikkert på tal der er tre uger gamle,
    uden at nogen opdager det. Rådgivning om "i dag" bygget på forældede data
    er værre end ingen rådgivning.
    """
    row = conn.execute(f"SELECT MAX(date) d FROM daily WHERE {_MEASURED}").fetchone()
    last = row["d"] if row and row["d"] else None
    if not last:
        return {"status": "tom database", "handling": "kør sync før du vurderer noget"}
    alder = (date.today() - date.fromisoformat(last)).days
    status = "aktuel" if alder <= 1 else ("lidt gammel" if alder <= 3 else "forældet")
    out = {"seneste_data": last, "dage_gammel": alder, "status": status}
    if alder > 3:
        out["handling"] = (
            f"Dataene er {alder} dage gamle. Sig det til brugeren og foreslå en "
            "sync, før du udtaler dig om aktuel form eller hvad der skal trænes i dag."
        )
    return out


def _gap_days(conn: sqlite3.Connection, days: int = 28) -> int:
    """Dage uden nogen wellness-måling overhovedet, altså hvor uret ikke var på.

    Vigtigt at kunne skelne fra hviledage: et hul i data ligner en hviledag i
    belastningsberegningen, men betyder noget helt andet.
    """
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    row = conn.execute(
        f"SELECT COUNT(*) n FROM daily WHERE date >= ? AND {_MEASURED}", (since,)
    ).fetchone()
    # Dage helt uden række tæller også som huller
    return days - (row["n"] if row else 0)


def zone_distribution(conn: sqlite3.Connection, days: int = 28) -> dict:
    """Faktisk tid i hver pulszone, målt af Garmin sekund for sekund.

    Det her er den rigtige opgørelse. Et intervalpas fordeles som det blev
    trænet, i stedet for at hele varigheden lander i én zone efter
    gennemsnitspulsen.
    """
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT z.zone, SUM(z.seconds) s
           FROM activity_zones z JOIN activities a ON a.activity_id = z.activity_id
           WHERE a.date >= ? GROUP BY z.zone ORDER BY z.zone""",
        (since,),
    ).fetchall()
    if not rows:
        return {"kilde": "ingen zonedata — kør sync for at hente dem fra Garmin"}

    total = sum(r["s"] or 0 for r in rows)
    if total <= 0:
        return {"kilde": "ingen zonedata"}

    # Hvert pas er gemt med de grænser der gjaldt da det blev registreret.
    # Grupperes de, kan vi se om grænserne har flyttet sig i perioden.
    bound_sets = _zone_bound_sets(conn, since)
    newest = bound_sets[0]["grænser"] if bound_sets else {}

    zoner = [
        {
            "zone": r["zone"],
            "fra_bpm": newest.get(r["zone"]),
            "minutter": round((r["s"] or 0) / 60),
            "procent": round(100 * (r["s"] or 0) / total),
        }
        for r in rows
    ]
    # Tre-bånds-model: under zone 3 er let, zone 3 er moderat, over er hårdt
    baand = {"let": 0.0, "moderat": 0.0, "hård": 0.0}
    for r in rows:
        key = "let" if r["zone"] <= 2 else ("moderat" if r["zone"] == 3 else "hård")
        baand[key] += r["s"] or 0

    out = {
        "kilde": "Garmins egen måling, sekund for sekund",
        "samlet_timer": round(total / 3600, 1),
        "zoner": zoner,
        "tre_baand_procent": {k: round(100 * v / total) for k, v in baand.items()},
        "note": (
            "Polariseret træning ligger typisk omkring 75-80 % let og 15-20 % "
            "hårdt, med lidt i midten. Meget tid i moderat båndet er det klassiske "
            "mønster hvor de lette pas bliver for hårde og de hårde for lette."
        ),
    }
    if len(bound_sets) > 1:
        out["zonegrænser_ændret"] = {
            "note": (
                "Zonegrænserne har ændret sig undervejs i perioden. Minutter og "
                "procenter er lagt sammen på tværs af forskellige grænser, så de "
                "er ikke direkte sammenlignelige over hele perioden. fra_bpm i "
                "zoner viser grænserne for de nyeste pas."
            ),
            "sæt": [
                {
                    "grænser_bpm": {f"zone{z}": b for z, b in g["grænser"].items()},
                    "pas": g["pas"],
                    "fra": g["fra"],
                    "til": g["til"],
                }
                for g in bound_sets
            ],
        }

    lthr = get_state(conn, "profile_lthr")
    method = get_state(conn, "zone_method")
    floors_raw = get_state(conn, "zone_floors")
    zone_max = get_state(conn, "zone_max_hr")

    if method or lthr:
        opsaetning = {"metode": method, "makspuls_i_opsætning": zone_max}
        if lthr:
            opsaetning["laktattærskel_bpm"] = float(lthr)
        if floors_raw:
            try:
                opsaetning["grænser_bpm"] = json.loads(floors_raw)
            except ValueError:
                pass
        out["zoneopsætning"] = opsaetning

        # Er zonerne sat efter makspuls, mens tærsklen er kendt, passer
        # grænserne ikke nødvendigvis med fysiologien. Sammenlign med den
        # zone 5-grænse passene faktisk blev talt op efter, ikke opsætningen
        # som den ser ud i dag.
        if method == "HR_MAX" and lthr:
            z5 = newest.get(5)
            if z5 is None and floors_raw:
                try:
                    z5 = json.loads(floors_raw).get("zone5")
                except (ValueError, AttributeError):
                    z5 = None
            try:
                lthr_f = float(lthr)
                if z5 and lthr_f < float(z5):
                    tekst = (
                        f"Zonerne er sat efter makspuls, ikke efter tærskel. Zone 5 "
                        f"starter ved {round(float(z5))} i de nyeste pas, mens "
                        f"laktattærsklen er {round(lthr_f)}. Arbejde mellem de to tal "
                        f"er fysiologisk over tærskel, men tælles her som zone 4. "
                        f"Tolk zone 4 med det in mente, og nævn for brugeren at "
                        f"tærskelbaserede zoner ville flytte grænsen."
                    )
                    older = {}
                    for g in bound_sets[1:]:
                        b = g["grænser"].get(5)
                        if b is not None and b != newest.get(5):
                            older[b] = older.get(b, 0) + g["pas"]
                    if older:
                        dele = ", ".join(
                            f"{b} ({n} pas)" for b, n in sorted(older.items())
                        )
                        tekst += (
                            f" Ældre pas i perioden havde en anden zone 5-grænse: "
                            f"{dele}. For dem gælder forbeholdet ikke på samme måde."
                        )
                    out["forbehold_zoner"] = tekst
            except (TypeError, ValueError):
                pass
    return out


def _zone_bound_sets(conn: sqlite3.Connection, since: str) -> list[dict]:
    """Distinkte sæt af zonegrænser i perioden, nyeste først.

    Pas uden registreret tid i nogen zone springes over, for deres grænser
    har ikke bidraget til fordelingen.
    """
    rows = conn.execute(
        """SELECT a.activity_id, a.date, a.start_local, z.zone, z.low_bpm, z.seconds
           FROM activity_zones z JOIN activities a ON a.activity_id = z.activity_id
           WHERE a.date >= ?
           ORDER BY a.start_local DESC, a.activity_id, z.zone""",
        (since,),
    ).fetchall()

    per_pas: dict[str, dict] = {}
    for r in rows:
        p = per_pas.setdefault(r["activity_id"], {"date": r["date"], "b": {}, "s": 0})
        if r["low_bpm"] is not None:
            p["b"][r["zone"]] = round(r["low_bpm"])
        p["s"] += r["seconds"] or 0

    sets: dict[tuple, dict] = {}
    for p in per_pas.values():  # indsat nyeste først
        if p["s"] <= 0 or not p["b"]:
            continue
        key = tuple(sorted(p["b"].items()))
        g = sets.get(key)
        if g is None:
            sets[key] = {"grænser": dict(key), "pas": 1, "fra": p["date"], "til": p["date"]}
        else:
            g["pas"] += 1
            g["fra"] = min(g["fra"], p["date"])
            g["til"] = max(g["til"], p["date"])
    return list(sets.values())


def intensity_split(conn: sqlite3.Connection, ath: Athlete, days: int = 28) -> dict:
    """Intensitetsfordeling. Bruger Garmins målte zonedata når de findes.

    Kun hvis zonedata mangler falder den tilbage på et skøn ud fra
    gennemsnitspuls per pas, og siger det tydeligt, for det skøn lægger hele
    passets varighed i én zone og undervurderer intervaltræning.
    """
    real = zone_distribution(conn, days)
    if "tre_baand_procent" in real:
        return real

    since = (date.today() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT duration_s, avg_hr FROM activities WHERE date >= ? AND avg_hr IS NOT NULL",
        (since,),
    ).fetchall()
    buckets = {"let": 0.0, "moderat": 0.0, "hård": 0.0}
    for r in rows:
        x = ath.hr_reserve_fraction(r["avg_hr"])
        key = "let" if x < 0.65 else ("moderat" if x < 0.80 else "hård")
        buckets[key] += (r["duration_s"] or 0) / 3600.0
    total = sum(buckets.values())
    if total <= 0:
        return {"målte_pas": 0}
    return {
        "kilde": "SKØN ud fra gennemsnitspuls per pas — ikke målt",
        "målte_pas": len(rows),
        "timer": {k: round(v, 1) for k, v in buckets.items()},
        "tre_baand_procent": {k: round(100 * v / total) for k, v in buckets.items()},
        "forbehold": (
            "Hele passets varighed lægges i én zone efter gennemsnitspulsen, så "
            "intervalpas undervurderes kraftigt. Kør sync for at hente Garmins "
            "målte zonedata i stedet."
        ),
    }


# --------------------------------------------------------------------------
# Belastning
# --------------------------------------------------------------------------

def banister_trimp(duration_s: float, avg_hr: float, ath: Athlete) -> float:
    """Banister TRIMP, pulsreserve-vægtet. Giver en session med høj puls
    eksponentielt mere vægt end en lang rolig tur."""
    if not duration_s or not avg_hr:
        return 0.0
    minutes = duration_s / 60.0
    x = ath.hr_reserve_fraction(avg_hr)
    if x <= 0:
        return 0.0
    factor = 0.86 * pow(2.718281828, 1.67 * x) if ath.sex == "f" else 0.64 * pow(
        2.718281828, 1.92 * x
    )
    return round(minutes * x * factor, 1)


# --------------------------------------------------------------------------
# Styrkepas fra Hevy
# --------------------------------------------------------------------------

# Tillæg pr. RPE-point over/under 8 for et sæt med dokumenteret anstrengelse.
# RPE 10 (til failure) vejer 1,3 sæt, RPE 8 ét sæt, RPE 6 0,7 sæt.
RPE_STEP = 0.15
# Under denne andel af arbejdssæt med RPE er ugens RPE-tal for tynde at læse
RPE_MIN_COVERAGE = 0.6


def _rpe_bonus(set_type: str | None, rpe: float | None) -> float | None:
    """Tillæg for dokumenteret anstrengelse, eller None hvis den ikke kendes.

    Et failure-sæt uden RPE er dokumenteret som RPE 10. Et sæt uden nogen af
    delene får intet tillæg — der gættes ikke på en RPE.
    """
    if rpe is not None:
        return RPE_STEP * (float(rpe) - 8)
    if set_type == "failure":
        return RPE_STEP * 2
    return None


_WORKING_SET = (
    "s.set_type IS NOT 'warmup' AND (s.reps IS NOT NULL OR "
    "(s.duration_s IS NOT NULL AND s.distance_m IS NULL))"
)


def _hevy_sessions(conn: sqlite3.Connection) -> dict[str, dict]:
    """Pr. pas: arbejdssæt, hvor mange har kendt anstrengelse, og point.

    Arbejdssæt er alt undtagen opvarmning og ren kardio (distance uden reps).
    Point = antal arbejdssæt + summen af RPE-tillæg på de sæt der har ét.
    """
    out: dict[str, dict] = {}
    rows = conn.execute(
        f"""SELECT w.activity_id, s.set_type, s.rpe FROM hevy_sets s
            JOIN hevy_workouts w ON w.workout_id = s.workout_id
            WHERE w.activity_id IS NOT NULL AND {_WORKING_SET}"""
    ).fetchall()
    for r in rows:
        h = out.setdefault(r["activity_id"], {"sæt": 0, "med_anstrengelse": 0, "point": 0.0})
        h["sæt"] += 1
        h["point"] += 1
        bonus = _rpe_bonus(r["set_type"], r["rpe"])
        if bonus is not None:
            h["med_anstrengelse"] += 1
            h["point"] += bonus
    return out


@dataclass
class LoadContext:
    hevy: dict[str, dict]
    trimp_per_point: float | None
    calibration_sessions: int


def load_context(conn: sqlite3.Connection, ath: Athlete) -> LoadContext:
    """Kalibrér Hevy-point til TRIMP på dine egne pas der har begge dele.

    Så ligger styrkepas på samme skala som alt andet, og historikken hopper
    ikke når kilden skifter fra puls til Hevy. Kræver mindst 5 pas med både
    puls og Hevy-sæt.
    """
    hevy = _hevy_sessions(conn)
    ratios = []
    if hevy:
        marks = ",".join("?" * len(hevy))
        for r in conn.execute(
            f"SELECT activity_id, duration_s, avg_hr FROM activities "
            f"WHERE avg_hr > 0 AND activity_id IN ({marks})", list(hevy)
        ):
            point = hevy[r["activity_id"]]["point"]
            trimp = banister_trimp(r["duration_s"], r["avg_hr"], ath)
            if point > 0 and trimp > 0:
                ratios.append(trimp / point)
    k = statistics.median(ratios) if len(ratios) >= 5 else None
    return LoadContext(hevy=hevy, trimp_per_point=k, calibration_sessions=len(ratios))


def session_load_detail(
    row: sqlite3.Row, ath: Athlete, ctx: LoadContext | None = None
) -> tuple[float, str]:
    """Belastning for ét pas og hvor den kommer fra: "hevy", "puls" eller "ingen".

    Hevy-data vinder hvor de findes, fordi sæt og RPE beskriver styrke bedre
    end en snitpuls omkring 100. Ellers Banister-TRIMP ud fra puls.
    Garmins egen training load bruges ikke: den mangler på styrkepas, og at
    blande den med TRIMP gav forskelle på 1-3x mellem sportsgrene.
    """
    h = ctx.hevy.get(row["activity_id"]) if ctx else None
    if h and h["point"] > 0 and ctx.trimp_per_point:
        return ctx.trimp_per_point * h["point"], "hevy"
    trimp = banister_trimp(row["duration_s"], row["avg_hr"], ath)
    if trimp > 0:
        return trimp, "puls"
    return 0.0, "ingen"


def session_load(row: sqlite3.Row, ath: Athlete, ctx: LoadContext | None = None) -> float:
    return session_load_detail(row, ath, ctx)[0]


def daily_loads(
    conn: sqlite3.Connection, start: date, end: date, ath: Athlete,
    ctx: LoadContext | None = None,
) -> dict[str, float]:
    """Belastning pr. dag, med nuller for hviledage (vigtigt for monotoni)."""
    ctx = ctx or load_context(conn, ath)
    rows = conn.execute(
        "SELECT * FROM activities WHERE date BETWEEN ? AND ? ORDER BY date",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    out = {
        (start + timedelta(days=i)).isoformat(): 0.0
        for i in range((end - start).days + 1)
    }
    for r in rows:
        if r["date"] in out:
            out[r["date"]] += session_load(r, ath, ctx)
    return out


def strength_weeks(conn: sqlite3.Connection, end: date, weeks: int) -> list[dict]:
    """Styrke pr. uge fra Hevy, nyeste først.

    RPE-tallene regnes kun over sæt der har en RPE, og er null når under
    60 % af ugens arbejdssæt har én. Ellers ville en uge hvor RPE blev glemt
    se lettere eller hårdere ud end den var.
    """
    out = []
    for w in range(weeks):
        hi = end - timedelta(days=7 * w)
        lo = hi - timedelta(days=6)
        rows = conn.execute(
            f"""SELECT s.set_type, s.rpe, s.weight_kg, s.reps, w.workout_id
                FROM hevy_sets s JOIN hevy_workouts w ON w.workout_id = s.workout_id
                JOIN activities a ON a.activity_id = w.activity_id
                WHERE a.date BETWEEN ? AND ? AND {_WORKING_SET}""",
            (lo.isoformat(), hi.isoformat()),
        ).fetchall()
        if not rows:
            out.append({"uge_siden": w, "pas": 0})
            continue
        rated = [float(r["rpe"]) for r in rows if r["rpe"] is not None]
        coverage = len(rated) / len(rows)
        enough = coverage >= RPE_MIN_COVERAGE
        out.append({
            "uge_siden": w,
            "pas": len({r["workout_id"] for r in rows}),
            "arbejdssæt": len(rows),
            "volumen_kg": round(sum((r["weight_kg"] or 0) * (r["reps"] or 0) for r in rows)),
            "rpe_dækning_pct": round(100 * coverage),
            "snit_rpe": round(statistics.mean(rated), 1) if enough and rated else None,
            "sæt_rpe_9_eller_mere": sum(1 for v in rated if v >= 9) if enough else None,
            **({} if enough else {"rpe_note": "for få sæt med RPE til at læse ugens anstrengelse"}),
        })
    return out


# --------------------------------------------------------------------------
# Periode-rapport (Form & Fokus)
# --------------------------------------------------------------------------

SPORT_DA = {
    "running": "Løb", "treadmill_running": "Løb", "trail_running": "Trailløb",
    "lap_swimming": "Svømning", "open_water_swimming": "Svømning",
    "strength_training": "Styrke", "bouldering": "Bouldering",
    "indoor_climbing": "Klatring", "hiking": "Vandring", "walking": "Gåtur",
    "volleyball": "Volleyball", "road_biking": "Cykling", "cycling": "Cykling",
    "indoor_cycling": "Indendørs cykling", "indoor_rowing": "Roning",
    "golf": "Golf", "paddelball": "Padel", "padel": "Padel", "yoga": "Yoga",
    "e_bike_fitness": "Elcykel", "e_bike_mountain": "Elcykel",
}
# Estimeret 1RM regnes kun for frie vægte: vægten på maskiner og kabler kan
# ikke sammenlignes på tværs af maskiner og træningscentre.
FREE_WEIGHT = ("(Barbell)", "(Dumbbell)", "(EZ Bar)", "(Trap Bar)")
# Epley er upålidelig ved mange gentagelser
E1RM_MAX_REPS = 12
LIFT_DA = {
    "Bench Press (Barbell)": "Bænkpres",
    "Bent Over Row (Barbell)": "Bent-over row",
    "Shoulder Press (Dumbbell)": "Skulderpres (håndvægt)",
    "Romanian Deadlift (Barbell)": "Rumænsk dødløft",
    "Incline Bench Press (Dumbbell)": "Skråbænkpres (håndvægt)",
    "Incline Bench Press (Barbell)": "Skråbænkpres",
    "Squat (Barbell)": "Squat",
    "Front Squat (Barbell)": "Frontsquat",
    "Deadlift (Barbell)": "Dødløft",
    "Bulgarian Split Squat (Dumbbell)": "Bulgarsk split squat",
    "Single Leg Standing Calf Raise (Dumbbell)": "Etbens-lægløft",
    "Seal Row (Barbell)": "Seal row",
    "Overhead Press (Barbell)": "Militærpres",
    "Seated Overhead Press (Barbell)": "Siddende skulderpres (stang)",
    "Seated Overhead Press (Dumbbell)": "Siddende skulderpres (håndvægt)",
    "Hip Thrust (Barbell)": "Hip thrust",
    "Hammer Curl (Dumbbell)": "Hammer curl",
    "Bicep Curl (Dumbbell)": "Biceps curl (håndvægt)",
    "Bicep Curl (Barbell)": "Biceps curl (stang)",
}


def lift_key(exercise: str) -> str:
    """Stabil nøgle til en Hevy-øvelse, fx 'bench_press_barbell'."""
    return re.sub(r"[^a-z0-9]+", "_", exercise.lower()).strip("_")


def _num(v: float) -> str:
    return f"{v:g}".replace(".", ",")
# Selvstudie logges i CalTask som begivenheder, der hedder "Selvstudie · <fag>"
SELVSTUDIE = "Selvstudie · "
# Pulszoner fra håndleddet siger intet om svømning og styrke
_NO_ZONE_SPORTS = ("lap_swimming", "strength_training")


def _r(v, d=1):
    return round(float(v), d) if v is not None else None


def periode_rapport(conn: sqlite3.Connection, start: str, slut: str) -> dict:
    """Alle tal til én periode på siden Form & Fokus, begge datoer inklusive.

    Felterne svarer til sidens dokumentformat, så de kan skrives direkte.
    "forbehold" samler det der gør tallene mindre sikre end de ser ud.
    """
    S, E = date.fromisoformat(start).isoformat(), date.fromisoformat(slut).isoformat()
    forbehold: list[str] = []

    # --- sundhed
    h = conn.execute(
        f"""SELECT SUM({_MEASURED}) dage, AVG(sleep_s)/3600.0 sovn,
                   SUM(sleep_s < 25200) u7, AVG(sleep_score) score, AVG(hrv_last_night) hrv,
                   AVG(resting_hr) rhr, AVG(stress_avg) stress, AVG(bb_high) bb,
                   AVG(training_readiness) ready, AVG(steps) skridt
            FROM daily WHERE date BETWEEN ? AND ?""", (S, E),
    ).fetchone()

    def latest(col):
        r = conn.execute(
            f"SELECT {col} v FROM daily WHERE date BETWEEN ? AND ? AND {col} IS NOT NULL "
            f"ORDER BY date DESC LIMIT 1", (S, E),
        ).fetchone()
        return r["v"] if r else None

    days_total = (date.fromisoformat(E) - date.fromisoformat(S)).days + 1
    dage = h["dage"] or 0
    if dage < days_total:
        forbehold.append(f"Wellness-data for {dage} af {days_total} dage.")
    sundhed = {
        "sovn_t": _r(h["sovn"], 2), "naetter_u7": h["u7"] or 0,
        "sovn_score": _r(h["score"]), "hrv": _r(h["hrv"]), "hvilepuls": _r(h["rhr"]),
        "stress": _r(h["stress"]), "body_battery": _r(h["bb"]), "readiness": _r(h["ready"]),
        "skridt": round(h["skridt"]) if h["skridt"] is not None else None,
        "vo2max": _r(latest("vo2max")), "vaegt": _r(latest("weight_kg"), 2),
    }

    # --- træning
    ath = athlete(conn)
    ctx = load_context(conn, ath)
    acts = conn.execute(
        "SELECT * FROM activities WHERE date BETWEEN ? AND ? ORDER BY start_local", (S, E)
    ).fetchall()
    belastning, kilder, uden = 0.0, {"hevy": 0, "puls": 0, "ingen": 0}, []
    sport: dict[str, dict] = {}
    zone = {"lav": 0.0, "mellem": 0.0, "hoj": 0.0}
    zone_pas = 0
    for a in acts:
        load, kilde = session_load_detail(a, ath, ctx)
        belastning += load
        kilder[kilde] += 1
        if kilde == "ingen":
            uden.append(f"{a['date']} {SPORT_DA.get(a['sport'], a['sport'])}")
        navn = SPORT_DA.get(a["sport"]) or (a["sport"] or "ukendt").replace("_", " ").capitalize()
        sp = sport.setdefault(navn, {"navn": navn, "pas": 0, "timer": 0.0})
        sp["pas"] += 1
        sp["timer"] += (a["duration_s"] or 0) / 3600
        if a["sport"] not in _NO_ZONE_SPORTS and a["raw"]:
            try:
                raw = json.loads(a["raw"])
            except ValueError:
                raw = {}
            secs = [raw.get(f"hrTimeInZone_{i}") for i in range(1, 6)]
            if any(v is not None for v in secs):
                z = [(v or 0) / 60 for v in secs]
                zone["lav"] += z[0] + z[1]
                zone["mellem"] += z[2]
                zone["hoj"] += z[3] + z[4]
                zone_pas += 1
    if uden:
        forbehold.append(
            "Uden belastning (hverken puls eller Hevy-sæt): " + ", ".join(uden) + "."
        )
    bounds = conn.execute(
        f"""SELECT COUNT(DISTINCT g) n FROM (
                SELECT group_concat(CAST(z.low_bpm AS INT), '/') g
                FROM activity_zones z JOIN activities a ON a.activity_id = z.activity_id
                WHERE a.date BETWEEN ? AND ? AND a.sport NOT IN {_NO_ZONE_SPORTS}
                GROUP BY z.activity_id)""", (S, E),
    ).fetchone()["n"]
    if bounds > 1:
        forbehold.append(
            "Pulszonegrænserne skiftede i perioden, så intensitetsfordelingen blander "
            "forskellige grænser."
        )
    traening = {
        "pas": len(acts),
        "timer": round(sum((a["duration_s"] or 0) for a in acts) / 3600, 1),
        "belastning": round(belastning),
        "belastningskilde": kilder,
        "intensitet_min": {k: round(v) for k, v in zone.items()} if zone_pas else None,
        "sport": sorted(
            ({**v, "timer": round(v["timer"], 2)} for v in sport.values()),
            key=lambda v: -v["timer"],
        ),
    }

    # --- styrke (Hevy)
    sets = conn.execute(
        f"""SELECT s.exercise, s.set_type, s.weight_kg, s.reps, s.rpe, w.workout_id
            FROM hevy_sets s JOIN hevy_workouts w ON w.workout_id = s.workout_id
            JOIN activities a ON a.activity_id = w.activity_id
            WHERE a.date BETWEEN ? AND ? AND {_WORKING_SET}""", (S, E),
    ).fetchall()
    rated = [float(r["rpe"]) for r in sets if r["rpe"] is not None]
    coverage = len(rated) / len(sets) if sets else None
    # Bedste sæt pr. frivægtsøvelse. Epley regnes uden RPE-justering, så et
    # sæt uden RPE aldrig ser svagere ud end et med; RPE følger med som
    # oplysning om hvor tæt på max sættet var.
    best: dict[str, tuple[float, sqlite3.Row]] = {}
    for r in sets:
        name = r["exercise"] or ""
        if not (any(t in name for t in FREE_WEIGHT) and r["weight_kg"]
                and r["reps"] and 1 <= r["reps"] <= E1RM_MAX_REPS):
            continue
        est = r["weight_kg"] * (1 + r["reps"] / 30.0)
        if name not in best or est > best[name][0]:
            best[name] = (est, r)
    e1rm, loeft = {}, {}
    for name, (est, r) in sorted(best.items()):
        key = lift_key(name)
        e1rm[key] = round(est, 1)
        loeft[key] = {
            "navn": LIFT_DA.get(name, name),
            "hevy": name,
            "bedste_saet": f"{_num(r['weight_kg'])} kg × {int(r['reps'])}",
            "rpe": r["rpe"],
        }
    enough = coverage is not None and coverage >= RPE_MIN_COVERAGE
    if sets and not enough:
        forbehold.append(
            f"RPE er kun udfyldt på {round(100 * coverage)} % af arbejdssættene, "
            "så periodens anstrengelse kan ikke læses af RPE."
        )
    styrke = {
        "pas": len({r["workout_id"] for r in sets}),
        "haarde_saet": len(sets),  # siden viser feltet som "Arbejdssæt"
        "rpe_daekning_pct": round(100 * coverage) if coverage is not None else None,
        "saet_rpe_9_plus": sum(1 for v in rated if v >= 9) if enough else None,
        "e1rm": e1rm,
        "loeft": loeft,
    }

    # --- studie (kalender)
    # Kalenderen dækker fra første sync-vindue; ældre databaser kender kun
    # deres tidligste begivenhed.
    cal_first = get_state(conn, "calendar_covered_from") or conn.execute(
        "SELECT MIN(start_local) d FROM calendar_events"
    ).fetchone()["d"]
    # Selvstudie logges i CalTask; før første session findes der ingen tal,
    # og 0 timer ville se ud som en måling.
    caltask_first = conn.execute(
        "SELECT MIN(start_local) d FROM calendar_events WHERE summary LIKE ?", (SELVSTUDIE + "%",)
    ).fetchone()["d"]
    if not cal_first or cal_first[:10] > S:
        studie = None
        forbehold.append("Kalenderdata dækker ikke hele perioden, så studie er udeladt.")
    else:
        ev = conn.execute(
            """SELECT summary, start_local, all_day, fag_kode,
                      (julianday(end_local) - julianday(start_local)) * 24 t
               FROM calendar_events WHERE date(start_local) BETWEEN ? AND ?
               ORDER BY start_local""", (S, E),
        ).fetchall()
        pr_fag: dict[str, float] = {}
        selv_t = undervisning = 0.0
        sessioner = 0
        andre = []
        for e in ev:
            summ = e["summary"] or ""
            t = e["t"] or 0
            if not e["all_day"] and summ.startswith(SELVSTUDIE):
                if t * 60 >= 5:
                    fag = re.sub(r"[^\w\s&/+-]", "", summ[len(SELVSTUDIE):]).strip() or "Andet"
                    pr_fag[fag] = pr_fag.get(fag, 0) + t
                    selv_t += t
                    sessioner += 1
            elif not e["all_day"] and e["fag_kode"]:
                undervisning += t
            else:
                d = date.fromisoformat(e["start_local"][:10])
                andre.append(f"{summ} ({d.day}/{d.month})")
        logged = caltask_first is not None and caltask_first[:10] <= E
        if logged and caltask_first[:10] > S:
            d = date.fromisoformat(caltask_first[:10])
            forbehold.append(
                f"Selvstudie er logget fra {d.day}/{d.month}, så perioden er kun delvist dækket."
            )
        studie = {
            "selvstudie_t": round(selv_t, 1) if logged else None,
            "sessioner": sessioner if logged else None,
            "pr_fag": [{"fag": f, "timer": round(v, 1)}
                       for f, v in sorted(pr_fag.items(), key=lambda x: -x[1])]
                      if logged else None,
            "undervisning_t": round(undervisning, 1),
            "andre_begivenheder": andre,
        }

    return {
        "start": S, "slut": E, "dage_med_data": dage,
        "sundhed": sundhed, "traening": traening, "styrke": styrke, "studie": studie,
        "forbehold": forbehold,
    }


def maanedsoversigt(conn: sqlite3.Connection, fra: str | None = None) -> dict:
    """Det store billede: nøgletal måned for måned, fra `fra` ('ÅÅÅÅ-MM')
    eller første måned med data.

    Hver måned regnes med periode_rapport, så tallene er de samme som på
    Form & Fokus. Mængder er omregnet til pr. uge, så korte måneder og den
    igangværende måned kan sammenlignes. "udvikling" holder de første tre
    fulde måneder op mod de seneste tre, så modellen ikke selv skal regne
    på en lang talrække.
    """
    first = conn.execute(
        f"SELECT MIN(d) d FROM (SELECT MIN(date) d FROM daily WHERE {_MEASURED} "
        f"UNION ALL SELECT MIN(date) FROM activities)"
    ).fetchone()["d"]
    if not first:
        return {"maaneder": [], "forbehold": ["Ingen data endnu — kør sync."]}
    today = date.today()
    start_month = datetime.strptime(fra or first[:7], "%Y-%m").date()  # ValueError ved fejl
    y, m = start_month.year, start_month.month
    hevy_first = conn.execute(
        "SELECT MIN(a.date) d FROM hevy_workouts w JOIN activities a ON a.activity_id = w.activity_id"
    ).fetchone()["d"]

    rows = []
    while (y, m) <= (today.year, today.month):
        start = date(y, m, 1)
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        end = min(nxt - timedelta(days=1), today)
        r = periode_rapport(conn, start.isoformat(), end.isoformat())
        weeks = ((end - start).days + 1) / 7
        t, sh, st = r["traening"], r["sundhed"], r["styrke"]
        z = t["intensitet_min"]
        ztot = sum(z.values()) if z else 0
        rows.append({
            "maaned": f"{y}-{m:02d}",
            "dage_med_data": r["dage_med_data"],
            **({"igangvaerende": True} if nxt > today else {}),
            "sovn_t": sh["sovn_t"], "sovn_score": sh["sovn_score"], "hrv": sh["hrv"],
            "hvilepuls": sh["hvilepuls"], "stress": sh["stress"], "readiness": sh["readiness"],
            "skridt": sh["skridt"], "vo2max": sh["vo2max"], "vaegt": sh["vaegt"],
            "pas_pr_uge": round(t["pas"] / weeks, 1),
            "timer_pr_uge": round(t["timer"] / weeks, 1),
            "belastning_pr_uge": round(t["belastning"] / weeks),
            "andel_lav_intensitet_pct": round(100 * z["lav"] / ztot) if ztot else None,
            "sport": [f"{s_['navn']} {s_['timer']:.1f} t" for s_ in t["sport"][:3]],
            # Før Hevy findes ingen sæt; 0 ville ligne en måned uden styrke
            "styrke_arbejdssaet_pr_uge": (
                round(st["haarde_saet"] / weeks, 1)
                if hevy_first and end.isoformat() >= hevy_first else None
            ),
        })
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    full = [r for r in rows if not r.get("igangvaerende") and r["dage_med_data"] >= 20]
    keys = ("sovn_t", "hrv", "hvilepuls", "vo2max", "vaegt", "skridt",
            "timer_pr_uge", "belastning_pr_uge")

    def avg(rs, k):
        vals = [r[k] for r in rs if r[k] is not None]
        return round(statistics.mean(vals), 1) if vals else None

    udvikling = None
    if len(full) >= 6:
        early, late = full[:3], full[-3:]
        udvikling = {
            "tidlig": f"{early[0]['maaned']}–{early[-1]['maaned']}",
            "seneste": f"{late[0]['maaned']}–{late[-1]['maaned']}",
            **{k: {"tidlig": avg(early, k), "seneste": avg(late, k)} for k in keys},
        }

    forbehold = []
    z3 = conn.execute(
        f"""SELECT MIN(z.low_bpm) lo, MAX(z.low_bpm) hi FROM activity_zones z
            JOIN activities a ON a.activity_id = z.activity_id
            WHERE z.zone = 3 AND z.low_bpm IS NOT NULL AND a.date >= ?
              AND a.sport NOT IN {_NO_ZONE_SPORTS}""",
        (rows[0]["maaned"] + "-01" if rows else first,),
    ).fetchone()
    if z3["lo"] is not None and z3["hi"] - z3["lo"] >= 3:
        forbehold.append(
            f"Pulszonegrænserne er ændret undervejs: zone 3 har startet mellem "
            f"{round(z3['lo'])} og {round(z3['hi'])} bpm. Andel lav intensitet er derfor "
            "ikke direkte sammenlignelig mellem måneder med forskellige grænser — lavere "
            "grænser flytter tid fra lav op i moderat."
        )
    thin = [r["maaned"] for r in rows if r["dage_med_data"] < 20 and not r.get("igangvaerende")]
    if thin:
        forbehold.append("Få dage med målinger (under 20) i: " + ", ".join(thin) + ".")
    no_hrv = [r["maaned"] for r in rows if r["hrv"] is None and r["dage_med_data"]]
    if no_hrv:
        forbehold.append("Ingen HRV-målinger i: " + ", ".join(no_hrv) + ".")
    return {"maaneder": rows, "udvikling": udvikling, "forbehold": forbehold}


def _last_complete_day(conn: sqlite3.Connection) -> date:
    """Sidste dag belastningsvinduerne må slutte på.

    I dag er ikke slut, og en dag uden sync ligner en hviledag. Vinduerne
    slutter derfor i går, eller på sidste dag med målinger hvis den ligger
    længere tilbage.
    """
    yesterday = date.today() - timedelta(days=1)
    row = conn.execute(f"SELECT MAX(date) d FROM daily WHERE {_MEASURED}").fetchone()
    if row and row["d"]:
        return min(yesterday, date.fromisoformat(row["d"]))
    return yesterday


def _history_days(conn: sqlite3.Connection, end: date) -> int:
    row = conn.execute(
        f"SELECT MIN(d) d FROM (SELECT MIN(date) d FROM activities "
        f"UNION ALL SELECT MIN(date) FROM daily WHERE {_MEASURED})"
    ).fetchone()
    if not row or not row["d"]:
        return 0
    return (end - date.fromisoformat(row["d"])).days + 1


def training_load(conn: sqlite3.Connection, weeks: int = 8) -> dict:
    ath = athlete(conn)
    end = _last_complete_day(conn)
    stale_days = (date.today() - end).days - 1  # 0 når vinduet slutter i går
    # ACWR skal altid have 28 dage, uanset hvor mange uger der vises
    span = max(weeks * 7, 28)
    ctx = load_context(conn, ath)
    loads = daily_loads(conn, end - timedelta(days=span - 1), end, ath, ctx)
    values = list(loads.values())
    history = _history_days(conn, end)

    acute = sum(values[-7:])
    chronic_weekly = sum(values[-28:]) / 4
    week7 = values[-7:]
    sd = statistics.pstdev(week7)
    monotony = round(statistics.mean(week7) / sd, 2) if sd > 0 else None
    strain = round(acute * monotony, 0) if monotony else None

    if stale_days > 2:
        acwr = monotony = strain = None
        fortolkning = (
            f"ikke beregnet: nyeste data er fra {end.isoformat()}, {stale_days} dage "
            "før i går. Manglende dage ville ligne hviledage. Kør sync først."
        )
    elif history < 28:
        acwr = None
        fortolkning = f"for lidt historik til at beregne ({history} dage, kræver 28)"
    else:
        acwr = round(acute / chronic_weekly, 2) if chronic_weekly else None
        fortolkning = _acwr_band(acwr)

    # Ugevis tilbage i tiden, nyeste uge først
    weekly = []
    for w in range(weeks):
        chunk = values[len(values) - (w + 1) * 7 : len(values) - w * 7]
        if chunk:
            weekly.append(
                {
                    "uge_siden": w,
                    "load": round(sum(chunk)),
                    "træningsdage": sum(1 for v in chunk if v > 0),
                }
            )

    today_load = sum(
        session_load(r, ath, ctx) for r in conn.execute(
            "SELECT * FROM activities WHERE date = ?", (date.today().isoformat(),)
        )
    )
    since_28 = (end - timedelta(days=27)).isoformat()
    sources: dict[str, int] = {"hevy": 0, "puls": 0, "ingen": 0}
    unloaded = []
    for r in conn.execute(
        "SELECT * FROM activities WHERE date BETWEEN ? AND ?", (since_28, end.isoformat())
    ):
        kilde = session_load_detail(r, ath, ctx)[1]
        sources[kilde] += 1
        if kilde == "ingen":
            unloaded.append(f"{r['date']} {r['sport']} ({round((r['duration_s'] or 0) / 60)} min)")
    by_sport = conn.execute(
        """SELECT sport, COUNT(*) n, ROUND(SUM(duration_s)/3600.0, 1) timer
           FROM activities WHERE date BETWEEN ? AND ? GROUP BY sport ORDER BY timer DESC""",
        (since_28, end.isoformat()),
    ).fetchall()

    return {
        "beregnet_til_og_med": end.isoformat(),
        "akut_7d": round(acute),
        "kronisk_uge_snit_28d": (
            round(chronic_weekly) if history >= 28 and stale_days <= 2 else None
        ),
        "acwr": acwr,
        "acwr_fortolkning": fortolkning,
        "monotoni_7d": monotony,
        "strain_7d": strain,
        "i_dag_indtil_nu": round(today_load),
        "ugentligt": weekly,
        "fordeling_28d": [dict(r) for r in by_sport],
        "belastningskilde_28d": sources,
        **({"pas_uden_belastning_28d": unloaded} if unloaded else {}),
        "styrke_ugentligt": strength_weeks(conn, end, min(weeks, 4)),
        "intensitetsfordeling_28d": intensity_split(conn, ath, 28),
        "dage_uden_data_28d": _gap_days(conn, 28),
        "datafriskhed": freshness(conn),
        "beregnet_med": {
            "metode": (
                "Styrkepas med Hevy-data: arbejdssæt plus RPE-tillæg, kalibreret til "
                "TRIMP på dine egne pas. Øvrige pas: Banister-TRIMP ud fra puls."
            ),
            "hevy_trimp_pr_point": (
                round(ctx.trimp_per_point, 2) if ctx.trimp_per_point else None
            ),
            "kalibreret_på_pas": ctx.calibration_sessions,
            "makspuls": ath.hr_max, "hvilepuls": ath.hr_rest, "kilder": ath.sources,
        },
        "note": (
            "Vinduerne slutter på sidste afsluttede dag; i dag står for sig. "
            "Pas uden både puls og Hevy-sæt tæller som 0 og står i "
            "pas_uden_belastning_28d. ACWR er et groft pejlemærke, ikke en "
            "valideret skadesforudsigelse — litteraturen er omdiskuteret. Brug "
            "det til at se retning, ikke som facit."
        ),
    }


def _acwr_band(acwr: float | None) -> str:
    if acwr is None:
        return "for lidt historik til at beregne (kræver 28 dage)"
    if acwr < 0.8:
        return "lav — du er i nedtrapning eller har mistet volumen"
    if acwr <= 1.3:
        return "stabil progression"
    if acwr <= 1.5:
        return "hurtig opbygning, hold øje med restitutionstallene"
    return "kraftigt spring i belastning"


# --------------------------------------------------------------------------
# Restitution
# --------------------------------------------------------------------------

def _series(conn: sqlite3.Connection, column: str, days: int, skip: int = 0) -> list[float]:
    """Værdier fra de seneste `days` dage inkl. i dag, minus de nyeste `skip`."""
    today = date.today()
    first = (today - timedelta(days=days - 1)).isoformat()
    last = (today - timedelta(days=skip)).isoformat()
    rows = conn.execute(
        f"SELECT {column} v FROM daily WHERE date >= ? AND date <= ? AND {column} IS NOT NULL "
        f"ORDER BY date",
        (first, last),
    ).fetchall()
    return [float(r["v"]) for r in rows]


def _baseline(conn: sqlite3.Connection, column: str) -> dict:
    """Snit af de seneste 7 dage holdt op mod de 53 dage før, udtrykt i
    standardafvigelser. Det er sådan man læser HRV og hvilepuls meningsfuldt.

    De aktuelle dage er ikke med i grundniveauet, ellers ville en ændring
    trække sin egen målestok med sig. Under 3 målte dage er "aktuel" for
    tyndt til at sammenligne.
    """
    recent = _series(conn, column, 7)
    base = _series(conn, column, 60, skip=7)
    out = {
        "aktuel": round(statistics.mean(recent), 1) if recent else None,
        "aktuelle_datapunkter": len(recent),
        "baseline": None,
        "afvigelse_sd": None,
        "baseline_datapunkter": len(base),
    }
    if len(recent) < 3 or len(base) < 14:
        return out
    mu = statistics.mean(base)
    sd = statistics.pstdev(base)
    out["baseline"] = round(mu, 1)
    out["afvigelse_sd"] = round((statistics.mean(recent) - mu) / sd, 2) if sd > 0 else None
    return out


def recovery(conn: sqlite3.Connection, days: int = 14) -> dict:
    # `days` dage inkl. i dag, så "14 nætter" også er 14 og ikke 15
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    rows = conn.execute(
        "SELECT * FROM daily WHERE date >= ? ORDER BY date DESC", (since,)
    ).fetchall()

    sleep_hours = [r["sleep_s"] / 3600 for r in rows if r["sleep_s"]]
    latest = rows[0] if rows else None

    return {
        "hrv": _baseline(conn, "hrv_last_night"),
        "hvilepuls": _baseline(conn, "resting_hr"),
        "søvn_timer": {
            "snit": round(statistics.mean(sleep_hours), 1) if sleep_hours else None,
            "mindst": round(min(sleep_hours), 1) if sleep_hours else None,
            "nætter_under_7t": sum(1 for h in sleep_hours if h < 7),
            "målte_nætter": len(sleep_hours),
        },
        "seneste_døgn": {
            "dato": latest["date"] if latest else None,
            "hrv_status": latest["hrv_status"] if latest else None,
            "søvnscore": latest["sleep_score"] if latest else None,
            "training_readiness": latest["training_readiness"] if latest else None,
            "body_battery_top": latest["bb_high"] if latest else None,
            "stress_snit": latest["stress_avg"] if latest else None,
        },
        "flag": _recovery_flags(conn),
        "datafriskhed": freshness(conn),
    }


def _recovery_flags(conn: sqlite3.Connection) -> list[str]:
    flags = []
    hrv = _baseline(conn, "hrv_last_night")
    rhr = _baseline(conn, "resting_hr")
    if hrv["aktuelle_datapunkter"] < 3 and rhr["aktuelle_datapunkter"] < 3:
        # En tom liste ville ellers blive læst som "alt ser fint ud"
        flags.append(
            "for få HRV- og hvilepulsmålinger de seneste 7 dage til at vurdere "
            "restitution — sig det, og lad være med at konkludere at alt er fint"
        )
    if hrv.get("afvigelse_sd") is not None and hrv["afvigelse_sd"] < -1:
        flags.append("HRV ligger mere end 1 SD under dit grundniveau")
    if rhr.get("afvigelse_sd") is not None and rhr["afvigelse_sd"] > 1:
        flags.append("hvilepuls ligger mere end 1 SD over dit grundniveau")
    sleep = _series(conn, "sleep_s", 7)
    if len(sleep) >= 3 and statistics.mean(sleep) / 3600 < 6.5:
        flags.append("søvn under 6,5 timer i snit den seneste uge")
    return flags


# Garmins egen skala for training readiness
def readiness_ord(v: float | None) -> str | None:
    if v is None:
        return None
    return ("topform" if v >= 95 else "høj" if v >= 75 else "moderat" if v >= 50
            else "lav" if v >= 25 else "meget lav")


DAGENS_RAAD = {
    "rolig": ("Rolig dag",
              "Ingen hårde pas i dag. En gåtur eller let bevægelse er fint, og de frie timer kan gå til selvstudie.",
              "plads til selvstudie eller en gåtur"),
    "moderat": ("Moderat dag",
                "Et roligt pas i zone 2 eller teknik er fint. Spar de tunge sæt til en dag med bedre restitution.",
                "plads til et roligt pas eller selvstudie"),
    "klar": ("Klar til træning",
             "Restitutionen ser god ud, så det er en god dag til et hårdt pas eller tunge løft.",
             "plads til træning eller selvstudie"),
}


def dagens_raad(conn: sqlite3.Connection) -> dict:
    """Dagens råd om træning: rolig, moderat eller klar, med grundene.

    Restitution går forud for hårde pas. Ét tydeligt tegn på manglende restitution giver
    en rolig dag: readiness under 50 (lav på Garmins skala), HRV mere end 1 SD under eller
    hvilepuls mere end 1 SD over grundniveauet (de samme grænser som flagene), eller under
    5 timers søvn i nat. Moderat readiness (50-74) eller under 6,5 timers søvn i snit den
    seneste uge giver en moderat dag. Kun readiness 75+ uden de tegn er klar.
    Uden dagens måling gives intet råd; det siges i stedet for at gætte."""
    today = date.today().isoformat()
    row = conn.execute(
        "SELECT training_readiness, sleep_s FROM daily WHERE date = ?", (today,)
    ).fetchone()
    readiness = row["training_readiness"] if row else None
    nat_t = row["sleep_s"] / 3600 if row and row["sleep_s"] else None
    hrv = _baseline(conn, "hrv_last_night").get("afvigelse_sd")
    rhr = _baseline(conn, "resting_hr").get("afvigelse_sd")
    uge = _series(conn, "sleep_s", 7)
    uge_t = statistics.mean(uge) / 3600 if len(uge) >= 3 else None

    if readiness is None:
        return {"dato": today, "niveau": None, "titel": None, "tekst": None, "fri": None,
                "grunde": ["ingen readiness fra Garmin for i dag endnu"]}

    rolig, moderat = [], []
    if readiness < 50:
        rolig.append(f"readiness {readiness:.0f} ({readiness_ord(readiness)})")
    elif readiness < 75:
        moderat.append(f"readiness {readiness:.0f} ({readiness_ord(readiness)})")
    if nat_t is not None and nat_t < 5:
        t, m = divmod(round(nat_t * 60), 60)
        rolig.append(f"{t} t {m} min søvn i nat")
    if hrv is not None and hrv < -1:
        rolig.append("HRV mere end 1 SD under dit grundniveau")
    if rhr is not None and rhr > 1:
        rolig.append("hvilepuls mere end 1 SD over dit grundniveau")
    if uge_t is not None and uge_t < 6.5:
        moderat.append("under 6,5 timers søvn i snit den seneste uge")

    niveau = "rolig" if rolig else "moderat" if moderat else "klar"
    grunde = (rolig + moderat) if rolig or moderat else [
        f"readiness {readiness:.0f} ({readiness_ord(readiness)})", "HRV, hvilepuls og søvn ligger normalt"]
    titel, tekst, fri = DAGENS_RAAD[niveau]
    return {"dato": today, "niveau": niveau, "titel": titel, "tekst": tekst, "fri": fri, "grunde": grunde}


# --------------------------------------------------------------------------
# Kropssammensætning og form
# --------------------------------------------------------------------------

def body_trend(conn: sqlite3.Connection, days: int = 90) -> dict:
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT date, weight_kg FROM daily WHERE date >= ? AND weight_kg IS NOT NULL ORDER BY date",
        (since,),
    ).fetchall()
    weights = [r["weight_kg"] for r in rows]
    trend = None
    if len(weights) >= 6:
        half = len(weights) // 2
        trend = round(statistics.mean(weights[half:]) - statistics.mean(weights[:half]), 2)

    vo2 = _series(conn, "vo2max", days)
    return {
        "vejninger": len(weights),
        "seneste_kg": weights[-1] if weights else None,
        "ændring_kg_over_perioden": trend,
        "vo2max_seneste": vo2[-1] if vo2 else None,
        "vo2max_ændring": round(vo2[-1] - vo2[0], 1) if len(vo2) >= 2 else None,
    }


# --------------------------------------------------------------------------
# Kalender
# --------------------------------------------------------------------------

def schedule(conn: sqlite3.Connection, days_ahead: int = 7) -> dict:
    """Kalenderen dag for dag: begivenhederne med tid og titel, optaget tid og
    frie vinduer.

    Heldagsbegivenheder kommer med i listen, fordi de ofte er dem der
    forklarer et søvnfald (en fest, en rejse), men de tæller ikke med i
    optaget tid, første start eller sidste slut.
    """
    now = datetime.now().replace(second=0, microsecond=0)
    today = now.date()
    end = today + timedelta(days=days_ahead)
    # Heldagsbegivenheder kan være startet før i dag og strække sig ind i perioden
    rows = conn.execute(
        """SELECT * FROM calendar_events
           WHERE start_local < ?
             AND (start_local >= ? OR (all_day = 1 AND end_local > ?))
           ORDER BY start_local""",
        (end.isoformat(), today.isoformat(), today.isoformat()),
    ).fetchall()

    days = []
    for i in range(days_ahead):
        d = today + timedelta(days=i)
        iso = d.isoformat()
        # Slutdatoen i iCal er eksklusiv: en fest den 26. slutter den 27. kl. 00
        all_day = [
            r for r in rows
            if r["all_day"] and (
                r["start_local"][:10] == iso
                or r["start_local"][:10] < iso < (r["end_local"] or "")[:10]
            )
        ]
        timed = [r for r in rows if not r["all_day"] and r["start_local"][:10] == iso]

        blocks = []
        program = [_punkt("heldag", r) for r in all_day]
        for e in timed:
            try:
                s = datetime.fromisoformat(e["start_local"])
                t = datetime.fromisoformat(e["end_local"]) if e["end_local"] else s
            except (TypeError, ValueError):
                continue
            blocks.append((s, t))
            program.append(_punkt(f"{s.strftime('%H:%M')}–{t.strftime('%H:%M')}", e))
        days.append(
            {
                "dato": iso,
                "ugedag": ["man", "tir", "ons", "tor", "fre", "lør", "søn"][d.weekday()],
                "begivenheder": len(program),
                "program": program,
                "optaget_timer": round(_busy_minutes(blocks) / 60, 1),
                "første_møde": min(b[0] for b in blocks).strftime("%H:%M") if blocks else None,
                "sidste_slut": max(b[1] for b in blocks).strftime("%H:%M") if blocks else None,
                "frie_vinduer": _free_windows(
                    blocks, d, not_before=now if d == today else None
                ),
            }
        )
    return {
        "dage": days,
        "kilder_konfigureret": len(CONFIG.ics_sources),
        "note": (
            "Frie vinduer er tid uden tidsfæstede begivenheder mellem kl. 6 og 22; "
            "for i dag regnes kun fra nu. Heldagsbegivenheder (rejser, fester) "
            "blokerer ikke vinduerne — vurdér selv om dagen reelt er fri."
        ),
    }


def _punkt(tid: str, r: sqlite3.Row) -> dict:
    """Et punkt i dagens program; undervisning fra skemaet får de felter, kalenderhentningen gemte, med under "fag"."""
    punkt = {"tid": tid, "titel": short_title(r["summary"])}
    if r["fag_navn"]:
        punkt["fag"] = {k: r[f"fag_{k}"] for k in FELTER}
    return punkt


def _busy_minutes(blocks) -> float:
    """Optaget tid som foreningsmængde, så overlappende begivenheder ikke
    tælles dobbelt."""
    total, cursor = 0.0, None
    for s, t in sorted(blocks):
        if cursor is None or s > cursor:
            total += max(0.0, (t - s).total_seconds() / 60)
            cursor = t
        elif t > cursor:
            total += (t - cursor).total_seconds() / 60
            cursor = t
    return total


def _free_windows(blocks, d: date, day_start=6, day_end=22, not_before=None) -> list[str]:
    """Finder sammenhængende frie lunser mellem kl. 6 og 22, og ikke før
    `not_before` (bruges for i dag, så passeret tid ikke foreslås)."""
    start = datetime.combine(d, datetime.min.time()).replace(hour=day_start)
    end = datetime.combine(d, datetime.min.time()).replace(hour=day_end)
    if not_before is not None:
        start = max(start, not_before)

    free, cursor = [], start
    for s, t in sorted(blocks):
        if s > cursor:
            free.append((cursor, min(s, end)))
        cursor = max(cursor, t)
    if cursor < end:
        free.append((cursor, end))

    return [
        f"{a.strftime('%H:%M')}–{b.strftime('%H:%M')}"
        for a, b in free
        if (b - a).total_seconds() / 60 >= CONFIG.min_training_window_min
    ]
