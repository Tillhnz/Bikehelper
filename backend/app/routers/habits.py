"""Nass-Putzen, Tags und Rad am Arbeitsplatz."""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import habits
from ..database import get_db
from ..models import Activity, ActivityTag, User, WashEvent
from ..security import current_user
from .garage import _own_bike

router = APIRouter(prefix="/api", tags=["habits"])

WASH_WET_KM_DRIED = 10.0   # nass geputzt, Kette danach abgetrocknet und nachgeölt: wie 10 km Fahrt im Regen
WASH_WET_KM_NOT_DRIED = 30.0  # nass geputzt und die Kette blieb feucht: deutlich mehr Belastung (Rost, Lager, Bremsen)


# ---------- Nass geputzt ----------

class WashIn(BaseModel):
    chain_dried: bool = True
    day: date | None = None  # Standard: heute


class WashOut(BaseModel):
    id: int
    at: datetime
    chain_dried: bool
    wet_km: float


def wash_km(chain_dried: bool) -> float:
    return WASH_WET_KM_DRIED if chain_dried else WASH_WET_KM_NOT_DRIED


@router.get("/bikes/{bike_id}/washes", response_model=list[WashOut])
def list_washes(bike_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own_bike(db, user, bike_id)
    rows = db.scalars(select(WashEvent).where(WashEvent.bike_id == bike_id).order_by(WashEvent.at.desc()).limit(20)).all()
    return [WashOut(id=w.id, at=w.at, chain_dried=w.chain_dried, wet_km=w.wet_km) for w in rows]


@router.post("/bikes/{bike_id}/washes", response_model=WashOut, status_code=201)
def add_wash(bike_id: int, data: WashIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own_bike(db, user, bike_id)
    day = data.day or datetime.now(timezone.utc).date()
    if day > datetime.now(timezone.utc).date():
        raise HTTPException(422, "Das Datum liegt in der Zukunft.")
    w = WashEvent(user_id=user.id, bike_id=bike_id, at=datetime.combine(day, datetime.min.time()).replace(hour=12),
                  chain_dried=data.chain_dried, wet_km=wash_km(data.chain_dried))
    db.add(w)
    db.commit()
    return WashOut(id=w.id, at=w.at, chain_dried=w.chain_dried, wet_km=w.wet_km)


@router.delete("/washes/{wash_id}", status_code=204)
def delete_wash(wash_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    w = db.get(WashEvent, wash_id)
    if not w or w.user_id != user.id:
        raise HTTPException(404, "Eintrag nicht gefunden")
    db.delete(w)
    db.commit()


# ---------- Tags ----------

class TagIn(BaseModel):
    tag: str = Field(min_length=1, max_length=60)


@router.get("/tags")
def list_tags(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(ActivityTag.tag, func.count()).where(ActivityTag.user_id == user.id, ActivityTag.state != "rejected")
        .group_by(ActivityTag.tag).order_by(func.count().desc())
    ).all()
    return [{"tag": t, "count": n} for t, n in rows]


def _tags_out(db: Session, activity_id: int) -> list[dict]:
    return tags_for(db, [activity_id]).get(activity_id, [])


def tags_for(db: Session, ids: list[int]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    if not ids:
        return out
    rows = db.execute(
        select(ActivityTag.activity_id, ActivityTag.tag, ActivityTag.state, ActivityTag.reason)
        .where(ActivityTag.activity_id.in_(ids), ActivityTag.state != "rejected").order_by(ActivityTag.tag)
    ).all()
    for aid, tag, state, reason in rows:
        out.setdefault(aid, []).append({"tag": tag, "auto": state == "auto", "reason": reason if state == "auto" else None})
    return out


@router.post("/activities/{activity_id}/tags")
def add_tag(activity_id: int, data: TagIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Activity, activity_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "Fahrt nicht gefunden")
    tag = habits.clean_tag(data.tag)
    if not tag:
        raise HTTPException(422, "Bitte ein Tag angeben.")
    row = db.get(ActivityTag, (activity_id, tag))
    if row is None:
        db.add(ActivityTag(activity_id=activity_id, tag=tag, user_id=user.id, state="manual"))
    else:  # bestätigt ein automatisches Tag oder holt ein entferntes zurück
        row.state, row.reason = "manual", None
    db.commit()
    habits.trigger(user.id)  # ähnliche Fahrten können jetzt automatisch dazukommen
    return _tags_out(db, activity_id)


@router.delete("/activities/{activity_id}/tags/{tag}")
def remove_tag(activity_id: int, tag: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Activity, activity_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "Fahrt nicht gefunden")
    row = db.get(ActivityTag, (activity_id, habits.clean_tag(tag)))
    if row is not None:
        if row.state == "auto":
            row.state = "rejected"  # merken, damit der Server es hier nicht wieder vergibt
        else:
            db.delete(row)
        db.commit()
    return _tags_out(db, activity_id)


# ---------- Rad am Arbeitsplatz ----------

class WorkplaceIn(BaseModel):
    storage: str | None = Field(default=None, pattern="^(dry|outdoor)$")


def _workplace(db: Session, user: User) -> dict:
    pairs = db.execute(
        select(func.count(), func.coalesce(func.avg(Activity.stand_h), 0.0), func.coalesce(func.sum(Activity.stand_wet_km), 0.0))
        .where(Activity.user_id == user.id, Activity.stand_status.is_not(None))
    ).one()
    commutes = db.scalar(
        select(func.count()).select_from(ActivityTag).where(ActivityTag.user_id == user.id, ActivityTag.tag == habits.COMMUTE_TAG,
                                                              ActivityTag.state != "rejected")) or 0
    return {**habits.overview(db, user), "storage": user.work_storage, "commute_rides": commutes, "stands": pairs[0], "avg_stand_h": round(float(pairs[1]), 1),
            "wet_km": round(float(pairs[2]), 1)}


@router.get("/settings/workplace")
def get_workplace(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _workplace(db, user)


@router.put("/settings/workplace")
def set_workplace(data: WorkplaceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    changed = user.work_storage != data.storage
    user.work_storage = data.storage
    db.commit()
    if changed:
        habits.clear_stands(db, user.id)  # alte Bewertungen passen nicht mehr zur neuen Einstellung
        if data.storage == "outdoor":
            habits.trigger(user.id)
    return _workplace(db, user)
