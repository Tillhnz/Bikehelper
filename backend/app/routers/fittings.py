"""Bikefitting: Messwerte aus dem Maßblatt des Fitters je Rad (Ausgangsposition und optimierte Position)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BikeFitting, User
from ..security import current_user
from .garage import _own_bike

router = APIRouter(prefix="/api", tags=["fitting"])

# Felder des Maßblatts: Schlüssel -> (Bezeichnung, Einheit, Art, kleinster, größter Wert). Art: num oder text.
FIELDS: dict[str, tuple[str, str, str, float, float]] = {
    "saddle_height": ("Sattelhöhe", "cm", "num", 40, 110),
    "saddle_setback": ("Sattelversatz", "cm", "num", -30, 30),
    "saddle_to_bar": ("Sattelspitze bis Armauflagen oder Lenker", "cm", "num", 30, 100),
    "drop": ("Überhöhung", "cm", "num", -15, 35),
    "bar_width": ("Lenkerbreite", "mm", "num", 250, 560),
    "stem_length": ("Vorbaulänge", "mm", "num", 30, 200),
    "stem_angle": ("Vorbauwinkel", "°", "num", -40, 40),
    "saddle_tilt": ("Sattelneigung", "°", "num", -20, 20),
    "lever_tilt": ("Bremsgriffneigung", "", "text", 0, 0),
}


def _clean(values: dict | None) -> dict:
    out: dict = {}
    for key, raw in (values or {}).items():
        spec = FIELDS.get(key)
        if spec is None:
            raise ValueError(f"Unbekanntes Feld: {key}")
        if raw is None or raw == "":
            continue
        label, _, kind, lo, hi = spec
        if kind == "text":
            out[key] = str(raw).strip()[:60]
            continue
        try:
            num = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{label}: bitte eine Zahl angeben") from None
        if not lo <= num <= hi:
            raise ValueError(f"{label}: {num:g} liegt außerhalb von {lo:g} bis {hi:g}")
        out[key] = num
    return out


class FittingIn(BaseModel):
    fitted_on: date
    fitter: str | None = Field(default=None, max_length=120)
    saddle_model: str | None = Field(default=None, max_length=80)
    pedal_system: str | None = Field(default=None, max_length=80)
    crank_mm: float | None = Field(default=None, ge=120, le=200)
    frame_size: str | None = Field(default=None, max_length=40)
    initial: dict = {}
    optimized: dict = {}
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("initial", "optimized")
    @classmethod
    def _values(cls, v):
        return _clean(v)


class FittingOut(FittingIn):
    id: int
    bike_id: int


def _out(f: BikeFitting) -> FittingOut:
    return FittingOut(id=f.id, bike_id=f.bike_id, fitted_on=f.fitted_on, fitter=f.fitter, saddle_model=f.saddle_model,
                      pedal_system=f.pedal_system, crank_mm=f.crank_mm, frame_size=f.frame_size, initial=f.initial or {},
                      optimized=f.optimized or {}, notes=f.notes)


def _own_fitting(db: Session, user: User, fitting_id: int) -> BikeFitting:
    f = db.get(BikeFitting, fitting_id)
    if not f or f.user_id != user.id:
        raise HTTPException(404, "Fitting nicht gefunden")
    return f


def _apply(f: BikeFitting, data: FittingIn) -> None:
    f.fitted_on, f.fitter, f.saddle_model, f.pedal_system = data.fitted_on, data.fitter or None, data.saddle_model or None, data.pedal_system or None
    f.crank_mm, f.frame_size, f.notes = data.crank_mm, data.frame_size or None, data.notes or None
    f.initial, f.optimized = data.initial, data.optimized


@router.get("/fitting/fields")
def fitting_fields():
    return [{"key": k, "label": v[0], "unit": v[1], "kind": v[2], "min": v[3], "max": v[4]} for k, v in FIELDS.items()]


@router.get("/bikes/{bike_id}/fittings", response_model=list[FittingOut])
def list_fittings(bike_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own_bike(db, user, bike_id)
    rows = db.scalars(select(BikeFitting).where(BikeFitting.bike_id == bike_id).order_by(BikeFitting.fitted_on.desc(), BikeFitting.id.desc())).all()
    return [_out(f) for f in rows]


@router.post("/bikes/{bike_id}/fittings", response_model=FittingOut, status_code=201)
def add_fitting(bike_id: int, data: FittingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own_bike(db, user, bike_id)
    f = BikeFitting(user_id=user.id, bike_id=bike_id)
    _apply(f, data)
    db.add(f)
    db.commit()
    return _out(f)


@router.put("/fittings/{fitting_id}", response_model=FittingOut)
def update_fitting(fitting_id: int, data: FittingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = _own_fitting(db, user, fitting_id)
    _apply(f, data)
    db.commit()
    return _out(f)


@router.delete("/fittings/{fitting_id}", status_code=204)
def delete_fitting(fitting_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own_fitting(db, user, fitting_id))
    db.commit()
