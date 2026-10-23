from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..security import current_user
from ..weather import service

router = APIRouter(prefix="/api", tags=["weather"])


@router.get("/weather/status")
def weather_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Wie viele Fahrten schon Wetterdaten haben und ob gerade abgefragt wird."""
    return service.coverage(db, user.id)


@router.post("/weather/enrich", status_code=202)
def weather_enrich(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Wetterdaten für alle Fahrten ohne Wetter jetzt abrufen (läuft im Hintergrund)."""
    service.trigger(user.id)
    return service.coverage(db, user.id)
