"""Fælles opsætning: testene rører aldrig de rigtige data eller netværket.

Miljøet sættes, før garmin_coach importeres. Variabler, der allerede er sat, vinder over .env, så de
tomme værdier holder de rigtige kalenderadresser og Hevy-nøglen ude af testene.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="garmin-coach-test-"))
os.environ["GC_DB"] = str(_TMP / "coach.db")
os.environ["GC_SITE"] = str(_TMP / "site")
os.environ["GC_ICS_URLS"] = ""
os.environ["HEVY_API_KEY"] = ""
os.environ["GARMINTOKENS"] = str(_TMP / "garminconnect")

import pytest  # noqa: E402

from garmin_coach.db import connect  # noqa: E402


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    c = connect(tmp_path / "coach.db")
    yield c
    c.close()
