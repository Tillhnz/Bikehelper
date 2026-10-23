from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Activity, Bike, Component, MaintenanceRule

SOON_THRESHOLD = 0.8


def _since(d: date | None) -> datetime | None:
    return datetime.combine(d, time.min) if d else None


def km_between(db: Session, bike_id: int | None, start: date | None, end: date | None = None) -> float:
    """Summe der Kilometer eines Rades im Zeitraum (start/end optional)."""
    if bike_id is None:
        return 0.0
    q = select(func.coalesce(func.sum(Activity.distance_km), 0.0)).where(Activity.bike_id == bike_id)
    if start:
        q = q.where(Activity.start_date >= _since(start))
    if end:
        q = q.where(Activity.start_date < datetime.combine(end, time.max))
    return float(db.scalar(q) or 0.0)


def bike_total_km(db: Session, bike: Bike) -> float:
    return bike.start_km + km_between(db, bike.id, None)


def component_km(db: Session, comp: Component) -> float:
    return comp.start_km + km_between(db, comp.bike_id, comp.installed_at, comp.retired_at)


def months_between(start: date, end: date) -> float:
    return max((end - start).days, 0) / 30.4375


def rule_state(db: Session, comp: Component, rule: MaintenanceRule, today: date | None = None) -> dict:
    """Verbrauch eines Wartungsintervalls seit der letzten Wartung (oder dem Einbau)."""
    today = today or date.today()
    last = max((l.performed_at for l in comp.logs), default=None)
    base = last or comp.installed_at
    km_since = km_between(db, comp.bike_id, base, comp.retired_at) if base or comp.bike_id else 0.0
    if not last and base is None:
        km_since = comp.start_km  # kein Datum bekannt: alles seit Neu
    months_since = months_between(base, today) if base else 0.0

    ratios = []
    if rule.interval_km:
        ratios.append(km_since / rule.interval_km)
    if rule.interval_months:
        ratios.append(months_since / rule.interval_months)
    progress = max(ratios) if ratios else 0.0

    if comp.retired_at:
        state = "ok"
    elif progress >= 1:
        state = "due"
    elif progress >= SOON_THRESHOLD:
        state = "soon"
    else:
        state = "ok"
    return {
        "km_since": round(km_since, 1),
        "months_since": round(months_since, 1),
        "progress": round(progress, 3),
        "status": state,
    }


def worst_status(states: list[str]) -> str:
    if "due" in states:
        return "due"
    if "soon" in states:
        return "soon"
    return "ok"


def component_status(db: Session, comp: Component) -> str:
    return worst_status([rule_state(db, comp, r)["status"] for r in comp.rules])
