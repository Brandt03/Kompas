"""Konfiguration. Alt læses fra miljøvariabler, så intet personligt ligger i koden."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    """Læs .env fra projektmappen ind i miljøet.

    Variabler der allerede er sat vinder, så Claude Desktops JSON kan overstyre
    filen hvis du vil have forskellige indstillinger de to steder. Uden det
    skulle samme værdi vedligeholdes begge steder.
    """
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        # Fjern eventuelle citationstegn folk kommer til at sætte omkring værdien
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _env_path(key: str, default: str) -> Path:
    return Path(os.environ.get(key, default)).expanduser()


def _env_opt_int(key: str) -> int | None:
    """Som _env_int, men returnerer None hvis variablen er tom eller mangler,
    så auto-udledningen kan tage over."""
    raw = (os.environ.get(key) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    # Hvor data ligger
    db_path: Path = field(default_factory=lambda: _env_path("GC_DB", "~/.garmin-coach/coach.db"))
    token_dir: Path = field(default_factory=lambda: _env_path("GARMINTOKENS", "~/.garminconnect"))

    # Garmin login (bruges kun første gang; derefter kører den på gemte tokens)
    garmin_email: str | None = field(default_factory=lambda: os.environ.get("GARMIN_EMAIL"))
    garmin_password: str | None = field(default_factory=lambda: os.environ.get("GARMIN_PASSWORD"))

    # Hevy (styrketræning). Kræver Hevy Pro; nøglen findes under Settings → API.
    hevy_api_key: str | None = field(
        default_factory=lambda: (os.environ.get("HEVY_API_KEY") or "").strip() or None
    )

    # Dine fysiologiske parametre. Lad dem stå tomme — så udleder programmet dem
    # selv fra Garmins profil og dine egne målinger. Sæt dem kun hvis du vil
    # overstyre med et tal du ved er rigtigt.
    hr_max: int | None = field(default_factory=lambda: _env_opt_int("GC_HR_MAX"))
    hr_rest: int | None = field(default_factory=lambda: _env_opt_int("GC_HR_REST"))
    # "m" eller "f" — styrer kun vægtningen i Banister-TRIMP-formlen.
    sex: str | None = field(
        default_factory=lambda: (os.environ.get("GC_SEX") or "").lower()[:1] or None
    )

    # Kalender: komma-separeret liste af .ics-URL'er eller lokale filstier.
    ics_sources: list[str] = field(
        default_factory=lambda: [
            s.strip() for s in os.environ.get("GC_ICS_URLS", "").split(",") if s.strip()
        ]
    )
    timezone: str = field(default_factory=lambda: os.environ.get("GC_TZ", "Europe/Copenhagen"))

    # Hvor lang en fri luge skal være for at tælle som et træningsvindue (minutter)
    min_training_window_min: int = field(
        default_factory=lambda: _env_int("GC_MIN_WINDOW", 60)
    )



CONFIG = Config()
