from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..catalog import catalog_payload
from ..database import get_db
from ..models import Bike, Component, MaintenanceLog, MaintenanceRule, User
from ..schemas import (
    BikeCreate, BikeIn, BikeOut, ComponentIn, ComponentOut, LogIn, LogOut, ReplaceIn, RuleDoneIn, RuleIn,
    RuleOut, StandardComponentsIn,
)
from ..security import current_user
from ..services import (
    bike_total_km, component_km, component_status, create_default_components, rule_state, worst_status,
)

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


def _own_rule(db: Session, user: User, rule_id: int) -> MaintenanceRule:
    rule = db.get(MaintenanceRule, rule_id)
    if not rule or rule.component.user_id != user.id:
        raise HTTPException(404, "Regel nicht gefunden")
    return rule


def _bike_out(db: Session, bike: Bike) -> BikeOut:
    active = [c for c in bike.components if not c.retired_at]
    statuses = [component_status(db, c) for c in active]
    return BikeOut(
        id=bike.id, name=bike.name, type=bike.type, brand=bike.brand, model=bike.model,
        year=bike.year, start_km=bike.start_km, strava_gear_id=bike.strava_gear_id,
        notes=bike.notes, retired=bike.retired,
        total_km=round(bike_total_km(db, bike), 1),
        component_count=len(active),
        due_count=sum(1 for s in statuses if s == "due"),
        unknown_count=sum(1 for s in statuses if s == "unknown"),
    )


def _component_out(db: Session, c: Component) -> ComponentOut:
    return ComponentOut(
        id=c.id, bike_id=c.bike_id, category=c.category, name=c.name, brand=c.brand,
        installed_at=c.installed_at, retired_at=c.retired_at, start_km=c.start_km, notes=c.notes,
        km=round(component_km(db, c), 1), status=component_status(db, c),
    )


def _rule_out(db: Session, c: Component, r: MaintenanceRule) -> RuleOut:
    return RuleOut(
        id=r.id, label=r.label, interval_km=r.interval_km, interval_months=r.interval_months,
        wet_factor=r.wet_factor or 1.0, hint=r.hint, **rule_state(db, c, r),
    )


# ---------- Katalog ----------

@router.get("/catalog")
def get_catalog(user: User = Depends(current_user)):
    """Standardkomponenten und Wartungsintervalle samt Nässefaktoren."""
    return catalog_payload()


# ---------- Räder ----------

@router.get("/bikes", response_model=list[BikeOut])
def list_bikes(user: User = Depends(current_user), db: Session = Depends(get_db)):
    bikes = db.scalars(select(Bike).where(Bike.user_id == user.id).order_by(Bike.retired, Bike.name)).all()
    return [_bike_out(db, b) for b in bikes]


@router.post("/bikes", response_model=BikeOut, status_code=201)
def create_bike(data: BikeCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bike = Bike(user_id=user.id, **data.model_dump(exclude={"with_defaults"}))
    db.add(bike)
    db.flush()
    if data.with_defaults:
        create_default_components(db, user.id, bike)
    db.commit()
    return _bike_out(db, bike)


@router.post("/bikes/{bike_id}/standard-components", response_model=list[ComponentOut], status_code=201)
def add_standard_components(
    bike_id: int, data: StandardComponentsIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    """Ergänzt fehlende Standardkomponenten (Kategorien, die das Rad schon hat, bleiben unberührt)."""
    bike = _own_bike(db, user, bike_id)
    created = create_default_components(db, user.id, bike, data.categories)
    db.commit()
    return [_component_out(db, c) for c in created]


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


@router.post("/components/{comp_id}/replace", response_model=ComponentOut, status_code=201)
def replace_component(
    comp_id: int, data: ReplaceIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    """Teil gewechselt: das alte Teil wird ausgemustert, ein neues mit denselben Regeln eingebaut."""
    old = _own_component(db, user, comp_id)
    if old.retired_at:
        raise HTTPException(409, "Dieses Teil ist bereits ausgemustert.")
    old.retired_at = data.performed_at
    new = Component(
        user_id=user.id, bike_id=old.bike_id, category=old.category,
        name=data.name or old.name, brand=data.brand if data.brand is not None else old.brand,
        installed_at=data.performed_at, start_km=0,
    )
    new.rules = [
        MaintenanceRule(
            label=r.label, interval_km=r.interval_km, interval_months=r.interval_months,
            wet_factor=r.wet_factor, hint=r.hint,
        )
        for r in old.rules
    ]
    db.add(new)
    db.commit()
    return _component_out(db, new)


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
    rule = _own_rule(db, user, rule_id)
    db.execute(delete(MaintenanceLog).where(MaintenanceLog.rule_id == rule.id))
    db.delete(rule)
    db.commit()


@router.post("/rules/{rule_id}/done", response_model=LogOut, status_code=201)
def rule_done(rule_id: int, data: RuleDoneIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Trägt ein, dass diese eine Aufgabe erledigt wurde; der Zähler dieser Regel startet neu."""
    rule = _own_rule(db, user, rule_id)
    log = MaintenanceLog(component_id=rule.component_id, rule_id=rule.id, **data.model_dump())
    db.add(log)
    db.commit()
    return log


@router.get("/components/{comp_id}/logs", response_model=list[LogOut])
def list_logs(comp_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    comp = _own_component(db, user, comp_id)
    return sorted(comp.logs, key=lambda l: l.performed_at, reverse=True)


@router.post("/components/{comp_id}/logs", response_model=LogOut, status_code=201)
def create_log(comp_id: int, data: LogIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Wartung für die ganze Komponente (setzt alle ihre Regeln zurück)."""
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
            if st["status"] in ("soon", "due"):
                items.append({
                    "component_id": c.id, "component": c.name, "category": c.category,
                    "bike_id": c.bike_id, "bike": c.bike.name if c.bike else None,
                    "rule": r.label, "wet_factor": r.wet_factor or 1.0, **st,
                })
    items.sort(key=lambda i: i["progress"], reverse=True)
    return {"items": items, "status": worst_status([i["status"] for i in items])}
