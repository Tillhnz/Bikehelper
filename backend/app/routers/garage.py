from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Bike, Component, MaintenanceLog, MaintenanceRule, User
from ..schemas import (
    BikeIn, BikeOut, ComponentIn, ComponentOut, LogIn, LogOut, RuleIn, RuleOut,
)
from ..security import current_user
from ..services import bike_total_km, component_km, component_status, rule_state, worst_status

router = APIRouter(prefix="/api", tags=["garage"])


# ---------- Hilfsfunktionen ----------

def _own_bike(db: Session, user: User, bike_id: int) -> Bike:
    bike = db.get(Bike, bike_id)
    if not bike or bike.user_id != user.id:
        raise HTTPException(404, "Rad nicht gefunden")
    return bike


def _own_component(db: Session, user: User, comp_id: int) -> Component:
    comp = db.get(Component, comp_id)
    if not comp or comp.user_id != user.id:
        raise HTTPException(404, "Komponente nicht gefunden")
    return comp


def _bike_out(db: Session, bike: Bike) -> BikeOut:
    active = [c for c in bike.components if not c.retired_at]
    due = sum(1 for c in active if component_status(db, c) == "due")
    return BikeOut(
        id=bike.id, name=bike.name, type=bike.type, brand=bike.brand, model=bike.model,
        year=bike.year, start_km=bike.start_km, strava_gear_id=bike.strava_gear_id,
        notes=bike.notes, retired=bike.retired,
        total_km=round(bike_total_km(db, bike), 1),
        component_count=len(active), due_count=due,
    )


def _component_out(db: Session, c: Component) -> ComponentOut:
    return ComponentOut(
        id=c.id, bike_id=c.bike_id, category=c.category, name=c.name, brand=c.brand,
        installed_at=c.installed_at, retired_at=c.retired_at, start_km=c.start_km, notes=c.notes,
        km=round(component_km(db, c), 1), status=component_status(db, c),
    )


def _rule_out(db: Session, c: Component, r: MaintenanceRule) -> RuleOut:
    return RuleOut(id=r.id, label=r.label, interval_km=r.interval_km,
                   interval_months=r.interval_months, **rule_state(db, c, r))


# ---------- Räder ----------

@router.get("/bikes", response_model=list[BikeOut])
def list_bikes(user: User = Depends(current_user), db: Session = Depends(get_db)):
    bikes = db.scalars(select(Bike).where(Bike.user_id == user.id).order_by(Bike.retired, Bike.name)).all()
    return [_bike_out(db, b) for b in bikes]


@router.post("/bikes", response_model=BikeOut, status_code=201)
def create_bike(data: BikeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bike = Bike(user_id=user.id, **data.model_dump())
    db.add(bike)
    db.commit()
    return _bike_out(db, bike)


@router.get("/bikes/{bike_id}", response_model=BikeOut)
def get_bike(bike_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _bike_out(db, _own_bike(db, user, bike_id))


@router.put("/bikes/{bike_id}", response_model=BikeOut)
def update_bike(bike_id: int, data: BikeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bike = _own_bike(db, user, bike_id)
    for k, v in data.model_dump().items():
        setattr(bike, k, v)
    db.commit()
    return _bike_out(db, bike)


@router.delete("/bikes/{bike_id}", status_code=204)
def delete_bike(bike_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bike = _own_bike(db, user, bike_id)
    db.delete(bike)
    db.commit()


# ---------- Komponenten ----------

@router.get("/components", response_model=list[ComponentOut])
def list_components(
    bike_id: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    q = select(Component).where(Component.user_id == user.id)
    if bike_id is not None:
        q = q.where(Component.bike_id == bike_id)
    comps = db.scalars(q.order_by(Component.retired_at.is_not(None), Component.category, Component.name)).all()
    return [_component_out(db, c) for c in comps]


@router.post("/components", response_model=ComponentOut, status_code=201)
def create_component(data: ComponentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if data.bike_id is not None:
        _own_bike(db, user, data.bike_id)
    comp = Component(user_id=user.id, **data.model_dump())
    db.add(comp)
    db.commit()
    return _component_out(db, comp)


@router.put("/components/{comp_id}", response_model=ComponentOut)
def update_component(comp_id: int, data: ComponentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    comp = _own_component(db, user, comp_id)
    if data.bike_id is not None:
        _own_bike(db, user, data.bike_id)
    for k, v in data.model_dump().items():
        setattr(comp, k, v)
    db.commit()
    return _component_out(db, comp)


@router.delete("/components/{comp_id}", status_code=204)
def delete_component(comp_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own_component(db, user, comp_id))
    db.commit()


# ---------- Wartungsregeln & -protokoll ----------

@router.get("/components/{comp_id}/rules", response_model=list[RuleOut])
def list_rules(comp_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    comp = _own_component(db, user, comp_id)
    return [_rule_out(db, comp, r) for r in comp.rules]


@router.post("/components/{comp_id}/rules", response_model=RuleOut, status_code=201)
def create_rule(comp_id: int, data: RuleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    comp = _own_component(db, user, comp_id)
    if not data.interval_km and not data.interval_months:
        raise HTTPException(422, "Mindestens ein Intervall (km oder Monate) angeben")
    rule = MaintenanceRule(component_id=comp.id, **data.model_dump())
    db.add(rule)
    db.commit()
    return _rule_out(db, comp, rule)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rule = db.get(MaintenanceRule, rule_id)
    if not rule or rule.component.user_id != user.id:
        raise HTTPException(404, "Regel nicht gefunden")
    db.delete(rule)
    db.commit()


@router.get("/components/{comp_id}/logs", response_model=list[LogOut])
def list_logs(comp_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    comp = _own_component(db, user, comp_id)
    return sorted(comp.logs, key=lambda l: l.performed_at, reverse=True)


@router.post("/components/{comp_id}/logs", response_model=LogOut, status_code=201)
def create_log(comp_id: int, data: LogIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    comp = _own_component(db, user, comp_id)
    log = MaintenanceLog(component_id=comp.id, **data.model_dump())
    db.add(log)
    db.commit()
    return log


# ---------- Übersicht: fällige Wartungen ----------

@router.get("/maintenance/overview")
def maintenance_overview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    comps = db.scalars(
        select(Component).where(Component.user_id == user.id, Component.retired_at.is_(None))
    ).all()
    items = []
    for c in comps:
        for r in c.rules:
            st = rule_state(db, c, r)
            if st["status"] != "ok":
                items.append({
                    "component_id": c.id, "component": c.name, "category": c.category,
                    "bike_id": c.bike_id, "bike": c.bike.name if c.bike else None,
                    "rule": r.label, **st,
                })
    items.sort(key=lambda i: i["progress"], reverse=True)
    return {"items": items, "status": worst_status([i["status"] for i in items])}
