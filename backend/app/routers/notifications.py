import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import notify
from ..config import settings
from ..database import get_db
from ..models import User
from ..security import current_user

router = APIRouter(prefix="/api/settings/notifications", tags=["notifications"])

TOPIC_RE = re.compile(r"^[A-Za-z0-9_\-]{6,64}$")


class NotificationsIn(BaseModel):
    email: bool = False
    ntfy_topic: str = ""  # leer = aus


def _out(u: User) -> dict:
    return {
        "email": bool(u.remind_email),
        "ntfy_topic": u.ntfy_topic or "",
        "ntfy_server": settings.ntfy_server,
        "smtp_available": notify.smtp_configured(),
        "enabled": settings.reminders_enabled,
    }


@router.get("")
def get_notifications(user: User = Depends(current_user)):
    return _out(user)


@router.put("")
def save_notifications(data: NotificationsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    topic = data.ntfy_topic.strip()
    if topic and not TOPIC_RE.match(topic):
        raise HTTPException(422, "Das ntfy-Thema darf nur Buchstaben, Ziffern, - und _ enthalten (6 bis 64 Zeichen).")
    user.remind_email = data.email
    user.ntfy_topic = topic or None
    db.commit()
    return _out(user)


@router.post("/test")
def send_test(user: User = Depends(current_user)):
    if not user.remind_email and not user.ntfy_topic:
        raise HTTPException(422, "Aktiviere zuerst E-Mail oder trage ein ntfy-Thema ein und speichere.")
    errors = notify.deliver(user, "BikeHelper: Testnachricht", "So sehen Erinnerungen aus. Alles eingerichtet.")
    if errors:
        raise HTTPException(502, " ".join(errors))
    return {"ok": True}
