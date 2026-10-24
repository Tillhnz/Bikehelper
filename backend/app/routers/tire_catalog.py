from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import tire_catalog as cat
from ..database import get_db
from ..models import User, UserTire
from ..security import current_user

router = APIRouter(prefix="/api/tire-catalog", tags=["tire-catalog"])


class ImportIn(BaseModel):
    csv: str = Field(max_length=cat.MAX_IMPORT_BYTES)
    replace: bool = False  # bisherige eigene Einträge vorher löschen


def _mine(db: Session, user: User) -> list[cat.TireEntry]:
    rows = db.scalars(select(UserTire).where(UserTire.user_id == user.id)).all()
    return [
        cat.TireEntry(
            key=f"u:{r.id}", brand=r.brand, model=r.model, category=r.category, width_mm=r.width_mm, tubeless=r.tubeless,
            weight_g=r.weight_g, watts=r.watts, watts_note=r.watts_note, source_url=r.source_url, own=True,
        )
        for r in rows
    ]


@router.get("")
def search_catalog(
    q: str = Query(default="", max_length=80), category: str | None = Query(default=None, max_length=12),
    limit: int = Query(default=20, ge=1, le=50), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    """Sucht im mitgelieferten Katalog und in den eigenen Einträgen (eigene zuerst bei gleichem Treffer)."""
    entries = _mine(db, user) + list(cat.bundled())
    hits = cat.search(entries, q, category, limit)
    return {
        "items": [e.to_dict() for e in hits],
        "bundled": len(cat.bundled()), "own": sum(1 for e in entries if e.own),
        "categories": cat.CATEGORY_LABEL,
    }


@router.post("/import")
def import_csv(data: ImportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        entries, errors = cat.parse_csv(data.csv, "u:", True)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not entries:
        raise HTTPException(422, "; ".join(errors[:3]) or "Keine Reifen in der Datei gefunden.")
    if data.replace:
        db.execute(delete(UserTire).where(UserTire.user_id == user.id))
    existing = {r.key: r for r in db.scalars(select(UserTire).where(UserTire.user_id == user.id))}
    added = updated = 0
    for e in entries:
        values = dict(
            brand=e.brand, model=e.model, category=e.category, width_mm=e.width_mm, tubeless=e.tubeless,
            weight_g=e.weight_g, watts=e.watts, watts_note=e.watts_note, source_url=e.source_url,
        )
        row = existing.get(e.key) if not data.replace else None
        if row:
            for k, v in values.items():
                setattr(row, k, v)
            updated += 1
        else:
            db.add(UserTire(user_id=user.id, key=e.key, **values))
            added += 1
    db.commit()
    return {"added": added, "updated": updated, "errors": errors[:20], "error_count": len(errors)}


@router.get("/mine")
def my_entries(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [e.to_dict() for e in sorted(_mine(db, user), key=lambda e: e.label.lower())]


@router.delete("/mine", status_code=204)
def delete_all_mine(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(UserTire).where(UserTire.user_id == user.id))
    db.commit()


@router.delete("/mine/{tire_id}", status_code=204)
def delete_mine(tire_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(UserTire, tire_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Eintrag nicht gefunden")
    db.delete(row)
    db.commit()
