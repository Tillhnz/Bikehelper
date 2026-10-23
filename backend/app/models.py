from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func,
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

    user: Mapped[User] = relationship(back_populates="bikes")
    components: Mapped[list["Component"]] = relationship(back_populates="bike")


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

    component: Mapped[Component] = relationship(back_populates="rules")


class MaintenanceLog(Base):
    __tablename__ = "maintenance_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"), index=True)
    performed_at: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

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
    # Wetter (wird später angereichert)
    temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    precip_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
