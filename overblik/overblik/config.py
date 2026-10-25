"""Stier til de tre kilder. Standardværdierne passer til maskinen; hver kan
overstyres med en miljøvariabel."""

from __future__ import annotations

import os
from pathlib import Path


def _path(env: str, default: str) -> Path:
    return Path(os.environ.get(env) or default).expanduser()


# Vægtiden, som kalenderen og dagsplanen regner i (som garmin-coach's GC_TZ), uanset maskinens egen tidszone.
TZ = os.environ.get("LIV_TZ", "Europe/Copenhagen")

# Egen database med én række pr. uge.
DB_PATH = _path("LIV_DB", "~/.overblik/liv.db")

# garmin-coach's SQLite. Læses kun, skrives aldrig.
GARMIN_DB = _path("LIV_GARMIN_DB", "~/.garmin-coach/coach.db")

# Træningsbelastning pr. dag, regnet af garmin-coach (TRIMP, styrkepas via Hevy) og skrevet af dens `site byg`.
# Belastningen regnes kun dér; her lægges dagene sammen til uger.
BELASTNING_JSON = _path("LIV_BELASTNING_JSON", "~/.garmin-coach/site/belastning.json")

# Sures eksport, som launchd skriver hvert 5. minut mens Sure kører.
SURE_JSON = _path("LIV_SURE_JSON", "~/kompas/okonomi/dashboard/public/data.json")

# Skærmtid pr. dag, regnet af ~/kompas/skaermtid (skaermtid.py byg). Læses kun; her bruges sen skærmtid pr. aften.
SKAERMTID_JSON = _path("LIV_SKAERMTID_JSON", "~/.kompas/skaermtid/skaermtid.json")

# Studiets eksport (Kompas' Studie), hvor svarene pr. dag i Træning og På farten står pr. fag (fag[].status.rytme).
STUDIE_JSON = _path("LIV_STUDIE_JSON", "~/.kompas/studie/studie.json")

# Selvstudie logges med CalTask som kalenderbegivenheder, fx "Selvstudie · Alfa".
SELVSTUDIE_PRAEFIKS = os.environ.get("LIV_SELVSTUDIE_PRAEFIKS", "Selvstudie ·")
# Dagen logningen begyndte. Uger før er ukendte, ikke 0 timer.
SELVSTUDIE_FRA = os.environ.get("LIV_SELVSTUDIE_FRA", "2026-09-28")

# Form & fokus-mappen, som Caddy leverer på https://kompas.localhost/form/. liv.json
# lægges ved siden af garmin-coach's datafiler.
SITE_DIR = _path("LIV_SITE", "~/.garmin-coach/site")

# Første uge der beregnes. Garmin-historikken starter i juni 2025, og før
# den er der intet at sammenligne økonomien med.
FOERSTE_UGE = os.environ.get("LIV_FRA", "2025-06-02")
