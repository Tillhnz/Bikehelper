"""Gruppen über mehrere Server, Gastgeber-Seite. Der Gast wird hier mit direkten Anfragen an /api/federation gespielt."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def _user(c, email):
    r = c.post("/api/auth/register", json={"email": email, "password": "geheim1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _day(d, km, rides=1):
    return {"day": d.isoformat(), "km": km, "rides": rides, "time_s": int(km / 25 * 3600), "elev_m": km * 5, "longest_km": km / rides}


def test_federation_is_off_by_default():
    assert settings.federation_enabled is False
    with TestClient(app) as c:
        assert c.get("/api/federation/ping").status_code == 404
        assert c.post("/api/federation/join", json={"token": "x" * 10, "display_name": "A"}).status_code == 404


def test_remote_member_joins_pushes_days_and_shows_up(monkeypatch):
    monkeypatch.setattr(settings, "federation_enabled", True)
    with TestClient(app) as c:
        a = _user(c, "fa@example.com")
        gid = c.post("/api/groups", headers=a, json={"name": "Landesweit", "display_name": "Anna"}).json()["id"]
        link = c.post(f"/api/groups/{gid}/invite-link", headers=a).json()["link"]
        token = link.rsplit("/", 1)[1]

        assert c.get("/api/federation/ping").json()["federation"] == 1
        assert c.get(f"/api/federation/invite/{token}").json()["group"] == "Landesweit"
        assert c.get("/api/federation/invite/gibtesnicht").status_code == 404
        assert c.post("/api/federation/join", json={"token": token, "display_name": "Anna"}).status_code == 409  # Name vergeben
        joined = c.post("/api/federation/join", json={"token": token, "display_name": "Fernando", "origin": "https://anderer.example.de"})
        assert joined.status_code == 200
        key = joined.json()["key"]
        h = {"Authorization": f"Bearer {key}"}

        assert c.get("/api/federation/info").status_code == 401
        assert c.get("/api/federation/info", headers={"Authorization": "Bearer falsch"}).status_code == 401

        today = date.today()
        body = {"display_name": "Fernando", "share": True, "since": None,
                "days": [_day(today, 40.0, rides=2), _day(today - timedelta(days=1), 25.0)]}
        assert c.post("/api/federation/push", headers=h, json=body).json() == {"group": "Landesweit", "members": 2}

        # Gastgeber sieht den externen Teilnehmer in Rangliste und Gruppenübersicht
        stats = c.get(f"/api/groups/{gid}/stats?period=all", headers=a).json()
        row = next(r for r in stats["rows"] if r["display_name"] == "Fernando")
        assert row["remote"] is True and row["km"] == 65.0 and row["rides"] == 3 and row["is_me"] is False
        assert row["longest_km"] == 25.0 and row["extras"] == {} and stats["has_remote"] is True
        members = c.get(f"/api/groups/{gid}", headers=a).json()["members"]
        assert next(m for m in members if m["display_name"] == "Fernando")["remote"] is True

        # Der Gast sieht dieselbe Rangliste, seine Zeile ist „ich“; Admin-Teile fehlen
        theirs = c.get("/api/federation/stats?period=all", headers=h).json()
        assert next(r for r in theirs["rows"] if r["display_name"] == "Fernando")["is_me"] is True
        info = c.get("/api/federation/info", headers=h).json()
        assert info["role"] == "member" and info["invites"] == [] and info["categories"] == []

        # Erneutes Senden ab einem Tag ersetzt nur die Tage ab da (hier: gestern gelöscht, heute geändert)
        body2 = {"display_name": "Fernando", "share": True, "since": today.isoformat(), "days": [_day(today, 10.0)]}
        c.post("/api/federation/push", headers=h, json=body2)
        c.post("/api/federation/push", headers=h, json={"share": True, "since": (today - timedelta(days=1)).isoformat(), "days": [_day(today, 10.0)]})
        row = next(r for r in c.get(f"/api/groups/{gid}/stats?period=all", headers=a).json()["rows"] if r["display_name"] == "Fernando")
        assert row["km"] == 10.0

        # Teilen abschalten: Werte verschwinden beim Gastgeber
        c.post("/api/federation/push", headers=h, json={"share": False, "days": []})
        stats = c.get(f"/api/groups/{gid}/stats?period=all", headers=a).json()
        assert all(r["display_name"] != "Fernando" for r in stats["rows"]) and "Fernando" in stats["not_sharing"]

        # Ungültige Werte werden abgelehnt
        assert c.post("/api/federation/push", headers=h, json={"share": True, "days": [{**_day(today, 10.0), "km": -5}]}).status_code == 422

        # Austritt vom Gast aus; der Schlüssel gilt danach nicht mehr
        assert c.delete("/api/federation/leave", headers=h).status_code == 204
        assert c.get("/api/federation/info", headers=h).status_code == 401
        assert [m["display_name"] for m in c.get(f"/api/groups/{gid}", headers=a).json()["members"]] == ["Anna"]


def test_host_admin_can_remove_remote_member_and_goal_counts_remote_days(monkeypatch):
    monkeypatch.setattr(settings, "federation_enabled", True)
    with TestClient(app) as c:
        a = _user(c, "fb@example.com")
        gid = c.post("/api/groups", headers=a, json={"name": "Ziel", "display_name": "Anna"}).json()["id"]
        token = c.post(f"/api/groups/{gid}/invite-link", headers=a).json()["link"].rsplit("/", 1)[1]
        key = c.post("/api/federation/join", json={"token": token, "display_name": "Fern"}).json()["key"]
        h = {"Authorization": f"Bearer {key}"}
        today = date.today()
        c.post("/api/federation/push", headers=h, json={"share": True, "days": [_day(today, 60.0)]})
        c.put(f"/api/groups/{gid}/goal", headers=a, json={"metric": "km", "target": 100, "start": (today - timedelta(days=5)).isoformat(),
                                                           "end": (today + timedelta(days=5)).isoformat()})
        goal = c.get(f"/api/groups/{gid}/goal", headers=a).json()["goal"]
        # alle teilenden Mitglieder stehen in der Liste, auch mit 0 km; der Gast vom anderen Server zählt mit
        assert goal["done"] == 60.0 and [(m["display_name"], m["value"]) for m in goal["members"]] == [("Fern", 60.0), ("Anna", 0.0)]
        # Der Gast sieht dasselbe Ziel
        assert c.get("/api/federation/goal", headers=h).json()["goal"]["done"] == 60.0

        info = c.get(f"/api/groups/{gid}", headers=a).json()
        rid = next(m["user_id"] for m in info["members"] if m["remote"])
        assert rid < 0
        assert c.put(f"/api/groups/{gid}/members/{rid}/role", headers=a, json={"role": "admin"}).status_code == 409
        assert c.delete(f"/api/groups/{gid}/members/{rid}", headers=a).status_code == 204
        assert c.get("/api/federation/info", headers=h).status_code == 401
