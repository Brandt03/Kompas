"""Stier til de tre kilder. Standardværdierne passer til maskinen; hver kan
overstyres med en miljøvariabel."""

from __future__ import annotations

import os
from pathlib import Path


def _path(env: str, default: str) -> Path:
    return Path(os.environ.get(env) or default).expanduser()


# Egen database med én række pr. uge.
DB_PATH = _path("LIV_DB", "~/.livsoverblik/liv.db")

# garmin-coach's SQLite. Læses kun, skrives aldrig.
GARMIN_DB = _path("LIV_GARMIN_DB", "~/.garmin-coach/coach.db")

# Sures eksport, som launchd skriver hvert 5. minut mens Sure kører.
SURE_JSON = _path("LIV_SURE_JSON", "~/kompas/okonomi/dashboard/public/data.json")

# Kalenderbegivenheder, hvis titel indeholder kursuskodens præfiks (fx "KURS101"), tæller som undervisning.
KURSUSKODE = os.environ.get("LIV_KURSUSKODE", "KURS")

# Selvstudie logges med CalTask som kalenderbegivenheder, fx "Selvstudie · Alfa".
SELVSTUDIE_PRAEFIKS = os.environ.get("LIV_SELVSTUDIE_PRAEFIKS", "Selvstudie ·")
# Dagen logningen begyndte. Uger før er ukendte, ikke 0 timer.
SELVSTUDIE_FRA = os.environ.get("LIV_SELVSTUDIE_FRA", "2026-09-28")

# Form & Fokus-siden, som Caddy leverer på https://localhost/form/. liv.json
# lægges ved siden af garmin-coach's datafiler.
SITE_DIR = _path("LIV_SITE", "~/.garmin-coach/site")

# Første uge der beregnes. Garmin-historikken starter i juni 2025, og før
# den er der intet at sammenligne økonomien med.
FOERSTE_UGE = os.environ.get("LIV_FRA", "2025-06-02")
