"""Kalender-import fra .ics-feeds.

Bevidst valgt frem for Google Calendar API: en hemmelig iCal-adresse virker med
Google, Apple og Outlook, kræver ingen OAuth-dans, og kan pege på en lokal fil.
I Google Kalender finder du den under Indstillinger → din kalender →
"Hemmelig adresse i iCal-format".
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import ssl
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from .config import CONFIG
from .db import connect, gem_fag, get_state, set_state, split_local_utc, upsert

log = logging.getLogger(__name__)


def _ssl_context() -> ssl.SSLContext:
    """Brug certifi's certifikatliste hvis den findes.

    Python installeret fra python.org bruger ikke macOS' eget nøglering og har
    en tom liste indtil "Install Certificates.command" er kørt. certifi følger
    med requests, som garminconnect alligevel trækker ind, så vi peger bare
    direkte på den og undgår problemet helt.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_SSL = _ssl_context()


_URL = re.compile(r"(?:https?|webcal)://[^\s'\"<>()]+", re.IGNORECASE)


class KalenderFejl(RuntimeError):
    """Et feed kunne ikke hentes. Beskeden nævner kun værtsnavnet, aldrig adressen."""


def vaert(source: str) -> str:
    """Det eneste fra en kalenderadresse, der må stå i en fejlbesked eller en log.

    En hemmelig iCal-adresse er selve adgangen til kalenderen: stien og
    forespørgslen er nøglen, så kun værtsnavnet er ufarligt at vise.
    """
    if _URL.match(source):
        return urlsplit(source).hostname or "ukendt vært"
    return "lokal fil"


def masker(tekst: str, source: str | None = None) -> str:
    """Fjern kalenderadresser fra en tekst, fx en undtagelse fra urllib.

    Hver adresse erstattes af sit værtsnavn. Kendes kilden, fjernes også dens
    sti og forespørgsel alene, fordi nogle undtagelser (fx http.client.InvalidURL)
    citerer stien uden værten.
    """
    if source and _URL.match(source):
        dele = urlsplit(source.replace("webcal://", "https://", 1))
        for stykke in sorted({source, source.replace("webcal://", "https://", 1),
                              dele.path + ("?" + dele.query if dele.query else ""),
                              dele.path, dele.query}, key=len, reverse=True):
            if len(stykke) > 1:
                tekst = tekst.replace(stykke, f"<{vaert(source)}>")
    return _URL.sub(lambda m: f"<{vaert(m.group())}>", tekst)


def _load(source: str) -> bytes:
    if source.startswith(("http://", "https://", "webcal://")):
        url = source.replace("webcal://", "https://", 1)
        try:
            with urlopen(url, timeout=30, context=_SSL) as resp:  # noqa: S310
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            # Undtagelser fra urllib kan citere adressen (fx "unknown url type: ..."), og en
            # traceback viser kæden. Omformulér, og skjul den oprindelige undtagelse.
            raise KalenderFejl(f"{vaert(source)}: {masker(str(exc) or type(exc).__name__, source)}") from None
    return Path(source).expanduser().read_bytes()


def _as_local(value, tz: ZoneInfo) -> tuple[str, str | None, bool]:
    """Returnerer (lokal vægurstid uden offset, UTC, er_heldagsbegivenhed).

    Lokaltiden gemmes uden offset, fordi SQLites datofunktioner ellers
    omregner den til UTC, og rå SQL så viser forkerte klokkeslæt.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=tz)
        local, utc = split_local_utc(value.astimezone(tz).isoformat(timespec="minutes"))
        return local, utc, False
    if isinstance(value, date):
        midnight = datetime(value.year, value.month, value.day, tzinfo=tz)
        local, utc = split_local_utc(midnight.isoformat(timespec="minutes"))
        return local, utc, True
    return str(value), None, False


def sync_calendar(conn: sqlite3.Connection, days_back: int = 14, days_ahead: int = 21) -> dict:
    """Hent kalenderen for vinduet [i dag - days_back, i dag + days_ahead].

    Alle feeds hentes før noget ryddes. Tidligere blev vinduet ryddet først,
    så et feed der ikke kunne hentes efterlod en tom kalender indtil næste
    sync — og en rapport der så ud som om der ingen undervisning var.
    """
    import recurring_ical_events
    from icalendar import Calendar

    if not CONFIG.ics_sources:
        log.warning("Ingen GC_ICS_URLS sat — springer kalender over")
        return {"begivenheder": 0, "status": "ingen kalender sat op"}

    tz = ZoneInfo(CONFIG.timezone)
    today = date.today()
    window_start = today - timedelta(days=days_back)
    window_end = today + timedelta(days=days_ahead)

    events, failed = [], 0
    for nr, source in enumerate(CONFIG.ics_sources, 1):
        try:
            cal = Calendar.from_ical(_load(source))
            # Kalenderens eget navn fra feedet (aldrig adressen, den er hemmelig), så siderne kan slå den til og fra
            navn = str(cal.get("X-WR-CALNAME") or "").strip() or f"Kalender {nr}"
            events.extend((e, navn) for e in recurring_ical_events.of(cal).between(window_start, window_end))
        except Exception as exc:  # noqa: BLE001
            # Aldrig adressen i loggen: den ender i ~/.kompas/opdater.log, og adressen er hemmelig
            besked = (str(exc) if isinstance(exc, KalenderFejl)
                      else f"{vaert(source)}: {masker(f'{type(exc).__name__}: {exc}', source)}")
            log.error("Kunne ikke læse kalender %d: %s", nr, besked)
            failed += 1

    if failed:
        # Uden en kildekolonne kan vi ikke se hvilke gemte begivenheder der
        # hører til det fejlende feed, så intet slettes. Aflyste begivenheder
        # bliver hængende til næste sync hvor alle feeds kan hentes.
        log.warning("%d af %d kalenderfeeds fejlede — beholder gemte begivenheder",
                    failed, len(CONFIG.ics_sources))
    else:
        # Ryd vinduet, så aflyste og flyttede begivenheder ikke bliver hængende
        conn.execute(
            "DELETE FROM calendar_events WHERE start_local >= ? AND start_local < ?",
            (window_start.isoformat(), (window_end + timedelta(days=1)).isoformat()),
        )
        covered = get_state(conn, "calendar_covered_from")
        if not covered or window_start.isoformat() < covered:
            set_state(conn, "calendar_covered_from", window_start.isoformat())
        # Kun når alle feeds kom igennem, som last_garmin_sync: datoen for seneste vellykkede hentning.
        # Overblik måler kalenderens friskhed på den.
        set_state(conn, "last_calendar_sync", date.today().isoformat())

    count = 0
    for event, kalender in events:
        start_raw = event.get("DTSTART")
        end_raw = event.get("DTEND")
        if start_raw is None:
            continue
        start_iso, start_utc, all_day = _as_local(start_raw.dt, tz)
        end_iso, end_utc, _ = (
            _as_local(end_raw.dt, tz) if end_raw is not None else (None, None, False)
        )
        uid = str(event.get("UID", "")) or f"nouid-{start_iso}"
        summary = str(event.get("SUMMARY", "(uden titel)"))
        upsert(
            conn,
            "calendar_events",
            {
                "uid": uid,
                "start_local": start_iso,
                "end_local": end_iso,
                "start_utc": start_utc,
                "end_utc": end_utc,
                "summary": summary,
                "all_day": 1 if all_day else 0,
                "kalender": kalender,
            },
            pk=["uid", "start_local"],
        )
        gem_fag(conn, uid, start_iso, summary)  # upsert springer tomme værdier over; fag-felterne skrives altid
        count += 1

    conn.commit()
    return {"begivenheder": count, "fejlede_feeds": failed}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    c = connect()
    # JSON på stdout, så Kompas' opdater.sh kan læse antallet af fejlede feeds
    print(json.dumps(sync_calendar(c)))
    c.close()
