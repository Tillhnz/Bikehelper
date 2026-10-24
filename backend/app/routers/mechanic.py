"""Mechanics-Modus: Räder von Partnern einsehen und bearbeiten, nachdem der Besitzer zugestimmt hat.

Die Anfrage geht von der Mechanikerin / dem Mechaniker aus (per E-Mail-Adresse). Erst wenn der Besitzer sie auf
der Startseite bestätigt, gilt die Freigabe. Sie umfasst nur Räder, Teile, Wartung und Reifen, keine Fahrten,
kein Lager, keine Ziele und keine Einstellungen.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import notify, ratelimit
from ..database import get_db
from ..models import Bike, MechanicGrant, User
from ..security import current_user
from . import garage

router = APIRouter(prefix="/api/mechanic", tags=["mechanic"])
log = logging.getLogger("bikehelper")

GENERIC = {"ok": True, "message": "Anfrage gesendet. Sie wird sichtbar, sobald es dieses Konto gibt und es sie bestätigt."}


class RequestIn(BaseModel):
    email: EmailStr


class EnabledIn(BaseModel):
    enabled: bool


def _mail_owner(owner_id: int, requester_email: str) -> None:
    from ..database import SessionLocal
    with SessionLocal() as db:
        owner = db.get(User, owner_id)
        if not owner or owner.active is False or not notify.smtp_configured():
            return
        try:
            notify.send_email(owner.email, "BikeHelper: Zugriffsanfrage",
                              f"{requester_email} möchte als Mechaniker deine Räder sehen und bearbeiten. "
                              "Du kannst das auf der Startseite zulassen oder ablehnen.")
        except Exception:
            log.exception("Mail zur Zugriffsanfrage konnte nicht gesendet werden")


def pending_for(db: Session, user: User) -> list[dict]:
    rows = db.execute(
        select(MechanicGrant, User.email).join(User, User.id == MechanicGrant.mechanic_id)
        .where(MechanicGrant.owner_id == user.id, MechanicGrant.status == "pending").order_by(MechanicGrant.id)
    ).all()
    return [{"id": g.id, "email": email} for g, email in rows]


@router.get("/state")
def state(user: User = Depends(current_user), db: Session = Depends(get_db)):
    given = db.execute(
        select(MechanicGrant, User.email).join(User, User.id == MechanicGrant.mechanic_id)
        .where(MechanicGrant.owner_id == user.id).order_by(MechanicGrant.id)
    ).all()
    mine = db.execute(
        select(MechanicGrant, User.email).join(User, User.id == MechanicGrant.owner_id)
        .where(MechanicGrant.mechanic_id == user.id).order_by(MechanicGrant.id)
    ).all()
    return {
        "enabled": bool(user.mechanic_enabled),
        "incoming": pending_for(db, user),
        "access_given": [{"id": g.id, "email": e, "status": g.status} for g, e in given],
        "partners": [{"id": g.id, "email": e, "status": g.status} for g, e in mine],
    }


@router.put("/enabled")
def set_enabled(data: EnabledIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.mechanic_enabled = data.enabled
    db.commit()
    return {"enabled": data.enabled}


@router.post("/requests", status_code=202)
def request_access(data: RequestIn, background: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ratelimit.check_mechanic(user.id)
    email = data.email.lower()
    if email == user.email.lower():
        raise HTTPException(400, "Das ist dein eigenes Konto. Deine Räder siehst du ohnehin.")
    owner = db.scalar(select(User).where(User.email == email))
    # Immer dieselbe Antwort, damit niemand erfahren kann, welche Adressen ein Konto haben
    if owner is None or owner.active is False:
        return GENERIC
    existing = db.scalar(select(MechanicGrant).where(MechanicGrant.owner_id == owner.id, MechanicGrant.mechanic_id == user.id))
    if existing is None:
        db.add(MechanicGrant(owner_id=owner.id, mechanic_id=user.id, status="pending"))
        db.commit()
        background.add_task(_mail_owner, owner.id, user.email)
    return GENERIC


def _grant_for_owner(db: Session, user: User, grant_id: int) -> MechanicGrant:
    g = db.get(MechanicGrant, grant_id)
    if not g or g.owner_id != user.id:
        raise HTTPException(404, "Anfrage nicht gefunden")
    return g


@router.post("/requests/{grant_id}/accept")
def accept(grant_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = _grant_for_owner(db, user, grant_id)
    g.status, g.decided_at = "active", datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/requests/{grant_id}/decline")
def decline(grant_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = _grant_for_owner(db, user, grant_id)
    db.delete(g)
    db.commit()
    return {"ok": True}


@router.delete("/grants/{grant_id}", status_code=204)
def revoke(grant_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Besitzer entzieht den Zugriff, oder der Mechaniker gibt ihn zurück bzw. zieht seine Anfrage zurück."""
    g = db.get(MechanicGrant, grant_id)
    if not g or user.id not in (g.owner_id, g.mechanic_id):
        raise HTTPException(404, "Freigabe nicht gefunden")
    db.delete(g)
    db.commit()


@router.get("/bikes")
def bikes(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Eigene Räder und die Räder aller Partner mit aktiver Freigabe, gruppiert nach Besitzer."""
    owners = [(user, True)]
    for g, owner in db.execute(
        select(MechanicGrant, User).join(User, User.id == MechanicGrant.owner_id)
        .where(MechanicGrant.mechanic_id == user.id, MechanicGrant.status == "active").order_by(User.email)
    ).all():
        if owner.active is not False:
            owners.append((owner, False))
    groups = []
    for owner, own in owners:
        rows = db.scalars(select(Bike).where(Bike.user_id == owner.id, Bike.retired.is_(False)).order_by(Bike.name)).all()
        outs = []
        for b in rows:
            o = garage._bike_out(db, b)
            if not own:
                o.shared_from = owner.email
            outs.append(o)
        groups.append({"owner": owner.email, "own": own, "bikes": outs})
    return groups
