"""Reifenmanagement: Reifensätze je Rad, welcher gerade montiert ist, und die Kilometer darauf."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Bike, TireMount, TireSet, User
from ..schemas import MountDateIn, MountOut, MountRangeIn, TireSetCreate, TireSetIn, TireSetOut
from ..security import current_user
from ..services import (
    find_overlap, mount_km, mount_tire_set, open_mount, sync_bike_tires, tire_set_km, unmount_tire_set,
)
from .garage import _own_bike

router = APIRouter(prefix="/api", tags=["tires"])


def _own_set(db: Session, user: User, set_id: int) -> TireSet:
    ts = db.get(TireSet, set_id)
    if not ts or ts.user_id != user.id:
        raise HTTPException(404, "Reifensatz nicht gefunden")
    return ts


def _out(db: Session, ts: TireSet) -> TireSetOut:
    km = tire_set_km(db, ts)
    current = open_mount(ts)
    mounts = sorted(ts.mounts, key=lambda m: m.from_date, reverse=True)
    return TireSetOut(
        id=ts.id, bike_id=ts.bike_id, name=ts.name, brand=ts.brand, width_mm=ts.width_mm, tubeless=ts.tubeless,
        start_km=ts.start_km, max_km=ts.max_km, notes=ts.notes, retired=ts.retired,
        km=round(km, 1), mounted=current is not None and not ts.retired,
        mounted_since=current.from_date if current else None,
        progress=round(km / ts.max_km, 3) if ts.max_km else None,
        mounts=[
            MountOut(id=m.id, from_date=m.from_date, to_date=m.to_date, km=round(mount_km(db, ts.bike_id, m), 1))
            for m in mounts
        ],
    )


@router.get("/bikes/{bike_id}/tire-sets", response_model=list[TireSetOut])
def list_tire_sets(bike_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own_bike(db, user, bike_id)
    sets = db.scalars(select(TireSet).where(TireSet.bike_id == bike_id).order_by(TireSet.retired, TireSet.name)).all()
    return [_out(db, ts) for ts in sets]


@router.post("/bikes/{bike_id}/tire-sets", response_model=TireSetOut, status_code=201)
def create_tire_set(bike_id: int, data: TireSetCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bike = _own_bike(db, user, bike_id)
    ts = TireSet(user_id=user.id, bike_id=bike.id, **data.model_dump(exclude={"mount_from"}))
    db.add(ts)
    db.flush()
    if data.mount_from and not ts.retired:
        mount_tire_set(db, ts, data.mount_from)
    db.commit()
    return _out(db, ts)


@router.put("/tire-sets/{set_id}", response_model=TireSetOut)
def update_tire_set(set_id: int, data: TireSetIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ts = _own_set(db, user, set_id)
    for k, v in data.model_dump().items():
        setattr(ts, k, v)
    if ts.retired:
        unmount_tire_set(db, ts, date.today())
    elif open_mount(ts):
        sync_bike_tires(ts.bike, ts)  # geänderte Breite gilt sofort für das Rad
    db.commit()
    return _out(db, ts)


@router.delete("/tire-sets/{set_id}", status_code=204)
def delete_tire_set(set_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own_set(db, user, set_id))
    db.commit()


@router.post("/tire-sets/{set_id}/mount", response_model=TireSetOut)
def mount(set_id: int, data: MountDateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Montiert den Satz ab dem Tag. Alle Fahrten des Rades ab da zählen auf diesen Satz, bis ein anderer montiert wird."""
    ts = _own_set(db, user, set_id)
    if ts.retired:
        raise HTTPException(409, "Dieser Satz ist ausgemustert. Hebe das Ausmustern auf, um ihn wieder zu montieren.")
    for other in db.scalars(select(TireSet).where(TireSet.bike_id == ts.bike_id)):
        for m in other.mounts:
            if (m.to_date is not None and m.to_date >= data.day) or (
                m.to_date is None and other.id != ts.id and m.from_date > data.day
            ):
                raise HTTPException(
                    409,
                    f"„{other.name}“ war ab dem {m.from_date:%d.%m.%Y} montiert. Wähle einen späteren Tag oder passe den Verlauf an.",
                )
    mount_tire_set(db, ts, data.day)
    db.commit()
    return _out(db, ts)


@router.post("/tire-sets/{set_id}/unmount", response_model=TireSetOut)
def unmount(set_id: int, data: MountDateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ts = _own_set(db, user, set_id)
    unmount_tire_set(db, ts, data.day)
    db.commit()
    return _out(db, ts)


def _check_range(db: Session, ts: TireSet, body: MountRangeIn, ignore_id: int | None) -> None:
    if body.to_date and body.to_date < body.from_date:
        raise HTTPException(422, "Das Ende liegt vor dem Beginn.")
    clash = find_overlap(db, ts.bike_id, body.from_date, body.to_date, ignore_id)
    if clash:
        raise HTTPException(409, f"Der Zeitraum überschneidet sich mit „{clash[0].name}“ ({clash[1].from_date:%d.%m.%Y}).")


@router.post("/tire-sets/{set_id}/mounts", response_model=TireSetOut, status_code=201)
def add_mount(set_id: int, data: MountRangeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Trägt einen Zeitraum nach, in dem der Satz montiert war (zum Beispiel vor der ersten Nutzung der App)."""
    ts = _own_set(db, user, set_id)
    _check_range(db, ts, data, None)
    db.add(TireMount(tire_set_id=ts.id, from_date=data.from_date, to_date=data.to_date))
    db.flush()
    if data.to_date is None and not ts.retired:
        sync_bike_tires(ts.bike, ts)
    db.commit()
    return _out(db, ts)


@router.put("/tire-mounts/{mount_id}", response_model=TireSetOut)
def update_mount(mount_id: int, data: MountRangeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = db.get(TireMount, mount_id)
    if not m or m.tire_set.user_id != user.id:
        raise HTTPException(404, "Zeitraum nicht gefunden")
    _check_range(db, m.tire_set, data, m.id)
    m.from_date, m.to_date = data.from_date, data.to_date
    db.commit()
    return _out(db, m.tire_set)


@router.delete("/tire-mounts/{mount_id}", response_model=TireSetOut)
def delete_mount(mount_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = db.get(TireMount, mount_id)
    if not m or m.tire_set.user_id != user.id:
        raise HTTPException(404, "Zeitraum nicht gefunden")
    ts = m.tire_set
    db.delete(m)
    db.commit()
    db.refresh(ts)
    return _out(db, ts)
