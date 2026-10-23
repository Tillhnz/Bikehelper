"""Zeitumrechnung: Eingaben erfolgen in Ortszeit, Fahrten liegen als UTC ohne Zeitzonenangabe in der Datenbank."""
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from .config import settings


def _tz():
    try:
        return ZoneInfo(settings.timezone)
    except Exception:  # unbekannte Zone: UTC verwenden
        return timezone.utc


def local_to_utc(day: date, at: time) -> datetime:
    """Ortszeit (Zeitzone aus den Einstellungen) als UTC ohne Zeitzonenangabe, passend zu Activity.start_date."""
    return datetime.combine(day, at, tzinfo=_tz()).astimezone(timezone.utc).replace(tzinfo=None)
