"""Blöcke der Startseite: Auswahl, Reihenfolge und die Daten der zusätzlichen Analyse-Blöcke.

Die Standardblöcke (Woche, Wartung, Räder, Jahresziel, letzte Fahrten) kommen aus /api/home. Die Analyse-Blöcke
(Eddington-Zahl, Serie, Rekorde, Form) werden nur berechnet, wenn der Nutzer sie auf seiner Startseite hat.
Reiner Rechenkern ohne Datenbank; die Endpunkte stehen in routers/home.py.
"""
from __future__ import annotations

import json
from datetime import date

from .stats import extra as X
from .stats.overview import Row, eddington_block, local, streaks

# id -> (Titel, Beschreibung, breit?, nur im Expertenmodus?, zusätzliche Daten nötig?)
CATALOG: dict[str, tuple[str, str, bool, bool, bool]] = {
    "week": ("Diese Woche", "Kilometer pro Tag, mit Blättern in frühere Wochen", False, False, False),
    "maintenance": ("Wartung", "Was bald oder jetzt fällig ist, mit Schnellerfassung", False, False, False),
    "bikes": ("Deine Räder", "Jedes Rad mit Kilometerstand und Status", True, False, False),
    "goal": ("Jahresziel", "Fortschritt zu deinem Ziel und was pro Woche nötig ist", False, False, False),
    "recent": ("Letzte Fahrten", "Die vier neuesten Fahrten", False, False, False),
    "eddington": ("Eddington-Zahl", "An wie vielen Tagen du mindestens so viele Kilometer gefahren bist", False, False, True),
    "streaks": ("Serie", "Tage in Folge mit einer Fahrt", False, False, True),
    "records": ("Rekorde", "Längste Fahrt, bester Tag und meiste Höhenmeter", False, False, True),
    "form": ("Form und Fitness", "Geschätzte Fitness, Ermüdung und Form aus deinen Fahrten", False, True, True),
}
DEFAULT_LAYOUT = ["week", "maintenance", "bikes", "goal", "recent"]
MAX_BLOCKS = 12


def catalog(mode: str) -> list[dict]:
    return [{"id": k, "title": t, "text": d, "wide": w, "expert": e, "available": mode == "expert" or not e}
            for k, (t, d, w, e, _) in CATALOG.items()]


def parse_layout(raw: str | None) -> list[str] | None:
    """Gespeicherte Anordnung als Liste; None = Standard. Unbekannte oder doppelte Einträge werden verworfen."""
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    out: list[str] = []
    for x in data:
        if isinstance(x, str) and x in CATALOG and x not in out:
            out.append(x)
    return out


def clean_layout(ids: list[str]) -> str:
    """Prüft eine vom Nutzer gesendete Anordnung und gibt sie als JSON zum Speichern zurück. Wirft ValueError bei Fehlern."""
    if len(ids) > MAX_BLOCKS:
        raise ValueError(f"Höchstens {MAX_BLOCKS} Blöcke")
    if len(set(ids)) != len(ids):
        raise ValueError("Jeder Block darf nur einmal vorkommen")
    bad = [i for i in ids if i not in CATALOG]
    if bad:
        raise ValueError("Unbekannter Block")
    return json.dumps(ids)


def needs_data(ids: list[str]) -> list[str]:
    return [i for i in ids if i in CATALOG and CATALOG[i][4]]


def compute(ids: list[str], rows: list[Row], tz, today: date) -> dict[str, dict]:
    """Daten der angefragten Analyse-Blöcke."""
    wanted = needs_data(ids)
    if not wanted:
        return {}
    loc = sorted(((local(r.start, tz), r) for r in rows), key=lambda x: x[0])
    per_day: dict[str, float] = {}
    for dt, r in loc:
        k = dt.date().isoformat()
        per_day[k] = per_day.get(k, 0.0) + r.km
    out: dict[str, dict] = {}
    if "eddington" in wanted:
        out["eddington"] = eddington_block(per_day) if per_day else {"value": 0, "next": 1, "missing_days": 1, "by_year": [], "history": []}
    if "streaks" in wanted:
        days = {dt.date() for dt, _ in loc}
        longest, current = streaks(days, today) if days else (0, 0)
        out["streaks"] = {"current": current, "longest": longest}
    if "records" in wanted:
        longest_ride = max(rows, key=lambda r: r.km, default=None)
        best_day = max(per_day.items(), key=lambda kv: kv[1], default=None)
        climb = max(rows, key=lambda r: r.elev_m or 0, default=None)
        out["records"] = {
            "longest": {"id": longest_ride.id, "km": round(longest_ride.km, 1)} if longest_ride else None,
            "best_day": {"date": best_day[0], "km": round(best_day[1], 1)} if best_day else None,
            "climb": {"id": climb.id, "m": round(climb.elev_m or 0)} if climb and (climb.elev_m or 0) > 0 else None,
        }
    if "form" in wanted:
        series = X.load_series(loc, today)
        now = series[-1] if series else None
        if now is None:
            out["form"] = {"fitness": None, "fatigue": None, "form": None, "state": None}
        else:
            f = now["form"]
            state = "frisch" if f > 5 else "im Gleichgewicht" if f >= -10 else "müde"
            out["form"] = {"fitness": now["fitness"], "fatigue": now["fatigue"], "form": f, "state": state}
    return out
