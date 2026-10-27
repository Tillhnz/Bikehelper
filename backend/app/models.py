from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint, func,
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

    # Erinnerungen, wenn eine Wartung bald oder jetzt fällig ist
    remind_email: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ntfy_topic: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Wahoo Cloud: eigene Entwickler-App des Nutzers (developers.wahooligan.com), Verbindung per OAuth
    wahoo_client_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    wahoo_client_secret: Mapped[str | None] = mapped_column(String(160), nullable=True)
    wahoo_access_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wahoo_refresh_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wahoo_expires_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    wahoo_bike_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Standardrad für importierte Fahrten
    wahoo_last_sync: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    mechanic_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # Mechanics-Modus aktiviert (eigener Tab)
    # intervals.icu: persönlicher API-Schlüssel des Nutzers
    icu_api_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    icu_bike_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    icu_last_sync: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    icu_synced_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    icu_status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    whatsnew_seen: Mapped[str | None] = mapped_column(String(32), nullable=True)  # zuletzt gezeigter Neuigkeiten-Hinweis
    wahoo_status: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Ergebnis des letzten Laufs

    # Wird beim "Überall abmelden" und bei Passwortänderung erhöht; ältere Login-Tokens werden ungültig
    token_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "admin" | "user"
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # False = Konto gesperrt (leer = aktiv)

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
    purchased_at: Mapped[date | None] = mapped_column(Date, nullable=True)  # Kaufdatum; gilt als Einbaudatum für Teile ohne eigenes Datum
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
    # Aus dem Reifenkatalog (alles optional und frei änderbar)
    model_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    category: Mapped[str | None] = mapped_column(String(12), nullable=True)
    weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)  # je Reifen
    watts: Mapped[float | None] = mapped_column(Float, nullable=True)  # Rollwiderstand je Reifen in Watt (Prüfstand)
    watts_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    casing: Mapped[str | None] = mapped_column(String(10), nullable=True)
    shop_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # eigener Einkaufslink für Ersatz
    check_km: Mapped[float | None] = mapped_column(Float, nullable=True)  # Sichtprüfung alle ... km (leer: Standard)
    checked_km: Mapped[float | None] = mapped_column(Float, nullable=True)  # Kilometerstand des Satzes bei der letzten Prüfung
    checked_on: Mapped[date | None] = mapped_column(Date, nullable=True)

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
    wear_limit_pct: Mapped[float | None] = mapped_column(Float, nullable=True)  # Kette: 0,5 (11/12-fach) oder 0,75 %
    shop_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # eigener Einkaufslink für Ersatz

    bike: Mapped[Bike | None] = relationship(back_populates="components")
    measurements: Mapped[list["ChainMeasurement"]] = relationship(back_populates="component", cascade="all, delete-orphan")
    rules: Mapped[list["MaintenanceRule"]] = relationship(back_populates="component", cascade="all, delete-orphan")
    logs: Mapped[list["MaintenanceLog"]] = relationship(back_populates="component", cascade="all, delete-orphan")


class ChainMeasurement(Base):
    """Messwert der Kettenlehre: Längung der Kette in Prozent."""
    __tablename__ = "chain_measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"), index=True)
    measured_at: Mapped[date] = mapped_column(Date)
    wear_pct: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    component: Mapped[Component] = relationship(back_populates="measurements")


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
    result: Mapped[str | None] = mapped_column(String(10), nullable=True)  # Prüfergebnis: good | watch | replace
    performed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)  # E-Mail des Mechanikers, wenn nicht der Besitzer eintrug

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
    # Merkmale für Radvorschläge (aus den Fahrdaten; NULL = noch nicht ausgewertet, 0 bzw. "" = nicht vorhanden)
    avg_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_cadence: Mapped[float | None] = mapped_column(Float, nullable=True)
    terrain: Mapped[str | None] = mapped_column(String(10), nullable=True)  # road | gravel | mtb | ebike | "" (unbekannt)


class RuleNotice(Base):
    """Merkt sich, bei welchem Status zuletzt erinnert wurde, damit jede Fälligkeit nur einmal gemeldet wird."""
    __tablename__ = "rule_notices"

    rule_id: Mapped[int] = mapped_column(ForeignKey("maintenance_rules.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(10))
    notified_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Goal(Base):
    """Jahresziel eines Nutzers: Kilometer, Höhenmeter, Fahrten oder Fahrzeit (Stunden)."""
    __tablename__ = "goals"
    __table_args__ = (UniqueConstraint("user_id", "year", "metric"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    metric: Mapped[str] = mapped_column(String(10))  # km | elev_m | rides | time_h
    target: Mapped[float] = mapped_column(Float)


class InventoryItem(Base):
    """Teil im Lager (Ersatzteile, Verschleißteile, Verbrauchsmaterial)."""
    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    bike_id: Mapped[int | None] = mapped_column(ForeignKey("bikes.id", ondelete="SET NULL"), nullable=True)  # passt zu
    category: Mapped[str] = mapped_column(String(40))  # Kategorie des Katalogs oder "other"
    name: Mapped[str] = mapped_column(String(160))
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    spec: Mapped[str | None] = mapped_column(String(160), nullable=True)  # Größe, Typ, Breite …
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    min_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)  # darunter erscheint eine Warnung
    price_eur: Mapped[float | None] = mapped_column(Float, nullable=True)  # Preis je Stück
    purchased_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Place(Base):
    """Ort (Stadt, Gemeinde) mit Fläche aus OpenStreetMap, einmal geholt und für alle Nutzer wiederverwendet."""
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(primary_key=True)
    osm_key: Mapped[str] = mapped_column(String(24), unique=True, index=True)  # z. B. R62422
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(10))  # city | town | village | county | area
    state: Mapped[str | None] = mapped_column(String(200), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    geometry: Mapped[str] = mapped_column(Text)  # GeoJSON
    total_tiles: Mapped[int] = mapped_column(Integer, default=0)


class PlaceVisit(Base):
    """Wie viel ein Nutzer von einem Ort erkundet hat (wird vom Hintergrundlauf berechnet)."""
    __tablename__ = "place_visits"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), primary_key=True)
    tiles: Mapped[int] = mapped_column(Integer, default=0)
    rides: Mapped[int] = mapped_column(Integer, default=0)  # Fahrten, die in diesem Ort starten


class GeoMiss(Base):
    """Kacheln, für die kein Ort gefunden wurde (Meer, Ausland ohne Treffer), damit nicht ständig neu gefragt wird."""
    __tablename__ = "geo_misses"

    x: Mapped[int] = mapped_column(Integer, primary_key=True)
    y: Mapped[int] = mapped_column(Integer, primary_key=True)


class GeoState(Base):
    __tablename__ = "geo_state"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    unresolved: Mapped[int] = mapped_column(Integer, default=0)
    explored: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)


class Invite(Base):
    """Einladungscode, mit dem sich jemand registrieren kann, auch wenn die offene Registrierung aus ist."""
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    used_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WahooSeen(Base):
    """Wahoo-Workouts, die schon verarbeitet wurden (importiert, Duplikat oder ohne verwertbare Datei)."""
    __tablename__ = "wahoo_seen"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    workout_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    status: Mapped[str] = mapped_column(String(12))  # imported | duplicate | skipped


class IntervalsSeen(Base):
    """intervals.icu-Aktivitäten, die schon verarbeitet wurden (importiert, Duplikat oder übersprungen)."""
    __tablename__ = "intervals_seen"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    activity_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    status: Mapped[str] = mapped_column(String(12))  # imported | duplicate | skipped


class UserTire(Base):
    """Eigener Eintrag im Reifenkatalog eines Nutzers (CSV-Import oder von Hand)."""
    __tablename__ = "user_tires"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(160))
    brand: Mapped[str] = mapped_column(String(120))
    model: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(12), default="road")
    width_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    tubeless: Mapped[str | None] = mapped_column(String(10), nullable=True)
    weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    watts: Mapped[float | None] = mapped_column(Float, nullable=True)
    watts_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    casing: Mapped[str | None] = mapped_column(String(10), nullable=True)


class AppSetting(Base):
    """Servereinstellungen, die der Administrator in der Oberfläche ändert (überschreiben die Umgebungsvariablen)."""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class AuditEntry(Base):
    """Protokoll sicherheitsrelevanter Verwaltungsvorgänge (ohne persönliche Inhalte und ohne Geheimnisse)."""
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    actor: Mapped[str] = mapped_column(String(255))  # E-Mail des Handelnden oder "System"
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str | None] = mapped_column(String(300), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # volle Fehlermeldung bei Serverfehlern (ohne Personendaten)


class PasswordReset(Base):
    """Einmal gültiger Link zum Zurücksetzen des Passworts; gespeichert wird nur der Hash des Codes."""
    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MechanicGrant(Base):
    """Freigabe: `mechanic` darf die Räder von `owner` einsehen und bearbeiten (Garage, Teile, Wartung, Reifen).
    Erst nach Bestätigung durch den Besitzer aktiv (status = "active"), jederzeit widerrufbar."""
    __tablename__ = "mechanic_grants"
    __table_args__ = (UniqueConstraint("owner_id", "mechanic_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    mechanic_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | active
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Group(Base):
    """Gruppe von Nutzern, die ihre Kennzahlen (nicht ihre Strecken) in einer Rangliste vergleichen."""
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(10), default="member")  # admin | member
    display_name: Mapped[str] = mapped_column(String(60))  # Anzeigename nur in dieser Gruppe, nie die E-Mail-Adresse
    share: Mapped[bool] = mapped_column(Boolean, default=True)  # Kennzahlen in dieser Gruppe zeigen
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class GroupInvite(Base):
    """Einladung per Link (einmal gültig, 14 Tage)."""
    __tablename__ = "group_invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    invited_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
