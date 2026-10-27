"""Servereinstellungen, die der Administrator in der Oberfläche ändert.

Die Umgebungsvariablen (.env) liefern die Startwerte. Was der Administrator speichert, steht in der Tabelle
app_settings und überschreibt sie. Geheimnisse (SMTP-Passwort, Kartenschlüssel) werden nie an den Browser
zurückgegeben; dort steht nur, ob ein Wert gesetzt ist.
"""
from __future__ import annotations

import re
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .config import settings
from .models import AppSetting

# key -> (Typ, Gruppe, Geheimnis?)
FIELDS: dict[str, tuple[str, str, bool]] = {
    "allow_registration": ("bool", "access", False),
    "token_expire_days": ("int:1:90", "access", False),
    "trusted_proxies": ("int:0:5", "access", False),
    "frame_ancestors": ("origins", "access", False),
    "public_url": ("url", "general", False),
    "timezone": ("tz", "general", False),
    "smtp_host": ("host", "email", False),
    "smtp_port": ("int:1:65535", "email", False),
    "smtp_user": ("str:255", "email", False),
    "smtp_password": ("str:255", "email", True),
    "smtp_from": ("str:255", "email", False),
    "smtp_starttls": ("bool", "email", False),
    "ntfy_server": ("url", "notify", False),
    "reminders_enabled": ("bool", "features", False),
    "weather_enabled": ("bool", "features", False),
    "geo_enabled": ("bool", "features", False),
    "intervals_enabled": ("bool", "features", False),
    "carto_api_key": ("str:128", "maps", True),
    "map_tile_url": ("tileurl", "maps", False),
    "map_tile_dark": ("bool", "maps", False),
}
HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.\-]{0,251}[A-Za-z0-9])?$")


class SettingError(ValueError):
    pass


ORIGIN_RE = re.compile(r"^(https?)://(\*\.)?[a-z0-9]([a-z0-9.-]*[a-z0-9])?(:\d{1,5})?$")


def normalize_origins(text: str) -> str:
    """Adressen, die BikeHelper einbetten dürfen (z. B. Home Assistant). Nur Schema, Name und Port, ohne Pfad."""
    out = []
    for item in re.split(r"[\s,;]+", text or ""):
        item = item.strip().lower().rstrip("/")
        if not item:
            continue
        m = re.match(r"^(https?://[^/]+)(/.*)?$", item)
        if m:
            item = m.group(1)  # Pfad weglassen, der Browser prüft nur die Herkunft
        if not ORIGIN_RE.match(item):
            raise SettingError(f"„{item}“ ist keine Adresse wie https://ha.example.de oder http://192.168.1.20:8123")
        if item not in out:
            out.append(item)
    if len(out) > 10:
        raise SettingError("Höchstens 10 Adressen")
    return " ".join(out)


def coerce(key: str, raw):
    """Prüft einen Wert und gibt ihn im richtigen Typ zurück."""
    kind = FIELDS[key][0]
    base, *args = kind.split(":")
    if base == "bool":
        if isinstance(raw, bool):
            return raw
        if str(raw).lower() in ("true", "1", "yes", "ja"):
            return True
        if str(raw).lower() in ("false", "0", "no", "nein", ""):
            return False
        raise SettingError("Ja oder Nein erwartet")
    if base == "int":
        try:
            n = int(str(raw).strip())
        except ValueError:
            raise SettingError("Ganze Zahl erwartet")
        lo, hi = int(args[0]), int(args[1])
        if not lo <= n <= hi:
            raise SettingError(f"Wert zwischen {lo} und {hi} erwartet")
        return n
    text = str(raw if raw is not None else "").strip()
    if base == "str":
        if len(text) > int(args[0]):
            raise SettingError("Zu lang")
        return text
    if base == "host":
        if text and not HOST_RE.match(text):
            raise SettingError("Ungültiger Servername")
        return text
    if base in ("url", "tileurl"):
        if base == "tileurl" and not text:
            return ""
        if not re.match(r"^https?://[^\s]+$", text) or len(text) > 500:
            raise SettingError("Eine Adresse mit http:// oder https:// erwartet")
        return text.rstrip("/") if base == "url" else text
    if base == "origins":
        return normalize_origins(text)
    if base == "tz":
        try:
            ZoneInfo(text)
        except Exception:
            raise SettingError("Unbekannte Zeitzone (z. B. Europe/Berlin)")
        return text
    raise SettingError("Unbekanntes Feld")


def _serialize(value) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def apply_overrides(db: Session) -> None:
    """Liest die gespeicherten Einstellungen und setzt sie für den laufenden Prozess."""
    for row in db.query(AppSetting).all():
        if row.key in FIELDS:
            try:
                setattr(settings, row.key, coerce(row.key, row.value))
            except SettingError:
                continue


def save(db: Session, values: dict) -> list[str]:
    """Speichert Änderungen. Gibt die geänderten Schlüssel zurück. Geheimnisse: None = behalten, "" = löschen."""
    clean: dict = {}
    errors = {}
    for key, raw in values.items():
        if key not in FIELDS:
            errors[key] = "Unbekannte Einstellung"
            continue
        if FIELDS[key][2] and raw is None:
            continue
        try:
            clean[key] = coerce(key, raw)
        except SettingError as e:
            errors[key] = str(e)
    if errors:
        raise SettingError("; ".join(f"{k}: {v}" for k, v in errors.items()))
    for key, value in clean.items():
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=_serialize(value)))
        else:
            row.value = _serialize(value)
        setattr(settings, key, value)
    db.commit()
    return list(clean)


def describe(db: Session) -> dict:
    """Aktuelle Werte für die Oberfläche; Geheimnisse nur als gesetzt/nicht gesetzt."""
    saved = {r.key for r in db.query(AppSetting).all()}
    out = {}
    for key, (kind, group, secret) in FIELDS.items():
        value = getattr(settings, key)
        out[key] = {
            "group": group, "secret": secret, "from_ui": key in saved,
            **({"set": bool(str(value).strip())} if secret else {"value": value}),
        }
    return out
