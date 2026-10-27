"""Versionshinweise („Was ist neu?“), die jedes Konto nach einem Update einmal beim Anmelden sieht.

Die Einträge stehen in data/changelog.json, der neueste zuerst. Zu jedem Update kommt oben ein Eintrag mit neuer `id` dazu
(Datum, bei mehreren am selben Tag mit Zähler: 2026-10-27.2); wer den Hinweis noch nicht gesehen hat, bekommt ihn bei der nächsten Anmeldung.
"""
import json
from functools import lru_cache
from pathlib import Path

_FILE = Path(__file__).parent / "data" / "changelog.json"
MAX_SHOWN = 5  # wer lange nicht da war (oder nie einen Hinweis gesehen hat), bekommt nur die letzten Einträge
LEGACY = {"intervals-2026-10": "2026-10-27.1"}  # alte Kennung des ersten Hinweises


@lru_cache(maxsize=1)
def entries() -> list[dict]:
    return json.loads(_FILE.read_text(encoding="utf-8"))


def latest_id() -> str:
    return entries()[0]["id"]


def unseen(seen: str | None) -> list[dict]:
    """Einträge, die seit der zuletzt gesehenen Version dazugekommen sind (neueste zuerst)."""
    seen = LEGACY.get(seen or "", seen)
    items = entries()
    ids = [e["id"] for e in items]
    if seen in ids:
        return items[: ids.index(seen)][:MAX_SHOWN]
    return items[:MAX_SHOWN]
