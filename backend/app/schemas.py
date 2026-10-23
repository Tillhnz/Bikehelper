from datetime import date

from pydantic import BaseModel, EmailStr, Field


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


class StravaSettingsIn(BaseModel):
    client_id: str = Field(min_length=1, max_length=64)
    client_secret: str = Field(min_length=1, max_length=128)


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


class BikeOut(BikeIn):
    id: int
    total_km: float
    component_count: int
    due_count: int


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


class RuleOut(RuleIn):
    id: int
    km_since: float
    months_since: float
    progress: float  # 0..1+ (Anteil des Intervalls, der verbraucht ist)
    status: str


class LogIn(BaseModel):
    performed_at: date
    note: str | None = None


class LogOut(LogIn):
    id: int
