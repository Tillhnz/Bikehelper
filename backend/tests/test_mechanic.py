import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["WEATHER_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _user(c, email):
    c.post("/api/auth/register", json={"email": email, "password": "geheim1234"})
    t = c.post("/api/auth/login", json={"email": email, "password": "geheim1234"}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


def test_shop_url_validation_and_copy_on_replace():
    with TestClient(app) as c:
        h = _user(c, "shop@example.com")
        bike = c.post("/api/bikes", headers=h, json={"name": "R", "type": "road"}).json()
        base = {"bike_id": bike["id"], "category": "chain", "name": "KMC"}
        assert c.post("/api/components", headers=h, json={**base, "shop_url": "javascript:alert(1)"}).status_code == 422
        assert c.post("/api/components", headers=h, json={**base, "shop_url": "https://shop.example/kmc x"}).status_code == 422
        comp = c.post("/api/components", headers=h, json={**base, "shop_url": " https://shop.example/kmc "}).json()
        assert comp["shop_url"] == "https://shop.example/kmc"
        r = c.post(f"/api/components/{comp['id']}/replace", headers=h, json={"performed_at": date.today().isoformat()}).json()
        new = [x for x in c.get(f"/api/components?bike_id={bike['id']}", headers=h).json() if x["id"] != comp["id"]]
        assert new and new[0]["shop_url"] == "https://shop.example/kmc", r


def test_mechanic_flow():
    with TestClient(app) as c:
        owner = _user(c, "owner@example.com")
        mech = _user(c, "mech@example.com")
        bike = c.post("/api/bikes", headers=owner, json={"name": "Partnerrad", "type": "road"}).json()
        comp = c.post("/api/components", headers=owner, json={"bike_id": bike["id"], "category": "chain", "name": "Kette"}).json()

        assert c.post("/api/mechanic/requests", headers=mech, json={"email": "mech@example.com"}).status_code == 400
        a = c.post("/api/mechanic/requests", headers=mech, json={"email": "owner@example.com"})
        b = c.post("/api/mechanic/requests", headers=mech, json={"email": "niemand@example.com"})
        assert a.status_code == b.status_code == 202 and a.json() == b.json()  # verrät nicht, ob es das Konto gibt

        # Offen: kein Zugriff, Besitzer sieht die Anfrage auf der Startseite
        assert c.get(f"/api/bikes/{bike['id']}", headers=mech).status_code == 404
        pending = c.get("/api/home", headers=owner).json()["mechanic_requests"]
        assert [p["email"] for p in pending] == ["mech@example.com"]
        # Nur der Besitzer kann bestätigen
        gid = pending[0]["id"]
        assert c.post(f"/api/mechanic/requests/{gid}/accept", headers=mech).status_code == 404
        assert c.post(f"/api/mechanic/requests/{gid}/accept", headers=owner).status_code == 200

        # Lesen und Schreiben auf dem Partnerrad
        got = c.get(f"/api/bikes/{bike['id']}", headers=mech).json()
        assert got["shared_from"] == "owner@example.com"
        assert c.put(f"/api/bikes/{bike['id']}", headers=mech, json={"name": "Umbenannt", "type": "road"}).status_code == 200
        new = c.post("/api/components", headers=mech, json={"bike_id": bike["id"], "category": "tire", "name": "Reifen"}).json()
        assert c.get(f"/api/components?bike_id={bike['id']}", headers=owner).json()  # gehört dem Besitzer
        assert any(x["id"] == new["id"] for x in c.get(f"/api/components?bike_id={bike['id']}", headers=owner).json())
        assert not any(x["id"] == new["id"] for x in c.get("/api/components", headers=mech).json())  # nicht im eigenen Bestand
        rule = c.post(f"/api/components/{comp['id']}/rules", headers=mech, json={"label": "Kette wechseln", "interval_km": 1000}).json()
        done = c.post(f"/api/rules/{rule['id']}/done", headers=mech, json={"performed_at": date.today().isoformat()})
        assert done.status_code == 201 and done.json()["performed_by"] == "mech@example.com"
        own_log = c.post(f"/api/components/{comp['id']}/logs", headers=owner, json={"performed_at": date.today().isoformat()}).json()
        assert own_log["performed_by"] is None
        assert c.post(f"/api/bikes/{bike['id']}/tire-sets", headers=mech, json={"name": "Satz", "width_mm": 28}).status_code == 201

        # Grenzen: Rad nicht löschbar, keine Fahrten/Lager des Partners
        assert c.delete(f"/api/bikes/{bike['id']}", headers=mech).status_code == 404
        groups = c.get("/api/mechanic/bikes", headers=mech).json()
        assert [g["owner"] for g in groups] == ["mech@example.com", "owner@example.com"]

        # Entzug
        gid = c.get("/api/mechanic/state", headers=owner).json()["access_given"][0]["id"]
        assert c.delete(f"/api/mechanic/grants/{gid}", headers=owner).status_code == 204
        assert c.get(f"/api/bikes/{bike['id']}", headers=mech).status_code == 404
        assert c.get(f"/api/components?bike_id={bike['id']}", headers=mech).status_code == 404


def test_decline_and_toggle():
    with TestClient(app) as c:
        owner = _user(c, "o2@example.com")
        mech = _user(c, "m2@example.com")
        c.post("/api/mechanic/requests", headers=mech, json={"email": "o2@example.com"})
        gid = c.get("/api/mechanic/state", headers=owner).json()["incoming"][0]["id"]
        assert c.post(f"/api/mechanic/requests/{gid}/decline", headers=owner).status_code == 200
        assert c.get("/api/mechanic/state", headers=owner).json()["incoming"] == []
        assert c.get("/api/me", headers=mech).json()["mechanic_enabled"] is False
        assert c.put("/api/mechanic/enabled", headers=mech, json={"enabled": True}).status_code == 200
        assert c.get("/api/me", headers=mech).json()["mechanic_enabled"] is True
