"""Kroppen i tal: alle Garmins døgn- og nattemålinger på én side, i stil med garmin-grafana.

Alt, siden viser, regnes her: døgnene som flade rækker, snit/min/maks pr. mål, ugens snit og ugen før, månedens
heatmap (hvert mål holdt op mod sit eget spænd i de 30 dage), den seneste nats faser og kurver og
aktiviteternes pulszoner. Tallene kommer fra `daily.raw` (Garmins stats, sleep og hrv) og `activities`.
En dag uden måling står med null, aldrig 0. GPS-spor og puls hen over dagen gemmes ikke, så de er ikke med.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import CONFIG

# Felterne fra Garmins stats pr. døgn: (vores navn, Garmins navn, omregning)
_T = lambda s: None if s is None else round(s / 3600, 2)  # noqa: E731
_STATS = (
    ("skridt", "totalSteps", None), ("skridtmaal", "dailyStepGoal", None),
    ("distance_km", "totalDistanceMeters", lambda m: round(m / 1000, 2)),
    ("kcal_hvile", "bmrKilocalories", None), ("kcal_aktiv", "activeKilocalories", None),
    ("etager", "floorsAscended", lambda x: round(x, 1)),
    ("puls_min", "minHeartRate", None), ("puls_maks", "maxHeartRate", None),
    ("stress_snit", "averageStressLevel", None),
    ("stress_hvile_t", "restStressDuration", _T), ("stress_lav_t", "lowStressDuration", _T),
    ("stress_middel_t", "mediumStressDuration", _T), ("stress_hoej_t", "highStressDuration", _T),
    ("stress_aktivitet_t", "activityStressDuration", _T), ("stress_ukendt_t", "uncategorizedStressDuration", _T),
    ("akt_soevn_t", "sleepingSeconds", _T), ("akt_stille_t", "sedentarySeconds", _T),
    ("akt_aktiv_t", "activeSeconds", _T), ("akt_meget_t", "highlyActiveSeconds", _T),
    ("int_moderat_min", "moderateIntensityMinutes", None), ("int_hoej_min", "vigorousIntensityMinutes", None),
    ("bb_top", "bodyBatteryHighestValue", None), ("bb_bund", "bodyBatteryLowestValue", None),
    ("bb_opladet", "bodyBatteryChargedValue", None),
    ("bb_draenet", "bodyBatteryDrainedValue", lambda x: -x),  # nedad i grafen, så den står negativ
    ("spo2_snit", "averageSpo2", None), ("spo2_laveste", "lowestSpo2", None),
    ("aanding_vaagen", "avgWakingRespirationValue", None),
)
# De mål, der får snit/min/maks. Søvnvinduet står som timer efter kl. 18 aftenen før.
_RESUME = (
    "skridt", "distance_km", "kcal_hvile", "kcal_aktiv", "etager", "hvilepuls", "puls_min", "puls_maks",
    "stress_snit", "stress_hvile_t", "stress_lav_t", "stress_middel_t", "stress_hoej_t", "stress_aktivitet_t",
    "akt_soevn_t", "akt_stille_t", "akt_aktiv_t", "akt_meget_t", "int_moderat_min", "int_hoej_min",
    "bb_top", "bb_bund", "bb_opladet", "bb_draenet", "spo2_snit", "aanding_vaagen", "aanding_soevn",
    "hrv", "soevn_t", "dyb_t", "let_t", "rem_t", "vaagen_t", "soevnscore", "soevn_stress", "readiness",
    "seng_t", "op_t", "belastning",
)
# Ugen i overblik: de syv seneste døgn, deres snit og snittet for de syv døgn før dem
_UGE = ("distance_km", "skridt", "soevn_t", "stress_hoej_t", "akt_meget_t", "hvilepuls", "spo2_snit", "bb_opladet")
# Måneden i overblik: (felt, navn, enhed, decimaler)
_MAANED = (
    ("traening_min", "Træning", "min", 0),
    ("hvilepuls", "Hvilepuls", "bpm", 0), ("stress_hoej_t", "Høj stress", "t", 1), ("akt_aktiv_t", "Aktiv tid", "t", 1),
    ("bb_top", "Body battery top", "", 0), ("skridt", "Skridt", "", 0), ("spo2_snit", "SpO2", "%", 0),
    ("soevnscore", "Søvnscore", "", 0), ("soevn_t", "Søvn", "t", 1), ("hrv", "HRV", "ms", 0),
)
_DOEGNTAL = {navn for navn, _, _ in _STATS} | {"belastning"}
FASER = {0: "dyb", 1: "let", 2: "rem", 3: "vaagen"}
# Garmins HRV-status på dansk; NONE er nætter, hvor Garmin ikke har sat en status (fx mens grundlinjen bygges)
HRV_STATUS = {"BALANCED": "balanceret", "UNBALANCED": "ubalanceret", "LOW": "lav", "POOR": "dårlig", "NONE": "ingen status"}


def hrv_status(s: str | None) -> str | None:
    """Garmins HRV-status oversat; en ukendt status står, som Garmin skrev den, med små bogstaver."""
    return None if not s else HRV_STATUS.get(s.upper(), s.lower())


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _resume(vals: list) -> dict:
    v = [x for x in vals if x is not None]
    if not v:
        return {"snit": None, "min": None, "maks": None, "n": 0}
    return {"snit": round(sum(v) / len(v), 2), "min": min(v), "maks": max(v), "n": len(v)}


def _efter18(dt: datetime, dag: date) -> float:
    """Timer efter kl. 18 aftenen før `dag` (Garmins døgn er den dag, du vågnede)."""
    nul = datetime.combine(dag - timedelta(days=1), datetime.min.time()).replace(hour=18, tzinfo=dt.tzinfo)
    return round((dt - nul).total_seconds() / 3600, 2)


def _doegn(r: sqlite3.Row, tz: ZoneInfo) -> dict:
    try:
        raw = json.loads(r["raw"] or "{}")
    except ValueError:
        raw = {}
    stats = raw.get("stats") or {}
    sl = (raw.get("sleep") or {}).get("dailySleepDTO") or {}
    d = {"dato": r["date"]}
    # Uden data fra uret i døgnet er alle stats-felter tomme, også dem Garmin sætter til 0
    har = bool(stats.get("includesWellnessData"))
    for navn, felt, f in _STATS:
        x = _num(stats.get(felt)) if har else None
        d[navn] = None if x is None else (f(x) if f else x)
    seng = op = None
    if _num(sl.get("sleepStartTimestampGMT")) and _num(sl.get("sleepEndTimestampGMT")):
        dag = date.fromisoformat(r["date"])
        start = datetime.fromtimestamp(sl["sleepStartTimestampGMT"] / 1000, timezone.utc).astimezone(tz)
        slut = datetime.fromtimestamp(sl["sleepEndTimestampGMT"] / 1000, timezone.utc).astimezone(tz)
        seng, op = _efter18(start, dag), _efter18(slut, dag)
        d["seng_kl"], d["op_kl"] = start.strftime("%H:%M"), slut.strftime("%H:%M")
    soevn = [_T(r[k]) for k in ("deep_s", "light_s", "rem_s", "awake_s")]
    d |= {
        "hvilepuls": r["resting_hr"], "hrv": r["hrv_last_night"], "hrv_status": hrv_status(r["hrv_status"]),
        "soevn_t": _T(r["sleep_s"]), "dyb_t": soevn[0], "let_t": soevn[1], "rem_t": soevn[2], "vaagen_t": soevn[3],
        "soevnscore": r["sleep_score"], "soevn_stress": _num(sl.get("avgSleepStress")),
        "aanding_soevn": _num(sl.get("averageRespirationValue")), "readiness": r["training_readiness"],
        "seng_t": seng, "op_t": op,
    }
    return d


def _kl(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _nat(r: sqlite3.Row, tz: ZoneInfo) -> dict | None:
    """Natten, der sluttede på døgnets dato: faserne som tidsrum og nattens kurver, alt i minutter efter kl. 18."""
    try:
        s = json.loads(r["raw"] or "{}").get("sleep") or {}
    except ValueError:
        return None
    levels = s.get("sleepLevels") or []
    if not levels:
        return None
    dag = date.fromisoformat(r["date"])
    nul = datetime.combine(dag - timedelta(days=1), datetime.min.time()).replace(hour=18, tzinfo=tz)
    gmt_str = lambda x: datetime.fromisoformat(x.split(".")[0]).replace(tzinfo=timezone.utc).astimezone(tz)  # noqa: E731
    gmt_ms = lambda x: datetime.fromtimestamp(x / 1000, timezone.utc).astimezone(tz)  # noqa: E731
    minut = lambda dt: round((dt - nul).total_seconds() / 60, 1)  # noqa: E731
    faser = []
    for lv in levels:
        a, b = gmt_str(lv["startGMT"]), gmt_str(lv["endGMT"])
        faser.append({"fra": minut(a), "til": minut(b), "fra_kl": _kl(a), "til_kl": _kl(b),
                      "fase": FASER.get(int(lv.get("activityLevel", -1)), "ukendt"),
                      "min": round((b - a).total_seconds() / 60)})

    def kurve(liste, tid, vaerdi, tidfn):
        ud = []
        for p in liste or []:
            v, t = _num(p.get(vaerdi)), p.get(tid)
            if v is None or t is None or v < 0:  # Garmin skriver -1/-2 for ingen måling
                continue
            ud.append([minut(tidfn(t)), v])  # [minutter efter kl. 18, værdi]
        return {"punkter": ud, **_resume([v for _, v in ud])}

    tid_i_fase = {f: round(sum(x["min"] for x in faser if x["fase"] == f)) for f in FASER.values()}
    return {
        "dato": r["date"], "faser": faser, "min_i_fase": tid_i_fase,
        "fra": faser[0]["fra"], "til": faser[-1]["til"],
        "kurver": {
            "puls": kurve(s.get("sleepHeartRate"), "startGMT", "value", gmt_ms),
            "hrv": kurve(s.get("hrvData"), "startGMT", "value", gmt_ms),
            "spo2": kurve(s.get("wellnessEpochSPO2DataDTOList"), "epochTimestamp", "spo2Reading", gmt_str),
            "aanding": kurve(s.get("wellnessEpochRespirationDataDTOList"), "startTimeGMT", "respirationValue", gmt_ms),
            "stress": kurve(s.get("sleepStress"), "startGMT", "value", gmt_ms),
            "bb": kurve(s.get("sleepBodyBattery"), "startGMT", "value", gmt_ms),
        },
    }


def _aktiviteter(conn: sqlite3.Connection, fra: str, til: str) -> dict:
    zoner = {}
    for z in conn.execute("SELECT activity_id, zone, seconds FROM activity_zones WHERE zone BETWEEN 1 AND 5"):
        zoner.setdefault(z["activity_id"], [0.0] * 5)[z["zone"] - 1] = z["seconds"] or 0
    pas = []
    for a in conn.execute("SELECT * FROM activities WHERE date BETWEEN ? AND ? ORDER BY start_local", (fra, til)):
        z = zoner.get(a["activity_id"])
        pas.append({
            "dato": a["date"], "start": a["start_local"][11:16], "navn": a["name"], "sport": a["sport"],
            "varighed_min": None if a["duration_s"] is None else round(a["duration_s"] / 60),
            "distance_km": round(a["distance_m"] / 1000, 2) if a["distance_m"] else None,
            "snitpuls": a["avg_hr"], "makspuls": a["max_hr"],
            "puls_forskel": None if a["avg_hr"] is None or a["max_hr"] is None else round(a["max_hr"] - a["avg_hr"]),
            "kcal": a["calories"], "zoner_min": None if z is None else [round(s / 60, 1) for s in z],
        })
    samlet = [round(sum((p["zoner_min"] or [0] * 5)[i] for p in pas), 1) for i in range(5)]
    i_alt = sum(samlet)
    return {"pas": pas, "zoner_min_i_alt": samlet,
            "zoner_procent": [round(100 * m / i_alt, 1) if i_alt else None for m in samlet]}


SPORT = {
    "running": "Løb", "treadmill_running": "Løb på bånd", "trail_running": "Trailløb", "walking": "Gåtur",
    "hiking": "Vandretur", "strength_training": "Styrke", "indoor_rowing": "Romaskine", "lap_swimming": "Svømning i bassin",
    "open_water_swimming": "Svømning i åbent vand", "road_biking": "Landevejscykling", "cycling": "Cykling",
    "e_bike_fitness": "Elcykel", "indoor_cycling": "Indendørs cykling", "bouldering": "Bouldering",
    "indoor_climbing": "Indendørs klatring", "golf": "Golf", "volleyball": "Volleyball", "paddelball": "Padel",
    "yoga": "Yoga", "cardio": "Kondition", "hiit": "HIIT",
}
# Sportsgrenene i grupper til kalenderens farvede prikker: få nok til, at farverne kan skelnes
GRUPPER = {
    "styrke": ("strength_training",),
    "loeb": ("running", "treadmill_running", "trail_running", "walking", "hiking"),
    "kondition": ("indoor_rowing", "road_biking", "cycling", "e_bike_fitness", "indoor_cycling", "cardio", "hiit"),
    "svoemning": ("lap_swimming", "open_water_swimming"),
    "klatring": ("bouldering", "indoor_climbing"),
}


def gruppe(sport: str | None) -> str:
    return next((g for g, sp in GRUPPER.items() if sport in sp), "andet")


# Garmins træningseffekt, som Connect skriver den på dansk
EFFEKT = {"RECOVERY": "Restitution", "AEROBIC_BASE": "Aerob base", "TEMPO": "Tempo", "LACTATE_THRESHOLD": "Tærskel",
          "THRESHOLD": "Tærskel", "VO2MAX": "VO2max", "ANAEROBIC_CAPACITY": "Anaerob kapacitet", "SPEED": "Fart",
          "SPRINT": "Sprint", "NO_BENEFIT": "Ingen effekt"}


def _tempo(sek_pr: float | None) -> str | None:
    if not sek_pr or sek_pr <= 0 or sek_pr > 3600:
        return None
    m, s = divmod(round(sek_pr), 60)
    return f"{m}:{s:02d}"


def _noegletal(sport: str | None, a: dict) -> list[dict]:
    """Pasets tal, som Garmin har dem, med navn og enhed; kun dem, der findes for netop det pas.
    Tempo regnes her ud fra Garmins snitfart: min/km for løb og gang, pr. 100 m i vand, pr. 500 m på romaskine."""
    n = lambda k: _num(a.get(k))  # noqa: E731
    ud = []

    def tal(navn, v, enhed="", dec=0):
        if v is not None:
            ud.append({"navn": navn, "v": v, "enhed": enhed, "dec": dec})

    def tekst(navn, t):
        if t:
            ud.append({"navn": navn, "tekst": t})

    fart = n("averageSpeed")  # m/s
    sport = sport or ""
    if fart and sport.endswith(("running", "walking", "hiking")):
        tekst("Tempo", f"{_tempo(1000 / fart)} /km" if _tempo(1000 / fart) else None)
    elif fart and "swimming" in sport:
        tekst("Tempo", f"{_tempo(100 / fart)} /100 m" if _tempo(100 / fart) else None)
    elif fart and sport == "indoor_rowing":
        tekst("Tempo", f"{_tempo(500 / fart)} /500 m" if _tempo(500 / fart) else None)
    elif fart and ("biking" in sport or "cycling" in sport):
        tal("Fart", round(fart * 3.6, 1), "km/t", 1)
    bev = n("movingDuration")
    if bev and n("duration") and n("duration") - bev > 60 and sport not in ("strength_training",):
        tal("I bevægelse", round(bev / 60), "min")
    tal("Stigning", n("elevationGain"), "m")
    tal("Kadence", n("averageRunningCadenceInStepsPerMinute") and round(n("averageRunningCadenceInStepsPerMinute")), "spm")
    tal("Skridtlængde", n("avgStrideLength") and round(n("avgStrideLength") / 100, 2), "m", 2)
    tal("Skridt", n("steps"))
    tal("Baner", n("activeLengths"))
    tal("Bassin", n("poolLength") and round(n("poolLength") / 100), "m")
    tal("Swolf", n("averageSwolf"))
    tal("Tag pr. min", n("averageSwimCadenceInStrokesPerMinute"))
    tal("Tag", n("strokes"))
    if sport == "indoor_rowing":
        tal("Højeste tagtal", n("maxStrokeCadence"), "pr. min")
    tal("Sæt", n("activeSets") or n("totalSets"))
    tal("Gentagelser", n("totalReps"))
    tal("Aerob effekt", n("aerobicTrainingEffect") and round(n("aerobicTrainingEffect"), 1), "", 1)
    tal("Anaerob effekt", n("anaerobicTrainingEffect") and round(n("anaerobicTrainingEffect"), 1), "", 1)
    lbl = a.get("trainingEffectLabel")
    if isinstance(lbl, str) and lbl != "UNKNOWN":
        tekst("Primær effekt", EFFEKT.get(lbl, lbl.replace("_", " ").lower().capitalize()))
    tal("Garmins belastning", n("activityTrainingLoad") and round(n("activityTrainingLoad")))
    tal("Body battery", n("differenceBodyBattery"))
    # Intensitetsminutter kun, når passet gav nogen
    tal("Moderat intensitet", n("moderateIntensityMinutes") or None, "min")
    tal("Høj intensitet", n("vigorousIntensityMinutes") or None, "min")
    tal("Væsketab", n("waterEstimated") and round(n("waterEstimated")), "ml")
    tal("VO2max", n("vO2MaxValue"))
    for k, navn in (("fastestSplit_1000", "Hurtigste km"), ("fastestSplit_5000", "Hurtigste 5 km"), ("fastestSplit_100", "Hurtigste 100 m")):
        tekst(navn, _tempo(n(k)) if n(k) and n(k) < 3600 else (f"{round(n(k) / 60)} min" if n(k) else None))
    return ud


def _ovelser(conn: sqlite3.Connection, activity_id: str) -> list[dict]:
    """Hevy-øvelserne i et styrkepas: arbejdssæt (uden opvarmning), det tungeste sæt og volumen (kg × gentagelser)."""
    ud = []
    for w in conn.execute("SELECT workout_id FROM hevy_workouts WHERE activity_id = ?", (activity_id,)):
        rk = {}
        for st in conn.execute("SELECT * FROM hevy_sets WHERE workout_id = ? ORDER BY exercise_index, set_index",
                               (w["workout_id"],)):
            o = rk.setdefault(st["exercise_index"], {"navn": st["exercise"], "saet": [], "opvarmning": 0})
            if st["set_type"] == "warmup":
                o["opvarmning"] += 1
                continue
            o["saet"].append({"kg": st["weight_kg"], "reps": st["reps"], "rpe": st["rpe"],
                              "sek": st["duration_s"], "m": st["distance_m"]})
        for o in rk.values():
            vaegt = [x for x in o["saet"] if x["kg"] is not None and x["reps"]]
            o["volumen_kg"] = round(sum(x["kg"] * x["reps"] for x in vaegt)) if vaegt else None
            o["tungeste"] = max(vaegt, key=lambda x: (x["kg"], x["reps"])) if vaegt else None
            ud.append(o)
    return ud


def _zonetid(z: list[float] | None, varighed_s: float | None) -> dict:
    if z is None:
        return {"min_i_zoner": None, "uden_zone_min": None}
    i_alt = round(sum(z) / 60)
    return {"min_i_zoner": i_alt,
            "uden_zone_min": None if varighed_s is None else max(0, round(varighed_s / 60) - i_alt)}


def _dagens_pas(conn: sqlite3.Connection, dato: str, ath, ctx) -> list[dict]:
    from . import metrics

    zoner = {}
    for z in conn.execute("""SELECT z.activity_id, z.zone, z.seconds FROM activity_zones z JOIN activities a USING (activity_id)
                             WHERE a.date = ? AND z.zone BETWEEN 1 AND 5""", (dato,)):
        zoner.setdefault(z["activity_id"], [0.0] * 5)[z["zone"] - 1] = z["seconds"] or 0
    ud = []
    for a in conn.execute("SELECT * FROM activities WHERE date = ? ORDER BY start_local", (dato,)):
        try:
            raw = json.loads(a["raw"] or "{}")
        except ValueError:
            raw = {}
        start = datetime.fromisoformat(a["start_local"][:19])
        slut = start + timedelta(seconds=a["duration_s"] or 0)
        last, kilde = metrics.session_load_detail(a, ath, ctx) if ath else (None, None)
        z = zoner.get(a["activity_id"])
        ud.append({
            "id": a["activity_id"], "navn": a["name"], "sport": a["sport"], "gruppe": gruppe(a["sport"]), "sport_navn": SPORT.get(a["sport"], (a["sport"] or "").replace("_", " ").capitalize()),
            "start": start.strftime("%H:%M"), "slut": slut.strftime("%H:%M"), "sted": raw.get("locationName"),
            "varighed_min": None if a["duration_s"] is None else round(a["duration_s"] / 60),
            "distance_km": round(a["distance_m"] / 1000, 2) if a["distance_m"] else None,
            "snitpuls": a["avg_hr"], "makspuls": a["max_hr"], "kcal": a["calories"],
            "belastning": None if last is None else round(last), "belastning_kilde": kilde,
            "zoner_min": None if z is None else [round(sek / 60, 1) for sek in z],
            # Tid med puls i zone 1–5 og resten af passet (under zone 1 eller uden pulsmåling), i hele minutter
            **_zonetid(z, a["duration_s"]),
            "noegletal": _noegletal(a["sport"], raw), "ovelser": _ovelser(conn, a["activity_id"]),
            # Start og slut i minutter efter midnat, så siden kan lægge passet ind på døgnets kurver
            "fra_min": start.hour * 60 + start.minute, "til_min": round(start.hour * 60 + start.minute + (a["duration_s"] or 0) / 60),
        })
    return ud


def periode(conn: sqlite3.Connection, fra: date, til: date, today: date | None = None,
            heatmap_dage: int | None = None) -> dict:
    """Døgn for døgn fra `fra` til `til` med snit/min/maks, ugen, månedens heatmap og aktiviteterne.
    Slutter perioden i dag, tæller dagens døgntal ikke med; heatmap_dage begrænser heatmappet til de
    seneste hele døgn (None: hele perioden)."""
    tz = ZoneInfo(CONFIG.timezone)
    today = today or datetime.now(tz).date()
    rows = {r["date"]: r for r in conn.execute("SELECT * FROM daily WHERE date >= ? AND date <= ? ORDER BY date",
                                               (fra.isoformat(), til.isoformat()))}
    # Alle dage i perioden er med, også dem uden række, så graferne viser hullet
    datoer = [(fra + timedelta(days=i)).isoformat() for i in range((til - fra).days + 1)]
    doegn = [_doegn(rows[d], tz) if d in rows else {"dato": d} for d in datoer]
    # Belastning pr. døgn (TRIMP, som i garmin-coach; styrkepas fra Hevy-sæt) og træning pr. døgn: minutter og
    # pas. Et døgn uden pas er 0, ikke tomt.
    from . import metrics

    ath = metrics.athlete(conn)
    last = metrics.daily_loads(conn, fra, til, ath, metrics.load_context(conn, ath))
    for d in doegn:
        d["belastning"] = round(last.get(d["dato"], 0.0), 1)
    traening = {r["date"]: r for r in conn.execute(
        "SELECT date, count(*) AS n, sum(duration_s) AS s FROM activities WHERE date BETWEEN ? AND ? GROUP BY date",
        (fra.isoformat(), til.isoformat()))}
    for d in doegn:
        t = traening.get(d["dato"])
        d["pas"], d["traening_min"] = (t["n"], round((t["s"] or 0) / 60)) if t else (0, 0)
    # I dag er ikke slut, så døgntallene fra uret (skridt, kalorier, stress …) tæller ikke med i snit, min og maks.
    # Nattens tal for i dag er hele og tæller med.
    delvis = til >= today
    hele = doegn[:-1] if delvis else doegn
    resume = {k: _resume([d.get(k) for d in (hele if k in _DOEGNTAL else doegn)]) for k in _RESUME}

    # Ugen: periodens sidste syv hele døgn (og i dag indtil nu øverst); snittet er de syv hele døgn
    uge_snit = {k: _resume([d.get(k) for d in hele[-7:]])["snit"] for k in _UGE}
    uge = doegn[-8:] if delvis else doegn[-7:]
    # Ugen før: de syv døgn før de syv. De hentes for sig, så de er med, selvom perioden (en måned) starter senere.
    sidste = til - timedelta(days=1) if delvis else til
    foer_fra, foer_til = sidste - timedelta(days=13), sidste - timedelta(days=7)
    foer = [_doegn(r, tz) for r in conn.execute("SELECT * FROM daily WHERE date >= ? AND date <= ?",
                                                (foer_fra.isoformat(), foer_til.isoformat()))]
    uge_foer = {k: _resume([d.get(k) for d in foer])["snit"] for k in _UGE}

    maaned = hele[-heatmap_dage:] if heatmap_dage else hele
    raekker = []
    for felt, navn, enhed, dec in _MAANED:
        vals = [d.get(felt) for d in maaned]
        r = _resume(vals)
        spaend = (r["maks"] - r["min"]) if r["n"] else None
        raekker.append({"felt": felt, "navn": navn, "enhed": enhed, "decimaler": dec, "min": r["min"], "maks": r["maks"],
                        "celler": [{"v": v, "niveau": None if v is None else (round((v - r["min"]) / spaend, 3) if spaend else 0.5)}
                                   for v in vals]})
    soevn = [d["soevn_t"] for d in doegn if d.get("soevn_t") is not None]
    # Belastningen uge for uge (mandag–søndag); en uge, perioden kun dækker en del af, står som ikke hel
    uger = {}
    for d in doegn:
        dag = date.fromisoformat(d["dato"])
        u = uger.setdefault((dag - timedelta(days=dag.weekday())).isoformat(), {"belastning": 0.0, "traeningsdage": 0, "dage": 0})
        u["belastning"] += d["belastning"]
        u["traeningsdage"] += d["pas"] > 0
        u["dage"] += 1
    uge_belastning = [{"mandag": m, "uge": date.fromisoformat(m).isocalendar()[1], "belastning": round(u["belastning"]),
                       "traeningsdage": u["traeningsdage"], "hel": u["dage"] == 7 and m <= (today - timedelta(days=7)).isoformat()}
                      for m, u in uger.items()]
    return {
        "fra": fra.isoformat(), "til": til.isoformat(), "i_dag": today.isoformat(), "dage": doegn, "resume": resume,
        "naetter_under_7t": {"under": sum(t < 7 for t in soevn), "maalte": len(soevn)},
        "uge_belastning": uge_belastning,
        "uge": {"dage": list(reversed(uge)), "snit": uge_snit,
                "foer": {"fra": foer_fra.isoformat(), "til": foer_til.isoformat(), "snit": uge_foer}},
        "maaned": {"datoer": [d["dato"] for d in maaned], "raekker": raekker},
        "aktiviteter": _aktiviteter(conn, fra.isoformat(), til.isoformat()),
        "genereret": _nu(),
    }


def _nu() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _historik(conn: sqlite3.Connection) -> dict:
    """Vægt og VO2max måles sjældent, så de står med hele historikken: kun de dage, de er målt."""
    historik = {}
    for felt, kol in (("vaegt", "weight_kg"), ("vo2max", "vo2max")):
        maalt = [{"dato": r["date"], "v": r["v"]} for r in
                 conn.execute(f"SELECT date, {kol} AS v FROM daily WHERE {kol} IS NOT NULL ORDER BY date")]
        historik[felt] = {"maalinger": maalt, **_resume([m["v"] for m in maalt])}
    return historik


def kroppen(conn: sqlite3.Connection, dage: int = 60, today: date | None = None) -> dict:
    """Siden, som den åbner: de seneste `dage` dage, heatmappet over de 30 hele døgn, hele historikken
    for vægt og VO2max og grundniveauet for HRV og hvilepuls fra metrics.recovery (de 53 dage før de
    seneste 7), som kun giver mening for de seneste dage."""
    from . import metrics

    today = today or datetime.now(ZoneInfo(CONFIG.timezone)).date()
    rec = metrics.recovery(conn, days=14)
    grund = {k: {f: (rec.get(k) or {}).get(f) for f in ("aktuel", "baseline", "afvigelse_sd")} for k in ("hrv", "hvilepuls")}
    # Det, der er målt mod i dag: dagens råd, flagene, belastningen nu og intensiteten de seneste 28 dage
    tl = metrics.training_load(conn, weeks=6)
    intens = tl.get("intensitetsfordeling_28d") or {}
    traening = {
        "dagens_raad": metrics.dagens_raad(conn), "flag": rec.get("flag") or [],
        "belastning": {k: tl.get(k) for k in ("beregnet_til_og_med", "akut_7d", "kronisk_uge_snit_28d", "acwr", "acwr_fortolkning")},
        "intensitet": {"tre_baand_procent": intens.get("tre_baand_procent"), "note": intens.get("note"),
                       "samlet_timer": intens.get("samlet_timer"), "kilde": intens.get("kilde")},
    }
    return periode(conn, today - timedelta(days=dage - 1), today, today, heatmap_dage=30) | {
        "periode": {"id": "seneste", "navn": f"Seneste {dage} dage"}, "historik": _historik(conn), "grundniveau": grund,
        "traening": traening}


MAANEDER = ("januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober",
            "november", "december")


def maaned(conn: sqlite3.Connection, md: str, today: date | None = None) -> dict:
    """Én kalendermåned ("ÅÅÅÅ-MM"), til og med i dag, hvis det er den aktuelle."""
    today = today or datetime.now(ZoneInfo(CONFIG.timezone)).date()
    fra = date.fromisoformat(f"{md}-01")
    slut = (fra.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return periode(conn, fra, min(slut, today), today) | {
        "periode": {"id": md, "navn": f"{MAANEDER[fra.month - 1].capitalize()} {fra.year}"}}


def _zonegraenser(conn: sqlite3.Connection) -> list | None:
    r = conn.execute("SELECT value FROM sync_state WHERE key = 'zone_floors'").fetchone()
    try:
        g = json.loads(r["value"]) if r else {}
    except ValueError:
        return None
    return [g[f"zone{i}"] for i in range(1, 6) if f"zone{i}" in g] or None


def doegnet(conn: sqlite3.Connection, dato: str, ath=None, ctx=None) -> dict | None:
    """Ét døgn: puls, stress, body battery og skridt hen over døgnet (minutter efter midnat), døgnets tal og
    natten, der sluttede den dag. None, hvis døgnet ikke findes."""
    tz = ZoneInfo(CONFIG.timezone)
    r = conn.execute("SELECT * FROM daily WHERE date = ?", (dato,)).fetchone()
    if r is None:
        return None
    try:
        raw = json.loads(r["raw"] or "{}")
    except ValueError:
        raw = {}
    midnat = datetime.combine(date.fromisoformat(dato), datetime.min.time()).replace(tzinfo=tz)
    minut = lambda ms: round((datetime.fromtimestamp(ms / 1000, timezone.utc) - midnat).total_seconds() / 60, 1)  # noqa: E731

    def kurve(par):
        # Garmin skriver negative tal for ingen måling (fx -1 uret af, -2 under aktivitet)
        ud = [[minut(t), v] for t, v in par if _num(t) is not None and _num(v) is not None and v >= 0]
        return {"punkter": ud, **_resume([v for _, v in ud])}

    hr = raw.get("heart_rates") or {}
    st = raw.get("all_day_stress") or {}
    skridt = []
    for b in raw.get("steps_day") or []:
        try:
            t = datetime.fromisoformat(b["startGMT"].split(".")[0]).replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            continue
        if _num(b.get("steps")) is not None:
            skridt.append([round((t - midnat).total_seconds() / 60), b["steps"], b.get("primaryActivityLevel")])
    return {
        "dato": dato, "har_kurver": bool(hr or st),
        "puls": kurve((p[0], p[1]) for p in hr.get("heartRateValues") or [] if isinstance(p, list) and len(p) > 1),
        "stress": kurve((p[0], p[1]) for p in st.get("stressValuesArray") or [] if isinstance(p, list) and len(p) > 1),
        "bb": kurve((p[0], p[2]) for p in st.get("bodyBatteryValuesArray") or [] if isinstance(p, list) and len(p) > 2),
        "skridt": skridt, "pulszoner": _zonegraenser(conn),
        "doegn": _doegn(r, tz), "nat": _nat(r, tz), "aktiviteter": _dagens_pas(conn, dato, ath, ctx),
    }


# Hæves, når filernes format ændres, så alle døgn- og månedsfiler skrives igen
FORMAT = 7


def byg_filer(conn: sqlite3.Connection, out: Path, skriv, today: date | None = None) -> dict:
    """Skriver kroppen/dag/<dato>.json og kroppen/maaned/<ÅÅÅÅ-MM>.json, så siden kan gå tilbage i tid, og
    kroppen/index.json med de døgn og måneder, der findes. En fil skrives kun, når dens kilde har ændret sig
    (rækkens længde, aktiviteterne, i dag for den aktuelle måned), så et byg ikke skriver hele historikken."""
    today = today or datetime.now(ZoneInfo(CONFIG.timezone)).date()
    mappe = out / "kroppen"
    (mappe / "dag").mkdir(parents=True, exist_ok=True)
    (mappe / "maaned").mkdir(parents=True, exist_ok=True)
    try:
        gamle = json.loads((mappe / "kilder.json").read_text())
    except (OSError, ValueError):
        gamle = {}
    from . import metrics

    zoner = _zonegraenser(conn)
    ath = metrics.athlete(conn)
    ctx = metrics.load_context(conn, ath)
    # Dagens pas, deres zoner og Hevy-sæt hører med til døgnets kilde
    pas_sig = {r["date"]: f"{r['n']}:{r['b']}:{r['z']}:{r['h']}" for r in conn.execute(
        """SELECT a.date, count(*) AS n, sum(length(a.raw)) AS b,
                  (SELECT count(*) FROM activity_zones z WHERE z.activity_id IN
                     (SELECT activity_id FROM activities WHERE date = a.date)) AS z,
                  (SELECT count(*) FROM hevy_sets s JOIN hevy_workouts w USING (workout_id) WHERE w.activity_id IN
                     (SELECT activity_id FROM activities WHERE date = a.date)) AS h
           FROM activities a GROUP BY a.date""")}
    dage = {r["date"]: f"{FORMAT}:{r['n']}:{zoner}:{pas_sig.get(r['date'])}" for r in
            conn.execute("SELECT date, length(raw) AS n FROM daily WHERE raw IS NOT NULL AND date <= ? ORDER BY date",
                         (today.isoformat(),))}
    akt = {r["md"]: f"{r['n']}:{r['b']}:{r['z']}" for r in conn.execute(
        """SELECT substr(a.date, 1, 7) AS md, count(*) AS n, sum(length(a.raw)) AS b,
                  (SELECT count(*) FROM activity_zones z WHERE z.activity_id IN
                     (SELECT activity_id FROM activities WHERE substr(date, 1, 7) = substr(a.date, 1, 7))) AS z
           FROM activities a GROUP BY md""")}
    maaneder = sorted({d[:7] for d in dage})
    kilder, skrevet = {}, 0
    for d, sig in dage.items():
        kilder[f"dag/{d}"] = sig
        if gamle.get(f"dag/{d}") != sig or not (mappe / "dag" / f"{d}.json").exists():
            skriv(mappe / "dag" / f"{d}.json", json.dumps(doegnet(conn, d, ath, ctx), ensure_ascii=False, separators=(",", ":")))
            skrevet += 1
    for md in maaneder:
        sig = f"{FORMAT}:{ctx.trimp_per_point}:{akt.get(md)}:" + ",".join(v for k, v in dage.items() if k.startswith(md))
        if md == today.isoformat()[:7]:
            sig += f":{today}"
        kilder[f"maaned/{md}"] = sig
        if gamle.get(f"maaned/{md}") != sig or not (mappe / "maaned" / f"{md}.json").exists():
            skriv(mappe / "maaned" / f"{md}.json", json.dumps(maaned(conn, md, today), ensure_ascii=False))
            skrevet += 1
    # Med kurver: de døgn, hvor Garmin har puls eller stress hen over døgnet
    med_kurver = [r["date"] for r in conn.execute(
        "SELECT date FROM daily WHERE date <= ? AND (raw LIKE '%\"heart_rates\": {%' OR raw LIKE '%\"all_day_stress\": {%')",
        (today.isoformat(),))]
    aktivitetsdage = {}
    for r in conn.execute("SELECT date, sport, name FROM activities WHERE date <= ? ORDER BY start_local", (today.isoformat(),)):
        aktivitetsdage.setdefault(r["date"], []).append({"sport": r["sport"], "gruppe": gruppe(r["sport"]),
                                                         "sport_navn": SPORT.get(r["sport"], r["sport"]), "navn": r["name"]})
    skriv(mappe / "index.json", json.dumps({
        "dage": list(dage), "med_kurver": med_kurver,
        # Til kalenderens markører: dagens pas som sport og navn
        "aktiviteter": aktivitetsdage,
        "maaneder": [{"id": md, "navn": f"{MAANEDER[int(md[5:]) - 1].capitalize()} {md[:4]}"} for md in reversed(maaneder)],
        "genereret": _nu()}, ensure_ascii=False))
    skriv(mappe / "kilder.json", json.dumps(kilder))
    return {"dage": len(dage), "maaneder": len(maaneder), "skrevet": skrevet}
