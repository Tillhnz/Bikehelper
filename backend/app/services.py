from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .catalog import CATALOG, LUBE_LABELS, categories_for, chain_rules
from .models import Activity, Bike, Component, MaintenanceRule

SOON_THRESHOLD = 0.8


def _since(d: date | None) -> datetime | None:
    return datetime.combine(d, time.min) if d else None


def _until(d: date) -> datetime:
    return datetime.combine(d, time.max)


def km_between(db: Session, bike_id: int | None, start: date | None, end: date | None = None) -> float:
    """Summe der Kilometer eines Rades im Zeitraum (start/end optional)."""
    if bike_id is None:
        return 0.0
    q = select(func.coalesce(func.sum(Activity.distance_km), 0.0)).where(Activity.bike_id == bike_id)
    if start:
        q = q.where(Activity.start_date >= _since(start))
    if end:
        q = q.where(Activity.start_date < _until(end))
    return float(db.scalar(q) or 0.0)


def wet_fraction(moving_time_s: int | None, wet_minutes: float | None) -> float:
    """Anteil der Fahrzeit bei Regen oder nasser Straße (0 bis 1); ohne Wetterdaten 0."""
    if wet_minutes is None or not moving_time_s:
        return 0.0
    return max(0.0, min(1.0, wet_minutes * 60.0 / moving_time_s))


def wear_between(
    db: Session, bike_id: int | None, start: date | None, end: date | None, wet_factor: float | None
) -> tuple[float, float, float]:
    """Gibt (km, nasse km, wirksame km) im Zeitraum zurück.

    Wirksame km = km + nasse km * (wet_factor - 1): Ein Kilometer bei Nässe zählt wie wet_factor Kilometer.
    """
    if bike_id is None:
        return 0.0, 0.0, 0.0
    q = select(Activity.distance_km, Activity.moving_time_s, Activity.wet_minutes).where(Activity.bike_id == bike_id)
    if start:
        q = q.where(Activity.start_date >= _since(start))
    if end:
        q = q.where(Activity.start_date < _until(end))
    km = wet = 0.0
    for dist, moving, wet_min in db.execute(q):
        dist = dist or 0.0
        km += dist
        wet += dist * wet_fraction(moving, wet_min)
    factor = wet_factor if wet_factor and wet_factor > 1 else 1.0
    return km, wet, km + wet * (factor - 1)


def bike_total_km(db: Session, bike: Bike) -> float:
    return bike.start_km + km_between(db, bike.id, None)


def component_km(db: Session, comp: Component) -> float:
    return comp.start_km + km_between(db, comp.bike_id, comp.installed_at, comp.retired_at)


def months_between(start: date, end: date) -> float:
    return max((end - start).days, 0) / 30.4375


def last_done(comp: Component, rule: MaintenanceRule) -> date | None:
    """Letzte Wartung dieser Regel; Einträge ohne Regelbezug gelten für alle Regeln der Komponente."""
    return max((l.performed_at for l in comp.logs if l.rule_id in (None, rule.id)), default=None)


def rule_state(db: Session, comp: Component, rule: MaintenanceRule, today: date | None = None) -> dict:
    """Verbrauch eines Wartungsintervalls seit der letzten Wartung (oder dem Einbau)."""
    today = today or date.today()
    last = last_done(comp, rule)
    base = last or comp.installed_at
    if base is None:
        # Ohne Einbaudatum und ohne Wartungseintrag lässt sich nichts zählen.
        return {
            "km_since": 0.0, "wet_km": 0.0, "effective_km": 0.0, "months_since": 0.0,
            "progress": 0.0, "status": "unknown", "last_done": None,
        }

    km, wet_km, effective = wear_between(db, comp.bike_id, base, comp.retired_at, rule.wet_factor)
    if last is None:  # noch nie gewartet: Kilometer, die ein gebrauchtes Teil schon hatte, zählen mit
        km += comp.start_km
        effective += comp.start_km
    months_since = months_between(base, today)

    ratios = []
    if rule.interval_km:
        ratios.append(effective / rule.interval_km)
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
        "km_since": round(km, 1),
        "wet_km": round(wet_km, 1),
        "effective_km": round(effective, 1),
        "months_since": round(months_since, 1),
        "progress": round(progress, 3),
        "status": state,
        "last_done": last,
    }


def worst_status(states: list[str]) -> str:
    if "due" in states:
        return "due"
    if "soon" in states:
        return "soon"
    return "ok"


def component_status(db: Session, comp: Component) -> str:
    states = [rule_state(db, comp, r)["status"] for r in comp.rules]
    known = [s for s in states if s != "unknown"]
    if states and not known:
        return "unknown"
    return worst_status(known)


def create_default_components(
    db: Session, user_id: int, bike: Bike, categories: list[str] | None = None
) -> list[Component]:
    """Legt die Standardkomponenten samt Wartungsregeln an. Vorhandene Kategorien werden übersprungen."""
    wanted = categories if categories is not None else list(categories_for(bike.type))
    existing = {c.category for c in bike.components if not c.retired_at}
    created: list[Component] = []
    for cat in wanted:
        tpl = CATALOG.get(cat)
        if tpl is None or cat in existing:
            continue
        comp = Component(user_id=user_id, bike_id=bike.id, category=cat, name=tpl.name)
        rules = chain_rules(bike.chain_lube) if cat == "chain" else tpl.rules
        comp.rules = [
            MaintenanceRule(
                label=r.label, interval_km=r.interval_km, interval_months=r.interval_months,
                wet_factor=r.wet_factor, hint=r.hint or None,
            )
            for r in rules
        ]
        db.add(comp)
        created.append(comp)
    db.flush()
    return created


def apply_chain_lube(db: Session, bike: Bike) -> int:
    """Passt die Regeln der Kette an die gewählte Schmierung an (Öl, Heißwachs, Tropfwachs).

    Schmier- und Wechselregel werden an Ort und Stelle geändert, damit bereits eingetragene Wartungen erhalten
    bleiben. Eigene Regeln mit anderen Namen bleiben unberührt. Gibt die Zahl geänderter Regeln zurück.
    """
    lube_rule, wear_rule = chain_rules(bike.chain_lube)
    changed = 0
    for comp in bike.components:
        if comp.category != "chain" or comp.retired_at:
            continue
        for r in comp.rules:
            tpl = lube_rule if r.label in LUBE_LABELS else wear_rule if r.label == wear_rule.label else None
            if tpl is None:
                continue
            r.label, r.interval_km, r.interval_months = tpl.label, tpl.interval_km, tpl.interval_months
            r.wet_factor, r.hint = tpl.wet_factor, tpl.hint or None
            changed += 1
    db.flush()
    return changed
