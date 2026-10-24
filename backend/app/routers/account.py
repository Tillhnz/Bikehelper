"""Konto-Funktionen: Datenexport, Passwort vergessen und die Suche über die eigenen Daten."""
import hashlib
import json
import secrets
from datetime import date, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import audit, notify, ratelimit
from ..config import settings
from ..database import SessionLocal, get_db
from ..models import (
    Activity, Bike, ChainMeasurement, Component, Goal, InventoryItem, MaintenanceLog, MaintenanceRule, PasswordReset,
    TireMount, TireSet, User, UserTire,
)
from ..security import current_user, hash_password

router = APIRouter(prefix="/api", tags=["account"])

# ---------- Export ----------

# Zugangsdaten und Rechenhilfen gehören nicht in den Export
_SKIP = {"password_hash", "token_version", "strava_client_secret", "strava_access_token", "strava_refresh_token",
         "wahoo_client_secret", "wahoo_access_token", "wahoo_refresh_token", "details", "tiles"}


def _plain(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _dump(rows) -> list[dict]:
    out = []
    for r in rows:
        out.append({c.name: _plain(getattr(r, c.name)) for c in r.__table__.columns if c.name not in _SKIP})
    return out


@router.get("/me/export")
def export_data(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Alle eigenen Daten als JSON-Datei (Räder, Teile, Wartungen, Reifen, Fahrten samt Strecke, Lager, Ziele)."""
    uid = user.id
    comps = db.scalars(select(Component).where(Component.user_id == uid)).all()
    cids = [c.id for c in comps]
    sets = db.scalars(select(TireSet).where(TireSet.user_id == uid)).all()
    sids = [s.id for s in sets]
    by = lambda model, col, ids: db.scalars(select(model).where(col.in_(ids))).all() if ids else []  # noqa: E731
    data = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "app": "BikeHelper",
        "account": {"email": user.email, "weight_kg": user.weight_kg},
        "bikes": _dump(db.scalars(select(Bike).where(Bike.user_id == uid))),
        "components": _dump(comps),
        "maintenance_rules": _dump(by(MaintenanceRule, MaintenanceRule.component_id, cids)),
        "maintenance_logs": _dump(by(MaintenanceLog, MaintenanceLog.component_id, cids)),
        "chain_measurements": _dump(by(ChainMeasurement, ChainMeasurement.component_id, cids)),
        "tire_sets": _dump(sets),
        "tire_mounts": _dump(by(TireMount, TireMount.tire_set_id, sids)),
        "own_tires": _dump(db.scalars(select(UserTire).where(UserTire.user_id == uid))),
        "inventory": _dump(db.scalars(select(InventoryItem).where(InventoryItem.user_id == uid))),
        "goals": _dump(db.scalars(select(Goal).where(Goal.user_id == uid))),
        "activities": _dump(db.scalars(select(Activity).where(Activity.user_id == uid).order_by(Activity.start_date))),
    }
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    name = f"bikehelper-export-{date.today().isoformat()}.json"
    return Response(body, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------- Passwort vergessen ----------

RESET_VALID = timedelta(hours=1)


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=20, max_length=100)
    password: str = Field(min_length=8, max_length=128)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _send_reset_mail(user_id: int, token: str) -> None:
    """Läuft nach der Antwort, damit die Antwortzeit nicht verrät, ob es das Konto gibt."""
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user:
            return
        link = f"{settings.public_url.rstrip('/')}/login?reset={token}"
        try:
            notify.send_email(user.email, "BikeHelper: Passwort zurücksetzen",
                              f"Über diesen Link vergibst du ein neues Passwort (eine Stunde gültig):\n{link}\n\n"
                              "Wenn du das nicht angefordert hast, kannst du diese Mail ignorieren.")
        except Exception:  # Fehler bleiben im Serverprotokoll, die Antwort an den Nutzer ist immer gleich
            import logging
            logging.getLogger("bikehelper").exception("Passwort-Mail konnte nicht gesendet werden")


@router.post("/auth/forgot", status_code=202)
def forgot_password(data: ForgotIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    email = data.email.lower()
    ratelimit.check_reset(ratelimit.client_ip(request), email)
    if not notify.smtp_configured():
        raise HTTPException(503, "Der E-Mail-Versand ist nicht eingerichtet. Bitte wende dich an den Administrator.")
    user = db.scalar(select(User).where(User.email == email))
    if user and user.active is not False:
        token = secrets.token_urlsafe(32)
        db.add(PasswordReset(user_id=user.id, token_hash=_hash(token), expires_at=datetime.utcnow() + RESET_VALID))
        db.commit()
        background.add_task(_send_reset_mail, user.id, token)
    return {"ok": True, "message": "Wenn es dieses Konto gibt, ist eine E-Mail mit einem Link unterwegs."}


@router.post("/auth/reset")
def reset_password(data: ResetIn, request: Request, db: Session = Depends(get_db)):
    ratelimit.check_reset(ratelimit.client_ip(request), "token")
    row = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == _hash(data.token)))
    if row is None or row.used_at is not None or row.expires_at < datetime.utcnow():
        raise HTTPException(400, "Dieser Link ist ungültig oder abgelaufen. Fordere einen neuen an.")
    user = db.get(User, row.user_id)
    if user is None or user.active is False:
        raise HTTPException(400, "Dieser Link ist ungültig oder abgelaufen. Fordere einen neuen an.")
    user.password_hash = hash_password(data.password)
    user.token_version = (user.token_version or 0) + 1  # alle bisherigen Anmeldungen enden
    row.used_at = datetime.utcnow()
    db.commit()
    audit.record(db, user.email, "password.reset")
    return {"ok": True}


# ---------- Suche ----------

@router.get("/search")
def search(q: str = Query(min_length=2, max_length=80), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Sucht in den eigenen Fahrten, Rädern, Teilen und im Lager. Je Gruppe höchstens sechs Treffer."""
    like = f"%{q.strip().replace('%', '').replace('_', '')}%"
    uid = user.id
    rides = db.scalars(select(Activity).where(Activity.user_id == uid, Activity.name.ilike(like))
                       .order_by(Activity.start_date.desc()).limit(6)).all()
    bikes = db.scalars(select(Bike).where(Bike.user_id == uid, or_(Bike.name.ilike(like), Bike.brand.ilike(like), Bike.model.ilike(like)))
                       .limit(6)).all()
    comps = db.scalars(select(Component).where(Component.user_id == uid, or_(Component.name.ilike(like), Component.brand.ilike(like)))
                       .limit(6)).all()
    items = db.scalars(select(InventoryItem).where(InventoryItem.user_id == uid, or_(InventoryItem.name.ilike(like), InventoryItem.brand.ilike(like)))
                       .limit(6)).all()
    return {
        "rides": [{"id": a.id, "title": a.name, "sub": a.start_date.date().isoformat() + f" · {a.distance_km:.0f} km", "to": f"/rides/{a.id}"} for a in rides],
        "bikes": [{"id": b.id, "title": b.name, "sub": " ".join(x for x in (b.brand, b.model) if x), "to": f"/bikes/{b.id}"} for b in bikes],
        "components": [{"id": c.id, "title": c.name, "sub": c.bike.name if c.bike else "ohne Rad",
                        "to": f"/bikes/{c.bike_id}" if c.bike_id else "/garage"} for c in comps],
        "inventory": [{"id": i.id, "title": i.name, "sub": f"{i.quantity} Stück", "to": "/inventory"} for i in items],
    }
