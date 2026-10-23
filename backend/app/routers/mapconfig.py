import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import User
from ..security import current_user

router = APIRouter(prefix="/api", tags=["map"])

OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende'
CARTO_ATTRIBUTION = OSM_ATTRIBUTION + ' &copy; <a href="https://carto.com/attributions">CARTO</a>'
KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{6,128}$")


def build_map_config(user_key: str | None = None) -> dict:
    """Kachelserver für die Karten. CARTO verlangt seit 2025 einen (kostenlosen) Schlüssel.

    Reihenfolge: eigene Kachel-URL des Servers, Schlüssel des Nutzers, Schlüssel des Servers, OpenStreetMap.
    """
    if settings.map_tile_url:
        return {"url": settings.map_tile_url, "dark": settings.map_tile_dark, "subdomains": "abc",
                "attribution": OSM_ATTRIBUTION, "max_zoom": 18, "provider": "custom"}
    key = (user_key or "").strip() or settings.carto_api_key.strip()
    if key and KEY_RE.match(key):
        return {
            "url": "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png?key=" + key,
            "dark": True, "subdomains": "abcd", "attribution": CARTO_ATTRIBUTION, "max_zoom": 18,
            "provider": "carto",
        }
    return {"url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "dark": False, "subdomains": "abc",
            "attribution": OSM_ATTRIBUTION, "max_zoom": 19, "provider": "osm"}


@router.get("/map-config")
def map_config(user: User = Depends(current_user)):
    return build_map_config(user.carto_api_key)


class MapSettingsIn(BaseModel):
    carto_api_key: str = ""  # leer = eigenen Schlüssel entfernen


def _settings_out(user: User) -> dict:
    cfg = build_map_config(user.carto_api_key)
    return {
        "provider": cfg["provider"],
        "has_user_key": bool(user.carto_api_key),
        "server_has_key": bool(settings.carto_api_key.strip()),
        "server_custom_url": bool(settings.map_tile_url),
        "key_hint": ("…" + user.carto_api_key[-4:]) if user.carto_api_key else None,
    }


@router.get("/settings/map")
def get_map_settings(user: User = Depends(current_user)):
    """Zeigt, welcher Kartenhintergrund aktiv ist. Der Schlüssel selbst wird nie zurückgegeben."""
    return _settings_out(user)


@router.put("/settings/map")
def save_map_settings(data: MapSettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    key = data.carto_api_key.strip()
    if key and not KEY_RE.match(key):
        raise HTTPException(
            422, "Der Schlüssel sieht ungültig aus. Erlaubt sind Buchstaben, Ziffern, - und _ (6 bis 128 Zeichen)."
        )
    user.carto_api_key = key or None
    db.commit()
    return _settings_out(user)
