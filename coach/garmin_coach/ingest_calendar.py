"""Kalender-import fra .ics-feeds.

Bevidst valgt frem for Google Calendar API: en hemmelig iCal-adresse virker med
Google, Apple og Outlook, kræver ingen OAuth-dans, og kan pege på en lokal fil.
I Google Kalender finder du den under Indstillinger → din kalender →
"Hemmelig adresse i iCal-format".
"""

from __future__ import annotations

import logging
import sqlite3
import ssl
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from .config import CONFIG
from .db import connect, get_state, set_state, split_local_utc, upsert

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


def _load(source: str) -> bytes:
    if source.startswith(("http://", "https://", "webcal://")):
        url = source.replace("webcal://", "https://", 1)
        with urlopen(url, timeout=30, context=_SSL) as resp:  # noqa: S310
            return resp.read()
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
    for source in CONFIG.ics_sources:
        try:
            cal = Calendar.from_ical(_load(source))
            events.extend(recurring_ical_events.of(cal).between(window_start, window_end))
        except Exception as exc:  # noqa: BLE001
            log.error("Kunne ikke læse kalender %s: %s", source[:60], exc)
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

    count = 0
    for event in events:
        start_raw = event.get("DTSTART")
        end_raw = event.get("DTEND")
        if start_raw is None:
            continue
        start_iso, start_utc, all_day = _as_local(start_raw.dt, tz)
        end_iso, end_utc, _ = (
            _as_local(end_raw.dt, tz) if end_raw is not None else (None, None, False)
        )
        upsert(
            conn,
            "calendar_events",
            {
                "uid": str(event.get("UID", "")) or f"nouid-{start_iso}",
                "start_local": start_iso,
                "end_local": end_iso,
                "start_utc": start_utc,
                "end_utc": end_utc,
                "summary": str(event.get("SUMMARY", "(uden titel)")),
                "all_day": 1 if all_day else 0,
            },
            pk=["uid", "start_local"],
        )
        count += 1

    conn.commit()
    return {"begivenheder": count, "fejlede_feeds": failed}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    c = connect()
    print(sync_calendar(c))
    c.close()
