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
