from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models import Activity, GroupInvite, User


def _user(c, email):
    r = c.post("/api/auth/register", json={"email": email, "password": "geheim1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _uid(email):
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == email))


def _rides(uid, km_list):
    now = datetime.utcnow().replace(hour=10, minute=0, second=0, microsecond=0)
    with SessionLocal() as db:
        for i, km in enumerate(km_list):
            db.add(Activity(user_id=uid, name=f"Geheimfahrt {i}", start_date=now - timedelta(days=i * 40), distance_km=km, moving_time_s=int(km / 25 * 3600), elevation_m=km * 5))
        db.commit()


def test_group_invite_join_ranking_and_privacy():
    with TestClient(app) as c:
        a = _user(c, "ga@example.com")
        b = _user(c, "gb@example.com")
        o = _user(c, "go@example.com")
        _rides(_uid("ga@example.com"), [50, 30])
        _rides(_uid("gb@example.com"), [80])
        gid = c.post("/api/groups", headers=a, json={"name": "Pendler", "display_name": "Anna"}).json()["id"]
        # nur Gruppenadmins laden ein
        assert c.post(f"/api/groups/{gid}/invites", headers=b, json={"email": "x@example.com"}).status_code == 404
        r = c.post(f"/api/groups/{gid}/invites", headers=a, json={"email": "gb@example.com"})
        assert r.status_code == 201 and r.json()["mailed"] is False
        token = r.json()["link"].rsplit("/", 1)[1]
        assert [i["group"] for i in c.get("/api/groups/invitations", headers=b).json()] == ["Pendler"]
        assert c.post("/api/groups/join", headers=b, json={"token": token, "display_name": "Anna"}).status_code == 409  # Name vergeben
        assert c.post("/api/groups/join", headers=b, json={"token": token, "display_name": "Ben"}).status_code == 200
        assert c.post("/api/groups/join", headers=o, json={"token": token, "display_name": "Otto"}).status_code == 404  # einmal gültig
        assert c.get(f"/api/groups/{gid}", headers=o).status_code == 404  # Fremde sehen nichts

        s = c.get(f"/api/groups/{gid}/stats?period=week", headers=a).json()
        assert {r["display_name"] for r in s["rows"]} == {"Anna", "Ben"}
        s = c.get(f"/api/groups/{gid}/stats?period=all", headers=a).json()
        by = {r["display_name"]: r for r in s["rows"]}
        assert by["Anna"]["km"] == 80 and by["Anna"]["rides"] == 2 and by["Ben"]["km"] == 80 and by["Ben"]["rank"]["km"] == by["Anna"]["rank"]["km"] == 1
        text = str(s)
        assert "Geheimfahrt" not in text and "example.com" not in text  # nur Kennzahlen, keine Namen oder Adressen

        # Pausieren nimmt aus der Wertung
        assert c.put(f"/api/groups/{gid}/me", headers=b, json={"share": False}).status_code == 200
        s = c.get(f"/api/groups/{gid}/stats?period=all", headers=a).json()
        assert [r["display_name"] for r in s["rows"]] == ["Anna"] and s["not_sharing"] == ["Ben"]

        # Rollen: letzter Admin kann nicht gehen, nach Ernennung schon
        assert c.delete(f"/api/groups/{gid}/me", headers=a).status_code == 409
        assert c.put(f"/api/groups/{gid}/members/{_uid('gb@example.com')}/role", headers=b, json={"role": "admin"}).status_code == 403
        assert c.put(f"/api/groups/{gid}/members/{_uid('gb@example.com')}/role", headers=a, json={"role": "admin"}).status_code == 200
        assert c.delete(f"/api/groups/{gid}/me", headers=a).status_code == 204
        assert [g["name"] for g in c.get("/api/groups", headers=b).json()] == ["Pendler"]
        assert c.delete(f"/api/groups/{gid}/me", headers=b).status_code == 204  # allein: Gruppe verschwindet
        with SessionLocal() as db:
            assert db.scalar(select(GroupInvite.id)) is None
        assert c.get(f"/api/groups/{gid}", headers=b).status_code == 404


def test_deleting_account_promotes_next_admin():
    with TestClient(app) as c:
        _user(c, "gd0@example.com")  # erstes Konto ist Server-Admin und darf bleiben
        a = _user(c, "gd1@example.com")
        b = _user(c, "gd2@example.com")
        gid = c.post("/api/groups", headers=a, json={"name": "G", "display_name": "Eins"}).json()["id"]
        token = c.post(f"/api/groups/{gid}/invites", headers=a, json={"email": "gd2@example.com"}).json()["link"].rsplit("/", 1)[1]
        c.post("/api/groups/join", headers=b, json={"token": token, "display_name": "Zwei"})
        assert c.post("/api/me/delete", headers=a, json={"password": "geheim1234"}).status_code == 204
        assert c.get(f"/api/groups/{gid}", headers=b).json()["role"] == "admin"


def test_group_invite_link_lets_new_people_register_and_join(monkeypatch):
    from app.config import settings
    with TestClient(app) as c:
        a = _user(c, "gl1@example.com")  # erstes Konto
        monkeypatch.setattr(settings, "allow_registration", False)
        gid = c.post("/api/groups", headers=a, json={"name": "Link", "display_name": "Lena"}).json()["id"]
        assert c.get(f"/api/groups/{gid}", headers=a).json()["invite_link"] is None
        link = c.post(f"/api/groups/{gid}/invite-link", headers=a).json()["link"]
        token = link.rsplit("/", 1)[1]
        assert c.get(f"/api/groups/{gid}", headers=a).json()["invite_link"] == link
        # ohne Anmeldung: Gruppenname, und Registrierung trotz geschlossener Anmeldung
        assert c.get(f"/api/groups/invite-info/{token}").json() == {"group": "Link"}
        assert c.get("/api/groups/invite-info/falsch").status_code == 404
        body = {"email": "gl2@example.com", "password": "geheim1234"}
        assert c.post("/api/auth/register", json=body).status_code == 403
        assert c.post("/api/auth/register", json={**body, "group_invite": "falsch"}).status_code == 403
        r = c.post("/api/auth/register", json={**body, "group_invite": token})
        assert r.status_code == 201
        b = {"Authorization": f"Bearer {r.json()['access_token']}"}
        assert c.post("/api/groups/join", headers=b, json={"token": token, "display_name": "Max"}).status_code == 200
        # der Link gilt für mehrere Personen
        r3 = c.post("/api/auth/register", json={"email": "gl3@example.com", "password": "geheim1234", "group_invite": token})
        c3 = {"Authorization": f"Bearer {r3.json()['access_token']}"}
        assert c.post("/api/groups/join", headers=c3, json={"token": token, "display_name": "Mia"}).status_code == 200
        assert len(c.get(f"/api/groups/{gid}", headers=a).json()["members"]) == 3
        # neuer Link ersetzt den alten, Abschalten sperrt
        new = c.post(f"/api/groups/{gid}/invite-link", headers=a).json()["link"]
        assert new != link and c.get(f"/api/groups/invite-info/{token}").status_code == 404
        assert c.delete(f"/api/groups/{gid}/invite-link", headers=a).status_code == 204
        assert c.get(f"/api/groups/{gid}", headers=a).json()["invite_link"] is None
        assert c.post(f"/api/groups/{gid}/invite-link", headers=b).status_code == 403  # nur Admins


def test_group_series_follows_period_and_extras_need_consent():
    with TestClient(app) as c:
        a = _user(c, "gs1@example.com")
        b = _user(c, "gs2@example.com")
        _rides(_uid("gs1@example.com"), [40, 25])
        _rides(_uid("gs2@example.com"), [60])
        gid = c.post("/api/groups", headers=a, json={"name": "Reihe", "display_name": "Anna", "shared": ["records", "weather"]}).json()["id"]
        token = c.post(f"/api/groups/{gid}/invite-link", headers=a).json()["link"].rsplit("/", 1)[1]
        assert c.get(f"/api/groups/join/{token}", headers=b).json()["categories"][0]["key"] == "rhythm"
        assert c.post("/api/groups/join", headers=b, json={"token": token, "display_name": "Ben", "shared": ["quatsch"]}).status_code == 422
        assert c.post("/api/groups/join", headers=b, json={"token": token, "display_name": "Ben"}).status_code == 200

        info = c.get(f"/api/groups/{gid}", headers=a).json()
        assert info["shared"] == ["records", "weather"] and [m["shared"] for m in info["members"]] == [["records", "weather"], []]

        year = c.get(f"/api/groups/{gid}/stats?period=year", headers=a).json()
        week = c.get(f"/api/groups/{gid}/stats?period=week", headers=a).json()
        allp = c.get(f"/api/groups/{gid}/stats?period=all", headers=a).json()
        assert len(year["series"]["labels"]) == 12 and len(week["series"]["labels"]) == 7  # Verlauf passt zum Zeitraum
        assert year["series"]["labels"] != week["series"]["labels"] and allp["series"]["labels"][-1] == str(datetime.utcnow().year)
        by = {r["display_name"]: r for r in allp["rows"]}
        assert abs(sum(by["Anna"] and next(m["km"] for m in allp["series"]["members"] if m["display_name"] == "Anna")) - 65) < 0.1
        # Bereiche nur bei Freigabe
        assert set(by["Anna"]["extras"]) == {"records", "weather"} and by["Ben"]["extras"] == {}
        assert by["Anna"]["extras"]["records"]["longest_km"] == 40
        assert "prev" in year["rows"][0] and "prev" not in allp["rows"][0]

        # Freigabe später ändern
        assert c.put(f"/api/groups/{gid}/me", headers=b, json={"shared": ["rhythm", "load"]}).status_code == 200
        by = {r["display_name"]: r for r in c.get(f"/api/groups/{gid}/stats?period=all", headers=a).json()["rows"]}
        assert set(by["Ben"]["extras"]) == {"rhythm", "load"} and sum(by["Ben"]["extras"]["rhythm"]["weekdays"]) == 60


def test_group_helpers():
    from datetime import date

    from app.routers.groups import crossed_milestone, current_week_streak, improvement_pct, rides_per_week
    today = date(2026, 10, 28)  # Mittwoch
    days = {date(2026, 10, 26), date(2026, 10, 20), date(2026, 10, 13)}
    assert current_week_streak(days, today) == 3
    assert current_week_streak({date(2026, 10, 20), date(2026, 10, 13)}, today) == 2  # diese Woche noch keine Fahrt: zählt bis letzte Woche
    assert current_week_streak({date(2026, 10, 1)}, today) == 0
    assert improvement_pct(120, 100) == 20.0 and improvement_pct(10, 0) is None and improvement_pct(10, 3) is None
    assert crossed_milestone(950, 1020) == 1000 and crossed_milestone(1020, 1100) is None
    assert rides_per_week(4, date(2026, 10, 1), date(2026, 10, 28)) == 1.0 and rides_per_week(0, None, today) is None
    assert rides_per_week(3, date(2026, 10, 26), today) == 3.0  # unter einer Woche: als Woche gerechnet


def test_group_goal_duel_and_fair_rank():
    with TestClient(app) as c:
        a = _user(c, "gg1@example.com")
        b = _user(c, "gg2@example.com")
        _rides(_uid("gg1@example.com"), [60, 40])
        _rides(_uid("gg2@example.com"), [30])
        gid = c.post("/api/groups", headers=a, json={"name": "Ziele", "display_name": "Gerda"}).json()["id"]
        token = c.post(f"/api/groups/{gid}/invites", headers=a, json={"email": "gg2@example.com"}).json()["link"].rsplit("/", 1)[1]
        assert c.post("/api/groups/join", headers=b, json={"token": token, "display_name": "Gustav"}).status_code == 200
        uid_a, uid_b = _uid("gg1@example.com"), _uid("gg2@example.com")

        # Ziel: nur Admins setzen, alle sehen es
        today = datetime.utcnow().date()
        body = {"metric": "km", "target": 1000, "start": (today - timedelta(days=100)).isoformat(), "end": (today + timedelta(days=100)).isoformat(), "title": "Herbst"}
        assert c.put(f"/api/groups/{gid}/goal", headers=b, json=body).status_code == 404
        assert c.put(f"/api/groups/{gid}/goal", headers=a, json={**body, "metric": "bpm"}).status_code == 422
        assert c.put(f"/api/groups/{gid}/goal", headers=a, json={**body, "end": (today - timedelta(days=200)).isoformat()}).status_code == 422
        g = c.put(f"/api/groups/{gid}/goal", headers=a, json=body).json()["goal"]
        assert g["done"] == 130 and g["target"] == 1000 and g["title"] == "Herbst" and not g["finished"]
        assert [m["display_name"] for m in g["members"]] == ["Gerda", "Gustav"]
        assert c.get(f"/api/groups/{gid}/goal", headers=b).json()["goal"]["done"] == 130
        # Pausierte Mitglieder zählen nicht mit
        c.put(f"/api/groups/{gid}/me", headers=b, json={"share": False})
        assert c.get(f"/api/groups/{gid}/goal", headers=a).json()["goal"]["done"] == 100
        c.put(f"/api/groups/{gid}/me", headers=b, json={"share": True})
        assert c.delete(f"/api/groups/{gid}/goal", headers=b).status_code == 404
        assert c.delete(f"/api/groups/{gid}/goal", headers=a).status_code == 204
        assert c.get(f"/api/groups/{gid}/goal", headers=a).json() == {"goal": None}

        # Duell
        d = c.get(f"/api/groups/{gid}/duel?a={uid_a}&b={uid_b}", headers=a).json()
        assert d["a"]["display_name"] == "Gerda" and len(d["weeks"]) == 12 and sum(d["weeks_won"].values()) == 12
        assert c.get(f"/api/groups/{gid}/duel?a={uid_a}&b={uid_a}", headers=a).status_code == 422
        c.put(f"/api/groups/{gid}/me", headers=b, json={"share": False})
        assert c.get(f"/api/groups/{gid}/duel?a={uid_a}&b={uid_b}", headers=a).status_code == 409
        c.put(f"/api/groups/{gid}/me", headers=b, json={"share": True})

        # faire Wertung: Felder sind da, ohne Namen oder Strecken
        s = c.get(f"/api/groups/{gid}/stats?period=month", headers=a).json()
        row = s["rows"][0]
        assert {"rides_per_week", "improve_pct", "milestone"} <= set(row) and "improve_pct" in row["rank"]
