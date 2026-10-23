from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..catalog import CATALOG, chain_rules
from ..database import get_db
from ..models import Bike, Component, InventoryItem, MaintenanceRule, User
from ..schemas import InstallIn, InventoryIn, InventoryOut
from ..security import current_user

router = APIRouter(prefix="/api", tags=["inventory"])


def _out(i: InventoryItem) -> InventoryOut:
    return InventoryOut(
        id=i.id, category=i.category, name=i.name, brand=i.brand, spec=i.spec, quantity=i.quantity,
        min_quantity=i.min_quantity, price_eur=i.price_eur, purchased_at=i.purchased_at, location=i.location,
        notes=i.notes, bike_id=i.bike_id,
        low=i.min_quantity is not None and i.quantity < i.min_quantity,
    )


def _own(db: Session, user: User, item_id: int) -> InventoryItem:
    item = db.get(InventoryItem, item_id)
    if not item or item.user_id != user.id:
        raise HTTPException(404, "Teil nicht gefunden")
    return item


def _check_bike(db: Session, user: User, bike_id: int | None) -> Bike | None:
    if bike_id is None:
        return None
    bike = db.get(Bike, bike_id)
    if not bike or bike.user_id != user.id:
        raise HTTPException(404, "Rad nicht gefunden")
    return bike


@router.get("/inventory")
def list_inventory(user: User = Depends(current_user), db: Session = Depends(get_db)):
    items = db.scalars(select(InventoryItem).where(InventoryItem.user_id == user.id).order_by(InventoryItem.category, InventoryItem.name)).all()
    out = [_out(i) for i in items]
    value = sum((i.price_eur or 0) * i.quantity for i in items)
    return {
        "items": out,
        "totals": {"items": len(items), "pieces": sum(i.quantity for i in items), "value_eur": round(value, 2),
                   "low": sum(1 for i in out if i.low)},
    }


@router.post("/inventory", response_model=InventoryOut, status_code=201)
def create_item(data: InventoryIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _check_bike(db, user, data.bike_id)
    item = InventoryItem(user_id=user.id, **data.model_dump())
    db.add(item)
    db.commit()
    return _out(item)


@router.put("/inventory/{item_id}", response_model=InventoryOut)
def update_item(item_id: int, data: InventoryIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = _own(db, user, item_id)
    _check_bike(db, user, data.bike_id)
    for k, v in data.model_dump().items():
        setattr(item, k, v)
    db.commit()
    return _out(item)


@router.delete("/inventory/{item_id}", status_code=204)
def delete_item(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own(db, user, item_id))
    db.commit()


@router.post("/inventory/{item_id}/install", status_code=201)
def install_item(item_id: int, data: InstallIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Baut ein Teil aus dem Lager ein: legt die Komponente mit Wartungsregeln an, mustert ein Teil derselben Art aus
    und verringert den Bestand um eins."""
    item = _own(db, user, item_id)
    bike = _check_bike(db, user, data.bike_id)
    if item.quantity < 1:
        raise HTTPException(409, "Dieses Teil ist nicht mehr auf Lager.")
    replaced = None
    if item.category in CATALOG:
        for c in bike.components:
            if c.category == item.category and not c.retired_at:
                c.retired_at = data.installed_at
                replaced = c.name
    comp = Component(
        user_id=user.id, bike_id=bike.id, category=item.category, name=item.name, brand=item.brand,
        installed_at=data.installed_at, start_km=0, notes=item.spec or None,
    )
    tpl = CATALOG.get(item.category)
    if tpl and data.with_rules:
        rules = chain_rules(bike.chain_lube) if item.category == "chain" else tpl.rules
        comp.rules = [
            MaintenanceRule(label=r.label, interval_km=r.interval_km, interval_months=r.interval_months,
                            wet_factor=r.wet_factor, hint=r.hint or None)
            for r in rules
        ]
    db.add(comp)
    item.quantity -= 1
    db.commit()
    return {"component_id": comp.id, "replaced": replaced, "item": _out(item)}
