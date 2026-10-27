import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..intervals import service
from ..models import Bike, IntervalsSeen, User
from ..security import current_user

router = APIRouter(prefix="/api", tags=["intervals"])
KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{8,100}$")


class IntervalsSettingsIn(BaseModel):
    api_key: str | None = Field(default=None, max_length=120)  # leer/None = bisherigen behalten
    bike_id: int | None = None


def _out(db: Session, user: User) -> dict:
    imported = db.scalar(
        select(func.count()).select_from(IntervalsSeen).where(IntervalsSeen.user_id == user.id, IntervalsSeen.status == "imported")
    )
    return {
        "enabled": settings.intervals_enabled,
        "connected": service.is_connected(user),
        "key_hint": ("…" + user.icu_api_key[-4:]) if user.icu_api_key else None,
        "running": service.is_running(user.id),
        "bike_id": user.icu_bike_id,
        "last_sync": user.icu_last_sync.isoformat() + "Z" if user.icu_last_sync else None,
        "status": user.icu_status,
        "imported": imported or 0,
    }


@router.get("/settings/intervals")
def get_intervals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Der Schlüssel selbst wird nie zurückgegeben."""
    return _out(db, user)


@router.put("/settings/intervals")
def save_intervals(data: IntervalsSettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not settings.intervals_enabled:
        raise HTTPException(404, "Der intervals.icu-Import ist auf diesem Server ausgeschaltet")
    if data.bike_id is not None:
        bike = db.get(Bike, data.bike_id)
        if bike is None or bike.user_id != user.id:
            raise HTTPException(404, "Rad nicht gefunden")
    user.icu_bike_id = data.bike_id
    key = (data.api_key or "").strip()
    if key:
        if not KEY_RE.match(key):
            raise HTTPException(422, "Der Schlüssel sieht ungültig aus. Kopiere ihn unverändert aus den Entwicklereinstellungen von intervals.icu.")
        try:
            who = service.check_key(key)
        except service.IntervalsError as e:
            raise HTTPException(422, str(e))
        user.icu_api_key = key
        user.icu_synced_until = None  # neuer Schlüssel: alles neu abgleichen (Bekanntes wird übersprungen)
        user.icu_status = f"Verbunden{(' mit ' + who) if who else ''}"
        db.commit()
        service.run_in_background(user.id)
    else:
        db.commit()
    return _out(db, user)


@router.post("/intervals/sync", status_code=202)
def intervals_sync(user: User = Depends(current_user)):
    if not service.is_connected(user):
        raise HTTPException(422, "intervals.icu ist nicht verbunden")
    return {"started": service.run_in_background(user.id)}


@router.delete("/intervals/connection", status_code=204)
def intervals_disconnect(user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.icu_api_key = None
    user.icu_synced_until = None
    user.icu_status = None
    db.commit()
