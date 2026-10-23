"""Erinnerungen: meldet per E-Mail und ntfy, wenn eine Wartung bald oder jetzt fällig ist.

Jede Regel wird je Stufe (bald, fällig) nur einmal gemeldet. Wird sie erledigt und später wieder fällig, kommt eine
neue Meldung. Gesendet wird nur tagsüber (8 bis 21 Uhr in der eingestellten Zeitzone).
"""
from __future__ import annotations

import logging
import smtplib
import threading
import time
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal
from .models import Component, RuleNotice, User
from .services import rule_state

log = logging.getLogger("bikehelper.notify")

CHECK_INTERVAL_S = 3600
DAY_START, DAY_END = 8, 21
STATUS_TEXT = {"soon": "bald fällig", "due": "fällig"}
RANK = {"ok": 0, "unknown": 0, "soon": 1, "due": 2}


def smtp_configured() -> bool:
    return bool(settings.smtp_host and (settings.smtp_from or settings.smtp_user))


def collect_changes(db: Session, user: User, record: bool = True) -> list[dict]:
    """Regeln, deren Status seit der letzten Meldung schlechter geworden ist."""
    comps = db.scalars(select(Component).where(Component.user_id == user.id, Component.retired_at.is_(None))).all()
    out = []
    for c in comps:
        for r in c.rules:
            st = rule_state(db, c, r)["status"]
            notice = db.get(RuleNotice, r.id)
            seen = RANK.get(notice.status, 0) if notice else 0
            now = RANK.get(st, 0)
            if now > seen:
                out.append({"bike": c.bike.name if c.bike else None, "component": c.name, "rule": r.label, "status": st})
                if record:
                    if notice:
                        notice.status, notice.notified_at = st, datetime.utcnow()
                    else:
                        db.add(RuleNotice(rule_id=r.id, status=st))
            elif now == 0 and notice:
                if record:
                    db.delete(notice)  # wieder in Ordnung: nächste Fälligkeit wird neu gemeldet
            elif now < seen and record and notice:
                notice.status = st
    return out


def format_message(items: list[dict]) -> tuple[str, str]:
    due = [i for i in items if i["status"] == "due"]
    title = f"BikeHelper: {len(due)} Wartung{'en' if len(due) != 1 else ''} fällig" if due else \
        f"BikeHelper: {len(items)} Wartung{'en' if len(items) != 1 else ''} bald fällig"
    lines = [
        f"{(i['bike'] + ': ') if i['bike'] else ''}{i['component']} – {i['rule']} ({STATUS_TEXT[i['status']]})"
        for i in sorted(items, key=lambda i: -RANK[i["status"]])
    ]
    return title, "\n".join(lines)


def send_email(to: str, title: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg.set_content(f"{body}\n\n{settings.public_url}")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
        if settings.smtp_starttls:
            s.starttls()
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)


def send_ntfy(topic: str, title: str, body: str) -> None:
    # HTTP-Header müssen ASCII sein, deshalb Titel als JSON-Nachricht senden
    payload = {"topic": topic, "title": title, "message": body, "tags": ["bike"], "click": settings.public_url}
    r = httpx.post(settings.ntfy_server.rstrip("/"), json=payload, timeout=15)
    r.raise_for_status()


def deliver(user: User, title: str, body: str) -> list[str]:
    """Sendet über alle eingerichteten Kanäle; gibt Fehlermeldungen zurück."""
    errors = []
    if user.remind_email:
        try:
            if not smtp_configured():
                raise RuntimeError("Der Server hat keinen E-Mail-Versand eingerichtet (SMTP_HOST fehlt).")
            send_email(user.email, title, body)
        except Exception as e:  # noqa: BLE001
            errors.append(f"E-Mail: {e}")
    if user.ntfy_topic:
        try:
            send_ntfy(user.ntfy_topic, title, body)
        except Exception as e:  # noqa: BLE001
            errors.append(f"ntfy: {e}")
    return errors


def run_once(db: Session | None = None, force: bool = False) -> int:
    """Prüft alle Nutzer mit Erinnerungen und sendet neue Meldungen. Gibt die Zahl gesendeter Meldungen zurück."""
    own = db is None
    db = db or SessionLocal()
    sent = 0
    try:
        hour = datetime.now(ZoneInfo(settings.timezone)).hour
        if not force and not (DAY_START <= hour < DAY_END):
            return 0
        users = db.scalars(select(User).where((User.remind_email.is_(True)) | (User.ntfy_topic.is_not(None)))).all()
        for u in users:
            items = collect_changes(db, u)
            if not items:
                continue
            title, body = format_message(items)
            errors = deliver(u, title, body)
            if errors:
                db.rollback()  # nicht als gemeldet merken, beim nächsten Lauf erneut versuchen
                log.warning("Erinnerung für Nutzer %s fehlgeschlagen: %s", u.id, "; ".join(errors))
                continue
            db.commit()
            sent += 1
    finally:
        if own:
            db.close()
    return sent


def start_background() -> None:
    if not settings.reminders_enabled:
        return

    def loop() -> None:
        time.sleep(120)
        while True:
            try:
                run_once()
            except Exception:
                log.exception("Erinnerungslauf fehlgeschlagen")
            time.sleep(CHECK_INTERVAL_S)

    threading.Thread(target=loop, daemon=True, name="reminders").start()
