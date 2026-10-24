"""Administration: Rollen, Einladungen und Servereinstellungen.

Der Administrator sieht hier nur Verwaltungsdaten (E-Mail-Adresse, Rolle, Status, Anlagedatum) und nie Inhalte
anderer Nutzer wie Räder, Fahrten, Gewicht oder Orte.
"""
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import notify, server_settings
from ..database import get_db
from ..models import Invite, User
from ..schemas import InviteOut
from ..security import require_admin
from .auth import delete_user_data

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _admin_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) or 0


# ---------- Einladungen ----------

@router.get("/invites", response_model=list[InviteOut])
def list_invites(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.scalars(select(Invite).order_by(Invite.id.desc())).all()


@router.post("/invites", response_model=InviteOut, status_code=201)
def create_invite(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    invite = Invite(code=secrets.token_hex(5).upper())
    db.add(invite)
    db.commit()
    return invite


@router.delete("/invites/{invite_id}", status_code=204)
def delete_invite(invite_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    invite = db.get(Invite, invite_id)
    if invite is None:
        raise HTTPException(404, "Einladung nicht gefunden")
    db.delete(invite)
    db.commit()


# ---------- Konten und Rollen ----------

class UserPatch(BaseModel):
    role: Literal["admin", "user"] | None = None
    active: bool | None = None


def _user_row(u: User, me: User) -> dict:
    return {
        "id": u.id, "email": u.email, "role": u.role or "user", "active": u.active is not False,
        "created_at": u.created_at.isoformat() if u.created_at else None, "is_me": u.id == me.id,
    }


@router.get("/users")
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_user_row(u, admin) for u in db.scalars(select(User).order_by(User.id))]


@router.put("/users/{user_id}")
def update_user(user_id: int, data: UserPatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Rolle ändern oder Konto sperren. Das eigene Konto und der letzte Administrator bleiben geschützt."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "Konto nicht gefunden")
    if target.id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Die eigene Rolle und das eigene Konto änderst du nicht selbst.")
    if data.role is not None and data.role != (target.role or "user"):
        if data.role == "user" and (target.role == "admin") and _admin_count(db) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Es muss mindestens ein Administrator bleiben.")
        target.role = data.role
    if data.active is not None:
        target.active = data.active
        if not data.active:
            target.token_version = (target.token_version or 0) + 1  # bestehende Anmeldungen enden sofort
    db.commit()
    return _user_row(target, admin)


@router.delete("/users/{user_id}", status_code=204)
def remove_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Entfernt ein fremdes Konto samt Daten (zum Beispiel, wenn jemand gehen möchte)."""
    if user_id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Das eigene Konto löschst du unter Einstellungen → Sicherheit.")
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "Konto nicht gefunden")
    if target.role == "admin" and _admin_count(db) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Es muss mindestens ein Administrator bleiben.")
    delete_user_data(db, target)


# ---------- Servereinstellungen ----------

class SettingsIn(BaseModel):
    values: dict


@router.get("/settings")
def get_settings(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"fields": server_settings.describe(db), "smtp_ready": notify.smtp_configured()}


@router.put("/settings")
def save_settings(data: SettingsIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        server_settings.save(db, data.values)
    except server_settings.SettingError as e:
        raise HTTPException(422, str(e))
    return {"fields": server_settings.describe(db), "smtp_ready": notify.smtp_configured()}


@router.post("/settings/test-email")
def test_email(admin: User = Depends(require_admin)):
    """Schickt eine Testmail an die Adresse des Administrators, mit den aktuell gespeicherten Einstellungen."""
    if not notify.smtp_configured():
        raise HTTPException(422, "Trage zuerst Server und Absender- oder Benutzeradresse ein und speichere.")
    try:
        notify.send_email(admin.email, "BikeHelper: Testmail", "Der E-Mail-Versand funktioniert.")
    except Exception as e:  # SMTP-Fehler verständlich weitergeben
        raise HTTPException(502, f"Versand fehlgeschlagen: {e.__class__.__name__}: {e}")
    return {"ok": True, "to": admin.email}
