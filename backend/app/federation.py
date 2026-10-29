"""Gruppen über mehrere BikeHelper-Server: die Gast-Seite.

Ein Server ist Gastgeber einer Gruppe. Ein Nutzer auf einem anderen Server (dem Gast) tritt über den Einladungslink bei. Sein Server
schickt dem Gastgeber nur Tageswerte (Datum, Kilometer, Fahrten, Zeit, Höhenmeter, längste Fahrt), nie Strecken, Orte, Räder oder
Fahrtnamen. Die Gruppenansicht holt der Gast-Server beim Gastgeber und reicht sie an seinen Nutzer weiter.

Die Verbindung ist ausgehend und läuft über HTTPS mit einem Schlüssel, den der Gastgeber beim Beitritt vergibt. Der Administrator
muss die Funktion einschalten (Einstellung federation_enabled). Weil dieser Server auf Adressen verbindet, die Nutzer eingeben, sind
Adressen im lokalen Netz gesperrt (außer mit FEDERATION_ALLOW_PRIVATE=true), Weiterleitungen werden nicht verfolgt und
Antworten sind auf 2 MB begrenzt.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import threading
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal
from .models import Activity, RemoteMembership
from .stats.overview import get_tz, local

log = logging.getLogger("bikehelper.federation")

REMOTE_BASE = 1_000_000_000  # Gruppen-IDs ab hier sind Gruppen auf anderen Servern (Basis + RemoteMembership.id)
SYNC_INTERVAL_S = 3 * 3600
RESEND_DAYS = 90      # nach der ersten Übertragung werden nur die letzten Tage neu gesendet
MAX_RESPONSE_BYTES = 2_000_000
TIMEOUT_S = 10


class FederationError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def is_remote_id(group_id: int) -> bool:
    return group_id >= REMOTE_BASE


def parse_link(link: str) -> tuple[str, str]:
    """Einladungslink (https://host/groups/join/TOKEN) -> (Adresse des Servers, Schlüssel)."""
    parts = urlsplit((link or "").strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FederationError("Das ist kein Einladungslink. Er beginnt mit https:// und endet auf /groups/join/…", 422)
    segs = [s for s in parts.path.split("/") if s]
    if len(segs) < 3 or segs[-3:-1] != ["groups", "join"] or not segs[-1].strip():
        raise FederationError("Das ist kein Einladungslink. Er endet auf /groups/join/… und kommt vom Gruppenadministrator.", 422)
    origin = f"{parts.scheme}://{parts.netloc}".lower()
    return origin, segs[-1]


def _own_origin() -> str:
    p = urlsplit(settings.public_url)
    return f"{p.scheme}://{p.netloc}".lower()


def check_origin(origin: str) -> None:
    """Sperrt Adressen, über die dieser Server unbeabsichtigt andere Dienste im eigenen Netz erreichen würde."""
    if not settings.federation_enabled:
        raise FederationError("Gruppen mit anderen Servern sind auf diesem Server nicht eingeschaltet. Das macht der Administrator unter Administration → Funktionen.", 409)
    p = urlsplit(origin)
    if origin == _own_origin():
        raise FederationError("Das ist ein Link von diesem Server. Dafür brauchst du ihn nicht hier einzufügen, öffne ihn einfach.", 422)
    if p.scheme != "https" and not settings.federation_allow_private:
        raise FederationError("Der andere Server muss über https erreichbar sein.", 422)
    if settings.federation_allow_private:
        return
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or 443, proto=socket.IPPROTO_TCP)
    except OSError:
        raise FederationError("Die Adresse des anderen Servers lässt sich nicht auflösen.", 422)
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise FederationError("Der andere Server liegt in einem privaten Netz und wird aus Sicherheitsgründen nicht angesprochen.", 422)


def call(origin: str, method: str, path: str, *, key: str | None = None, json: dict | None = None, params: dict | None = None) -> dict | None:
    """Ruft die Schnittstelle des Gastgebers auf. Gibt die JSON-Antwort zurück (None bei 204)."""
    check_origin(origin)
    headers = {"User-Agent": "BikeHelper (self-hosted)", "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        with httpx.Client(timeout=TIMEOUT_S, follow_redirects=False, headers=headers) as c:
            r = c.request(method, f"{origin}/api/federation{path}", json=json, params=params)
    except httpx.HTTPError:
        raise FederationError("Der andere Server ist gerade nicht erreichbar.")
    if len(r.content) > MAX_RESPONSE_BYTES:
        raise FederationError("Die Antwort des anderen Servers ist zu groß.", r.status_code)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = None
        if r.status_code == 404 and not detail:
            detail = "Der andere Server kennt diese Funktion nicht (ältere Version oder nicht eingeschaltet)."
        raise FederationError(detail if isinstance(detail, str) else f"Fehler {r.status_code} beim anderen Server", r.status_code)
    if r.status_code == 204 or not r.content:
        return None
    try:
        return r.json()
    except ValueError:
        raise FederationError("Der andere Server hat unverständlich geantwortet.")


def host_label(ms: RemoteMembership) -> str:
    return urlsplit(ms.host_url).netloc


def membership(db: Session, user_id: int, group_id: int) -> RemoteMembership | None:
    ms = db.get(RemoteMembership, group_id - REMOTE_BASE)
    return ms if ms is not None and ms.user_id == user_id else None


# ---------- Tageswerte senden ----------

def daily_values(db: Session, user_id: int, since: date | None) -> list[dict]:
    """Tageswerte der eigenen Fahrten (lokale Tage) ab `since`; ohne Datum alle."""
    tz = get_tz(settings.timezone)
    q = select(Activity.start_date, Activity.distance_km, Activity.moving_time_s, Activity.elevation_m).where(Activity.user_id == user_id)
    if since is not None:
        q = q.where(Activity.start_date >= datetime.combine(since - timedelta(days=1), datetime.min.time()))
    days: dict[date, dict] = {}
    for start, km, secs, elev in db.execute(q):
        d = local(start, tz).date()
        if since is not None and d < since:
            continue
        x = days.setdefault(d, {"km": 0.0, "rides": 0, "time_s": 0, "elev_m": 0.0, "longest_km": 0.0})
        km = km or 0.0
        x["km"] += km
        x["rides"] += 1
        x["time_s"] += secs or 0
        x["elev_m"] += elev or 0.0
        x["longest_km"] = max(x["longest_km"], km)
    return [{"day": d.isoformat(), "km": round(v["km"], 2), "rides": v["rides"], "time_s": int(v["time_s"]),
             "elev_m": round(v["elev_m"], 1), "longest_km": round(v["longest_km"], 2)} for d, v in sorted(days.items())]


def sync_membership(db: Session, ms: RemoteMembership) -> None:
    """Sendet Freigabe und Tageswerte an den Gastgeber und merkt sich das Ergebnis."""
    today = local(datetime.now(timezone.utc).replace(tzinfo=None), get_tz(settings.timezone)).date()
    since = None if not ms.full_synced else today - timedelta(days=RESEND_DAYS)
    try:
        body = {"display_name": ms.display_name, "share": ms.share, "since": since.isoformat() if since else None,
                "days": daily_values(db, ms.user_id, since) if ms.share else []}
        out = call(ms.host_url, "POST", "/push", key=ms.member_key, json=body) or {}
        ms.full_synced = True
        ms.last_sync_at = datetime.utcnow()
        ms.last_error = None
        if out.get("group"):
            ms.group_name = str(out["group"])[:80]
        if isinstance(out.get("members"), int):
            ms.members = out["members"]
    except FederationError as e:
        if e.status_code in (401, 404):
            ms.last_error = "Der Gastgeber kennt dich nicht mehr. Du wurdest entfernt oder die Gruppe gibt es nicht mehr."
        else:
            ms.last_error = e.message[:300]
    db.commit()


def sync_user(user_id: int | None = None) -> None:
    with SessionLocal() as db:
        q = select(RemoteMembership)
        if user_id is not None:
            q = q.where(RemoteMembership.user_id == user_id)
        for ms in db.scalars(q).all():
            if ms.last_error and ms.last_error.startswith("Der Gastgeber kennt dich nicht mehr"):
                continue  # nicht erneut versuchen, der Nutzer kann die Mitgliedschaft entfernen
            try:
                sync_membership(db, ms)
            except Exception:
                db.rollback()
                log.exception("Gruppen-Abgleich fehlgeschlagen")


def trigger(user_id: int) -> None:
    """Sendet im Hintergrund, z. B. nach dem Beitritt oder nach einem Import."""
    if settings.federation_enabled:
        threading.Thread(target=sync_user, args=(user_id,), daemon=True, name="federation-sync").start()


def start_background() -> None:
    def loop() -> None:
        time.sleep(90)
        while True:
            try:
                if settings.federation_enabled:
                    sync_user(None)
            except Exception:
                log.exception("Geplanter Gruppen-Abgleich fehlgeschlagen")
            time.sleep(SYNC_INTERVAL_S)

    threading.Thread(target=loop, daemon=True, name="federation-scheduler").start()


def leave_all(db: Session, user_id: int) -> None:
    """Beim Löschen eines Kontos: bei den Gastgebern abmelden (soweit erreichbar) und die Mitgliedschaften löschen."""
    for ms in db.scalars(select(RemoteMembership).where(RemoteMembership.user_id == user_id)).all():
        try:
            call(ms.host_url, "DELETE", "/leave", key=ms.member_key)
        except FederationError:
            pass
        db.delete(ms)
