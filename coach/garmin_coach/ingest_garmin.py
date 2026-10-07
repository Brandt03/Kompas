"""Henter Garmin-data ind i den lokale database.

Bruger det uofficielle `garminconnect`-bibliotek, fordi Garmins officielle
Connect Developer Program ikke tager imod nye ansøgninger i øjeblikket.
Det betyder også at endpoints kan ændre sig uden varsel — derfor er alt
feltudtræk defensivt, og rådata gemmes altid som JSON ved siden af.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .config import CONFIG
from .db import connect, set_state, upsert
from .metrics import _MEASURED

log = logging.getLogger(__name__)

# Garmin tåler ikke at blive hamret. Pause mellem kald.
THROTTLE_S = 1.2
# Så mange dage/pas i træk uden et eneste svar betyder at Garmin afviser os
# (typisk HTTP 429). Flere forsøg forlænger kun spærringen.
MAX_FAILURES = 5


class GarminUnavailable(RuntimeError):
    """Garmin svarer ikke længere — stop frem for at blive ved."""


def _dig(obj: Any, *path, default=None):
    """Hent en nøgle dybt nede uden at crashe hvis strukturen har ændret sig."""
    cur = obj
    for key in path:
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list) and isinstance(key, int) and len(cur) > key:
            cur = cur[key]
        else:
            return default
        if cur is None:
            return default
    return cur


def login():
    """Log ind på Garmin.

    login(tokenstore) klarer begge tilfælde selv: den indlæser gemte tokens hvis
    de findes, og gemmer nye tokens automatisk hvis den må bruge email/password.
    MFA-koden hentes gennem prompt_mfa-callbacket.
    """
    from garminconnect import (
        Garmin,
        GarminConnectAuthenticationError,
        GarminConnectTooManyRequestsError,
    )

    tokendir = str(CONFIG.token_dir)
    have_tokens = Path(tokendir).expanduser().exists()

    if not have_tokens and not (CONFIG.garmin_email and CONFIG.garmin_password):
        raise RuntimeError(
            "Ingen gemte tokens og intet login. Sæt GARMIN_EMAIL og "
            "GARMIN_PASSWORD i .env og kør:\n"
            "  set -a; source .env; set +a\n"
            "  .venv/bin/python -m garmin_coach.ingest_garmin --login"
        )

    api = Garmin(
        CONFIG.garmin_email,
        CONFIG.garmin_password,
        prompt_mfa=lambda: input("Garmin MFA-kode: ").strip(),
    )

    try:
        api.login(tokendir)
    except GarminConnectTooManyRequestsError as exc:
        raise RuntimeError(
            "Garmin har midlertidigt spærret din IP efter for mange loginforsøg "
            "(HTTP 429). Vent 30-60 minutter og prøv igen. Lad være med at prøve "
            "gentagne gange imens — det forlænger spærringen."
        ) from exc
    except GarminConnectAuthenticationError as exc:
        raise RuntimeError(
            f"Garmin afviste dit login: {exc}\n"
            "Tjek email og password i .env, og at kontoen ikke er låst på "
            "https://sso.garmin.com"
        ) from exc

    log.info("Logget ind som %s (tokens i %s)", api.display_name or "ukendt", tokendir)
    return api


# --------------------------------------------------------------------------
# Profil: Garmins egne indstillinger for makspuls, hvilepuls og køn
# --------------------------------------------------------------------------

def _scan(obj: Any, keys: tuple[str, ...], lo: float, hi: float) -> float | None:
    """Gennemsøg en vilkårligt indlejret struktur for første plausible værdi.

    Garmin flytter rundt på hvor tallene ligger mellem endpoints og versioner,
    så vi leder efter navnene frem for at antage en bestemt sti. Lo/hi filtrerer
    urealistiske værdier fra, fx en nulstillet indstilling.
    """
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k in keys:
                v = cur.get(k)
                if isinstance(v, (int, float)) and lo <= v <= hi:
                    return float(v)
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


HR_MAX_KEYS = ("maxHeartRate", "maxHr", "maxHeartRateUsed", "userMaxHeartRate")
HR_REST_KEYS = ("restingHeartRate", "restingHr", "restingHrUsed")


def sync_profile(api, conn: sqlite3.Connection) -> dict:
    """Hent brugerprofil og pulszoner, og gem det Garmin selv mener om dine tal."""
    raw: dict[str, Any] = {}
    for label, fn in (
        ("user_profile", api.get_user_profile),
        ("hr_zones", api.get_heart_rate_zones),
    ):
        try:
            time.sleep(THROTTLE_S)
            raw[label] = fn()
        except Exception as exc:  # noqa: BLE001
            log.debug("%s fejlede: %s", label, exc)

    found = {
        "hr_max": _scan(raw, HR_MAX_KEYS, 120, 230),
        "hr_rest": _scan(raw, HR_REST_KEYS, 25, 95),
        "sex": (_dig(raw, "user_profile", "userData", "gender") or "").lower()[:1] or None,
    }
    for key, value in found.items():
        if value is not None:
            set_state(conn, f"profile_{key}", str(value))
    if raw:
        set_state(conn, "profile_raw", json.dumps(raw, default=str)[:20000])
    conn.commit()
    return found


def sync_hr_zones(api, conn: sqlite3.Connection) -> dict:
    """Hent dine faktiske pulszoner og laktattærskel som de står i Garmin.

    Det slår enhver procent-af-makspuls-formel, fordi det er de grænser din
    egen profil er sat op med, og fordi tærsklen er målt frem for udledt.
    """
    try:
        time.sleep(THROTTLE_S)
        zones = api.get_heart_rate_zones()
    except Exception as exc:  # noqa: BLE001
        log.warning("Kunne ikke hente pulszoner: %s", exc)
        return {}

    lthr = _scan(
        zones,
        ("lactateThresholdHeartRateUsed", "lactateThresholdHeartRate", "lactateThresholdHr"),
        100,
        220,
    )
    # Find profilen for DEFAULT-sporten, ellers den første
    profiles = [z for z in (zones or []) if isinstance(z, dict)]
    if not profiles:
        # Tomt svar eller ændret format: behold det vi har frem for at
        # overskrive rådata mens de gamle grænser stille bliver stående.
        log.warning("Pulszoner: uventet svar fra Garmin, beholder gemte værdier")
        return {}
    default = next((z for z in profiles if z.get("sport") == "DEFAULT"), None) or (
        profiles[0] if profiles else {}
    )
    floors = {
        f"zone{i}": default.get(f"zone{i}Floor")
        for i in range(1, 6)
        if default.get(f"zone{i}Floor")
    }
    method = default.get("trainingMethod")
    zone_max = default.get("maxHeartRateUsed")

    set_state(conn, "hr_zones_raw", json.dumps(zones, default=str)[:20000])
    for key, value in (
        ("profile_lthr", lthr),
        ("zone_method", method),
        ("zone_max_hr", zone_max),
        ("zone_floors", json.dumps(floors) if floors else None),
    ):
        if value is not None:
            set_state(conn, key, str(value))
    conn.commit()
    return {
        "laktattærskel": lthr,
        "zonemetode": method,
        "makspuls_i_zoneopsætning": zone_max,
        "grænser": floors,
    }


def sync_activity_zones(
    api, conn: sqlite3.Connection, limit: int = 200, max_failures: int = MAX_FAILURES
) -> int:
    """Hent Garmins egen optælling af tid i hver zone, pas for pas.

    Det her er den rigtige måde: Garmin har målt sekund for sekund, så et
    intervalpas fordeles korrekt i stedet for at hele varigheden lander i én
    zone efter gennemsnitspulsen. Kun pas vi ikke allerede har hentes.
    """
    rows = conn.execute(
        """SELECT a.activity_id FROM activities a
           LEFT JOIN activity_zones z ON z.activity_id = a.activity_id
           WHERE z.activity_id IS NULL AND a.avg_hr IS NOT NULL
           ORDER BY a.date DESC LIMIT ?""",
        (limit,),
    ).fetchall()

    done = failures = 0
    for i, r in enumerate(rows, 1):
        aid = r["activity_id"]
        try:
            time.sleep(THROTTLE_S)
            data = api.get_activity_hr_in_timezones(aid)
        except Exception as exc:  # noqa: BLE001
            log.debug("Zoner fejlede for %s: %s", aid, exc)
            failures += 1
            if failures >= max_failures:
                log.warning("Zonedata: %d fejl i træk, stopper (resten hentes ved næste sync)",
                            failures)
                break
            continue
        failures = 0
        for entry in data or []:
            if not isinstance(entry, dict):
                continue
            zone = entry.get("zoneNumber")
            if zone is None:
                continue
            upsert(
                conn,
                "activity_zones",
                {
                    "activity_id": aid,
                    "zone": int(zone),
                    "seconds": entry.get("secsInZone"),
                    "low_bpm": entry.get("zoneLowBoundary"),
                },
                pk=["activity_id", "zone"],
            )
        conn.commit()
        done += 1
        if i % 10 == 0:
            log.info("  %d/%d pas med zonedata", i, len(rows))
    return done


# --------------------------------------------------------------------------
# Aktiviteter
# --------------------------------------------------------------------------

def sync_activities(api, conn: sqlite3.Connection, start: date, end: date) -> int:
    activities = api.get_activities_by_date(start.isoformat(), end.isoformat())
    for a in activities or []:
        start_local = a.get("startTimeLocal") or ""
        upsert(
            conn,
            "activities",
            {
                "activity_id": str(a.get("activityId")),
                "start_local": start_local,
                "date": start_local[:10],
                "sport": _dig(a, "activityType", "typeKey"),
                "name": a.get("activityName"),
                "duration_s": a.get("duration"),
                "distance_m": a.get("distance"),
                "avg_hr": a.get("averageHR"),
                "max_hr": a.get("maxHR"),
                "elev_gain_m": a.get("elevationGain"),
                "calories": a.get("calories"),
                "garmin_load": a.get("activityTrainingLoad"),
                "aerobic_te": a.get("aerobicTrainingEffect"),
                "anaerobic_te": a.get("anaerobicTrainingEffect"),
                "raw": json.dumps(a, default=str),
            },
            pk=["activity_id"],
        )
    conn.commit()
    return len(activities or [])


# --------------------------------------------------------------------------
# Daglige wellness-tal
# --------------------------------------------------------------------------

def _fetch_day(api, d: date) -> dict | None:
    """Samler ét døgns tal. Hvert kald pakkes ind, så en enkelt fejlende
    metrik ikke vælter hele dagen.

    Fejler alle kald, returneres None. En række med kun en dato ville ellers
    få dagen til at se synket ud, og datafriskheden til at sige "aktuel".
    """
    iso = d.isoformat()
    row: dict[str, Any] = {"date": iso}
    raw: dict[str, Any] = {}

    def attempt(label: str, fn):
        try:
            time.sleep(THROTTLE_S)
            value = fn()
            raw[label] = value
            return value
        except Exception as exc:  # noqa: BLE001
            log.debug("%s fejlede for %s: %s", label, iso, exc)
            return None

    stats = attempt("stats", lambda: api.get_stats(iso)) or {}
    row["steps"] = stats.get("totalSteps")
    row["resting_hr"] = stats.get("restingHeartRate")
    row["stress_avg"] = stats.get("averageStressLevel")
    row["bb_high"] = stats.get("bodyBatteryHighestValue")
    row["bb_low"] = stats.get("bodyBatteryLowestValue")

    sleep = attempt("sleep", lambda: api.get_sleep_data(iso)) or {}
    dto = sleep.get("dailySleepDTO") or {}
    row["sleep_s"] = dto.get("sleepTimeSeconds")
    row["deep_s"] = dto.get("deepSleepSeconds")
    row["rem_s"] = dto.get("remSleepSeconds")
    row["light_s"] = dto.get("lightSleepSeconds")
    row["awake_s"] = dto.get("awakeSleepSeconds")
    row["sleep_score"] = _dig(dto, "sleepScores", "overall", "value")

    hrv = attempt("hrv", lambda: api.get_hrv_data(iso)) or {}
    row["hrv_last_night"] = _dig(hrv, "hrvSummary", "lastNightAvg")
    row["hrv_status"] = _dig(hrv, "hrvSummary", "status")

    readiness = attempt("readiness", lambda: api.get_training_readiness(iso))
    if isinstance(readiness, list) and readiness:
        row["training_readiness"] = readiness[0].get("score")

    vo2 = attempt("vo2max", lambda: api.get_max_metrics(iso))
    if isinstance(vo2, list) and vo2:
        row["vo2max"] = _dig(vo2, 0, "generic", "vo2MaxPreciseValue") or _dig(
            vo2, 0, "generic", "vo2MaxValue"
        )

    if not raw:
        log.warning("Ingen data for %s — alle kald fejlede", iso)
        return None
    row["raw"] = raw  # flettes med det gemte i sync_daily
    return row


def sync_daily(
    api, conn: sqlite3.Connection, start: date, end: date,
    skip_measured: bool = False, max_failures: int | None = None,
) -> int:
    """Returnerer antal dage hvor der faktisk kom noget igennem.

    skip_measured springer dage over der allerede har målinger, så en lang
    backfill kan køres igen efter en afbrydelse uden at hente alt forfra.
    max_failures stopper med GarminUnavailable efter så mange dage i træk hvor
    alle kald fejlede; de dage der nåede at komme ind, er gemt.
    """
    measured: set[str] = set()
    if skip_measured:
        measured = {r["date"] for r in conn.execute(
            f"SELECT date FROM daily WHERE date BETWEEN ? AND ? AND {_MEASURED}",
            (start.isoformat(), end.isoformat()),
        )}
    todo = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    todo = [d for d in todo if d.isoformat() not in measured]
    written = failures = 0
    for n, d in enumerate(todo, 1):
        row = _fetch_day(api, d)
        if row is None:
            failures += 1
            if max_failures and failures >= max_failures:
                raise GarminUnavailable(
                    f"{failures} dage i træk uden svar fra Garmin (senest {d}). "
                    "Vent en time og kør igen — hentede dage springes over."
                )
        else:
            failures = 0
            # Flet rådata pr. kilde: et kald der fejler i dag må ikke slette
            # det svar der blev gemt i går. upsert beskytter de udtrukne
            # felter mod None, men raw er én samlet streng.
            old = conn.execute("SELECT raw FROM daily WHERE date = ?", (row["date"],)).fetchone()
            try:
                merged = json.loads(old["raw"]) if old and old["raw"] else {}
            except ValueError:
                merged = {}
            merged.update(row["raw"])
            row["raw"] = json.dumps(merged, default=str)
            upsert(conn, "daily", row, pk=["date"])
            conn.commit()
            written += 1
        if n % 10 == 0 or n == len(todo):
            log.info("  %d/%d dage hentet (%s)", n, len(todo), d.isoformat())
    return written


def sync_weight(api, conn: sqlite3.Connection, start: date, end: date) -> int:
    """Vejninger i bidder på 90 dage, så lange perioder ikke rammer en
    ukendt grænse i Garmins endpoint."""
    entries: list[dict] = []
    chunk = start
    while chunk <= end:
        chunk_end = min(end, chunk + timedelta(days=89))
        try:
            time.sleep(THROTTLE_S)
            body = api.get_body_composition(chunk.isoformat(), chunk_end.isoformat()) or {}
            entries.extend(body.get("dateWeightList") or [])
        except Exception as exc:  # noqa: BLE001
            log.warning("Vægtdata fejlede for %s → %s: %s", chunk, chunk_end, exc)
        chunk = chunk_end + timedelta(days=1)
    for e in entries:
        grams = e.get("weight")
        upsert(
            conn,
            "daily",
            {
                "date": (e.get("calendarDate") or "")[:10],
                "weight_kg": round(grams / 1000.0, 2) if grams else None,
            },
            pk=["date"],
        )
    conn.commit()
    return len(entries)


# --------------------------------------------------------------------------

def run_sync(days: int = 7, full_history_days: int | None = None) -> dict:
    """Standard-sync henter de seneste `days` dage. Første gang kan du køre
    med --days 400 for at bygge et ordentligt baseline-grundlag."""
    conn = connect()
    api = login()
    end = date.today()
    start = end - timedelta(days=(full_history_days or days))

    result = {
        "period": f"{start} → {end}",
        "profil": sync_profile(api, conn),
        "pulszoner": sync_hr_zones(api, conn),
        "activities": sync_activities(api, conn, start, end),
        "days": sync_daily(api, conn, start, end),
        "weigh_ins": sync_weight(api, conn, start, end),
        "pas_med_zonedata": sync_activity_zones(api, conn),
    }
    # Hevy efter Garmins aktiviteter, så Hevy-pas kan parres med deres
    # Garmin-kopi i stedet for at blive oprettet som egne pas.
    try:
        from .ingest_hevy import sync_hevy

        result["hevy"] = sync_hevy(conn)
    except Exception as exc:  # noqa: BLE001
        log.warning("Hevy-sync fejlede: %s", exc)
        result["hevy"] = {"fejl": str(exc)}
    # Kun en sync der faktisk hentede noget, tæller som en sync
    if result["days"] or result["activities"]:
        set_state(conn, "last_garmin_sync", f"{date.today().isoformat()}")
    conn.commit()
    conn.close()
    return result


def run_backfill(start: date, end: date | None = None) -> dict:
    """Hent historik fra `start` og frem.

    Dage der allerede har målinger springes over, så kørslen kan gentages
    efter en afbrydelse. Stopper hvis Garmin begynder at afvise kald.
    """
    end = end or date.today()
    conn = connect()
    api = login()
    result: dict[str, Any] = {"periode": f"{start} → {end}"}
    try:
        result["aktiviteter"] = sync_activities(api, conn, start, end)
        result["dage_hentet"] = sync_daily(
            api, conn, start, end, skip_measured=True, max_failures=MAX_FAILURES
        )
        result["vejninger"] = sync_weight(api, conn, start, end)
        result["pas_med_zonedata"] = sync_activity_zones(api, conn, limit=5000)
    except GarminUnavailable as exc:
        result["stoppet"] = str(exc)
    finally:
        conn.close()
    return result


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Sync Garmin-data til lokal database")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--login", action="store_true", help="Kun login og gem tokens")
    parser.add_argument("--fra", type=date.fromisoformat, metavar="ÅÅÅÅ-MM-DD",
                        help="Hent historik fra denne dato (springer hentede dage over)")
    args = parser.parse_args()

    if args.login:
        login()
        print("Tokens gemt. Du kan nu fjerne GARMIN_PASSWORD fra miljøet.")
    elif args.fra:
        print(json.dumps(run_backfill(args.fra), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(run_sync(days=args.days), indent=2, ensure_ascii=False))
