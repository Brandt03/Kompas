"""MCP-server der eksponerer dine Garmin- og kalenderdata som værktøjer.

Værktøjsbeskrivelserne nedenfor er det, modellen faktisk læser når den vælger
værktøj, så de er skrevet til at blive læst — ikke som intern dokumentation.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import metrics
from .db import connect, connect_readonly, get_state

logging.basicConfig(level=logging.INFO)

# "instructions" sendes til klienten ved opstart og rammesætter hele serveren,
# så vejledningen gælder uanset hvordan samtalen begynder.
INSTRUCTIONS = """
Denne server giver adgang til brugerens egne Garmin- og kalenderdata.

Hent altid data før du vurderer noget. Gæt aldrig på tal. Værktøjerne har
allerede lavet beregningerne — fortolk dem, regn ikke videre på dem.

Forankr anbefalinger i etablerede principper: polariseret intensitetsfordeling,
progression i volumen frem for spring, og restitution som forudsætning for
hårde pas. Afviger HRV eller hvilepuls tydeligt fra grundniveauet, vejer det
tungere end hvad planen siger.

Vær ærlig når datagrundlaget er for tyndt til en vurdering, frem for at
udglatte. Dette er ikke lægefaglig rådgivning: vedvarende afvigelser, smerter
eller symptomer hører hjemme hos en fagperson.
""".strip()

OPSLAG_MAX_ROWS = 500
# En forespørgsel, der løber løbsk (fx en krydsjoin uden betingelse), stoppes efter så mange sekunder
OPSLAG_SEKUNDER = 10

mcp = MCPServer("garmin-coach", instructions=INSTRUCTIONS, version="0.1.0")


# --------------------------------------------------------------------------
# Værktøjer
# --------------------------------------------------------------------------

@mcp.tool()
def traeningsbelastning(uger: int = 8) -> dict:
    """Træningsbelastning over tid: akut (7 dage) mod kronisk (28 dage), ACWR,
    monotoni, strain, ugentlige totaler og fordeling på sportsgrene.

    Brug dette til spørgsmål om volumen, opbygning, nedtrapning, om der er
    trænet for hårdt eller for ensformigt, og til at planlægge kommende uger.
    Alle tal er færdigberegnede — regn ikke videre på dem, fortolk dem.

    Belastning er i TRIMP-enheder. Styrkepas med Hevy-data regnes ud fra
    arbejdssæt og RPE (se "beregnet_med"), øvrige pas ud fra puls.
    Vinduerne slutter på "beregnet_til_og_med" (normalt i går); dagens pas
    står i "i_dag_indtil_nu". Står der noget i "pas_uden_belastning_28d",
    er belastningen undervurderet — nævn det. Er acwr null, så læs
    acwr_fortolkning for hvorfor, og gæt ikke selv et tal.

    "styrke_ugentligt" er styrke i styrketermer: arbejdssæt, volumen og RPE.
    RPE-tallene gælder kun sæt med RPE og er null når dækningen er for lav;
    sammenlign kun uger hvor de ikke er null.
    """
    conn = connect()
    try:
        return metrics.training_load(conn, weeks=uger)
    finally:
        conn.close()


@mcp.tool()
def restitution(dage: int = 14) -> dict:
    """Restitutionsstatus: HRV og hvilepuls udtrykt som afvigelse i
    standardafvigelser fra et 60-dages grundniveau, søvnmængde, søvnscore,
    stress, Body Battery og Garmins training readiness.

    Brug dette før du anbefaler intensitet for i dag eller i morgen, og når
    brugeren spørger om træthed, overtræning, sygdom eller søvn. Feltet "flag"
    indeholder forhold der allerede er vurderet til at være værd at nævne.
    En tom flag-liste betyder kun noget hvis der er data: tjek
    "aktuelle_datapunkter" (de seneste 7 dage) og "datafriskhed" før du
    siger at restitutionen ser fin ud.
    """
    conn = connect()
    try:
        return metrics.recovery(conn, days=dage)
    finally:
        conn.close()


def _activities(conn, dage: int, sportsgren: str | None = None) -> list[dict]:
    ath = metrics.athlete(conn)
    ctx = metrics.load_context(conn, ath)
    since = (date.today() - timedelta(days=dage)).isoformat()
    sql = "SELECT * FROM activities WHERE date >= ?"
    params: list = [since]
    if sportsgren:
        sql += " AND sport LIKE ?"
        params.append(f"%{sportsgren}%")
    sql += " ORDER BY start_local DESC"
    rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        load, kilde = metrics.session_load_detail(r, ath, ctx)
        h = ctx.hevy.get(r["activity_id"])
        out.append({
            "dato": r["date"],
            "sport": r["sport"],
            "navn": r["name"],
            "varighed_min": round(r["duration_s"] / 60) if r["duration_s"] else None,
            "distance_km": round(r["distance_m"] / 1000, 2) if r["distance_m"] else None,
            "snitpuls": r["avg_hr"],
            "makspuls": r["max_hr"],
            "højdemeter": round(r["elev_gain_m"]) if r["elev_gain_m"] else None,
            "belastning": round(load),
            "belastning_kilde": kilde,
            **({"arbejdssæt": h["sæt"],
                "sæt_med_rpe_eller_failure": h["med_anstrengelse"]} if h else {}),
            "garmin_load": round(r["garmin_load"]) if r["garmin_load"] else None,
            "aerob_te": r["aerobic_te"],
            "anaerob_te": r["anaerobic_te"],
        })
    return out


@mcp.tool()
def seneste_traening(dage: int = 14, sportsgren: str | None = None) -> list[dict]:
    """De enkelte træningspas i perioden med varighed, distance, gennemsnitspuls,
    højdemeter og belastning pr. pas.

    "belastning" er samme skala som i traeningsbelastning og kan sammenlignes
    på tværs af sportsgrene. "belastning_kilde" siger hvordan: "hevy" (sæt fra
    Hevy plus tillæg for sæt med RPE eller til failure, kalibreret til TRIMP),
    "puls" (Banister-TRIMP) eller "ingen" (hverken puls eller sæt; tæller 0).
    Har et Hevy-pas få "sæt_med_rpe_eller_failure" i forhold til
    "arbejdssæt", er belastningen snarere for lav end for høj.
    "garmin_load" er Garmins egen EPOC-baserede værdi, en anden skala —
    sammenlign den aldrig med "belastning".

    Brug dette når spørgsmålet handler om konkrete pas frem for om helheden,
    for eksempel "hvordan gik mit interval i tirsdags" eller "har jeg løbet
    nok langt for nylig". Filtrér med sportsgren, fx "running", "cycling",
    "strength_training", "lap_swimming".
    """
    conn = connect()
    try:
        return _activities(conn, dage, sportsgren)
    finally:
        conn.close()


@mcp.tool()
def kalender(dage_frem: int = 7) -> dict:
    """Kommende dage med dagens program (tid og titel på hver begivenhed),
    antal begivenheder, samlet optaget tid, første start og sidste slut, samt
    sammenhængende frie vinduer der er lange nok til at træne i.

    Brugeren er studerende, så kalenderen er mest forelæsninger, øvelser og
    supervision, plus sociale arrangementer. Heldagsbegivenheder står i
    programmet med tid "heldag", men tæller ikke med i optaget tid.

    Brug dette når du skal placere træning realistisk i ugen, vurdere om en
    hård dag kolliderer med en tung studiedag, eller koble søvn og
    restitution til hvad der skete. Tider er lokal tid.

    Frie vinduer for i dag starter ved nu. Heldagsbegivenheder blokerer ikke
    vinduerne, så en rejse- eller festdag kan stå som helt fri — kig på
    programmet før du foreslår et pas.
    """
    conn = connect()
    try:
        return metrics.schedule(conn, days_ahead=dage_frem)
    finally:
        conn.close()


@mcp.tool()
def kropsudvikling(dage: int = 90) -> dict:
    """Vægtudvikling over perioden og VO2max-tendens.

    Brug dette til spørgsmål om form, vægt og udholdenhedsudvikling. Bemærk at
    vægt kun findes hvis der er vejet på en Garmin-vægt eller indtastet manuelt.
    """
    conn = connect()
    try:
        return metrics.body_trend(conn, days=dage)
    finally:
        conn.close()


@mcp.tool()
def dagens_status() -> dict:
    """Samlet øjebliksbillede: restitution, belastning, de seneste fem pas og de
    næste tre dages kalender i ét kald.

    Start med dette når brugeren stiller et bredt spørgsmål som "hvad skal jeg
    træne i dag", "hvordan ser det ud" eller beder om en daglig briefing.
    """
    conn = connect()
    try:
        recent = _activities(conn, dage=10)[:5]
        return {
            "dato": date.today().isoformat(),
            "sidste_sync": get_state(conn, "last_garmin_sync"),
            "restitution": metrics.recovery(conn, days=14),
            "belastning": metrics.training_load(conn, weeks=6),
            "seneste_pas": recent,
            "kalender": metrics.schedule(conn, days_ahead=3),
            "datafriskhed": metrics.freshness(conn),
        }
    finally:
        conn.close()


@mcp.tool()
def opslag(sql: str) -> dict:
    """Kør en skrivebeskyttet SELECT direkte mod databasen, når de øvrige
    værktøjer ikke dækker spørgsmålet.

    Svaret er {"rækker": [...], "antal": n, "afkortet": bool}. Højst 500
    rækker returneres; står "afkortet" til true, mangler der rækker, og så
    skal du aggregere i SQL i stedet for at tælle eller summere selv.

    Tabeller: activities(activity_id, start_local, date, sport, name,
    duration_s, distance_m, avg_hr, max_hr, elev_gain_m, calories, garmin_load,
    aerobic_te, anaerobic_te, raw), daily(date, resting_hr, hrv_last_night,
    hrv_status, sleep_s, deep_s, rem_s, light_s, awake_s, sleep_score,
    stress_avg, bb_high, bb_low, steps, training_readiness, vo2max, weight_kg),
    activity_zones(activity_id, zone, seconds, low_bpm),
    hevy_workouts(workout_id, activity_id, title, start_utc, end_utc,
    updated_at, raw), hevy_sets(workout_id, exercise_index, set_index,
    exercise, template_id, set_type, weight_kg, reps, duration_s, distance_m,
    rpe). hevy_workouts.activity_id peger på passet i activities; set_type
    er warmup/normal/dropset/failure, og rpe er NULL når den ikke er udfyldt.
    calendar_events(uid, start_local, end_local, start_utc, end_utc, summary,
    all_day). Datoer er ISO-strenge.

    Tider: start_local/end_local er lokal tid uden offset ('2026-09-23T08:00'),
    så time(), date() og strftime() giver det klokkeslæt der står i
    kalenderen. start_utc/end_utc er de samme tidspunkter i UTC.
    Heldagsbegivenheder har all_day = 1 og starter kl. 00:00.

    activities.raw er Garmins fulde JSON for passet. Blandt andet:
      tid i pulszone (sekunder):  json_extract(raw, '$.hrTimeInZone_1') .. _5
      styrkepas fra Hevy (øvelser, sæt, vægt × gentagelser som tekst):
        SELECT date, json_extract(raw, '$.description') FROM activities
        WHERE sport = 'strength_training' ORDER BY date DESC LIMIT 5

    Lad SQL'en lave aggregeringen frem for at hente mange rækker hjem.
    """
    cleaned = sql.strip().rstrip(";")
    if not cleaned.lower().startswith(("select", "with")):
        raise ToolError("Kun SELECT- og WITH-forespørgsler er tilladt")
    conn = connect_readonly()
    # SQLite spørger handleren for hver 10.000 trin og afbryder forespørgslen, når den svarer sandt
    slut = time.monotonic() + OPSLAG_SEKUNDER
    conn.set_progress_handler(lambda: time.monotonic() > slut, 10_000)
    try:
        rows = conn.execute(cleaned).fetchmany(OPSLAG_MAX_ROWS + 1)
    except sqlite3.OperationalError as exc:
        if time.monotonic() > slut:
            raise ToolError(f"Forespørgslen tog over {OPSLAG_SEKUNDER} sekunder og blev stoppet. "
                            "Afgræns den med WHERE, eller aggregér i SQL.") from exc
        raise ToolError(f"SQLite: {exc}") from exc
    except sqlite3.Error as exc:
        # ToolError når frem til modellen med teksten, så den kan rette sin
        # SQL. Andre undtagelser bliver til en generisk fejl uden forklaring.
        raise ToolError(f"SQLite: {exc}") from exc
    finally:
        conn.close()
    return {
        "rækker": [dict(r) for r in rows[:OPSLAG_MAX_ROWS]],
        "antal": min(len(rows), OPSLAG_MAX_ROWS),
        "afkortet": len(rows) > OPSLAG_MAX_ROWS,
    }


@mcp.tool()
def pulszoner(dage: int = 28) -> dict:
    """Faktisk tid i hver pulszone, målt af Garmin sekund for sekund, plus
    fordelingen på let, moderat og hårdt og din laktattærskel hvis den er sat.

    Brug dette ved alle spørgsmål om intensitet, zoner, polarisering eller om
    de lette pas er for hårde. Konstruér ALDRIG selv zonegrænser ud fra procent
    af makspuls — det ignorerer hvor brugerens tærskel faktisk ligger, og at
    lægge et helt pas i én zone efter gennemsnitspulsen undervurderer
    intervaltræning kraftigt. Siger feltet "kilde" at det er et skøn, så sig
    det videre til brugeren.
    """
    conn = connect()
    try:
        return metrics.zone_distribution(conn, days=dage)
    finally:
        conn.close()


@mcp.tool()
def periode(start: str, slut: str) -> dict:
    """Alle nøgletal for én periode (start og slut som 'YYYY-MM-DD', begge
    inklusive): sundhed, træning, styrke fra Hevy og studie fra kalenderen.

    Brug dette til periodevise rapporter og sammenligninger, fx Form &
    Fokus-siden. Felterne har samme navne og format som siden, så tallene kan
    skrives direkte uden omregning. "forbehold" lister det der gør tallene
    mindre sikre (manglende dage, pas uden belastning, skiftende zonegrænser,
    lav RPE-dækning, manglende kalenderdata) — tag dem med i vurderingen.

    belastning er i TRIMP-enheder som i traeningsbelastning; styrke.haarde_saet
    er antal arbejdssæt (uden opvarmning og kardio). saet_rpe_9_plus er null når
    under 60 % af sættene har RPE. styrke.e1rm har estimeret 1RM (Epley) for
    hver øvelse med stang eller håndvægt og højst 12 gentagelser; styrke.loeft
    har navn, bedste sæt og dets RPE. Er rpe null, kan et fald bare være et
    lettere sæt. studie er null når kalenderen ikke dækker hele perioden, og
    selvstudie er null før CalTask-logningen begyndte (ikke logget, ikke 0).
    """
    conn = connect()
    try:
        return metrics.periode_rapport(conn, start, slut)
    except ValueError as exc:
        raise ToolError(f"Ugyldig dato: {exc}") from exc
    finally:
        conn.close()


@mcp.tool()
def maanedsoversigt(fra_maaned: str | None = None) -> dict:
    """Det store billede: søvn, HRV, hvilepuls, VO2max, vægt, skridt og
    træning måned for måned, fra fra_maaned ('ÅÅÅÅ-MM') eller første måned
    med data.

    Brug dette til spørgsmål om lange tendenser: "er jeg i bedre form end
    sidste år", "hvordan har min søvn udviklet sig", "træner jeg mere nu".
    Mængder er pr. uge, så måneder kan sammenlignes. "udvikling" holder de
    første tre fulde måneder op mod de seneste tre — brug den frem for selv at
    regne på rækkerne. Læs "forbehold": intensitetsfordelingen er ikke
    sammenlignelig over hele perioden, og måneder med få målinger er usikre.
    """
    conn = connect()
    try:
        return metrics.maanedsoversigt(conn, fra_maaned)
    except ValueError as exc:
        raise ToolError(f"Ugyldig måned: {exc}") from exc
    finally:
        conn.close()


@mcp.tool()
def profil() -> dict:
    """Hvilke fysiologiske tal beregningerne kører på, og hvor hvert tal kommer fra.

    Brug dette hvis brugeren tvivler på om belastningstallene er troværdige,
    eller spørger hvordan noget er regnet ud. Står en kilde som
    "standardværdi (upålidelig)", bør du sige det højt — så er tallet gættet,
    og alt der bygger på det skal tages med forbehold.
    """
    conn = connect()
    try:
        a = metrics.athlete(conn)
        return {
            "makspuls": a.hr_max,
            "hvilepuls": a.hr_rest,
            "køn": a.sex,
            "kilder": a.sources,
            "forklaring": (
                "Makspuls: manuelt sat, ellers Garmins konfigurerede makspuls "
                "(samme tal som pulszonerne bygger på), ellers tredjehøjeste "
                "registrerede puls det seneste år. Den registrerede er et gulv, "
                "ikke en testet makspuls, og bruges kun foran Garmins tal hvis "
                "den ligger over. Hvilepuls: manuelt sat, ellers median af målt "
                "hvilepuls de seneste 60 dage, ellers Garmins profil."
            ),
        }
    finally:
        conn.close()


# Garmin kaldes med pause mellem hvert kald, så 16 dage tager over to
# minutter — længere end klienten venter på et værktøjskald. Syncen kører
# derfor i en baggrundstråd, og værktøjet svarer senest efter SYNC_WAIT_S.
SYNC_WAIT_S = 45
_sync_lock = threading.Lock()
_sync_job: dict = {}


def _run_sync_job(job: dict, dage: int, inkluder_kalender: bool) -> None:
    from .ingest_calendar import sync_calendar
    from .ingest_garmin import run_sync

    try:
        result = run_sync(days=dage)
        if inkluder_kalender:
            conn = connect()
            try:
                result["kalender"] = sync_calendar(conn)
            finally:
                conn.close()
        job["result"] = result
    except Exception as exc:  # noqa: BLE001
        logging.exception("Sync fejlede")
        job["fejl"] = str(exc)


@mcp.tool()
def sync(dage: int = 7, inkluder_kalender: bool = True) -> dict:
    """Hent nye data fra Garmin og kalenderen ind i den lokale database.

    Kør kun dette når brugeren beder om friske tal, eller når de øvrige
    værktøjer viser at sidste sync ligger mere end et døgn tilbage. Garmin
    kaldes skånsomt, så en sync tager 1–3 minutter. Den kører i baggrunden:
    er den ikke færdig inden for 45 sekunder, svarer værktøjet med status
    "kører". Kald så sync igen (med samme argumenter). Det starter ikke en ny
    sync, men venter videre og returnerer resultatet når det er klar.
    """
    global _sync_job
    with _sync_lock:
        job = _sync_job
        thread = job.get("thread")
        running = thread is not None and thread.is_alive()
        undelivered = thread is not None and not running and not job.get("leveret")
        if not running and not undelivered:
            job = {"startet": datetime.now().isoformat(timespec="seconds"), "dage": dage}
            job["thread"] = threading.Thread(
                target=_run_sync_job, args=(job, dage, inkluder_kalender),
                name="garmin-sync", daemon=True,
            )
            _sync_job = job
            job["thread"].start()

    job["thread"].join(timeout=SYNC_WAIT_S)
    if job["thread"].is_alive():
        return {
            "status": "kører",
            "startet": job["startet"],
            "dage": job["dage"],
            "besked": "Syncen kører stadig i baggrunden. Kald sync igen for at "
                      "vente videre og få resultatet.",
        }
    with _sync_lock:
        job["leveret"] = True
    if "fejl" in job:
        raise ToolError(f"Sync fejlede: {job['fejl']}")
    return {"status": "færdig", "startet": job["startet"], **job["result"]}


# --------------------------------------------------------------------------
# Prompt: rammen modellen skal fortolke tallene indenfor
# --------------------------------------------------------------------------

@mcp.prompt()
def ugeplan(maal: str = "generel form") -> str:
    """Færdig oplæg til at lægge den kommende uges træning."""
    return (
        f"Læg min træning for den kommende uge med {maal} for øje.\n\n"
        "Hent først dagens status og kalenderen. Placér passene i de frie "
        "vinduer der faktisk findes, og lad den samlede belastning følge "
        "naturligt af de seneste ugers udvikling frem for at springe. "
        "Sig tydeligt hvilke pas der er de vigtige, og hvad jeg kan droppe "
        "hvis ugen skrider."
    )


@mcp.prompt()
def evaluering(uger: int = 6) -> str:
    """Tilbageblik på de seneste ugers træning."""
    return (
        f"Kig på de seneste {uger} ugers træning og restitution. "
        "Hvad er mønsteret, hvad går den rigtige vej, og hvor er der noget "
        "der ikke hænger sammen? Vær konkret om hvad jeg bør ændre."
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
