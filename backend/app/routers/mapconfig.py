from fastapi import APIRouter, Depends

from ..config import settings
from ..models import User
from ..security import current_user

router = APIRouter(prefix="/api", tags=["map"])

OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende'
CARTO_ATTRIBUTION = OSM_ATTRIBUTION + ' &copy; <a href="https://carto.com/attributions">CARTO</a>'


def build_map_config() -> dict:
    """Kachelserver für die Karten. CARTO verlangt seit 2025 einen (kostenlosen) Schlüssel."""
    if settings.map_tile_url:
        return {"url": settings.map_tile_url, "dark": settings.map_tile_dark, "subdomains": "abc",
                "attribution": OSM_ATTRIBUTION, "max_zoom": 18}
    key = settings.carto_api_key.strip()
    if key:
        return {
            "url": "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png?key=" + key,
            "dark": True, "subdomains": "abcd", "attribution": CARTO_ATTRIBUTION, "max_zoom": 18,
        }
    return {"url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "dark": False, "subdomains": "abc",
            "attribution": OSM_ATTRIBUTION, "max_zoom": 19}


@router.get("/map-config")
def map_config(user: User = Depends(current_user)):
    return build_map_config()
