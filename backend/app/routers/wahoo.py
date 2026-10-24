from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Bike, User, WahooSeen
from ..security import current_user
from ..wahoo import service

router = APIRouter(prefix="/api", tags=["wahoo"])


class WahooSettingsIn(BaseModel):
    client_id: str | None = Field(default=None, max_length=128)
    client_secret: str | None = Field(default=None, max_length=160)  # leer lassen = bisherigen behalten
    bike_id: int | None = None


def _out(db: Session, user: User) -> dict:
    imported = db.scalar(
        select(func.count()).select_from(WahooSeen).where(WahooSeen.user_id == user.id, WahooSeen.status == "imported")
    )
    return {
        "enabled": settings.wahoo_enabled,
        "configured": bool(user.wahoo_client_id and user.wahoo_client_secret),
        "client_id": user.wahoo_client_id or "",
        "connected": service.is_connected(user),
        "running": service.is_running(user.id),
        "redirect_uri": service.redirect_uri(),
        "bike_id": user.wahoo_bike_id,
        "last_sync": user.wahoo_last_sync.isoformat() + "Z" if user.wahoo_last_sync else None,
        "status": user.wahoo_status,
        "imported": imported or 0,
    }


@router.get("/settings/wahoo")
def get_wahoo(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _out(db, user)


@router.put("/settings/wahoo")
def save_wahoo(data: WahooSettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if data.bike_id is not None:
        bike = db.get(Bike, data.bike_id)
        if bike is None or bike.user_id != user.id:
            raise HTTPException(404, "Rad nicht gefunden")
    user.wahoo_bike_id = data.bike_id
    cid = (data.client_id or "").strip()
    secret = (data.client_secret or "").strip()
    if cid and (cid != user.wahoo_client_id or secret):
        if not secret and not user.wahoo_client_secret:
            raise HTTPException(422, "Bitte auch das Client-Secret eintragen")
        user.wahoo_client_id = cid
        if secret:
            user.wahoo_client_secret = secret
        service.disconnect(db, user)  # neue App-Zugangsdaten: Verbindung neu aufbauen
    db.commit()
    return _out(db, user)


@router.get("/wahoo/connect")
def wahoo_connect(user: User = Depends(current_user)):
    """Adresse der Wahoo-Anmeldeseite; die App leitet den Browser dorthin."""
    if not settings.wahoo_enabled:
        raise HTTPException(404, "Der Wahoo-Import ist auf diesem Server ausgeschaltet")
    if not (user.wahoo_client_id and user.wahoo_client_secret):
        raise HTTPException(422, "Trage zuerst Client-ID und Client-Secret deiner Wahoo-App ein")
    return {"url": service.authorize_url(user)}


@router.get("/wahoo/callback", include_in_schema=False)
def wahoo_callback(code: str | None = None, state: str = "", error: str | None = None, db: Session = Depends(get_db)):
    """Ziel der Weiterleitung von Wahoo (Browser, ohne App-Anmeldung; der Nutzer steckt im signierten `state`)."""
    uid = service.read_state(state)
    user = db.get(User, uid) if uid else None
    if user is None:
        raise HTTPException(400, "Ungültige oder abgelaufene Anfrage. Bitte die Verbindung in den Einstellungen neu starten.")
    if error or not code:
        return RedirectResponse("/settings?wahoo=denied", status_code=303)
    try:
        service.exchange_code(db, user, code)
    except (service.WahooError, PermissionError):
        return RedirectResponse("/settings?wahoo=failed", status_code=303)
    service.run_in_background(user.id)
    return RedirectResponse("/settings?wahoo=ok", status_code=303)


@router.post("/wahoo/sync", status_code=202)
def wahoo_sync(user: User = Depends(current_user)):
    if not service.is_connected(user):
        raise HTTPException(422, "Wahoo ist nicht verbunden")
    return {"started": service.run_in_background(user.id)}


@router.delete("/wahoo/connection", status_code=204)
def wahoo_disconnect(user: User = Depends(current_user), db: Session = Depends(get_db)):
    service.disconnect(db, user)
