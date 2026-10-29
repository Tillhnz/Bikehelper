from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..catalog import INSPECTIONS, WAX_LUBE_LABEL, WAX_VARIANTS, catalog_payload, guides_for
from ..database import get_db
from ..access import can_use
from ..models import Bike, ChainMeasurement, Component, MaintenanceLog, MaintenanceRule, TireSet, User
from ..schemas import (
    BikeCreate, BikeIn, BikeOut, ComponentIn, ComponentOut, InspectionIn, LogIn, LogOut, ReplaceIn, RuleDoneIn, RuleIn,
    MeasurementIn, MeasurementOut, MountedTireSet, RuleOut, StandardComponentsIn, WaxVariantOut,
)
from ..security import current_user
from ..services import (
    apply_chain_lube, bike_total_km, component_km, component_status, create_default_components, current_tire_set,
    effective_installed, is_replacement_rule, is_tracked, measurement_points, open_mount,
    rule_state, tire_set_km, tire_state, worst_status,
)

router = APIRouter(prefix="/api", tags=["garage"])


# ---------- Hilfsfunktionen ----------

def _own_bike(db: Session, user: User, bike_id: int) -> Bike:
    bike = db.get(Bike, bike_id)
    if not bike or bike.user_id != user.id:
        raise HTTPException(404, "Rad nicht gefunden")
    return bike


def _shared_bike(db: Session, user: User, bike_id: int) -> Bike:
    """Eigenes Rad oder Rad eines Partners, der dem Nutzer als Mechaniker Zugriff gegeben hat."""
    bike = db.get(Bike, bike_id)
    if not bike or not can_use(db, user, bike.user_id):
        raise HTTPException(404, "Rad nicht gefunden")
    return bike


def _own_component(db: Session, user: User, comp_id: int) -> Component:
    comp = db.get(Component, comp_id)
    if not comp or not can_use(db, user, comp.user_id):
        raise HTTPException(404, "Komponente nicht gefunden")
    return comp


def _own_rule(db: Session, user: User, rule_id: int) -> MaintenanceRule:
    rule = db.get(MaintenanceRule, rule_id)
    if not rule or not can_use(db, user, rule.component.user_id):
        raise HTTPException(404, "Regel nicht gefunden")
    return rule


def _by(user: User, owner_id: int) -> str | None:
    """Wer hat eingetragen? Nur gesetzt, wenn ein Mechaniker für einen Partner arbeitet."""
    return user.email if user.id != owner_id else None


def _bike_out(db: Session, bike: Bike) -> BikeOut:
    active = [c for c in bike.components if not c.retired_at and is_tracked(c)]
    statuses = [component_status(db, c) for c in active]
    ts = current_tire_set(db, bike.id)
    return BikeOut(
        id=bike.id, name=bike.name, type=bike.type, brand=bike.brand, model=bike.model,
        year=bike.year, start_km=bike.start_km, strava_gear_id=bike.strava_gear_id,
        notes=bike.notes, retired=bike.retired, purchased_at=bike.purchased_at,
        chain_lube=bike.chain_lube or "oil", tire_width_mm=bike.tire_width_mm, rim_inner_mm=bike.rim_inner_mm,
        bike_weight_kg=bike.bike_weight_kg, tubeless=True if bike.tubeless is None else bike.tubeless,
        hookless=bool(bike.hookless),
        total_km=round(bike_total_km(db, bike), 1),
        component_count=len(active),
        due_count=sum(1 for s in statuses if s == "due"),
        unknown_count=sum(1 for s in statuses if s == "unknown"),
        tire_set=MountedTireSet(id=ts.id, name=ts.name, width_mm=ts.width_mm, km=round(tire_set_km(db, ts), 1)) if ts else None,
    )


def _component_out(db: Session, c: Component) -> ComponentOut:
    return ComponentOut(
        id=c.id, bike_id=c.bike_id, category=c.category, name=c.name, brand=c.brand,
        installed_at=c.installed_at, retired_at=c.retired_at, start_km=c.start_km, notes=c.notes,
        wear_limit_pct=c.wear_limit_pct, shop_url=c.shop_url, km=round(component_km(db, c), 1), status=component_status(db, c),
        installed_effective=effective_installed(c), installed_inherited=not c.installed_at and effective_installed(c) is not None,
    )


def _rule_out(db: Session, c: Component, r: MaintenanceRule) -> RuleOut:
    st = rule_state(db, c, r)
    interval_km = st.pop("interval_km_eff")
    if interval_km is not None:
        interval_km = max(1, round(interval_km))  # Prüfergebnisse können das Intervall krumm machen
    variants = (
        [WaxVariantOut(key=k, name=v["name"], interval_km=v["interval_km"]) for k, v in WAX_VARIANTS.items()]
        if r.label == WAX_LUBE_LABEL else None
    )
    return RuleOut(
        id=r.id, label=r.label, interval_km=interval_km, interval_months=r.interval_months,
        wet_factor=r.wet_factor or 1.0, hint=r.hint, is_inspection=r.label in INSPECTIONS, visual_check=is_replacement_rule(r), variants=variants, guides=guides_for(r.label), **st,
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
    bike = _shared_bike(db, user, bike_id)
    created = create_default_components(db, bike.user_id, bike, data.categories)
    db.commit()
    return [_component_out(db, c) for c in created]


@router.get("/bikes/{bike_id}", response_model=BikeOut)
def get_bike(bike_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bike = _shared_bike(db, user, bike_id)
    out = _bike_out(db, bike)
    if bike.user_id != user.id:
        out.shared_from = db.get(User, bike.user_id).email
    return out


@router.put("/bikes/{bike_id}", response_model=BikeOut)
def update_bike(bike_id: int, data: BikeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bike = _shared_bike(db, user, bike_id)
    old_lube = bike.chain_lube or "oil"
    for k, v in data.model_dump().items():
        setattr(bike, k, v)
    if (bike.chain_lube or "oil") != old_lube:
        apply_chain_lube(db, bike)
    db.commit()
    out = _bike_out(db, bike)
    if bike.user_id != user.id:
        out.shared_from = db.get(User, bike.user_id).email
    return out


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
    if bike_id is not None:
        bike = _shared_bike(db, user, bike_id)  # auch Räder von Partnern
        q = select(Component).where(Component.user_id == bike.user_id, Component.bike_id == bike_id)
    else:
        q = select(Component).where(Component.user_id == user.id)
    comps = db.scalars(q.order_by(Component.retired_at.is_not(None), Component.category, Component.name)).all()
    return [_component_out(db, c) for c in comps]


@router.post("/components", response_model=ComponentOut, status_code=201)
def create_component(data: ComponentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owner_id = user.id
    if data.bike_id is not None:
        owner_id = _shared_bike(db, user, data.bike_id).user_id
    comp = Component(user_id=owner_id, **data.model_dump())
    db.add(comp)
    db.commit()
    return _component_out(db, comp)


@router.put("/components/{comp_id}", response_model=ComponentOut)
def update_component(comp_id: int, data: ComponentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    comp = _own_component(db, user, comp_id)
    if data.bike_id is not None and _shared_bike(db, user, data.bike_id).user_id != comp.user_id:
        raise HTTPException(404, "Rad nicht gefunden")  # Teile wandern nie zwischen Konten
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
        user_id=old.user_id, bike_id=old.bike_id, category=old.category,
        name=data.name or old.name, brand=data.brand if data.brand is not None else old.brand,
        installed_at=data.performed_at, start_km=0, shop_url=old.shop_url,
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
    values = data.model_dump()
    if rule.label != WAX_LUBE_LABEL:
        values["variant"] = None  # die Wachsart gibt es nur bei der Wachsregel
    if rule.label not in INSPECTIONS:
        values["result"] = None  # ein Prüfergebnis gibt es nur bei Prüfregeln
    log = MaintenanceLog(component_id=rule.component_id, rule_id=rule.id, performed_by=_by(user, rule.component.user_id), **values)
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
    log = MaintenanceLog(component_id=comp.id, performed_by=_by(user, comp.user_id), **data.model_dump())
    db.add(log)
    db.commit()
    return log


@router.post("/components/{comp_id}/inspections", response_model=LogOut, status_code=201)
def create_inspection(comp_id: int, data: InspectionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Sichtprüfung der Komponente: gut, im Auge behalten (Restlaufzeit halbiert) oder wechseln (sofort fällig).
    Zählt nicht als Wartung, die Zähler der Regeln bleiben unberührt."""
    comp = _own_component(db, user, comp_id)
    log = MaintenanceLog(component_id=comp.id, rule_id=None, performed_by=_by(user, comp.user_id), **data.model_dump())
    db.add(log)
    db.commit()
    return log


@router.delete("/logs/{log_id}", status_code=204)
def delete_log(log_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Entfernt einen Wartungseintrag, zum Beispiel bei einem falschen Datum. Die Zähler rechnen danach neu."""
    log = db.get(MaintenanceLog, log_id)
    if not log or not can_use(db, user, log.component.user_id):
        raise HTTPException(404, "Wartungseintrag nicht gefunden")
    db.delete(log)
    db.commit()


# ---------- Kettenmessung ----------

@router.get("/components/{comp_id}/measurements", response_model=list[MeasurementOut])
def list_measurements(comp_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return measurement_points(db, _own_component(db, user, comp_id))


@router.post("/components/{comp_id}/measurements", response_model=list[MeasurementOut], status_code=201)
def add_measurement(comp_id: int, data: MeasurementIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Trägt einen Messwert der Kettenlehre ein. Die Verschleißregel der Kette rechnet danach mit dem Messwert."""
    comp = _own_component(db, user, comp_id)
    if comp.category != "chain":
        raise HTTPException(422, "Messwerte gibt es nur für Ketten.")
    if data.limit_pct is not None:
        comp.wear_limit_pct = data.limit_pct
    db.add(ChainMeasurement(component_id=comp.id, measured_at=data.measured_at, wear_pct=data.wear_pct, note=data.note))
    db.commit()
    db.refresh(comp)
    return measurement_points(db, comp)


@router.delete("/measurements/{m_id}", response_model=list[MeasurementOut])
def delete_measurement(m_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = db.get(ChainMeasurement, m_id)
    if not m or not can_use(db, user, m.component.user_id):
        raise HTTPException(404, "Messwert nicht gefunden")
    comp = m.component
    db.delete(m)
    db.commit()
    db.refresh(comp)
    return measurement_points(db, comp)


# ---------- Übersicht: fällige Wartungen ----------

@router.get("/maintenance/overview")
def maintenance_overview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    comps = db.scalars(
        select(Component).where(Component.user_id == user.id, Component.retired_at.is_(None))
    ).all()
    items = []
    for c in comps:
        if not is_tracked(c):
            continue
        for r in c.rules:
            st = rule_state(db, c, r)
            if st["status"] in ("soon", "due"):
                items.append({
                    "component_id": c.id, "component": c.name, "category": c.category,
                    "bike_id": c.bike_id, "bike": c.bike.name if c.bike else None,
                    "shop_url": c.shop_url, "rule_id": r.id, "is_inspection": r.label in INSPECTIONS, "visual_check": is_replacement_rule(r),
                    "rule": r.label, "wet_factor": r.wet_factor or 1.0, **{k: v for k, v in st.items() if k != "interval_km_eff"},
                })
    # Montierte Reifensätze: Lebensdauer und Sichtprüfung
    for ts in db.scalars(select(TireSet).where(TireSet.user_id == user.id, TireSet.retired.is_(False))).all():
        if open_mount(ts) is None or ts.bike.retired:
            continue
        st = tire_state(db, ts)
        base = {"component_id": f"tire-{ts.id}", "tire_set_id": ts.id, "component": ts.name, "category": "tires",
                "bike_id": ts.bike_id, "bike": ts.bike.name, "shop_url": ts.shop_url, "rule_id": None, "wet_factor": 1.0}
        if st["life_status"] != "ok":
            items.append({**base, "rule": "Reifen wechseln", "is_inspection": False, "status": st["life_status"],
                          "progress": st["progress"], "km": round(st["km"], 1)})
        if st["check_status"] != "ok":
            items.append({**base, "rule": "Reifen prüfen", "is_inspection": True, "status": st["check_status"],
                          "progress": st["check_progress"], "km": round(st["km_since_check"], 1)})
    items.sort(key=lambda i: i["progress"], reverse=True)
    return {"items": items, "status": worst_status([i["status"] for i in items])}
