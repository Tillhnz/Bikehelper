"""Ereignisprotokoll für den Administrator: Anmeldungen, Verwaltungsvorgänge, grobe Aktionen und Serverfehler.

Es enthält bewusst keine Inhalte: keine Namen von Fahrten oder Rädern, keine Zahlen, keine Passwörter, keine IP-Adressen.
Bei Aktionen steht nur der Bereich (zum Beispiel „Lager“) und ob etwas neu, geändert oder gelöscht wurde.
"""
import logging
import re
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import AuditEntry

KEEP_DAYS = 30
MAX_ROWS = 20000
log = logging.getLogger("bikehelper")


def _prune(db: Session) -> None:
    db.execute(delete(AuditEntry).where(AuditEntry.at < datetime.utcnow() - timedelta(days=KEEP_DAYS)))
    over = db.query(AuditEntry.id).order_by(AuditEntry.id.desc()).offset(MAX_ROWS).limit(1).scalar()
    if over:
        db.execute(delete(AuditEntry).where(AuditEntry.id <= over))
    db.commit()


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_IP = re.compile(r"\b\d{1,3}(\.\d{1,3}){3}\b")


def scrub(text: str, limit: int = 4000) -> str:
    """Entfernt aus einer Fehlermeldung, was Personendaten sein könnte: SQL-Parameter, E-Mail-Adressen, IP-Adressen."""
    text = re.split(r"\[parameters:|\[SQL:|\(Background on this error", text)[0]
    text = _IP.sub("<IP>", _EMAIL.sub("<E-Mail>", text))
    return text.strip()[:limit]


def record(db: Session, actor: str, action: str, detail: str = "", error_text: str | None = None) -> None:
    """Schreibt einen Eintrag in die übergebene Sitzung und räumt gelegentlich alte Einträge auf."""
    entry = AuditEntry(actor=actor[:255], action=action[:40], detail=(detail or None) and detail[:300],
                       error_text=scrub(error_text) if error_text else None)
    db.add(entry)
    db.commit()
    if entry.id % 100 == 0:
        _prune(db)


def event(actor: str, action: str, detail: str = "", error_text: str | None = None) -> None:
    """Wie record, mit eigener Sitzung. Fehler hier dürfen nie eine Anfrage stören."""
    try:
        with SessionLocal() as db:
            record(db, actor, action, detail, error_text)
    except Exception:
        log.exception("Protokolleintrag fehlgeschlagen")
