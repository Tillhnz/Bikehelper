from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..advisor import clothing, forecast, tires
from ..config import settings
from ..database import get_db
from ..models import Activity, Bike, User
from ..security import current_user
from ..services import current_tire_set
from .garage import _own_bike

router = APIRouter(prefix="/api", tags=["advisor"])

USER_AGENT = "BikeHelper (self-hosted)"


class ProfileIn(BaseModel):
    weight_kg: float | None = Field(default=None, ge=30, le=250)
    max_hr: int | None = Field(default=None, ge=120, le=230)


@router.put("/settings/profile")
def save_profile(data: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.weight_kg = data.weight_kg
    user.max_hr = data.max_hr
    db.commit()
    return {"weight_kg": user.weight_kg, "max_hr": user.max_hr}


@router.get("/advisor/defaults")
def defaults(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Vorbelegung für den Ratgeber: Gewicht, Räder mit Reifendaten, Ort der letzten Fahrt."""
    bikes = db.scalars(select(Bike).where(Bike.user_id == user.id, Bike.retired.is_(False)).order_by(Bike.name)).all()
    last = db.execute(
        select(Activity.start_lat, Activity.start_lng)
        .where(Activity.user_id == user.id, Activity.start_lat.is_not(None))
        .order_by(Activity.start_date.desc()).limit(1)
    ).first()
    return {
        "weight_kg": user.weight_kg,
        "weather_enabled": settings.weather_enabled,
        "last_location": {"lat": round(last[0], 2), "lng": round(last[1], 2)} if last else None,
        "bikes": [
            {
                "id": b.id, "name": b.name, "type": b.type, "tire_width_mm": b.tire_width_mm,
                "tire_set": ({"name": ts.name, "width_mm": ts.width_mm, "casing": ts.casing} if (ts := current_tire_set(db, b.id)) else None),
                "rim_inner_mm": b.rim_inner_mm, "bike_weight_kg": b.bike_weight_kg,
                "tubeless": True if b.tubeless is None else b.tubeless, "hookless": bool(b.hookless),
            }
            for b in bikes
        ],
    }


@router.get("/advisor/geocode")
def geocode(q: str = Query(min_length=2, max_length=80), user: User = Depends(current_user)):
    """Ortssuche über Open-Meteo (nur der Suchbegriff wird gesendet)."""
    if not settings.weather_enabled:
        raise HTTPException(409, "Die Wetterabfrage ist auf diesem Server abgeschaltet.")
    import httpx

    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15) as client:
            return forecast.geocode(client, q)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Die Ortssuche ist gerade nicht erreichbar ({e.__class__.__name__}).")


class ManualWeather(BaseModel):
    temp_c: float = Field(ge=-40, le=55)
    wind_kmh: float = Field(default=0, ge=0, le=150)
    rain: Literal["none", "light", "heavy"] = "none"


class PlanIn(BaseModel):
    # Fahrt
    start: datetime  # Ortszeit des Startorts
    duration_min: float = Field(default=120, ge=10, le=1440)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    manual: ManualWeather | None = None
    intensity: Literal["easy", "normal", "hard"] = "normal"
    avg_speed_kmh: float | None = Field(default=None, ge=5, le=60)  # hat Vorrang vor intensity
    sensitivity: Literal["cold", "normal", "warm"] = "normal"
    elevation_gain_m: float | None = Field(default=None, ge=0, le=10000)
    # Reifen
    bike_id: int | None = None
    bike_type: Literal["road", "gravel", "mtb", "other"] | None = None
    rider_kg: float | None = Field(default=None, ge=30, le=250)
    bike_kg: float | None = Field(default=None, ge=3, le=40)
    luggage_kg: float = Field(default=1.5, ge=0, le=40)
    tire_width_mm: float | None = Field(default=None, ge=18, le=80)
    rim_inner_mm: float | None = Field(default=None, ge=12, le=40)
    measured_width_mm: float | None = Field(default=None, ge=18, le=85)
    tubeless: bool | None = None
    hookless: bool | None = None
    casing: Literal["supple", "standard", "stiff"] | None = None  # leer: Karkasse des montierten Reifensatzes, sonst normal
    surface: Literal["asphalt", "rough", "hardpack", "gravel", "chunky"] = "asphalt"
    wetness: Literal["auto", "dry", "damp", "wet"] = "auto"


def _manual_weather(m: ManualWeather, duration_min: float) -> forecast.RideWeather:
    rain = {"none": (0.0, 0.0, 0), "light": (0.4, duration_min * 0.5, 50), "heavy": (2.0 * duration_min / 60, duration_min, 90)}[m.rain]
    return forecast.RideWeather(
        temp_start=m.temp_c, temp_avg=m.temp_c, temp_min=m.temp_c, temp_max=m.temp_c, wind_kmh=m.wind_kmh,
        gust_kmh=None, precip_mm=rain[0], precip_prob=rain[2], wet_minutes=rain[1], uv=None, weather_code=None,
        dark_minutes=0, hours=[],
    )


def _wetness(w: forecast.RideWeather, duration_min: float) -> str:
    wet_min = w.wet_minutes or 0
    if wet_min >= 0.2 * duration_min or (w.precip_mm or 0) >= 1.0:
        return "wet"
    if wet_min > 0 or (w.precip_mm or 0) >= 0.2 or (w.precip_prob or 0) >= 50:
        return "damp"
    return "dry"


@router.post("/advisor/plan")
def plan(data: PlanIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Reifendruck und Kleidung für die nächste Tour."""
    start = data.start.replace(tzinfo=None)
    bike = _own_bike(db, user, data.bike_id) if data.bike_id is not None else None

    # ---- Wetter ----
    if data.manual is not None:
        rw = _manual_weather(data.manual, data.duration_min)
        source = "manual"
    else:
        if data.lat is None or data.lng is None:
            raise HTTPException(422, "Bitte einen Ort wählen oder das Wetter von Hand eingeben.")
        if not settings.weather_enabled:
            raise HTTPException(409, "Die Wetterabfrage ist abgeschaltet. Gib das Wetter bitte von Hand ein.")
        problem = forecast.check_start(start, datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2))
        if problem:
            raise HTTPException(422, problem)
        import httpx

        end = start + timedelta(minutes=data.duration_min)
        try:
            with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20) as client:
                fc = forecast.fetch_forecast(client, data.lat, data.lng, start, end)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Die Wettervorhersage ist gerade nicht erreichbar ({e.__class__.__name__}).")
        rw = forecast.ride_weather(fc, start, data.duration_min)
        if rw is None or rw.temp_avg is None:
            raise HTTPException(422, "Für diesen Zeitraum liegt keine Vorhersage vor.")
        source = "forecast"

    bike_type = data.bike_type or (bike.type if bike else "road")

    # ---- Kleidung ----
    c = clothing.advise(
        temp_avg=rw.temp_avg, temp_start=rw.temp_start, temp_min=rw.temp_min, temp_max=rw.temp_max,
        wind_kmh=rw.wind_kmh or 0.0, gust_kmh=rw.gust_kmh, precip_mm=rw.precip_mm or 0.0,
        precip_prob=rw.precip_prob, wet_minutes=rw.wet_minutes or 0.0, uv=rw.uv,
        duration_min=data.duration_min, intensity=data.intensity, speed_kmh=data.avg_speed_kmh, sensitivity=data.sensitivity,
        bike_type=bike_type, elevation_gain_m=data.elevation_gain_m, dark_minutes=rw.dark_minutes,
    )

    # ---- Reifen ----
    rider = data.rider_kg or user.weight_kg
    width = data.tire_width_mm or (bike.tire_width_mm if bike else None)
    bike_kg = data.bike_kg or (bike.bike_weight_kg if bike else None) or {"road": 8.0, "gravel": 10.0, "mtb": 13.0}.get(bike_type, 11.0)
    rim = data.rim_inner_mm or (bike.rim_inner_mm if bike else None)
    tubeless = data.tubeless if data.tubeless is not None else (True if not bike or bike.tubeless is None else bike.tubeless)
    hookless = data.hookless if data.hookless is not None else bool(bike and bike.hookless)
    wetness = _wetness(rw, data.duration_min) if data.wetness == "auto" else data.wetness
    garage_set = current_tire_set(db, bike.id) if bike else None
    casing = data.casing or (garage_set.casing if garage_set else None) or "standard"
    missing = [name for name, v in (("Körpergewicht", rider), ("Reifenbreite", width)) if not v]
    tire_out = None
    if not missing:
        r = tires.recommend(
            rider_kg=rider, bike_kg=bike_kg, luggage_kg=data.luggage_kg, tire_width_mm=width, bike_type=bike_type,
            rim_inner_mm=rim, measured_width_mm=data.measured_width_mm, surface=data.surface, wetness=wetness,
            tubeless=tubeless, casing=casing, hookless=hookless,
        )
        tire_out = asdict(r)
        tire_out["wetness"] = wetness
        tire_out["bike_kg_used"] = bike_kg

    return {
        "weather": {"source": source, **asdict(rw)},
        "clothing": asdict(c),
        "tires": tire_out,
        "tires_missing": missing,
    }
