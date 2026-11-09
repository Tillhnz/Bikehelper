"""Update-Wächter: meldet Administratoren per Push (ntfy), sobald auf GitHub eine neue Version bereitliegt.

Fragt alle 6 Stunden den Update-Dienst (git fetch) und meldet jede neue Version genau einmal. Enthält sie
Paket- oder Sicherheitsupdates (z. B. von Dependabot), steht das im Titel.
"""
from __future__ import annotations

import logging
import re
import threading
import time

from sqlalchemy import select

from .config import settings
from .database import SessionLocal
from .models import AppSetting, User

log = logging.getLogger("bikehelper.updatewatch")
CHECK_EVERY_S = 6 * 3600
KEY = "_update_notified"
SECURITY = re.compile(r"\b(bump|sicherheit|security|cve-|lücke|vulnerab|dependabot)\b", re.I)


def describe(changes: list[str], behind: int) -> tuple[bool, str]:
    subjects = [c.split("  ", 1)[-1] for c in changes]
    sec = any(SECURITY.search(s) for s in subjects)
    lines = "\n".join(f"• {s}" for s in subjects[:8]) + (f"\n… und {behind - 8} weitere" if behind > 8 else "")
    return sec, lines


def run_once(fetch_status=None, send=None) -> bool:
    """Gibt True zurück, wenn eine Meldung verschickt wurde."""
    from . import notify
    from .routers.admin import _updater
    if not settings.update_notify:
        return False
    try:
        st = (fetch_status or (lambda: _updater("GET", "/status?check=1", timeout=120)))()
    except Exception as e:  # noqa: BLE001 - kein Update-Dienst (z. B. Docker-Images) oder nicht erreichbar
        log.info("Update-Prüfung nicht möglich: %s", getattr(e, "detail", e))
        return False
    behind, changes = st.get("behind") or 0, st.get("changes") or []
    if not behind or not changes:
        return False
    with SessionLocal() as db:
        row = db.get(AppSetting, KEY)
        if row is not None and row.value == changes[0]:
            return False
        sec, lines = describe(changes, behind)
        title = ("Sicherheitsupdate" if sec else "Neue Version") + " für BikeHelper verfügbar"
        body = (f"{behind} {'Änderung' if behind == 1 else 'Änderungen'}:\n{lines}\n\n"
                "Einspielen: Administration → Update.")
        admins = db.scalars(select(User).where(User.role == "admin", User.ntfy_topic.is_not(None))).all()
        for u in admins:
            try:
                (send or notify.send_ntfy)(u.ntfy_topic, title, body)
            except Exception as e:  # noqa: BLE001
                log.warning("Push an %s fehlgeschlagen: %s", u.email, e)
        if row is None:
            db.add(AppSetting(key=KEY, value=changes[0]))
        else:
            row.value = changes[0]
        db.commit()
        return bool(admins)


def start_background() -> None:
    def loop() -> None:
        time.sleep(300)
        while True:
            try:
                run_once()
            except Exception:
                log.exception("Update-Prüfung fehlgeschlagen")
            time.sleep(CHECK_EVERY_S)

    threading.Thread(target=loop, daemon=True, name="updatewatch").start()
