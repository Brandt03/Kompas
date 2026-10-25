"""Ugereviewet til Kompas: forsiden I dag og Form & fokus → Ugereview (https://kompas.localhost/form/uge.html).

Et review gemmes som modellens tekst plus et øjebliksbillede af tallene,
regnet her: rapporten (afvigelser og sammenhænge), ugens dage og pas fra
Garmin og kalenderen for ugen og ugen efter. Kalenderen i garmin-coach
dækker kun ca. 14 dage bagud, så uden øjebliksbilledet ville en gammel uges
kalender forsvinde fra siden.

`eksport` skriver liv.json til Form & fokus-mappen, også de seneste 28 nætter med sengetid og sen skærmtid
(Kroppen i tal). Siderne dér (uge.html,
index.html) bygges af garmin-coach og henter filen ved siden af sig selv. Den skriver
også kalenderen for forrige, denne og næste uge, som den ser ud nu, til
Ugeoverblik i Kompas; reviewets øjebliksbillede er fra mandag og viser ikke
ændringer senere i ugen."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import config, kilder, rapport
from .db import KOLONNER
from .kilder import mandag as mandag_i

TEKST_LISTER = ("udskilte", "sammenhaenge", "kommende_uge", "forbehold")


def _garmin() -> sqlite3.Connection | None:
    if not config.GARMIN_DB.exists():
        return None
    conn = sqlite3.connect(f"{config.GARMIN_DB.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _t(s: float | None) -> float | None:
    return None if s is None else round(s / 3600, 2)


def _dage(g: sqlite3.Connection, m: date) -> list[dict]:
    """Ugens syv dage. En dag uden Garmin-data står med null, ikke 0."""
    rows = {r["date"]: r for r in g.execute(
        """SELECT date, sleep_s, deep_s, rem_s, light_s, awake_s, sleep_score, hrv_last_night,
                  resting_hr, stress_avg, steps, bb_high, training_readiness
           FROM daily WHERE date BETWEEN ? AND ?""",
        [m.isoformat(), (m + timedelta(days=6)).isoformat()])}
    ud = []
    for i in range(7):
        d = (m + timedelta(days=i)).isoformat()
        r = rows.get(d)
        ud.append({"dato": d} | ({} if r is None else {
            "soevn_t": _t(r["sleep_s"]), "dyb_t": _t(r["deep_s"]), "rem_t": _t(r["rem_s"]),
            "let_t": _t(r["light_s"]), "vaagen_t": _t(r["awake_s"]),
            "soevnscore": r["sleep_score"], "hrv": r["hrv_last_night"], "hvilepuls": r["resting_hr"],
            "stress": r["stress_avg"], "skridt": r["steps"], "bb_top": r["bb_high"],
            "readiness": r["training_readiness"],
        }))
    return ud


NAETTER = 28
# Sen skærmtid ↔ søvnscore samme nat: nætter ligner deres naboer, så p-værdien findes ved permutation i blokke af 3
# nætter, og der skal mindst 28 nætter med begge tal til. Nætterne er alle dem, Skærmtid dækker (op til 8 uger).
NAT_SAMMENHAENG_NAETTER = 56
NAT_MIN = 28
NAT_BLOK = 3


def _sengetid(raw: str | None) -> tuple[str, float] | None:
    """Garmins sengetid for natten: (kl., timer efter kl. 18). sleepStartTimestampLocal er lokal vægtid som epoke."""
    try:
        ms = json.loads(raw)["sleep"]["dailySleepDTO"]["sleepStartTimestampLocal"]
    except (TypeError, ValueError, KeyError):
        return None
    if not ms:
        return None
    t = datetime.fromtimestamp(ms / 1000, timezone.utc)
    return t.strftime("%H:%M"), round((t.hour + t.minute / 60 - 18) % 24, 2)


def _naetter(g: sqlite3.Connection, idag: date, n: int = NAETTER) -> list[dict]:
    """De seneste n nætter, hver under aftenens dato: sengetid og søvn fra Garmin (som dater natten ved opvågningen,
    altså dagen efter) og sen skærmtid den aften fra Skærmtid. Uden måling står feltet som null, ikke 0; en dag,
    ingen enhed sendte skærmtid, er ikke 0 timer."""
    try:
        skaerm = {d["dato"]: d for d in json.loads(config.SKAERMTID_JSON.read_text()).get("dage") or []}
    except (OSError, ValueError):
        skaerm = {}
    fra = idag - timedelta(days=n)
    rows = {r["date"]: r for r in g.execute(
        "SELECT date, sleep_s, sleep_score, raw FROM daily WHERE date BETWEEN ? AND ?",
        [(fra + timedelta(days=1)).isoformat(), idag.isoformat()])}
    ud = []
    for i in range(n):
        aften = fra + timedelta(days=i)
        r, s = rows.get((aften + timedelta(days=1)).isoformat()), skaerm.get(aften.isoformat())
        seng = _sengetid(r["raw"]) if r else None
        ud.append({"dato": aften.isoformat(), "sengetid": seng[0] if seng else None, "sengetid_t": seng[1] if seng else None,
                   "soevn_t": _t(r["sleep_s"]) if r else None, "soevnscore": r["sleep_score"] if r else None,
                   "sen_skaermtid_t": s.get("sen_timer") if s and s.get("enheder") else None})
    return ud


DAGSPLAN_DAGE = 14
DOEGNSKIFTE = 6  # kl.; som Skærmtid, så en aften efter midnat hører til dagen før


def _lokal(s: str) -> datetime:
    """ISO-tidspunkt, med eller uden zone, som lokal vægtid uden zone (kalenderen gemmer uden, Skærmtid med)."""
    t = datetime.fromisoformat(s)
    return t.astimezone().replace(tzinfo=None) if t.tzinfo else t


def _minutter(a: datetime, z: datetime, b: datetime, y: datetime) -> float:
    return max(0.0, (min(z, y) - max(a, b)).total_seconds() / 60)


def _dagsplan(g: sqlite3.Connection, idag: date, n: int = DAGSPLAN_DAGE) -> list[dict]:
    """Planlagt mod faktisk for de seneste n døgn (kl. 6 til kl. 6, som Skærmtid). Plan er undervisningen og dine egne
    blokke i kalenderen; faktisk er skærmtiden i kvarterer (Skærmtids forløb), det, CalTask har logget som selvstudie,
    og Garmins pas. Hver planlagt blok får minutterne pr. gruppe og kategori, der faldt i den, og hvor meget af den der
    var selvstudie eller træning. Uden Skærmtids forløb for dagen er `skaerm` null, ikke en dag uden skærm."""
    try:
        skaerm = {d["dato"]: d.get("forloeb") for d in json.loads(config.SKAERMTID_JSON.read_text()).get("dage") or []}
    except (OSError, ValueError):
        skaerm = {}
    try:
        svar: dict[str, int] = {}
        for f in json.loads(config.STUDIE_JSON.read_text()).get("fag") or []:
            for d, k in ((f.get("status") or {}).get("rytme") or {}).get("dage", {}).items():
                svar[d] = svar.get(d, 0) + k
    except (OSError, ValueError):
        svar = None
    fra = idag - timedelta(days=n - 1)
    # plan_blok: blokken har Kompas' planmærke (garmin-coach læser det i beskrivelsen). En coach.db fra før mærket har
    # ikke kolonnen, og så er ingen blok en del af planen.
    plan_sql = "plan_blok" if "plan_blok" in {r[1] for r in g.execute("PRAGMA table_info(calendar_events)")} else "0 AS plan_blok"
    start = lambda d: datetime.combine(d, datetime.min.time()) + timedelta(hours=DOEGNSKIFTE)
    events = list(g.execute(
        f"SELECT start_local, end_local, summary, all_day, fag_kode, fag_navn, {plan_sql} FROM calendar_events "
        "WHERE start_local >= ? AND start_local < ? AND NOT all_day AND end_local IS NOT NULL ORDER BY start_local",
        [start(fra).isoformat(timespec="minutes"), start(idag + timedelta(days=1)).isoformat(timespec="minutes")]))
    pas = list(g.execute("SELECT start_local, duration_s, sport FROM activities WHERE date BETWEEN ? AND ? ORDER BY start_local",
                         [fra.isoformat(), (idag + timedelta(days=1)).isoformat()]))
    ud = []
    for i in range(n):
        d = fra + timedelta(days=i)
        a, z = start(d), start(d + timedelta(days=1))
        i_dagen = lambda t: a <= t < z
        plan, logget = [], []
        for e in events:
            s, slut = _lokal(e["start_local"]), _lokal(e["end_local"])
            if not i_dagen(s):
                continue
            type_ = _type(e["summary"] or "", e["fag_kode"])
            blok = {"start": s.isoformat(timespec="minutes"), "slut": slut.isoformat(timespec="minutes"),
                    "titel": e["summary"] or "", "fag": e["fag_navn"]}
            if type_ == "selvstudie":  # CalTask logger, hvad du faktisk studerede
                logget.append(blok | {"type": "selvstudie"})
            else:
                plan.append(blok | ({"type": "undervisning"} if type_ == "undervisning" else {"type": "blok", "plan": bool(e["plan_blok"])}))
        for p in pas:
            s = _lokal(p["start_local"].replace(" ", "T"))
            if i_dagen(s):
                logget.append({"start": s.isoformat(timespec="minutes"),
                               "slut": (s + timedelta(seconds=p["duration_s"] or 0)).isoformat(timespec="minutes"),
                               "titel": p["sport"] or "", "type": "traening"})
        blokke = skaerm.get(d.isoformat())
        for p in plan:
            ps, pe = _lokal(p["start"]), _lokal(p["slut"])
            grupper: dict[str, float] = {}
            kategorier: dict[str, float] = {}
            for b in blokke or []:
                m = _minutter(ps, pe, _lokal(b["start"]), _lokal(b["slut"]))
                if m:
                    grupper[b["gruppe"]] = grupper.get(b["gruppe"], 0) + m
                    kategorier[b["kategori"]] = kategorier.get(b["kategori"], 0) + m
            varighed = (pe - ps).total_seconds() / 60
            p["faktisk"] = {
                "minutter": round(varighed),
                "skaerm": None if blokke is None else {k: round(v) for k, v in sorted(grupper.items(), key=lambda x: -x[1])},
                "kategorier": None if blokke is None else {k: round(v) for k, v in sorted(kategorier.items(), key=lambda x: -x[1])},
                "uden_skaerm": None if blokke is None else round(max(0.0, varighed - sum(grupper.values()))),
                "selvstudie": round(sum(_minutter(ps, pe, _lokal(x["start"]), _lokal(x["slut"])) for x in logget if x["type"] == "selvstudie")),
                "traening": round(sum(_minutter(ps, pe, _lokal(x["start"]), _lokal(x["slut"])) for x in logget if x["type"] == "traening")),
            }
        ud.append({"dato": d.isoformat(), "fra": a.isoformat(timespec="minutes"), "til": z.isoformat(timespec="minutes"),
                   "plan": plan, "logget": sorted(logget, key=lambda x: x["start"]), "skaerm": blokke,
                   "studiesvar": None if svar is None else svar.get(d.isoformat(), 0)})
    return ud


GLIPPET_DAGE = 3     # de seneste afsluttede døgn, der ses på
GLIPPET_GRAENSE = 2  # så mange af dem uden logget studietid, før I dag siger det


def _kalender_gammel(kalender_hentet: str | None, nu: datetime) -> str | None:
    """Hvorfor det loggede ikke kendes: kalenderen er ikke hentet siden i går. None, når den er frisk."""
    if not kalender_hentet:
        return "kalenderen er aldrig hentet"
    if kalender_hentet < (nu.date() - timedelta(days=1)).isoformat():
        return f"kalenderen er ikke hentet siden {kalender_hentet}"
    return None


def _glippede(dagsplan: list[dict], kalender_hentet: str | None, nu: datetime) -> dict:
    """Planens studieblokke uden logget studietid de seneste GLIPPET_DAGE afsluttede døgn. Et døgn er glippet, når det
    havde blokke med planmærket, og CalTask intet selvstudie har logget i hele døgnet, også uden for blokkene. `vis`
    er sand fra GLIPPET_GRAENSE glippede døgn. Er kalenderen ikke hentet siden i går, kendes det loggede ikke."""
    res = {"dage": GLIPPET_DAGE, "graense": GLIPPET_GRAENSE, "glippet": [], "vis": False}
    if status := _kalender_gammel(kalender_hentet, nu):
        return res | {"status": status}
    afsluttede = [d for d in dagsplan if _lokal(d["til"]) <= nu][-GLIPPET_DAGE:]
    for d in afsluttede:
        blokke = [p for p in d["plan"] if p.get("plan")]
        logget = sum((_lokal(x["slut"]) - _lokal(x["start"])).total_seconds() / 60 for x in d["logget"] if x["type"] == "selvstudie")
        if blokke and not logget:
            res["glippet"].append({"dato": d["dato"], "blokke": len(blokke), "minutter": sum(p["faktisk"]["minutter"] for p in blokke),
                                   "titler": [p["titel"] for p in blokke], "studiesvar": d["studiesvar"]})
    return res | {"fra": afsluttede[0]["dato"] if afsluttede else None, "til": afsluttede[-1]["dato"] if afsluttede else None,
                  "vis": len(res["glippet"]) >= GLIPPET_GRAENSE}


def _studieuge(g: sqlite3.Connection, uge: dict | None, kalender_hentet: str | None, nu: datetime) -> dict:
    """Denne ISO-uges selvstudie mod ugens planlagte studieblokke (blokke med planmærket, hele ugen, også dem, der
    ikke er kommet endnu). Det loggede er ugetabellens `selvstudie_timer` og `selvstudie_dage` (null før logningen
    begyndte). Blokkene tælles under den dato, de starter, som selvstudiet i ugetabellen."""
    m = mandag_i(nu.date())
    plan_sql = "plan_blok" if "plan_blok" in {r[1] for r in g.execute("PRAGMA table_info(calendar_events)")} else "0"
    blokke = [(_lokal(r["end_local"]) - _lokal(r["start_local"])).total_seconds() / 3600 for r in g.execute(
        f"SELECT start_local, end_local FROM calendar_events WHERE {plan_sql} AND NOT all_day AND end_local IS NOT NULL "
        "AND date(start_local) BETWEEN ? AND ?", [m.isoformat(), (m + timedelta(days=6)).isoformat()])]
    res = {"mandag": m.isoformat(), "planlagt_timer": round(sum(blokke), 2), "planlagt_blokke": len(blokke),
           "selvstudie_timer": (uge or {}).get("selvstudie_timer"), "selvstudie_dage": (uge or {}).get("selvstudie_dage")}
    return res | ({"status": status} if (status := _kalender_gammel(kalender_hentet, nu)) else {})


def _studietid(g: sqlite3.Connection, nu: datetime) -> dict:
    """Tid pr. fag fra kalenderen, til Studies side Selvstudie: undervisningen pr. kursuskode (garmin-coach's fag_kode),
    det, CalTask har logget som selvstudie pr. titel ("Selvstudie · Beta🤖" → "Beta"), og studieblokkene (planmærket) pr. det, der
    står før " · " i titlen. Undervisning og selvstudie tæller kun, når de er slut; studieblokkene både planlagt i alt og
    det, der er forbi. Alt pr. ISO-uge (mandagens dato). Navnene oversættes ikke her; Studie kender sine fag."""
    import re
    plan_sql = "plan_blok" if "plan_blok" in {r[1] for r in g.execute("PRAGMA table_info(calendar_events)")} else "0"
    rows = g.execute(f"""SELECT start_local, end_local, summary, fag_kode, fag_navn, fag_art, fag_form, {plan_sql} AS plan FROM calendar_events
                        WHERE NOT all_day AND end_local IS NOT NULL ORDER BY start_local""").fetchall()
    undervisning, selvstudie, blokke = {}, {}, {}

    def læg(d, nøgle, navn, m, timer, felt="timer", dag=None):
        x = d.setdefault(nøgle, {"navn": navn, "timer": 0.0, "uger": {}})
        x[felt] = x.get(felt, 0.0) + timer
        if felt == "timer":
            x["uger"][m] = x["uger"].get(m, 0.0) + timer
        if dag:  # selvstudiet også pr. dag (den dag, sessionen begyndte), til dage i træk, medaljer og kalenderen
            x.setdefault("dage", {})[dag] = x.setdefault("dage", {}).get(dag, 0.0) + timer
            x.setdefault("sessioner", {})[dag] = x.setdefault("sessioner", {}).get(dag, 0) + 1  # én CalTask-logning

    set_ = set()
    for r in rows:
        # Kalenderen kan have samme undervisning to gange (fx to feeds); den tæller én gang
        if r["fag_kode"]:
            nøgle = (r["fag_kode"], r["start_local"], r["end_local"])
            if nøgle in set_:
                continue
            set_.add(nøgle)
        s, e = _lokal(r["start_local"]), _lokal(r["end_local"])
        timer, m, titel = (e - s).total_seconds() / 3600, mandag_i(s.date()).isoformat(), r["summary"] or ""
        if timer <= 0:
            continue
        if r["fag_kode"]:
            if e <= nu:
                læg(undervisning, r["fag_kode"], r["fag_navn"], m, timer)
                # Også pr. slags (garmin-coach's art og form, fx Forelæsning · forudindspillet), så Studie kan lade det, du
                # ikke bruger, ude af den brugte tid
                f = undervisning[r["fag_kode"]].setdefault("former", {}).setdefault((r["fag_art"] or "", r["fag_form"] or ""), {"timer": 0.0, "uger": {}})
                f["timer"] += timer
                f["uger"][m] = f["uger"].get(m, 0.0) + timer
        elif titel.startswith(config.SELVSTUDIE_PRAEFIKS):
            if e <= nu:
                navn = re.sub(r"[^\w\s&-]+", "", titel[len(config.SELVSTUDIE_PRAEFIKS):]).strip()
                læg(selvstudie, navn, navn, m, timer, dag=s.date().isoformat())
        elif r["plan"]:
            navn = titel.split(" · ")[0].strip()
            læg(blokke, navn, navn, m, timer, "planlagt_timer")
            if e <= nu:
                læg(blokke, navn, navn, m, timer)

    def ud(d, kode=False):
        return [{**({"kode": k} if kode else {}), "navn": x["navn"], "timer": round(x.get("timer", 0.0), 2),
                 **({"planlagt_timer": round(x["planlagt_timer"], 2)} if "planlagt_timer" in x else {}),
                 "uger": {m: round(t, 2) for m, t in sorted(x["uger"].items())},
                 **({"dage": {dg: round(t, 2) for dg, t in sorted(x["dage"].items())},
                     "sessioner": dict(sorted(x["sessioner"].items()))} if "dage" in x else {}),
                 **({"former": [{"art": a, "form": fo, "timer": round(v["timer"], 2), "uger": {m: round(t, 2) for m, t in sorted(v["uger"].items())}}
                                for (a, fo), v in sorted(x["former"].items())]} if "former" in x else {})} for k, x in sorted(d.items())]
    første = rows[0]["start_local"][:10] if rows else None
    return {"fra": første, "selvstudie_fra": config.SELVSTUDIE_FRA, "til": nu.date().isoformat(),
            "undervisning": ud(undervisning, kode=True), "selvstudie": ud(selvstudie), "studieblokke": ud(blokke)}


def _nat_sammenhaeng(g: sqlite3.Connection, idag: date) -> dict:
    """En fast hypotese pr. nat: følger en dårligere søvnscore efter en aften med mere sen skærmtid? Samme vurdering som
    ugernes sammenhænge (stærk ved p < 0,01, antydning ved p < 0,05, begge med |rho| ≥ 0,3), men på nætter."""
    par = [(n["sen_skaermtid_t"], n["soevnscore"]) for n in _naetter(g, idag, NAT_SAMMENHAENG_NAETTER)
           if n["sen_skaermtid_t"] is not None and n["soevnscore"] is not None]
    res = {"x": "sen_skaermtid_t", "y": "soevnscore", "spoergsmaal": "Sover du dårligere efter en aften med sen skærmtid?",
           "n_naetter": len(par), "min_naetter": NAT_MIN}
    if len(par) < NAT_MIN:
        return res | {"status": f"for få nætter ({len(par)} af {NAT_MIN})"}
    rho, p = rapport.spearman([a for a, _ in par], [b for _, b in par], blok=NAT_BLOK)
    status = "stærk" if p < 0.01 and abs(rho) >= 0.3 else "antydning" if p < 0.05 and abs(rho) >= 0.3 else "ingen sammenhæng"
    return res | {"rho": round(rho, 2), "p": round(p, 4), "status": status}


def _pas(g: sqlite3.Connection, m: date) -> list[dict]:
    # Belastningen pr. pas er garmin-coach's (TRIMP), samme tal som ugens sum. Mangler den, står den som None.
    try:
        belastning = json.loads(config.BELASTNING_JSON.read_text()).get("pas") or {}
    except (OSError, ValueError):
        belastning = {}
    return [
        {"dato": r["date"], "start": r["start_local"][11:16], "sport": r["sport"], "navn": r["name"],
         "minutter": round((r["duration_s"] or 0) / 60),
         "belastning": None if belastning.get(str(r["activity_id"])) is None else round(belastning[str(r["activity_id"])])}
        for r in g.execute(
            """SELECT activity_id, date, start_local, sport, name, duration_s FROM activities
               WHERE date BETWEEN ? AND ? ORDER BY start_local""",
            [m.isoformat(), (m + timedelta(days=6)).isoformat()])
    ]


def _type(titel: str, fag_kode: str | None) -> str:
    if fag_kode:  # undervisning fra skemaet, som garmin-coach har genkendt
        return "undervisning"
    if titel.startswith(config.SELVSTUDIE_PRAEFIKS):
        return "selvstudie"
    return "andet"


# Undervisningens felter fra skemaet, som garmin-coach gemmer, når den henter kalenderen. Titlerne tolkes kun dér.
_FAG = ("navn", "kode", "art", "form")
_FAG_SQL = ", ".join(f"fag_{k}" for k in _FAG)


def _fag(r: sqlite3.Row) -> dict | None:
    return {k: r[f"fag_{k}"] for k in _FAG} if r["fag_navn"] else None


def _kalender(g: sqlite3.Connection, m: date) -> list[dict]:
    return [
        {"dato": r["start_local"][:10], "start": None if r["all_day"] else r["start_local"][11:16],
         "slut": None if r["all_day"] or not r["end_local"] else r["end_local"][11:16],
         "titel": r["summary"] or "", "heldag": bool(r["all_day"]), "type": _type(r["summary"] or "", r["fag_kode"]),
         "fag": _fag(r), "kalender": r["kalender"]}
        for r in g.execute(
            f"""SELECT start_local, end_local, summary, all_day, kalender, {_FAG_SQL} FROM calendar_events
               WHERE date(start_local) BETWEEN ? AND ? ORDER BY start_local""",
            [m.isoformat(), (m + timedelta(days=6)).isoformat()])
    ]


def _med_fag(g: sqlite3.Connection, rs: list[dict]) -> None:
    """Reviews gemt, før kalenderen havde fag-felterne, får dem fra garmin-coach ved eksporten, så siderne
    aldrig selv tolker titler. Det gemte review i databasen røres ikke."""
    fag = {(r["start_local"][:10], None if r["all_day"] else r["start_local"][11:16], r["summary"]): _fag(r)
           for r in g.execute(f"SELECT start_local, summary, all_day, {_FAG_SQL} FROM calendar_events "
                              "WHERE fag_navn IS NOT NULL")}
    for doc in rs:
        for e in (doc.get("kalender") or []) + (doc.get("kommende") or []):
            if "fag" not in e:
                e["fag"] = fag.get((e["dato"], e["start"], e["titel"]))


def snapshot(conn: sqlite3.Connection, m: date) -> dict:
    """Alle tal for ugen der starter mandag m. Kommende uge er ugen efter."""
    r = rapport.lav(conn, m)
    if "fejl" in r:
        raise ValueError(r["fejl"])
    r.pop("seneste_uger", None)
    doc = {"uge": r.pop("uge"), "mandag": r.pop("mandag"), "rapport": r}
    g = _garmin()
    if g is not None:
        doc |= {"dage": _dage(g, m), "pas": _pas(g, m), "kalender": _kalender(g, m),
                "kommende": _kalender(g, m + timedelta(days=7))}
        g.close()
    return doc


def _check_tekst(t: dict) -> None:
    if not isinstance(t, dict) or not isinstance(t.get("saetning"), str) or not t["saetning"].strip():
        raise ValueError("teksten skal være et objekt med en ikke-tom 'saetning'")
    for k in TEKST_LISTER:
        if k in t and not isinstance(t[k], list):
            raise ValueError(f"tekst.{k} skal være en liste")
    if "en_ting" in t and not isinstance(t["en_ting"], str):
        raise ValueError("tekst.en_ting skal være en streng")


def gem_review(conn: sqlite3.Connection, m: date, tekst: dict, nu: datetime | None = None) -> dict:
    """Gem reviewets tekst med ugens tal. `genereret` er tidspunktet med tidszone og `metode` den metode, tallene er
    regnet efter (rapport.METODE), så siderne kan vise, hvornår og efter hvilken metode reviewet er skrevet. Reviews
    gemt, før feltet fandtes, har ingen `metode` og et `genereret` i lokal tid uden tidszone; de
    får intet påført bagefter."""
    _check_tekst(tekst)
    genereret = (nu or datetime.now()).astimezone().isoformat(timespec="seconds")
    doc = snapshot(conn, m) | {"tekst": tekst, "genereret": genereret, "metode": rapport.METODE}
    with conn:
        conn.execute(
            "INSERT INTO reviews (uge, doc) VALUES (?, ?) ON CONFLICT(uge) DO UPDATE SET doc = excluded.doc",
            [doc["uge"], json.dumps(doc, ensure_ascii=False)])
    return doc


def reviews(conn: sqlite3.Connection) -> list[dict]:
    return [json.loads(r["doc"]) for r in conn.execute("SELECT doc FROM reviews ORDER BY uge")]


# Samme opdeling som rapport.py, så siden farver som reviewet vurderer.
def _god(k: str) -> str | None:
    return "op" if k in rapport.HOEJ_ER_GODT else "ned" if k in rapport.LAV_ER_GODT else None


def eksport(conn: sqlite3.Connection, mappe: Path = config.SITE_DIR) -> dict:
    rs = reviews(conn)
    # Sidste hele uge uden review vises med tal men uden tekst, så siden ikke
    # halter en uge efter, hvis rutinen Overblik ikke har kørt.
    sidste = kilder.sidste_hele_uge(date.today())
    if not any(r["mandag"] == sidste.isoformat() for r in rs):
        try:
            rs.append(snapshot(conn, sidste) | {"tekst": None})
        except ValueError:
            pass
    denne = mandag_i(date.today())
    g = _garmin()
    kalender = {} if g is None else {
        m.isoformat(): _kalender(g, m) for m in (denne - timedelta(days=7), denne, denne + timedelta(days=7))}
    uger = [dict(r) for r in conn.execute("SELECT * FROM uger ORDER BY mandag")]
    naetter, dagsplan, nat, glippede, studieuge, studietid = [], [], None, None, None, None
    if g is not None:
        _med_fag(g, rs)
        naetter = _naetter(g, date.today())
        dagsplan = _dagsplan(g, date.today())
        hentet = g.execute("SELECT value FROM sync_state WHERE key = 'last_calendar_sync'").fetchone()
        glippede = _glippede(dagsplan, hentet[0] if hentet else None, datetime.now())
        studieuge = _studieuge(g, next((u for u in uger if u["mandag"] == denne.isoformat()), None),
                               hentet[0] if hentet else None, datetime.now())
        nat = _nat_sammenhaeng(g, date.today())
        studietid = _studietid(g, datetime.now())
        g.close()
    ud = {
        "genereret": datetime.now().isoformat(timespec="seconds"),
        # Den metode, tallene regnes efter nu. Hvert review har sin egen `metode` fra dagen, det blev gemt (ældre
        # reviews ingen), så en side kan se, at et review er skrevet efter en ældre metode.
        "metode": rapport.METODE,
        "kalender": kalender,
        "z_graense": rapport.Z_GRAENSE,
        "min_uger_korrelation": rapport.MIN_UGER_KORRELATION,
        "selvstudie_fra": config.SELVSTUDIE_FRA,
        "kolonner": [{"k": k, "forklaring": f, "god": _god(k)} for k, f in KOLONNER],
        "uger": uger,
        "kilder": kilder.status([dict(r) for r in conn.execute("SELECT * FROM kilder ORDER BY kilde")], date.today()),
        "reviews": rs,
        # Til Kroppen i tal: sengetid og sen skærmtid pr. aften (sengetid_t er timer efter kl. 18)
        "naetter": naetter,
        "nat_sammenhaeng": nat,
        # Til Ugereview og I dag: planlagt mod faktisk de seneste 14 døgn (kl. 6 til kl. 6)
        "dagsplan": dagsplan,
        # Til I dag: planens studieblokke uden logget studietid de seneste døgn (null uden garmin-coach)
        "glippede": glippede,
        # Til I dag: denne uges selvstudie mod ugens planlagte studieblokke (null uden garmin-coach)
        "studieuge": studieuge,
        # Til Studies side Selvstudie: undervisning, logget selvstudie og studieblokke pr. fag og uge (null uden garmin-coach)
        "studietid": studietid,
    }
    mappe.mkdir(parents=True, exist_ok=True)
    tmp = mappe / "liv.json.tmp"
    tmp.write_text(json.dumps(ud, ensure_ascii=False))
    os.replace(tmp, mappe / "liv.json")  # atomisk, så Caddy aldrig leverer en halv fil
    return {"fil": str(mappe / "liv.json"), "uger": len(ud["uger"]), "reviews": len(rs)}
