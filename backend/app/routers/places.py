
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..geo import service as geo
from ..models import GeoState, Place, PlaceVisit, User
from ..security import current_user
from ..stats import places as P

router = APIRouter(prefix="/api", tags=["places"])


def build_places(rows: list[tuple[PlaceVisit, Place]]) -> dict:
    """Städte und Länder aus den gespeicherten Besuchen. Reiner Aufbau der Antwort, ohne Netzwerk."""
    cities = []
    countries: dict[str, dict] = {}
    for v, p in rows:
        cities.append({
            "id": p.id, "name": p.name, "kind": p.kind, "state": p.state, "country": p.country,
            "country_code": p.country_code, "tiles": v.tiles, "total": p.total_tiles,
            "percent": P.percent(v.tiles, p.total_tiles), "rides": v.rides,
        })
        code = p.country_code or "?"
        c = countries.setdefault(code, {"code": code, "name": p.country or "Unbekannt", "tiles": 0, "places": 0})
        c["tiles"] += v.tiles
        c["places"] += 1
    for c in countries.values():
        total = P.country_total_tiles(c["code"])
        c["total"] = total
        c["percent"] = P.percent(c["tiles"], total)
    real = [c for c in cities if c["kind"] in ("city", "town", "village")]
    home = max(real, key=lambda c: (c["rides"], c["tiles"]), default=None)
    cities.sort(key=lambda c: -c["tiles"])
    return {
        "home": home if home and home["rides"] > 0 else None,
        "cities": cities[:150],
        "countries": sorted(countries.values(), key=lambda c: -c["tiles"]),
    }


@router.get("/stats/places")
def places(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(PlaceVisit, Place).join(Place, Place.id == PlaceVisit.place_id).where(PlaceVisit.user_id == user.id)
    ).all()
    state = db.get(GeoState, user.id)
    return {
        "enabled": settings.geo_enabled,
        **build_places([(v, p) for v, p in rows]),
        "status": {
            **geo.status(user.id),
            "unresolved": state.unresolved if state else None,
            "explored": state.explored if state else None,
            "updated_at": state.updated_at.isoformat() if state and state.updated_at else None,
            "error": state.error if state else None,
        },
        "source": "Orte und Grenzen: © OpenStreetMap-Mitwirkende (ODbL), abgefragt über Nominatim",
    }


@router.post("/stats/places/refresh")
def refresh(user: User = Depends(current_user)):
    if not settings.geo_enabled:
        return {"started": False, "reason": "disabled"}
    return {"started": geo.start(user.id)}
