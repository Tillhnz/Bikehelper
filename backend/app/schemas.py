from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


def clean_shop_url(v: str | None) -> str | None:
    """Einkaufslinks: leer wird zu None, sonst nur http(s) (nie javascript: oder data:)."""
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    if not v.lower().startswith(("http://", "https://")) or " " in v:
        raise ValueError("Der Link muss mit http:// oder https:// beginnen.")
    return v


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    invite: str | None = Field(default=None, max_length=32)  # Einladungscode, wenn die Registrierung geschlossen ist
    group_invite: str | None = Field(default=None, max_length=64)  # Schlüssel aus einem Gruppen-Einladungslink; erlaubt ebenfalls die Registrierung


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class PasswordConfirmIn(BaseModel):
    password: str = Field(max_length=128)


class InviteOut(BaseModel):
    id: int
    code: str
    used_by_email: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    strava_configured: bool
    strava_connected: bool
    weight_kg: float | None = None
    is_admin: bool = False
    role: str = "user"
    mechanic_enabled: bool = False
    whatsnew: list[dict] | None = None  # noch nicht gezeigte Versionshinweise, neueste zuerst


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
    purchased_at: date | None = None  # Kaufdatum des Rades
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
    shared_from: str | None = None  # E-Mail des Besitzers, wenn das Rad einem Partner gehört (Mechanics-Modus)


class ComponentIn(BaseModel):
    bike_id: int | None = None
    category: str
    name: str = Field(min_length=1, max_length=160)
    brand: str | None = None
    installed_at: date | None = None
    retired_at: date | None = None
    start_km: float = 0
    notes: str | None = None
    wear_limit_pct: float | None = None  # Kette: Grenzwert der Kettenlehre
    shop_url: str | None = Field(default=None, max_length=500)  # eigener Einkaufslink

    @field_validator("shop_url")
    @classmethod
    def _shop_url(cls, v):
        return clean_shop_url(v)


class ComponentOut(ComponentIn):
    installed_effective: date | None = None  # eigenes Einbaudatum, sonst das Kaufdatum des Rades
    installed_inherited: bool = False
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
    guides: list[dict] | None = None  # Anleitungen und Videos zur Aufgabe
    measure: dict | None = None  # Hochrechnung aus der letzten Kettenmessung (nur Verschleißregel der Kette)
    is_inspection: bool = False  # Prüfregel: beim Eintragen wird ein Ergebnis gewählt
    assessment: dict | None = None  # Prüfergebnis, das Intervall dieser Regel beeinflusst (Prüf- und Wechselregel)
    km_since: float
    wet_km: float
    effective_km: float  # gefahrene km inklusive Nässe-Zuschlag
    months_since: float
    progress: float  # 0..1+ (Anteil des Intervalls, der verbraucht ist)
    status: str  # ok | soon | due | unknown
    last_done: date | None = None


class RuleDoneIn(BaseModel):
    performed_at: date
    performed_time: time | None = None  # Ortszeit
    note: str | None = None
    variant: Literal["hot_wax", "drip_wax"] | None = None  # nur für die Wachsregel
    result: Literal["good", "watch", "replace"] | None = None  # nur für Prüfregeln


class ReplaceIn(BaseModel):
    performed_at: date
    name: str | None = Field(default=None, min_length=1, max_length=160)
    brand: str | None = None


class StandardComponentsIn(BaseModel):
    categories: list[str] | None = None  # leer: Standardsatz passend zum Radtyp


class LogIn(BaseModel):
    performed_at: date
    performed_time: time | None = None  # Ortszeit
    note: str | None = None


class LogOut(LogIn):
    id: int
    rule_id: int | None = None
    variant: str | None = None
    result: str | None = None
    performed_by: str | None = None  # E-Mail des Mechanikers, falls nicht der Besitzer eingetragen hat


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


class AssignMatch(BaseModel):
    unassigned: bool = False
    q: str | None = Field(default=None, max_length=200)
    day: date | None = None
    source: str | None = Field(default=None, max_length=20)


class AssignIn(BaseModel):
    bike_id: int | None
    gear_name: str | None = None
    activity_ids: list[int] | None = Field(default=None, max_length=5000)
    match: AssignMatch | None = None
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
    model_key: str | None = Field(default=None, max_length=160)
    category: str | None = Field(default=None, max_length=12)
    weight_g: float | None = Field(default=None, ge=50, le=3000)
    watts: float | None = Field(default=None, ge=0.5, le=100)
    watts_note: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=255, pattern=r"^https?://")
    casing: Literal["supple", "standard", "stiff"] | None = None  # Karkasse, wird vom Ratgeber genutzt
    shop_url: str | None = Field(default=None, max_length=500)  # eigener Einkaufslink
    check_km: float | None = Field(default=None, gt=0, le=20000)  # Sichtprüfung alle ... km; leer = Standard (1.000 km)

    @field_validator("shop_url")
    @classmethod
    def _shop_url(cls, v):
        return clean_shop_url(v)


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
    km_left: float | None = None  # bis zur erwarteten Lebensdauer
    life_status: str = "ok"
    check_interval_km: float = 1000  # wirksames Prüfintervall
    checked_on: date | None = None
    km_since_check: float = 0
    check_progress: float = 0
    check_status: str = "ok"
    status: str = "ok"  # das Schlechtere von Lebensdauer und Prüfung
    mounts: list[MountOut] = []


class MountDateIn(BaseModel):
    day: date


class MountRangeIn(BaseModel):
    from_date: date
    to_date: date | None = None


class MeasurementIn(BaseModel):
    measured_at: date
    wear_pct: float = Field(ge=0, le=3)
    note: str | None = None
    limit_pct: Literal[0.5, 0.75] | None = None  # Grenzwert der Kettenlehre; ändert die Einstellung der Kette


class MeasurementOut(BaseModel):
    id: int
    measured_at: date
    wear_pct: float
    note: str | None = None
    km: float  # gefahrene Kilometer der Kette bis zur Messung


class InventoryIn(BaseModel):
    category: str = Field(max_length=40)
    name: str = Field(min_length=1, max_length=160)
    brand: str | None = None
    spec: str | None = None
    quantity: int = Field(default=1, ge=0, le=9999)
    min_quantity: int | None = Field(default=None, ge=0, le=9999)
    price_eur: float | None = Field(default=None, ge=0, le=100000)
    purchased_at: date | None = None
    location: str | None = None
    notes: str | None = None
    bike_id: int | None = None


class InventoryOut(InventoryIn):
    id: int
    low: bool = False


class InstallIn(BaseModel):
    bike_id: int
    installed_at: date
    with_rules: bool = True
