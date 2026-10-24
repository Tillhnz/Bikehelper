"""Automatischer Import aus der Wahoo Cloud (ELEMNT-Radcomputer).

Der Nutzer legt unter developers.wahooligan.com eine eigene App an und verbindet sein Konto per OAuth. Danach holt
BikeHelper regelmäßig neue Workouts: Die Liste enthält noch keine Zusammenfassung, deshalb braucht jede neue Fahrt
einen Detailabruf, der die Adresse der FIT-Datei liefert. Die Datei selbst kommt von einem CDN und zählt nicht zum
API-Limit (Sandbox: 25 pro 5 Minuten, 100 pro Stunde, 250 pro Tag). Ein Lauf holt deshalb nur einen Teil der neuen
Fahrten und macht beim nächsten Mal weiter; bei HTTP 429 hört er sofort auf.

Wahoo-Refresh-Tokens gelten nur einmal. Der neue Token wird deshalb sofort gespeichert.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..importers import service as imports
from ..importers.parsers import ParseError, is_cycling, parse_activity_file
from ..models import Bike, User, WahooSeen

log = logging.getLogger("bikehelper.wahoo")

SCOPES = "user_read workouts_read offline_data"
PER_PAGE = 100
MAX_PAGES = 60                 # höchstens 6000 Workouts pro Durchlauf der Liste
DETAILS_PER_RUN = 40           # Detailabrufe pro Lauf (das Stundenlimit der Sandbox beträgt 100)
SCHEDULE_INTERVAL_S = 30 * 60
STATE_TTL_S = 15 * 60

_lock = threading.Lock()
_running: set[int] = set()


class WahooError(Exception):
    """Fehler mit Text für den Nutzer."""


class RateLimited(WahooError):
    pass


@dataclass
class SyncResult:
    imported: int = 0
    duplicates: int = 0
    skipped: int = 0
    remaining: int = 0
    note: str = ""
    errors: list[str] = field(default_factory=list)

    def text(self) -> str:
        parts = [f"{self.imported} neu importiert"]
        if self.duplicates:
            parts.append(f"{self.duplicates} schon vorhanden")
        if self.skipped:
            parts.append(f"{self.skipped} ohne Datei übersprungen")
        if self.remaining:
            parts.append(f"{self.remaining} folgen im nächsten Lauf")
        if self.note:
            parts.append(self.note)
        return ", ".join(parts)


# ---------- OAuth ----------

def redirect_uri() -> str:
    return f"{settings.public_url.rstrip('/')}/api/wahoo/callback"


def make_state(user_id: int) -> str:
    return jwt.encode({"sub": str(user_id), "purpose": "wahoo", "exp": int(time.time()) + STATE_TTL_S},
                      settings.secret_key, algorithm="HS256")


def read_state(state: str) -> int | None:
    try:
        payload = jwt.decode(state, settings.secret_key, algorithms=["HS256"])
        return int(payload["sub"]) if payload.get("purpose") == "wahoo" else None
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def authorize_url(user: User) -> str:
    from urllib.parse import urlencode
    q = urlencode({
        "client_id": user.wahoo_client_id, "redirect_uri": redirect_uri(), "response_type": "code",
        "scope": SCOPES, "state": make_state(user.id),
    })
    return f"{settings.wahoo_api_url}/oauth/authorize?{q}"


def _store_tokens(db: Session, user: User, data: dict) -> None:
    user.wahoo_access_token = data["access_token"]
    if data.get("refresh_token"):
        user.wahoo_refresh_token = data["refresh_token"]
    user.wahoo_expires_at = int(time.time()) + int(data.get("expires_in") or 7200)
    db.commit()  # Refresh-Tokens sind einmalig: sofort sichern


def _token_request(http: httpx.Client, user: User, params: dict) -> dict:
    try:
        r = http.post(f"{settings.wahoo_api_url}/oauth/token", data={
            "client_id": user.wahoo_client_id, "client_secret": user.wahoo_client_secret, **params,
        })
    except httpx.HTTPError as e:
        raise WahooError(f"Wahoo nicht erreichbar: {e.__class__.__name__}") from e
    if r.status_code in (400, 401):
        raise PermissionError("Wahoo hat die Anmeldung abgelehnt")
    if r.status_code >= 400:
        raise WahooError(f"Wahoo antwortete mit Fehler {r.status_code}")
    return r.json()


def exchange_code(db: Session, user: User, code: str, http: httpx.Client | None = None) -> None:
    with (http or httpx.Client(timeout=30)) as c:
        data = _token_request(c, user, {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri()})
    _store_tokens(db, user, data)
    user.wahoo_status = "Verbunden"
    db.commit()


def disconnect(db: Session, user: User) -> None:
    user.wahoo_access_token = user.wahoo_refresh_token = None
    user.wahoo_expires_at = None
    user.wahoo_status = None
    db.commit()


def is_connected(user: User) -> bool:
    return bool(user.wahoo_refresh_token)


def _access_token(db: Session, user: User, http: httpx.Client) -> str:
    if user.wahoo_access_token and (user.wahoo_expires_at or 0) - 60 > time.time():
        return user.wahoo_access_token
    try:
        data = _token_request(http, user, {"grant_type": "refresh_token", "refresh_token": user.wahoo_refresh_token})
    except PermissionError:
        disconnect(db, user)
        user.wahoo_status = "Verbindung abgelaufen, bitte neu verbinden"
        db.commit()
        raise WahooError(user.wahoo_status)
    _store_tokens(db, user, data)
    return user.wahoo_access_token


# ---------- API ----------

def _get(http: httpx.Client, token: str, path: str, params: dict | None = None) -> dict:
    try:
        r = http.get(f"{settings.wahoo_api_url}{path}", params=params, headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as e:
        raise WahooError(f"Wahoo nicht erreichbar: {e.__class__.__name__}") from e
    if r.status_code == 429:
        raise RateLimited("Wahoo-Limit erreicht, der nächste Lauf macht weiter")
    if r.status_code in (401, 403):
        raise WahooError("Wahoo verweigert den Zugriff, bitte neu verbinden")
    if r.status_code >= 400:
        raise WahooError(f"Wahoo antwortete mit Fehler {r.status_code}")
    return r.json()


def list_workouts(http: httpx.Client, token: str) -> list[dict]:
    out: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        data = _get(http, token, "/v1/workouts", {"page": page, "per_page": PER_PAGE})
        items = data.get("workouts") or []
        out.extend(items)
        if len(items) < PER_PAGE or len(out) >= int(data.get("total") or 0):
            break
    return out


def fit_url(workout: dict) -> str | None:
    """Adresse der FIT-Datei aus dem Workout-Detail (workout_summary.file.url)."""
    summary = workout.get("workout_summary") or {}
    return (summary.get("file") or {}).get("url") or None


def download(http: httpx.Client, url: str) -> bytes:
    """Lädt die Datei (CDN, ohne Anmeldung), höchstens MAX_UPLOAD_FILE_BYTES."""
    chunks, size = [], 0
    try:
        with http.stream("GET", url, follow_redirects=True) as r:
            if r.status_code >= 400:
                raise WahooError(f"Dateiabruf fehlgeschlagen ({r.status_code})")
            for chunk in r.iter_bytes():
                size += len(chunk)
                if size > imports.MAX_UPLOAD_FILE_BYTES:
                    raise ParseError("Die Datei ist zu groß.")
                chunks.append(chunk)
    except httpx.HTTPError as e:
        raise WahooError(f"Dateiabruf fehlgeschlagen: {e.__class__.__name__}") from e
    return b"".join(chunks)


# ---------- Synchronisieren ----------

def sync_user(db: Session, user: User, http: httpx.Client | None = None, max_details: int = DETAILS_PER_RUN) -> SyncResult:
    """Holt neue Wahoo-Fahrten. Wirft WahooError nur bei Problemen, die den ganzen Lauf betreffen."""
    result = SyncResult()
    own = http is None
    http = http or httpx.Client(timeout=30)
    try:
        token = _access_token(db, user, http)
        known = set(db.scalars(select(WahooSeen.workout_id).where(WahooSeen.user_id == user.id)))
        new = [w for w in list_workouts(http, token) if w.get("id") not in known]
        new.sort(key=lambda w: w.get("starts") or "", reverse=True)  # neueste zuerst
        bike = db.get(Bike, user.wahoo_bike_id) if user.wahoo_bike_id else None
        if bike is not None and bike.user_id != user.id:
            bike = None
        todo, result.remaining = new[:max_details], max(0, len(new) - max_details)
        try:
            for i, w in enumerate(todo):
                _import_one(db, user, http, token, w, bike, result)
        except RateLimited as e:
            result.remaining += len(todo) - i
            result.note = str(e)
    except WahooError as e:
        user.wahoo_status = str(e)
        db.commit()
        raise
    finally:
        if own:
            http.close()
    user.wahoo_last_sync = datetime.utcnow()
    user.wahoo_status = result.text()
    db.commit()
    return result


def _mark(db: Session, user: User, workout_id: int, status: str) -> None:
    db.add(WahooSeen(user_id=user.id, workout_id=workout_id, status=status))
    db.commit()


def _import_one(db: Session, user: User, http: httpx.Client, token: str, w: dict, bike: Bike | None, result: SyncResult) -> None:
    wid = int(w["id"])
    detail = _get(http, token, f"/v1/workouts/{wid}")
    url = fit_url(detail)
    if not url:  # z. B. Training ohne aufgezeichnete Datei
        _mark(db, user, wid, "skipped")
        result.skipped += 1
        return
    try:
        data = download(http, url)
        parsed = parse_activity_file("wahoo.fit", data)
    except ParseError as e:
        result.errors.append(f"{wid}: {e}")
        _mark(db, user, wid, "skipped")
        result.skipped += 1
        return
    except WahooError as e:  # vorübergehend: nicht merken, beim nächsten Lauf erneut versuchen
        result.errors.append(f"{wid}: {e}")
        return
    if not is_cycling(parsed.sport):
        _mark(db, user, wid, "skipped")
        result.skipped += 1
        return
    stored = imports.store_activity(
        db, user.id, parsed, name=(detail.get("name") or None), strava_id=None, gear_name=None,
        bike=bike, sport_type=None, source="wahoo",
    )
    _mark(db, user, wid, "imported" if stored else "duplicate")
    if stored:
        result.imported += 1
    else:
        result.duplicates += 1


# ---------- Hintergrund ----------

def run_in_background(user_id: int) -> bool:
    """Startet einen Lauf für einen Nutzer; False, wenn schon einer läuft."""
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
        except WahooError:
            pass  # Text steht schon in wahoo_status
        except Exception:
            log.exception("Wahoo-Import fehlgeschlagen")
        finally:
            with _lock:
                _running.discard(user_id)

    threading.Thread(target=work, daemon=True, name=f"wahoo-{user_id}").start()
    return True


def is_running(user_id: int) -> bool:
    with _lock:
        return user_id in _running


def start_background() -> None:
    def loop() -> None:
        time.sleep(180)
        while True:
            try:
                with SessionLocal() as db:
                    ids = db.scalars(select(User.id).where(User.wahoo_refresh_token.is_not(None))).all() if settings.wahoo_enabled else []
                for uid in ids:
                    run_in_background(uid)
            except Exception:
                log.exception("Geplanter Wahoo-Import fehlgeschlagen")
            time.sleep(SCHEDULE_INTERVAL_S)

    threading.Thread(target=loop, daemon=True, name="wahoo-scheduler").start()
