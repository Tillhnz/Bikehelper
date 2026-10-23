from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Strava: jeder Nutzer hinterlegt seine eigene Strava-API-App
    strava_client_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strava_client_secret: Mapped[str | None] = mapped_column(String(128), nullable=True)
    strava_access_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    strava_refresh_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    strava_expires_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    strava_athlete_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)  # Körpergewicht für den Ratgeber
    # Kartenhintergrund: eigener CARTO-Schlüssel (hat Vorrang vor dem Schlüssel des Servers)
    carto_api_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    bikes: Mapped[list["Bike"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Bike(Base):
    __tablename__ = "bikes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(20), default="road")  # road, gravel, mtb, other
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_km: Mapped[float] = mapped_column(Float, default=0)  # Kilometer vor Nutzung der App
    strava_gear_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    retired: Mapped[bool] = mapped_column(Boolean, default=False)
    # Kette und Ratgeber
    chain_lube: Mapped[str | None] = mapped_column(String(12), nullable=True)  # oil | wax, leer = oil
    tire_width_mm: Mapped[float | None] = mapped_column(Float, nullable=True)   # aufgezogene Reifenbreite laut Aufdruck
    rim_inner_mm: Mapped[float | None] = mapped_column(Float, nullable=True)    # Maulweite der Felge
    bike_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    tubeless: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    hookless: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    user: Mapped[User] = relationship(back_populates="bikes")
    components: Mapped[list["Component"]] = relationship(back_populates="bike")
    tire_sets: Mapped[list["TireSet"]] = relationship(back_populates="bike", cascade="all, delete-orphan")


class TireSet(Base):
    """Ein Satz Reifen (Mäntel) für ein Rad. Die Kilometer ergeben sich aus den Zeiträumen, in denen er montiert war."""
    __tablename__ = "tire_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    bike_id: Mapped[int] = mapped_column(ForeignKey("bikes.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    width_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    tubeless: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    start_km: Mapped[float] = mapped_column(Float, default=0)  # Kilometer, die der Satz schon vor der App hatte
    max_km: Mapped[float | None] = mapped_column(Float, nullable=True)  # erwartete Lebensdauer, optional
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    retired: Mapped[bool] = mapped_column(Boolean, default=False)

    bike: Mapped[Bike] = relationship(back_populates="tire_sets")
    mounts: Mapped[list["TireMount"]] = relationship(back_populates="tire_set", cascade="all, delete-orphan")


class TireMount(Base):
    """Zeitraum, in dem ein Reifensatz auf dem Rad war. to_date leer = noch montiert (beide Tage zählen mit)."""
    __tablename__ = "tire_mounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tire_set_id: Mapped[int] = mapped_column(ForeignKey("tire_sets.id", ondelete="CASCADE"), index=True)
    from_date: Mapped[date] = mapped_column(Date)
    to_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    tire_set: Mapped[TireSet] = relationship(back_populates="mounts")


class Component(Base):
    __tablename__ = "components"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    bike_id: Mapped[int | None] = mapped_column(ForeignKey("bikes.id", ondelete="SET NULL"), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(30))  # chain, cassette, chainring, tire_front, ...
    name: Mapped[str] = mapped_column(String(160))
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    installed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    retired_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_km: Mapped[float] = mapped_column(Float, default=0)  # Kilometer, die das Teil schon hatte
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    bike: Mapped[Bike | None] = relationship(back_populates="components")
    rules: Mapped[list["MaintenanceRule"]] = relationship(back_populates="component", cascade="all, delete-orphan")
    logs: Mapped[list["MaintenanceLog"]] = relationship(back_populates="component", cascade="all, delete-orphan")


class MaintenanceRule(Base):
    __tablename__ = "maintenance_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(160))  # z. B. "Kette wechseln"
    interval_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wet_factor: Mapped[float | None] = mapped_column(Float, nullable=True, default=1.0)  # 1 Nass-km zählt wie x km
    hint: Mapped[str | None] = mapped_column(Text, nullable=True)

    component: Mapped[Component] = relationship(back_populates="rules")


class MaintenanceLog(Base):
    __tablename__ = "maintenance_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"), index=True)
    # Leer: gilt für alle Regeln der Komponente. Gesetzt: nur für diese eine Regel (z. B. "Kette schmieren").
    rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("maintenance_rules.id", ondelete="CASCADE"), nullable=True, index=True
    )
    performed_at: Mapped[date] = mapped_column(Date)
    # Uhrzeit (Ortszeit): Fahrten davor am selben Tag zählen nicht mehr mit. Leer bei älteren Einträgen: ganzer Tag.
    performed_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    variant: Mapped[str | None] = mapped_column(String(12), nullable=True)  # Wachsart: hot_wax | drip_wax

    component: Mapped[Component] = relationship(back_populates="logs")


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    bike_id: Mapped[int | None] = mapped_column(ForeignKey("bikes.id", ondelete="SET NULL"), nullable=True, index=True)
    strava_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)
    name: Mapped[str] = mapped_column(String(255))
    sport_type: Mapped[str] = mapped_column(String(40), default="Ride")
    start_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    distance_km: Mapped[float] = mapped_column(Float, default=0)
    moving_time_s: Mapped[int] = mapped_column(Integer, default=0)
    elevation_m: Mapped[float] = mapped_column(Float, default=0)
    polyline: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    gear_name: Mapped[str | None] = mapped_column(String(160), nullable=True)  # Radname laut Strava-Export
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "upload" oder "strava_export"
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: Kennzahlen und Verlauf (Höhe, Tempo, Puls …)
    tiles: Mapped[str | None] = mapped_column(Text, nullable=True)  # erkundete z14-Kacheln, '' = keine, NULL = offen
    # Wetter (wird später angereichert)
    temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    precip_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    wet_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)  # Fahrzeit bei Regen oder nasser Straße
    weather_code: Mapped[int | None] = mapped_column(Integer, nullable=True)  # WMO-Wettercode (höchster während der Fahrt)
    weather_status: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ok | prelim | none; leer = offen
