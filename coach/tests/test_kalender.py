"""Opg. 1: kalenderens hemmelige adresser står aldrig i fejlbeskeder eller loggen, kun værtsnavnet.
Og last_calendar_sync gemmes kun efter en vellykket hentning."""

import http.client
import logging
import socket
import traceback
import urllib.error
from datetime import date

import pytest

from garmin_coach import ingest_calendar as ic
from garmin_coach.config import CONFIG
from garmin_coach.db import get_state

DELT = "https://calendar.example.com/calendar/ical/abc%40group.calendar.example.com/private-HEMMELIGDELT/basic.ics"
PUBLICERET = "webcal://p01-caldav.example.net/published/2/HEMMELIGPUBLICERET"
SKEMA = "https://skema.example.edu/ical/HEMMELIGSKEMA?token=HEMMELIGTOKEN"
HEMMELIGT = ("HEMMELIG", "private-", "/published/", "/ical/", "token=")

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//test//DA
X-WR-CALNAME:Test
BEGIN:VEVENT
UID:a1
DTSTART:%(d)sT080000Z
DTEND:%(d)sT100000Z
SUMMARY:Forel\xc3\xa6sning
END:VEVENT
END:VCALENDAR
""" % {b"d": date.today().strftime("%Y%m%d").encode()}


def _ingen_hemmeligheder(tekst: str) -> None:
    for h in HEMMELIGT:
        assert h not in tekst, f"{h!r} slap igennem: {tekst}"


def test_vaert():
    assert ic.vaert(DELT) == "calendar.example.com"
    assert ic.vaert(PUBLICERET) == "p01-caldav.example.net"
    assert ic.vaert(SKEMA) == "skema.example.edu"
    assert ic.vaert("~/kalender.ics") == "lokal fil"


@pytest.mark.parametrize("kilde, tekst", [
    (DELT, f"unknown url type: {DELT}"),
    (PUBLICERET, f"<urlopen error for {PUBLICERET.replace('webcal://', 'https://')}>"),
    (SKEMA, "URL can't contain control characters. '/ical/HEMMELIGSKEMA?token=HEMMELIGTOKEN' (found at least ' ')"),
    (SKEMA, "HTTPSConnectionPool(host='skema.example.edu', port=443): Max retries exceeded with url: "
          "/ical/HEMMELIGSKEMA?token=HEMMELIGTOKEN"),
])
def test_masker_fjerner_adresse_sti_og_forespoergsel(kilde, tekst):
    ud = ic.masker(tekst, kilde)
    _ingen_hemmeligheder(ud)
    assert f"<{ic.vaert(kilde)}>" in ud


def test_masker_uden_kilde_tager_alle_adresser():
    ud = ic.masker(f"to fejl: {DELT} og {PUBLICERET}")
    assert ud == "to fejl: <calendar.example.com> og <p01-caldav.example.net>"


def _fejl(url):
    return {
        DELT: urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided, or not known")),
        PUBLICERET: ValueError(f"unknown url type: {url}"),
        SKEMA: http.client.InvalidURL("URL can't contain control characters. '/ical/HEMMELIGSKEMA?token=HEMMELIGTOKEN'"),
    }[next(k for k in (DELT, PUBLICERET, SKEMA) if ic.vaert(k) in url)]


def test_fejlede_feeds_logges_kun_med_vaertsnavn(conn, monkeypatch, caplog):
    monkeypatch.setattr(CONFIG, "ics_sources", [DELT, PUBLICERET, SKEMA])

    def urlopen(url, **kw):
        raise _fejl(url)

    monkeypatch.setattr(ic, "urlopen", urlopen)
    with caplog.at_level(logging.DEBUG):
        res = ic.sync_calendar(conn)
    assert res == {"begivenheder": 0, "fejlede_feeds": 3}
    log = caplog.text
    _ingen_hemmeligheder(log)
    for vaert in ("calendar.example.com", "p01-caldav.example.net", "skema.example.edu"):
        assert vaert in log
    assert "nodename nor servname" in log  # årsagen står der stadig
    assert get_state(conn, "last_calendar_sync") is None


def test_undtagelsen_fra_load_baerer_ikke_adressen_i_kaeden(monkeypatch):
    monkeypatch.setattr(ic, "urlopen", lambda url, **kw: (_ for _ in ()).throw(_fejl(url)))
    with pytest.raises(ic.KalenderFejl) as info:
        ic._load(PUBLICERET)
    assert str(info.value).startswith("p01-caldav.example.net: ")
    _ingen_hemmeligheder("".join(traceback.format_exception(info.value)))


def test_last_calendar_sync_kun_ved_vellykket_hentning(conn, monkeypatch):
    monkeypatch.setattr(CONFIG, "ics_sources", [DELT, SKEMA])
    monkeypatch.setattr(ic, "_load", lambda source: ICS)
    assert ic.sync_calendar(conn)["fejlede_feeds"] == 0
    assert get_state(conn, "last_calendar_sync") == date.today().isoformat()

    # Én fejlende kilde: tidspunktet bliver stående fra sidst og flyttes ikke
    conn.execute("UPDATE sync_state SET value = '2026-01-01' WHERE key = 'last_calendar_sync'")
    conn.commit()

    def halvt(source):
        if source == SKEMA:
            raise ic.KalenderFejl("skema.example.edu: timed out")
        return ICS

    monkeypatch.setattr(ic, "_load", halvt)
    assert ic.sync_calendar(conn)["fejlede_feeds"] == 1
    assert get_state(conn, "last_calendar_sync") == "2026-01-01"


def test_ingen_kalender_sat_op_gemmer_intet_tidspunkt(conn, monkeypatch):
    monkeypatch.setattr(CONFIG, "ics_sources", [])
    ic.sync_calendar(conn)
    assert get_state(conn, "last_calendar_sync") is None


def test_plan_blok_kommer_fra_maerket_i_beskrivelsen(conn, monkeypatch):
    d = date.today().strftime("%Y%m%d")
    ics = (f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//test//DA\r\n"
           f"BEGIN:VEVENT\r\nUID:plan\r\nDTSTART:{d}T080000Z\r\nDTEND:{d}T090000Z\r\nSUMMARY:Alpha · fagnoter\r\n"
           f"DESCRIPTION:Databases.\\n{ic.PLAN_MAERKE}\r\nEND:VEVENT\r\n"
           f"BEGIN:VEVENT\r\nUID:tand\r\nDTSTART:{d}T100000Z\r\nDTEND:{d}T110000Z\r\nSUMMARY:Tandlæge\r\nEND:VEVENT\r\n"
           f"END:VCALENDAR\r\n").encode()
    monkeypatch.setattr(CONFIG, "ics_sources", [DELT])
    monkeypatch.setattr(ic, "_load", lambda source: ics)
    ic.sync_calendar(conn)
    plan = dict(conn.execute("SELECT uid, plan_blok FROM calendar_events").fetchall())
    assert plan == {"plan": 1, "tand": 0}

    # Fjernes mærket, er blokken ikke længere en del af planen
    monkeypatch.setattr(ic, "_load", lambda source: ics.replace(ic.PLAN_MAERKE.encode(), b""))
    ic.sync_calendar(conn)
    assert conn.execute("SELECT plan_blok FROM calendar_events WHERE uid = 'plan'").fetchone()[0] == 0
