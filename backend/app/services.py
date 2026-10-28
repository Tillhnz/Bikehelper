from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import wear as wear_model
from .catalog import CATALOG, CHAIN_WEAR_LABEL, INSPECTIONS, WEAR_TO_INSPECTION, LEGACY_CATEGORIES, LUBE_LABELS, WAX_LUBE_LABEL, categories_for, chain_rules, wax_interval_km
from .timeutil import local_to_utc
from .models import Activity, Bike, Component, MaintenanceLog, MaintenanceRule, TireMount, TireSet

SOON_THRESHOLD = 0.8


def _since(d: date | datetime | None) -> datetime | None:
    if isinstance(d, datetime):  # genauer Zeitpunkt (UTC): spätere Fahrten zählen
        return d
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


def is_tracked(comp: Component) -> bool:
    """Ältere Reifen-Komponenten zählen nicht mehr zur Wartung (Reifen laufen über die Reifensätze)."""
    return comp.category not in LEGACY_CATEGORIES


def effective_installed(comp: Component) -> date | None:
    """Einbaudatum der Komponente; ohne eigenes Datum gilt das Kaufdatum des Rades."""
    if comp.installed_at:
        return comp.installed_at
    return comp.bike.purchased_at if comp.bike is not None else None


def component_km(db: Session, comp: Component) -> float:
    return comp.start_km + km_between(db, comp.bike_id, effective_installed(comp), comp.retired_at)


def months_between(start: date, end: date) -> float:
    return max((end - start).days, 0) / 30.4375


def is_visual_check(log: MaintenanceLog) -> bool:
    """Sichtprüfung der ganzen Komponente (okay, im Auge behalten, austauschen), nicht an eine Regel gebunden."""
    return log.rule_id is None and log.result is not None


def _counts(log: MaintenanceLog, rule: MaintenanceRule) -> bool:
    """Gilt dieser Eintrag als Erledigt-Vermerk für die Regel? Einträge ohne Regelbezug gelten für alle Regeln der Komponente.
    Eine Sichtprüfung mit okay oder im Auge behalten startet die Wechselregeln neu, "austauschen" tut das nicht."""
    if is_visual_check(log):
        return log.result in ("good", "watch") and visual_applies(rule)
    return log.rule_id in (None, rule.id)


def last_done(comp: Component, rule: MaintenanceRule) -> date | None:
    """Letzte Wartung dieser Regel."""
    return max((l.performed_at for l in comp.logs if _counts(l, rule)), default=None)


def last_log(comp: Component, rule: MaintenanceRule) -> MaintenanceLog | None:
    """Jüngster Wartungseintrag, der für diese Regel gilt (bei gleichem Datum der zuletzt angelegte)."""
    logs = [l for l in comp.logs if _counts(l, rule)]
    return max(logs, key=lambda l: (l.performed_at, l.performed_time or time.min, l.id or 0), default=None)


# Wie stark ein Prüfergebnis das nächste Prüfintervall verkürzt
WATCH_RECHECK_FACTOR = 0.4
# Anteil des Wechselintervalls, der zum Prüfzeitpunkt höchstens (gut) bzw. mindestens (beobachten) verbraucht gilt
GOOD_MAX_RATIO = 0.5
WATCH_MIN_RATIO = 0.8


def inspection_result(comp: Component, rule: MaintenanceRule, after: date | None = None) -> MaintenanceLog | None:
    """Jüngster Prüfeintrag mit Ergebnis für die Prüfregel dieser Wechselregel (nur Einträge ab `after`)."""
    name = WEAR_TO_INSPECTION.get(rule.label)
    sib = next((r for r in comp.rules if r.label == name), None) if name else None
    if sib is None:
        return None
    logs = [l for l in comp.logs if l.rule_id == sib.id and l.result and (after is None or l.performed_at >= after)]
    return max(logs, key=lambda l: (l.performed_at, l.performed_time or time.min, l.id or 0), default=None)


# Die Sichtprüfung der Komponente wirkt auf Regeln, die das Teil austauschen. Flüssigkeiten und Dichtmilch lassen sich nicht ansehen.
VISUAL_WATCH_FACTOR = 0.5  # "im Auge behalten": das Intervall wird halbiert


def visual_applies(rule: MaintenanceRule) -> bool:
    label = rule.label
    if label in WEAR_TO_INSPECTION or label in INSPECTIONS:
        return False  # Bremsbeläge haben ihre eigene Prüfregel
    if any(w in label for w in ("Flüssigkeit", "Dichtmilch")):
        return False
    return is_replacement_rule(rule) or "warten" in label  # Lager (Steuersatz, Innenlager, Naben): Spiel und Lauf lassen sich prüfen


def is_replacement_rule(rule: MaintenanceRule) -> bool:
    """Regel zum Austausch des Teils; sie wird über Sichtprüfung oder „Teil gewechselt“ erledigt."""
    label = rule.label
    if label in WEAR_TO_INSPECTION or label in INSPECTIONS or any(w in label for w in ("Flüssigkeit", "Dichtmilch")):
        return False
    return any(w in label for w in ("wechseln", "erneuern"))


def visual_replace_after(comp: Component, entry: MaintenanceLog | None) -> MaintenanceLog | None:
    """Sichtprüfung "austauschen", die jünger ist als der letzte Erledigt-Vermerk der Regel (danach hat sich nichts getan)."""
    def key(l):
        return (l.performed_at, l.performed_time or time.min, l.id or 0)
    logs = [l for l in comp.logs if is_visual_check(l) and l.result == "replace" and (entry is None or key(l) > key(entry))]
    return max(logs, key=key, default=None)


def rule_state(db: Session, comp: Component, rule: MaintenanceRule, today: date | None = None) -> dict:
    """Verbrauch eines Wartungsintervalls seit der letzten Wartung (oder dem Einbau)."""
    today = today or date.today()
    entry = last_log(comp, rule)
    last = entry.performed_at if entry else None
    variant = entry.variant if entry and rule.label == WAX_LUBE_LABEL else None
    interval_km = wax_interval_km(rule.label, variant, rule.interval_km)
    interval_months = rule.interval_months
    assessment = None
    if rule.label in INSPECTIONS and entry is not None and entry.result:
        wear_rule = next((r for r in comp.rules if r.label == INSPECTIONS[rule.label]), None)
        wear_last = last_log(comp, wear_rule) if wear_rule else None
        if wear_last is None or wear_last.performed_at < entry.performed_at:  # nach dem Wechsel gilt es nicht mehr
            factor = WATCH_RECHECK_FACTOR if entry.result == "watch" else 1.0
            if interval_km:
                interval_km = interval_km * factor
            if interval_months:
                interval_months = max(1, round(interval_months * factor))
            assessment = {"result": entry.result, "date": entry.performed_at.isoformat(), "interval_km": round(interval_km) if interval_km else None}
    # Sichtprüfung der Komponente: okay startet das Intervall neu, im Auge behalten halbiert es, austauschen macht den Wechsel fällig
    visual_replace = False
    if assessment is None and visual_applies(rule):
        if entry is not None and is_visual_check(entry):
            if entry.result == "watch":
                if interval_km:
                    interval_km = interval_km * VISUAL_WATCH_FACTOR
                if interval_months:
                    interval_months = max(1, round(interval_months * VISUAL_WATCH_FACTOR))
            assessment = {"result": entry.result, "date": entry.performed_at.isoformat(),
                          "interval_km": round(interval_km) if interval_km else None, "visual": True}
        bad = visual_replace_after(comp, entry)
        if bad is not None:
            visual_replace = True
            assessment = {"result": "replace", "date": bad.performed_at.isoformat(), "interval_km": None, "km_left": 0, "visual": True}
    base = last or effective_installed(comp)
    # Mit Uhrzeit zählen nur Fahrten, die nach der Wartung begannen; ohne Uhrzeit der ganze Tag
    since = local_to_utc(last, entry.performed_time) if entry and entry.performed_time else base
    if base is None:
        # Ohne Einbaudatum und ohne Wartungseintrag lässt sich nichts zählen.
        return {
            "km_since": 0.0, "wet_km": 0.0, "effective_km": 0.0, "months_since": 0.0,
            "progress": 0.0, "status": "unknown", "last_done": None, "interval_km_eff": interval_km,
            "variant": variant, "measure": None, "assessment": None,
        }

    km, wet_km, effective = wear_between(db, comp.bike_id, since, comp.retired_at, rule.wet_factor)
    if last is None:  # noch nie gewartet: Kilometer, die ein gebrauchtes Teil schon hatte, zählen mit
        km += comp.start_km
        effective += comp.start_km
    months_since = months_between(base, today)

    ratios = []
    measure = None
    # Messwerte einer früheren Kette (vor dem letzten Kettenwechsel) zählen nicht
    mine = [m for m in comp.measurements if last is None or m.measured_at >= last]
    latest = max(mine, key=lambda m: (m.measured_at, m.id or 0), default=None) if (
        comp.category == "chain" and rule.label == CHAIN_WEAR_LABEL
    ) else None
    if latest is not None:
        # Gemessener Verschleiß ersetzt die Kilometerschätzung
        eff_at = wear_between(db, comp.bike_id, since, latest.measured_at, rule.wet_factor)[2]
        if last is None:
            eff_at += comp.start_km
        proj = wear_model.project(latest.wear_pct, eff_at, effective, comp.wear_limit_pct, interval_km)
        ratios.append(proj.ratio)
        factor = effective / km if km > 0 else 1.0
        measure = {
            "measured_at": latest.measured_at.isoformat(), "wear_pct": proj.measured_pct,
            "projected_pct": round(proj.projected_pct, 3), "limit_pct": proj.limit_pct,
            "km_left": round(proj.km_left / factor) if proj.km_left is not None else None,
            "rate_pct_per_1000": round(proj.rate_pct_per_1000, 3),
        }
    elif interval_km:
        ratio = effective / interval_km
        insp = inspection_result(comp, rule, last)
        if insp is not None:
            # Prüfung (gut / beobachten / wechseln) ersetzt die reine Kilometerschätzung ab dem Prüfzeitpunkt
            i_since = local_to_utc(last, entry.performed_time) if entry and entry.performed_time else base
            eff_at = wear_between(db, comp.bike_id, i_since, insp.performed_at, rule.wet_factor)[2]
            if last is None:
                eff_at += comp.start_km
            calc = eff_at / interval_km
            at = {"good": min(calc, GOOD_MAX_RATIO), "watch": max(calc, WATCH_MIN_RATIO)}.get(insp.result, max(calc, 1.0))
            ratio = at + max(0.0, effective - eff_at) / interval_km
            factor = effective / km if km > 0 else 1.0
            assessment = {
                "result": insp.result, "date": insp.performed_at.isoformat(),
                "interval_km": round(eff_at + (1 - at) * interval_km),
                "km_left": round(max(0.0, 1 - ratio) * interval_km / factor),
            }
            interval_km = eff_at + (1 - at) * interval_km
        ratios.append(ratio)
    if interval_months:
        ratios.append(months_since / interval_months)
    progress = max(ratios) if ratios else 0.0
    if visual_replace:
        progress = max(progress, 1.0)
    if assessment and assessment.get("visual") and assessment["result"] == "watch" and interval_km:
        assessment["km_left"] = round(max(0.0, interval_km - effective) / (effective / km if km > 0 else 1.0))

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
        "interval_km_eff": interval_km,
        "variant": variant,
        "measure": measure,
        "assessment": assessment,
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


def migrate_legacy_lube(db: Session) -> int:
    """Früher gab es hot_wax und drip_wax als Schmierung. Jetzt heißt sie wax; die Wachsart steht an der Wartung.

    Bereits eingetragene Schmierwartungen bekommen die bisherige Wachsart, damit ihre Intervalle gleich bleiben.
    """
    bikes = db.scalars(select(Bike).where(Bike.chain_lube.in_(("hot_wax", "drip_wax")))).all()
    for bike in bikes:
        old = bike.chain_lube
        bike.chain_lube = "wax"
        for comp in bike.components:
            if comp.category != "chain":
                continue
            lube_ids = {r.id for r in comp.rules if r.label in LUBE_LABELS}
            for log in comp.logs:
                if log.variant is None and log.rule_id in lube_ids:
                    log.variant = old
        apply_chain_lube(db, bike)
    db.commit()
    return len(bikes)


# ---------- Reifensätze ----------

def _tire_sets_of(db: Session, bike_id: int) -> list[TireSet]:
    return list(db.scalars(select(TireSet).where(TireSet.bike_id == bike_id)))


def mount_km(db: Session, bike_id: int, m: TireMount) -> float:
    return km_between(db, bike_id, m.from_date, m.to_date)


def tire_set_km(db: Session, ts: TireSet) -> float:
    return ts.start_km + sum(mount_km(db, ts.bike_id, m) for m in ts.mounts)


DEFAULT_TIRE_CHECK_KM = 1000


def tire_state(db: Session, ts: TireSet) -> dict:
    """Lebensdauer (max_km) und Sichtprüfung eines Reifensatzes. Gleiche Schwellen wie bei den Regeln: ab 80 % bald, ab 100 % fällig."""
    km = tire_set_km(db, ts)
    life = km / ts.max_km if ts.max_km else None
    interval = ts.check_km or DEFAULT_TIRE_CHECK_KM
    base = ts.checked_km if ts.checked_km is not None else ts.start_km
    since = max(0.0, km - base)
    cp = since / interval

    def level(p):
        return "ok" if p is None or p < 0.8 else "due" if p >= 1 else "soon"

    life_status, check_status = level(life), level(cp)
    return {
        "km": km, "progress": round(life, 3) if life is not None else None,
        "km_left": round(max(0.0, ts.max_km - km), 1) if ts.max_km else None, "life_status": life_status,
        "check_interval_km": interval, "checked_on": ts.checked_on, "km_since_check": round(since, 1),
        "check_progress": round(cp, 3), "check_status": check_status,
        "status": worst_status([life_status, check_status]),
    }


def open_mount(ts: TireSet) -> TireMount | None:
    return next((m for m in ts.mounts if m.to_date is None), None)


def current_tire_set(db: Session, bike_id: int) -> TireSet | None:
    return next((ts for ts in _tire_sets_of(db, bike_id) if not ts.retired and open_mount(ts)), None)


def sync_bike_tires(bike: Bike, ts: TireSet) -> None:
    """Der montierte Satz bestimmt Breite und Tubeless-Angabe des Rades (für den Ratgeber)."""
    if ts.width_mm is not None:
        bike.tire_width_mm = ts.width_mm
    if ts.tubeless is not None:
        bike.tubeless = ts.tubeless


def mount_tire_set(db: Session, ts: TireSet, day: date) -> None:
    """Montiert den Satz ab `day`. Ein bisher montierter Satz des Rades endet am Vortag."""
    for other in _tire_sets_of(db, ts.bike_id):
        m = open_mount(other)
        if m is None:
            continue
        if other.id == ts.id:
            return  # ist schon montiert
        if m.from_date >= day:
            db.delete(m)  # war keinen vollen Tag montiert
        else:
            m.to_date = day - timedelta(days=1)
    db.add(TireMount(tire_set_id=ts.id, from_date=day, to_date=None))
    sync_bike_tires(ts.bike, ts)
    db.flush()


def unmount_tire_set(db: Session, ts: TireSet, day: date) -> None:
    m = open_mount(ts)
    if m is None:
        return
    if m.from_date >= day:
        db.delete(m)
    else:
        m.to_date = day - timedelta(days=1)
    db.flush()


def find_overlap(db: Session, bike_id: int, from_date: date, to_date: date | None, ignore_id: int | None = None):
    """Gibt einen anderen Zeitraum desselben Rades zurück, der sich mit dem angegebenen überschneidet."""
    for ts in _tire_sets_of(db, bike_id):
        for m in ts.mounts:
            if m.id == ignore_id:
                continue
            if from_date <= (m.to_date or date.max) and m.from_date <= (to_date or date.max):
                return ts, m
    return None


def measurement_points(db: Session, comp: Component) -> list[dict]:
    """Messwerte mit den bis dahin gefahrenen Kilometern der Kette (für Liste und Diagramm)."""
    rule = next((r for r in comp.rules if r.label == CHAIN_WEAR_LABEL), None)
    entry = last_log(comp, rule) if rule else None
    base = effective_installed(comp) if entry is None else entry.performed_at
    out = []
    since = entry.performed_at if entry else None
    for m in sorted(comp.measurements, key=lambda m: (m.measured_at, m.id)):
        if since and m.measured_at < since:
            continue
        km = km_between(db, comp.bike_id, base, m.measured_at) + (comp.start_km if entry is None else 0.0)
        out.append({"id": m.id, "measured_at": m.measured_at, "wear_pct": m.wear_pct, "note": m.note, "km": round(km, 1)})
    return out
