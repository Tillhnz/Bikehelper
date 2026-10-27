"""Automatischer Import aus intervals.icu.

intervals.icu sammelt Fahrten aus Garmin Connect, Wahoo, Zwift, Polar, Suunto, Hammerhead und mehr. Der Nutzer trägt
seinen persönlichen API-Schlüssel ein (intervals.icu → Einstellungen → Entwicklereinstellungen); BikeHelper holt damit
regelmäßig neue Fahrten als Originaldatei (FIT, GPX oder TCX). Von Strava stammende Fahrten gibt intervals.icu nicht
heraus, sie werden übersprungen (dafür gibt es den Strava-Export).

Die Anmeldung läuft per HTTP Basic: Benutzername `API_KEY`, Passwort der Schlüssel.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..importers import service as imports
from ..importers.parsers import ParseError, is_cycling, parse_activity_file
from ..models import Bike, IntervalsSeen, User

log = logging.getLogger("bikehelper.intervals")

FIRST_YEAR = 2015              # früher gab es intervals.icu noch nicht
DOWNLOADS_PER_RUN = 60
OVERLAP_DAYS = 14              # später hochgeladene Fahrten mit älterem Datum werden so noch erfasst
SCHEDULE_INTERVAL_S = 30 * 60

_lock = threading.Lock()
_running: set[int] = set()


class IntervalsError(Exception):
    """Fehler mit Text für den Nutzer."""


class RateLimited(IntervalsError):
    pass


@dataclass
class SyncResult:
    imported: int = 0
    duplicates: int = 0
    skipped: int = 0
    found: int = 0           # neue, noch nicht verarbeitete Aktivitäten laut intervals.icu
    strava: int = 0          # von Strava stammend: gibt intervals.icu nicht heraus
    no_file: int = 0         # ohne Originaldatei
    other_sport: int = 0
    remaining: int = 0
    note: str = ""
    errors: list[str] = field(default_factory=list)

    def text(self) -> str:
        parts = [f"{self.found} neue Aktivitäten bei intervals.icu gefunden", f"{self.imported} importiert"]
        if self.duplicates:
            parts.append(f"{self.duplicates} schon vorhanden")
        if self.strava:
            parts.append(f"{self.strava} von Strava (nicht abrufbar)")
        if self.no_file:
            parts.append(f"{self.no_file} ohne Datei")
        if self.other_sport:
            parts.append(f"{self.other_sport} andere Sportart")
        if self.errors:
            parts.append(f"{len(self.errors)} Fehler (z. B. {self.errors[0][:80]})")
        if self.remaining:
            parts.append(f"{self.remaining} folgen im nächsten Lauf")
        if self.note:
            parts.append(self.note)
        return ", ".join(parts)


def new_client(key: str) -> httpx.Client:
    return httpx.Client(timeout=30, auth=("API_KEY", key), base_url=settings.intervals_api_url.rstrip("/"))


def _get(http: httpx.Client, path: str, params: dict | None = None) -> httpx.Response:
    try:
        r = http.get(path, params=params)
    except httpx.HTTPError as e:
        raise IntervalsError(f"intervals.icu nicht erreichbar: {e.__class__.__name__}") from e
    if r.status_code == 429:
        raise RateLimited("intervals.icu-Limit erreicht, der nächste Lauf macht weiter")
    if r.status_code in (401, 403):
        raise IntervalsError("intervals.icu lehnt den API-Schlüssel ab. Bitte prüfe oder erneuere ihn.")
    return r


def check_key(key: str) -> str:
    """Prüft den Schlüssel und gibt den Namen des Kontos zurück."""
    with new_client(key) as http:
        r = _get(http, "/api/v1/athlete/0")
        if r.status_code >= 400:
            raise IntervalsError(f"intervals.icu antwortete mit Fehler {r.status_code}")
        data = r.json() if r.content else {}
    return str(data.get("name") or data.get("email") or "")[:80]


def list_activities(http: httpx.Client, oldest: date, newest: date) -> list[dict]:
    """Aktivitäten im Zeitraum, jahresweise abgefragt, damit die Antworten klein bleiben."""
    out: list[dict] = []
    year = oldest.year
    while year <= newest.year:
        lo = max(oldest, date(year, 1, 1))
        hi = min(newest, date(year, 12, 31))
        r = _get(http, "/api/v1/athlete/0/activities", {"oldest": lo.isoformat(), "newest": hi.isoformat()})
        if r.status_code >= 400:
            raise IntervalsError(f"intervals.icu antwortete mit Fehler {r.status_code}")
        data = r.json()
        if isinstance(data, list):
            out.extend(a for a in data if isinstance(a, dict))
        year += 1
    return out


def downloadable(a: dict) -> bool:
    """Strava-Fahrten und Einträge ohne Datei liefert intervals.icu nicht aus."""
    if not a.get("id") or a.get("_note"):
        return False
    return str(a.get("source") or "").upper() != "STRAVA"


def download(http: httpx.Client, activity_id: str) -> bytes | None:
    """Originaldatei (None, wenn es keine gibt). Größe begrenzt wie bei Uploads."""
    r = _get(http, f"/api/v1/activity/{activity_id}/file")
    if r.status_code in (404, 422):
        return None
    if r.status_code >= 400:
        raise IntervalsError(f"Dateiabruf fehlgeschlagen ({r.status_code})")
    if len(r.content) > imports.MAX_UPLOAD_FILE_BYTES:
        raise ParseError("Die Datei ist zu groß.")
    return r.content or None


def sync_user(db: Session, user: User, http: httpx.Client | None = None, max_downloads: int = DOWNLOADS_PER_RUN) -> SyncResult:
    result = SyncResult()
    own = http is None
    http = http or new_client(user.icu_api_key or "")
    try:
        today = date.today()
        oldest = (user.icu_synced_until - timedelta(days=OVERLAP_DAYS)) if user.icu_synced_until else date(FIRST_YEAR, 1, 1)
        known = set(db.scalars(select(IntervalsSeen.activity_id).where(IntervalsSeen.user_id == user.id)))
        new = [a for a in list_activities(http, oldest, today + timedelta(days=1)) if str(a.get("id")) not in known]
        new.sort(key=lambda a: a.get("start_date_local") or "", reverse=True)  # neueste zuerst
        bikes = db.scalars(select(Bike).where(Bike.user_id == user.id)).all()
        default = next((b for b in bikes if b.id == user.icu_bike_id), None)
        result.found = len(new)
        todo = []
        for a in new:  # Aussortieren kostet keinen Abruf
            if not downloadable(a):
                if str(a.get("source") or "").upper() == "STRAVA" or a.get("_note"):
                    result.strava += 1
                else:
                    result.no_file += 1
                _mark(db, user, str(a.get("id") or ""), "skipped")
                result.skipped += 1
            elif a.get("type") and not is_cycling(a["type"]):
                _mark(db, user, str(a.get("id") or ""), "skipped")
                result.other_sport += 1
                result.skipped += 1
            else:
                todo.append(a)
        todo, result.remaining = todo[:max_downloads], max(0, len(todo) - max_downloads)
        i = 0
        try:
            for i, a in enumerate(todo):
                _import_one(db, user, http, a, default, bikes, result)
        except RateLimited as e:
            result.remaining += len(todo) - i
            result.note = str(e)
        if result.remaining == 0:
            user.icu_synced_until = today
    except IntervalsError as e:
        user.icu_status = str(e)
        db.commit()
        raise
    finally:
        if own:
            http.close()
    user.icu_last_sync = datetime.utcnow()
    user.icu_status = result.text()
    db.commit()
    return result


def _mark(db: Session, user: User, activity_id: str, status: str) -> None:
    if not activity_id:
        return
    db.merge(IntervalsSeen(user_id=user.id, activity_id=activity_id[:40], status=status))
    db.commit()


def _import_one(db: Session, user: User, http: httpx.Client, a: dict, default: Bike | None, bikes: list[Bike], result: SyncResult) -> None:
    aid = str(a["id"])
    try:
        data = download(http, aid)
        if data is None:
            _mark(db, user, aid, "skipped")
            result.skipped += 1
            result.no_file += 1
            return
        ext = str(a.get("file_type") or "fit").lower().lstrip(".")
        parsed = parse_activity_file(f"intervals.{ext}", data)
    except ParseError as e:
        result.errors.append(f"{aid}: {e}")
        _mark(db, user, aid, "skipped")
        result.skipped += 1
        return
    except RateLimited:
        raise
    except IntervalsError as e:  # vorübergehend: nicht merken, beim nächsten Lauf erneut versuchen
        result.errors.append(f"{aid}: {e}")
        return
    if not is_cycling(parsed.sport):
        _mark(db, user, aid, "skipped")
        result.skipped += 1
        result.other_sport += 1
        return
    gear = ((a.get("gear") or {}).get("name") or "").strip() or None
    bike = default or (next((b for b in bikes if gear and b.name.strip().lower() == gear.lower()), None))
    stored = imports.store_activity(
        db, user.id, parsed, name=(a.get("name") or None), strava_id=None, gear_name=gear,
        bike=bike, sport_type=None, source="intervals",
    )
    _mark(db, user, aid, "imported" if stored else "duplicate")
    if stored:
        result.imported += 1
    else:
        result.duplicates += 1


# ---------- Hintergrund ----------

def is_connected(user: User) -> bool:
    return bool(user.icu_api_key)


def run_in_background(user_id: int) -> bool:
    with _lock:
        if user_id in _running:
            return False
        _running.add(user_id)

    def work() -> None:
        try:
            with SessionLocal() as db:
                user = db.get(User, user_id)
                if user is not None and is_connected(user):
                    sync_user(db, user)
        except IntervalsError:
            pass  # Text steht schon in icu_status
        except Exception:
            log.exception("intervals.icu-Import fehlgeschlagen")
        finally:
            with _lock:
                _running.discard(user_id)

    threading.Thread(target=work, daemon=True, name=f"intervals-{user_id}").start()
    return True


def is_running(user_id: int) -> bool:
    with _lock:
        return user_id in _running


def start_background() -> None:
    def loop() -> None:
        time.sleep(240)
        while True:
            try:
                with SessionLocal() as db:
                    ids = db.scalars(select(User.id).where(User.icu_api_key.is_not(None))).all() if settings.intervals_enabled else []
                for uid in ids:
                    run_in_background(uid)
            except Exception:
                log.exception("Geplanter intervals.icu-Import fehlgeschlagen")
            time.sleep(SCHEDULE_INTERVAL_S)

    threading.Thread(target=loop, daemon=True, name="intervals-scheduler").start()
