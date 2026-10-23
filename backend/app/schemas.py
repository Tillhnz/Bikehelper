from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    strava_configured: bool
    strava_connected: bool
    weight_kg: float | None = None


class StravaSettingsIn(BaseModel):
    client_id: str = Field(min_length=1, max_length=64)
    client_secret: str = Field(min_length=1, max_length=128)


class MountedTireSet(BaseModel):
    id: int
    name: str
    width_mm: float | None = None
    km: float


class BikeIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = "road"
    brand: str | None = None
    model: str | None = None
    year: int | None = None
    start_km: float = 0
    strava_gear_id: str | None = None
    notes: str | None = None
    retired: bool = False
    chain_lube: Literal["oil", "wax"] | None = "oil"
    tire_width_mm: float | None = Field(default=None, ge=18, le=80)
    rim_inner_mm: float | None = Field(default=None, ge=12, le=40)
    bike_weight_kg: float | None = Field(default=None, ge=3, le=40)
    tubeless: bool | None = True
    hookless: bool | None = False

    @field_validator("chain_lube", mode="before")
    @classmethod
    def _legacy_lube(cls, v):
        return "wax" if v in ("hot_wax", "drip_wax") else v


class BikeCreate(BikeIn):
    with_defaults: bool = True  # Standardkomponenten mit Wartungsintervallen mit anlegen


class BikeOut(BikeIn):
    id: int
    total_km: float
    component_count: int
    due_count: int
    unknown_count: int = 0  # Komponenten ohne Einbaudatum, bei denen noch nichts gezählt werden kann
    tire_set: MountedTireSet | None = None  # aktuell montierter Reifensatz


class ComponentIn(BaseModel):
    bike_id: int | None = None
    category: str
    name: str = Field(min_length=1, max_length=160)
    brand: str | None = None
    installed_at: date | None = None
    retired_at: date | None = None
    start_km: float = 0
    notes: str | None = None


class ComponentOut(ComponentIn):
    id: int
    km: float
    status: str  # ok, soon, due


class RuleIn(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    interval_km: float | None = Field(default=None, gt=0)
    interval_months: int | None = Field(default=None, gt=0)
    wet_factor: float = Field(default=1.0, ge=1.0, le=5.0)  # 1 km bei Nässe zählt wie x km
    hint: str | None = None


class WaxVariantOut(BaseModel):
    key: str
    name: str
    interval_km: float


class RuleOut(RuleIn):
    id: int
    variant: str | None = None  # Wachsart der letzten Wartung (nur Wachsregel)
    variants: list[WaxVariantOut] | None = None  # wählbare Wachsarten (nur Wachsregel)
    km_since: float
    wet_km: float
    effective_km: float  # gefahrene km inklusive Nässe-Zuschlag
    months_since: float
    progress: float  # 0..1+ (Anteil des Intervalls, der verbraucht ist)
    status: str  # ok | soon | due | unknown
    last_done: date | None = None


class RuleDoneIn(BaseModel):
    performed_at: date
    note: str | None = None
    variant: Literal["hot_wax", "drip_wax"] | None = None  # nur für die Wachsregel


class ReplaceIn(BaseModel):
    performed_at: date
    name: str | None = Field(default=None, min_length=1, max_length=160)
    brand: str | None = None


class StandardComponentsIn(BaseModel):
    categories: list[str] | None = None  # leer: Standardsatz passend zum Radtyp


class LogIn(BaseModel):
    performed_at: date
    note: str | None = None


class LogOut(LogIn):
    id: int
    rule_id: int | None = None
    variant: str | None = None


class ActivityOut(BaseModel):
    id: int
    name: str
    sport_type: str
    start_date: datetime  # UTC, ohne Zeitzonenangabe
    distance_km: float
    moving_time_s: int
    elevation_m: float
    bike_id: int | None
    gear_name: str | None
    source: str | None
    has_track: bool
    temp_c: float | None = None
    precip_mm: float | None = None
    wind_kmh: float | None = None
    wet_minutes: float | None = None
    weather_code: int | None = None
    weather_status: str | None = None


class ActivityDetail(ActivityOut):
    bike_name: str | None = None
    polyline: str | None = None
    avg_speed: float | None = None
    details: dict | None = None  # fehlt bei Fahrten, die vor dieser Funktion importiert wurden
    start_lat: float | None = None
    start_lng: float | None = None


class ActivityPage(BaseModel):
    total: int
    items: list[ActivityOut]


class ActivityUpdate(BaseModel):
    bike_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)


class AssignIn(BaseModel):
    bike_id: int | None
    gear_name: str | None = None
    activity_ids: list[int] | None = None
    only_unassigned: bool = True


class GearOut(BaseModel):
    gear_name: str | None
    count: int
    unassigned: int
    km: float


class TireSetIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    brand: str | None = None
    width_mm: float | None = Field(default=None, ge=18, le=85)
    tubeless: bool | None = None
    start_km: float = Field(default=0, ge=0)
    max_km: float | None = Field(default=None, gt=0)
    notes: str | None = None
    retired: bool = False


class TireSetCreate(TireSetIn):
    mount_from: date | None = None  # gleich ab diesem Tag montieren


class MountOut(BaseModel):
    id: int
    from_date: date
    to_date: date | None
    km: float


class TireSetOut(TireSetIn):
    id: int
    bike_id: int
    km: float  # gesamt: Kilometer vor der App plus alle Zeiträume auf dem Rad
    mounted: bool
    mounted_since: date | None = None
    progress: float | None = None  # km / max_km
    mounts: list[MountOut] = []


class MountDateIn(BaseModel):
    day: date


class MountRangeIn(BaseModel):
    from_date: date
    to_date: date | None = None
