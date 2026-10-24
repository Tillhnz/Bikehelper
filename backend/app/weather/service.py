"""Wetter für importierte Fahrten von Open-Meteo holen (kostenlos, ohne Schlüssel, für private Nutzung).

Die Abfragen werden gebündelt (eine je Gitterzelle und Zeitraum von bis zu 90 Tagen) und gedrosselt, damit das
kostenlose Limit (600 pro Minute, 10.000 pro Tag) weit unterschritten bleibt. Es werden nur die gerundeten
Startkoordinaten der Fahrten und Zeiträume an Open-Meteo gesendet, keine Konto- oder Fahrtnamen.
Daten: Open-Meteo.com, Lizenz CC BY 4.0.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import Activity
from . import core

log = logging.getLogger("bikehelper.weather")

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY = "temperature_2m,precipitation,wind_speed_10m,weather_code"
PAUSE_BETWEEN_REQUESTS_S = 0.6
SCHEDULE_INTERVAL_S = 6 * 3600


class RateLimited(Exception):
    pass


def fetch_window(client: httpx.Client, w: core.Window) -> core.Series:
    params: dict = {
        "latitude": w.lat,
        "longitude": w.lng,
        "hourly": HOURLY,
        "timezone": "GMT",
        "wind_speed_unit": "kmh",
    }
    if w.recent:
        url = FORECAST_URL  # das Archiv hinkt etwa 5 Tage hinterher
        params.update(past_days=10, forecast_days=1)
    else:
        url = ARCHIVE_URL
        params.update(start_date=w.start_date.isoformat(), end_date=w.end_date.isoformat())
    r = client.get(url, params=params)
    if r.status_code == 429:
        raise RateLimited()
    r.raise_for_status()
    return core.parse_hourly(r.json())


_lock = threading.Lock()
_progress: dict = {"running": False, "total": 0, "done": 0, "error": None, "finished_at": None}


def _today():
    return datetime.now(timezone.utc).date()


def _candidates(db: Session, user_id: int | None) -> list[core.Item]:
    q = select(
        Activity.id, Activity.start_lat, Activity.start_lng, Activity.start_date,
        Activity.moving_time_s, Activity.weather_status,
    ).where(Activity.start_lat.is_not(None), Activity.start_lng.is_not(None))
    if user_id is not None:
        q = q.where(Activity.user_id == user_id)
    today = _today()
    items = []
    for aid, lat, lng, start, dur, status in db.execute(q):
        age_days = (today - start.date()).days
        # offen, oder vorläufig und inzwischen im Archiv verfügbar
        if status is None or (status == "prelim" and age_days >= core.ARCHIVE_DELAY_DAYS):
            items.append(core.Item(aid, lat, lng, start, dur or 0))
    return items


def enrich(user_id: int | None = None, fetch=fetch_window, pause: float = PAUSE_BETWEEN_REQUESTS_S) -> None:
    """Holt Wetter für alle Fahrten ohne Wetterdaten (eines Nutzers oder aller)."""
    if not settings.weather_enabled:
        return
    if not _lock.acquire(blocking=False):
        return  # läuft schon
    try:
        _progress.update(running=True, total=0, done=0, error=None)
        with SessionLocal() as db:
            items = _candidates(db, user_id)
            _progress["total"] = len(items)
            windows = core.plan_windows(items, _today())
            with httpx.Client(headers={"User-Agent": "BikeHelper (self-hosted)"}, timeout=30) as client:
                for w in windows:
                    try:
                        series = fetch(client, w)
                    except RateLimited:
                        _progress["error"] = (
                            "Das Abfragelimit von Open-Meteo ist erreicht. Der nächste Versuch läuft automatisch später."
                        )
                        break
                    except Exception as e:  # Netzwerkfehler o. Ä.: überspringen, später erneut versuchen
                        log.warning("Wetterabruf fehlgeschlagen (%s, %s): %s", w.lat, w.lng, e)
                        _progress["done"] += len(w.items)
                        continue
                    if not series:
                        _progress["done"] += len(w.items)
                        continue
                    for it in w.items:
                        s = core.summarize(series, it.start, it.duration_s)
                        values: dict = {"weather_status": "none" if s is None else ("prelim" if w.recent else "ok")}
                        if s is not None:
                            values.update(
                                temp_c=s.temp_c, precip_mm=s.precip_mm, wind_kmh=s.wind_kmh,
                                wet_minutes=s.wet_minutes, weather_code=s.weather_code,
                            )
                        db.execute(update(Activity).where(Activity.id == it.activity_id).values(**values))
                    db.commit()
                    _progress["done"] += len(w.items)
                    if pause:
                        time.sleep(pause)
    except Exception as e:
        log.exception("Wetter-Anreicherung fehlgeschlagen")
        _progress["error"] = f"Wetterabruf fehlgeschlagen: {e}"
    finally:
        _progress.update(running=False, finished_at=time.time())
        _lock.release()


def trigger(user_id: int | None = None) -> None:
    """Startet die Anreicherung im Hintergrund (z. B. nach einem Import)."""
    if settings.weather_enabled:
        threading.Thread(target=enrich, args=(user_id,), daemon=True, name="weather-enrich").start()


def start_background() -> None:
    """Prüft regelmäßig, ob neue Fahrten Wetterdaten brauchen (auch vorläufige werden später ersetzt)."""
    def loop() -> None:
        time.sleep(60)
        while True:
            try:
                if settings.weather_enabled:  # kann der Administrator in der Oberfläche ändern
                    enrich(None)
            except Exception:
                log.exception("Geplante Wetter-Anreicherung fehlgeschlagen")
            time.sleep(SCHEDULE_INTERVAL_S)

    threading.Thread(target=loop, daemon=True, name="weather-scheduler").start()


def coverage(db: Session, user_id: int) -> dict:
    rows = db.execute(
        select(Activity.weather_status, Activity.start_lat.is_not(None), func.count())
        .where(Activity.user_id == user_id)
        .group_by(Activity.weather_status, Activity.start_lat.is_not(None))
    ).all()
    counts = {"with_location": 0, "without_location": 0, "ok": 0, "prelim": 0, "none": 0, "pending": 0}
    for status, has_loc, n in rows:
        if not has_loc:
            counts["without_location"] += n
            continue
        counts["with_location"] += n
        counts[status or "pending"] += n
    return {
        **counts,
        "enabled": settings.weather_enabled,
        "running": _progress["running"],
        "progress_total": _progress["total"],
        "progress_done": _progress["done"],
        "error": _progress["error"],
    }
