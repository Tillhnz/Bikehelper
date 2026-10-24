import os
import tempfile
from datetime import date, datetime, timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["WEATHER_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Activity  # noqa: E402


def test_full_flow():
    with TestClient(app) as c:
        # Registrierung + Login
        r = c.post("/api/auth/register", json={"email": "A@Example.com", "password": "geheim1234"})
        assert r.status_code == 201
        assert c.post("/api/auth/login", json={"email": "a@example.com", "password": "falsch"}).status_code == 401
        token = c.post("/api/auth/login", json={"email": "a@example.com", "password": "geheim1234"}).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        assert c.get("/api/me").status_code == 401
        me = c.get("/api/me", headers=h).json()
        assert me["strava_configured"] is False

        # Strava-Einstellungen
        me = c.put("/api/settings/strava", headers=h, json={"client_id": "123", "client_secret": "abc"}).json()
        assert me["strava_configured"] is True and me["strava_connected"] is False

        # Rad + Komponente + Regel
        bike = c.post("/api/bikes", headers=h, json={"name": "Canyon Endurace", "type": "road", "start_km": 1000}).json()
        installed = date.today() - timedelta(days=60)
        comp = c.post("/api/components", headers=h, json={
            "bike_id": bike["id"], "category": "chain", "name": "KMC X11",
            "installed_at": installed.isoformat(),
        }).json()
        rule = c.post(f"/api/components/{comp['id']}/rules", headers=h,
                      json={"label": "Kette wechseln", "interval_km": 1000}).json()
        assert rule["status"] == "ok"

        # Fahrten seit Einbau: 850 km => "soon" (>= 80 %)
        with SessionLocal() as db:
            for i in range(5):
                db.add(Activity(user_id=me["id"], bike_id=bike["id"], name=f"Ride {i}",
                                start_date=datetime.now() - timedelta(days=10 + i), distance_km=170))
            db.commit()

        rules = c.get(f"/api/components/{comp['id']}/rules", headers=h).json()
        assert rules[0]["km_since"] == 850 and rules[0]["status"] == "soon"
        assert c.get(f"/api/bikes/{bike['id']}", headers=h).json()["total_km"] == 1850

        # weitere 200 km => fällig
        with SessionLocal() as db:
            db.add(Activity(user_id=me["id"], bike_id=bike["id"], name="Long",
                            start_date=datetime.now() - timedelta(days=2), distance_km=200))
            db.commit()
        overview = c.get("/api/maintenance/overview", headers=h).json()
        assert overview["status"] == "due" and overview["items"][0]["rule"] == "Kette wechseln"

        # Wartung eintragen => Zähler startet neu
        c.post(f"/api/components/{comp['id']}/logs", headers=h,
               json={"performed_at": date.today().isoformat(), "note": "gewechselt"})
        assert c.get("/api/maintenance/overview", headers=h).json()["items"] == []

        # Fremde Nutzer sehen nichts
        t2 = c.post("/api/auth/register", json={"email": "b@example.com", "password": "geheim1234"}).json()["access_token"]
        h2 = {"Authorization": f"Bearer {t2}"}
        assert c.get("/api/bikes", headers=h2).json() == []
        assert c.get(f"/api/bikes/{bike['id']}", headers=h2).status_code == 404


def test_activity_detail_and_delete_all():
    import json

    with TestClient(app) as c:
        def login(mail):
            c.post("/api/auth/register", json={"email": mail, "password": "geheim1234"})
            t = c.post("/api/auth/login", json={"email": mail, "password": "geheim1234"}).json()["access_token"]
            return {"Authorization": f"Bearer {t}"}

        h1, h2 = login("detail1@example.com"), login("detail2@example.com")
        uid1 = c.get("/api/me", headers=h1).json()["id"]
        uid2 = c.get("/api/me", headers=h2).json()["id"]
        with SessionLocal() as db:
            a = Activity(user_id=uid1, name="Mit Details", start_date=datetime(2026, 5, 1, 8), distance_km=40.0,
                         moving_time_s=5400, elevation_m=300,
                         details=json.dumps({"max_speed": 55.5, "profile": {"d": [1.0, 2.0], "e": [10, 20]}}))
            b = Activity(user_id=uid1, name="Ohne Details", start_date=datetime(2026, 5, 2, 8), distance_km=10.0,
                         moving_time_s=1800, elevation_m=10)
            other = Activity(user_id=uid2, name="Fremd", start_date=datetime(2026, 5, 3, 8), distance_km=5.0,
                             moving_time_s=900, elevation_m=5)
            db.add_all([a, b, other])
            db.commit()
            ida, idb, ido = a.id, b.id, other.id

        d = c.get(f"/api/activities/{ida}", headers=h1).json()
        assert d["details"]["max_speed"] == 55.5 and d["avg_speed"] == 26.7
        assert c.get(f"/api/activities/{idb}", headers=h1).json()["details"] is None
        assert c.get(f"/api/activities/{ido}", headers=h1).status_code == 404
        assert c.get("/api/activities/gear", headers=h1).status_code == 200  # darf nicht als ID gelesen werden

        assert c.delete("/api/activities", headers=h1).status_code == 422
        r = c.delete("/api/activities?confirm=true", headers=h1)
        assert r.status_code == 200 and r.json() == {"deleted": 2}
        assert c.get(f"/api/activities/{ido}", headers=h2).status_code == 200  # fremde Fahrten bleiben


def test_map_settings():
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "map@example.com", "password": "geheim1234"})
        t = c.post("/api/auth/login", json={"email": "map@example.com", "password": "geheim1234"}).json()["access_token"]
        h = {"Authorization": f"Bearer {t}"}
        assert c.get("/api/map-config").status_code == 401
        assert c.get("/api/map-config", headers=h).json()["provider"] == "osm"

        bad = c.put("/api/settings/map", headers=h, json={"carto_api_key": "x?y=1&z"})
        assert bad.status_code == 422

        ok = c.put("/api/settings/map", headers=h, json={"carto_api_key": "abc123DEF-_456"}).json()
        assert ok["provider"] == "carto" and ok["has_user_key"] and ok["key_hint"] == "…_456"
        assert "abc123DEF" not in str(ok)  # Schlüssel nie zurückgeben
        cfg = c.get("/api/map-config", headers=h).json()
        assert cfg["dark"] and cfg["url"].endswith("?key=abc123DEF-_456")

        gone = c.put("/api/settings/map", headers=h, json={"carto_api_key": ""}).json()
        assert gone["provider"] == "osm" and not gone["has_user_key"]


def test_active_import_route_is_not_taken_for_a_job_id():
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "imp@example.com", "password": "geheim1234"})
        t = c.post("/api/auth/login", json={"email": "imp@example.com", "password": "geheim1234"}).json()["access_token"]
        h = {"Authorization": f"Bearer {t}"}
        assert c.get("/api/imports/active", headers=h).json() == {"job": None}
        assert c.get("/api/imports/unbekannt", headers=h).status_code == 404


def test_advisor_with_manual_weather_and_chain_lube():
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "adv@example.com", "password": "geheim1234"})
        t = c.post("/api/auth/login", json={"email": "adv@example.com", "password": "geheim1234"}).json()["access_token"]
        h = {"Authorization": f"Bearer {t}"}

        # ohne Gewicht und Reifenbreite keine Reifenempfehlung, Kleidung trotzdem
        body = {"start": "2026-10-25T09:00:00", "duration_min": 120, "manual": {"temp_c": 8, "wind_kmh": 10, "rain": "none"}}
        r = c.post("/api/advisor/plan", headers=h, json=body).json()
        assert r["tires"] is None and set(r["tires_missing"]) == {"Körpergewicht", "Reifenbreite"}
        assert r["clothing"]["headline"].startswith("Lang") and r["weather"]["source"] == "manual"

        assert c.put("/api/settings/profile", headers=h, json={"weight_kg": 75}).json()["weight_kg"] == 75
        assert c.get("/api/me", headers=h).json()["weight_kg"] == 75

        bike = c.post("/api/bikes", headers=h, json={
            "name": "Gravel", "type": "gravel", "tire_width_mm": 40, "rim_inner_mm": 25, "bike_weight_kg": 10,
        }).json()
        assert bike["chain_lube"] == "oil" and bike["tire_width_mm"] == 40
        defaults = c.get("/api/advisor/defaults", headers=h).json()
        assert defaults["weight_kg"] == 75 and defaults["bikes"][0]["tire_width_mm"] == 40

        dry = c.post("/api/advisor/plan", headers=h, json={**body, "bike_id": bike["id"]}).json()
        wet = c.post("/api/advisor/plan", headers=h, json={
            **body, "bike_id": bike["id"], "manual": {"temp_c": 8, "wind_kmh": 10, "rain": "heavy"}}).json()
        assert dry["tires"]["rear_bar"] > wet["tires"]["rear_bar"] and wet["tires"]["wetness"] == "wet"
        assert wet["clothing"]["groups"]["Regen & Wind"]

        # ohne Ort und ohne manuelles Wetter: klare Fehlermeldung
        assert c.post("/api/advisor/plan", headers=h, json={"start": "2026-10-25T09:00:00"}).status_code == 422

        # Kettenschmierung wechseln passt die Regeln an
        comps = c.get(f"/api/components?bike_id={bike['id']}", headers=h).json()
        chain = next(x for x in comps if x["category"] == "chain")
        before = {r["label"]: r for r in c.get(f"/api/components/{chain['id']}/rules", headers=h).json()}
        assert before["Kette wechseln"]["interval_km"] == 3000
        upd = {k: v for k, v in bike.items() if k not in ("id", "total_km", "component_count", "due_count", "unknown_count")}
        upd["chain_lube"] = "wax"
        assert c.put(f"/api/bikes/{bike['id']}", headers=h, json=upd).json()["chain_lube"] == "wax"
        after = {r["label"]: r for r in c.get(f"/api/components/{chain['id']}/rules", headers=h).json()}
        assert "Kette wachsen" in after and "Kette reinigen und schmieren" not in after
        assert after["Kette wechseln"]["interval_km"] == 5000
        assert after["Kette wechseln"]["id"] == before["Kette wechseln"]["id"]  # gleiche Regel, Wartungen bleiben erhalten

        # Die Wachsart wählt man beim Eintragen; sie bestimmt das Intervall
        wax = after["Kette wachsen"]
        assert {v["key"] for v in wax["variants"]} == {"hot_wax", "drip_wax"} and wax["interval_km"] == 500
        c.post(f"/api/rules/{wax['id']}/done", headers=h, json={"performed_at": date.today().isoformat(), "variant": "drip_wax"})
        wax = next(r for r in c.get(f"/api/components/{chain['id']}/rules", headers=h).json() if r["label"] == "Kette wachsen")
        assert wax["variant"] == "drip_wax" and wax["interval_km"] == 250


def _user(c, email):
    c.post("/api/auth/register", json={"email": email, "password": "geheim1234"})
    t = c.post("/api/auth/login", json={"email": email, "password": "geheim1234"}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


def test_maintenance_log_and_install_date_can_be_removed():
    with TestClient(app) as c:
        h = _user(c, "undo@example.com")
        bike = c.post("/api/bikes", headers=h, json={"name": "Rad", "type": "road", "with_defaults": False}).json()
        comp = c.post("/api/components", headers=h, json={
            "bike_id": bike["id"], "category": "chain", "name": "Kette", "installed_at": date.today().isoformat(),
        }).json()
        rule = c.post(f"/api/components/{comp['id']}/rules", headers=h, json={"label": "Wechseln", "interval_km": 1000}).json()
        done = c.post(f"/api/rules/{rule['id']}/done", headers=h, json={"performed_at": date.today().isoformat()}).json()
        logs = c.get(f"/api/components/{comp['id']}/logs", headers=h).json()
        assert logs[0]["id"] == done["id"] and logs[0]["rule_id"] == rule["id"]
        assert c.delete(f"/api/logs/{done['id']}", headers=h).status_code == 204
        assert c.get(f"/api/components/{comp['id']}/logs", headers=h).json() == []
        assert c.delete(f"/api/logs/{done['id']}", headers=h).status_code == 404

        # Einbaudatum entfernen: Status wird wieder "unknown"
        body = {k: v for k, v in comp.items() if k not in ("id", "km", "status")}
        body["installed_at"] = None
        upd = c.put(f"/api/components/{comp['id']}", headers=h, json=body).json()
        assert upd["installed_at"] is None and upd["status"] == "unknown"

        # fremde Nutzer kommen nicht an den Eintrag
        other = _user(c, "other-undo@example.com")
        done2 = c.post(f"/api/rules/{rule['id']}/done", headers=h, json={"performed_at": date.today().isoformat()}).json()
        assert c.delete(f"/api/logs/{done2['id']}", headers=other).status_code == 404


def test_tire_sets_mount_history_and_km():
    with TestClient(app) as c:
        h = _user(c, "tires@example.com")
        bike = c.post("/api/bikes", headers=h, json={"name": "Renner", "type": "road", "with_defaults": False}).json()
        bid = bike["id"]
        today = date.today()
        d = lambda n: (today - timedelta(days=n)).isoformat()  # noqa: E731

        with SessionLocal() as db:
            uid = db.execute(__import__("sqlalchemy").text("select id from users where email='tires@example.com'")).scalar()
            for days_ago, km in ((50, 100.0), (30, 60.0), (5, 40.0)):
                db.add(Activity(user_id=uid, bike_id=bid, name="Fahrt", start_date=datetime.combine(today - timedelta(days=days_ago), datetime.min.time()) + timedelta(hours=9), distance_km=km))
            db.commit()

        a = c.post(f"/api/bikes/{bid}/tire-sets", headers=h, json={
            "name": "GP5000 28", "width_mm": 28, "tubeless": True, "start_km": 500, "mount_from": d(60),
        }).json()
        b = c.post(f"/api/bikes/{bid}/tire-sets", headers=h, json={"name": "Winterreifen 32", "width_mm": 32, "tubeless": False}).json()
        assert a["mounted"] and not b["mounted"] and a["km"] == 500 + 100 + 60 + 40

        # Montieren schließt den bisherigen Satz am Vortag; Fahrten davor bleiben beim alten Satz
        b = c.post(f"/api/tire-sets/{b['id']}/mount", headers=h, json={"day": d(10)}).json()
        assert b["mounted"] and b["km"] == 40.0
        sets = {s["name"]: s for s in c.get(f"/api/bikes/{bid}/tire-sets", headers=h).json()}
        assert not sets["GP5000 28"]["mounted"] and sets["GP5000 28"]["km"] == 500 + 100 + 60
        mounted = c.get(f"/api/bikes/{bid}", headers=h).json()
        assert mounted["tire_set"]["name"] == "Winterreifen 32" and mounted["tire_width_mm"] == 32 and mounted["tubeless"] is False

        # Überschneidung wird abgelehnt, Korrektur des Zeitraums rechnet neu
        old_mount = sets["GP5000 28"]["mounts"][0]
        r = c.put(f"/api/tire-mounts/{old_mount['id']}", headers=h, json={"from_date": d(60), "to_date": d(3)})
        assert r.status_code == 409
        r = c.put(f"/api/tire-mounts/{old_mount['id']}", headers=h, json={"from_date": d(60), "to_date": d(20)})
        assert r.status_code == 200 and r.json()["km"] == 500 + 100 + 60

        # ausmustern nimmt den Satz vom Rad
        upd = {k: v for k, v in b.items() if k in ("name", "brand", "width_mm", "tubeless", "start_km", "max_km", "notes")}
        r = c.put(f"/api/tire-sets/{b['id']}", headers=h, json={**upd, "retired": True}).json()
        assert not r["mounted"] and c.get(f"/api/bikes/{bid}", headers=h).json()["tire_set"] is None

        # fremde Nutzer sehen nichts
        other = _user(c, "other-tires@example.com")
        assert c.get(f"/api/bikes/{bid}/tire-sets", headers=other).status_code == 404
        assert c.post(f"/api/tire-sets/{a['id']}/mount", headers=other, json={"day": d(0)}).status_code == 404


def test_maintenance_time_of_day_decides_which_rides_count():
    with TestClient(app) as c:
        h = _user(c, "clock@example.com")
        bike = c.post("/api/bikes", headers=h, json={"name": "Rad", "type": "road", "with_defaults": False}).json()
        comp = c.post("/api/components", headers=h, json={
            "bike_id": bike["id"], "category": "chain", "name": "Kette",
            "installed_at": (date.today() - timedelta(days=5)).isoformat(),
        }).json()
        rule = c.post(f"/api/components/{comp['id']}/rules", headers=h, json={"label": "Wachsen", "interval_km": 500}).json()
        with SessionLocal() as db:
            uid = db.execute(__import__("sqlalchemy").text("select id from users where email='clock@example.com'")).scalar()
            noon = datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=10)  # 10:00 UTC, also 11:00 oder 12:00 Ortszeit
            db.add(Activity(user_id=uid, bike_id=bike["id"], name="Tour", start_date=noon, distance_km=80))
            db.commit()

        def km_since():
            return next(r for r in c.get(f"/api/components/{comp['id']}/rules", headers=h).json())["km_since"]

        assert km_since() == 80
        today = date.today().isoformat()
        # Abends gewachst: die Tour vom Vormittag zählt nicht mehr
        evening = c.post(f"/api/rules/{rule['id']}/done", headers=h, json={"performed_at": today, "performed_time": "23:30:00"}).json()
        assert evening["performed_time"] == "23:30:00" and km_since() == 0
        c.delete(f"/api/logs/{evening['id']}", headers=h)
        # Früh am Morgen gewachst: die Tour kam danach und zählt
        c.post(f"/api/rules/{rule['id']}/done", headers=h, json={"performed_at": today, "performed_time": "06:00:00"})
        assert km_since() == 80


def test_chain_measurement_drives_the_wear_rule():
    with TestClient(app) as c:
        h = _user(c, "chain@example.com")
        bike = c.post("/api/bikes", headers=h, json={"name": "Rad", "type": "road", "with_defaults": False}).json()
        uid = c.get("/api/me", headers=h).json()["id"]
        start = date.today() - timedelta(days=30)
        comp = c.post("/api/components", headers=h, json={
            "bike_id": bike["id"], "category": "chain", "name": "Kette", "installed_at": start.isoformat(),
        }).json()
        rule = c.post(f"/api/components/{comp['id']}/rules", headers=h, json={"label": "Kette wechseln", "interval_km": 3000}).json()
        with SessionLocal() as db:
            for i in range(3):
                db.add(Activity(user_id=uid, bike_id=bike["id"], name="x", distance_km=500.0,
                                start_date=datetime.combine(start + timedelta(days=i + 1), datetime.min.time())))
            db.commit()
        before = [r for r in c.get(f"/api/components/{comp['id']}/rules", headers=h).json() if r["id"] == rule["id"]][0]
        assert before["measure"] is None

        m = c.post(f"/api/components/{comp['id']}/measurements", headers=h,
                   json={"measured_at": date.today().isoformat(), "wear_pct": 0.45, "limit_pct": 0.5}).json()
        assert m[0]["wear_pct"] == 0.45 and m[0]["km"] == 1500.0
        after = [r for r in c.get(f"/api/components/{comp['id']}/rules", headers=h).json() if r["id"] == rule["id"]][0]
        assert after["measure"]["limit_pct"] == 0.5
        assert after["progress"] >= 0.89  # 0,45 von 0,5 %: bald fällig, obwohl erst 1500 von 3000 km

        # Messung löschen: zurück zur Kilometerschätzung
        c.delete(f"/api/measurements/{m[0]['id']}", headers=h)
        back = [r for r in c.get(f"/api/components/{comp['id']}/rules", headers=h).json() if r["id"] == rule["id"]][0]
        assert back["measure"] is None and back["progress"] < 0.6

        other = _user(c, "chain-other@example.com")
        assert c.post(f"/api/components/{comp['id']}/measurements", headers=other,
                      json={"measured_at": date.today().isoformat(), "wear_pct": 0.1}).status_code == 404


def test_brake_pad_inspection_result_adjusts_intervals():
    with TestClient(app) as c:
        h = _user(c, "pads@example.com")
        bike = c.post("/api/bikes", headers=h, json={"name": "Rad", "type": "road", "with_defaults": False}).json()
        uid = c.get("/api/me", headers=h).json()["id"]
        start = date.today() - timedelta(days=60)
        comp = c.post("/api/components", headers=h, json={
            "bike_id": bike["id"], "category": "brake_pads", "name": "Beläge", "installed_at": start.isoformat(),
        }).json()
        with SessionLocal() as db:
            for i in range(3):
                db.add(Activity(user_id=uid, bike_id=bike["id"], name="x", distance_km=400.0,
                                start_date=datetime.combine(start + timedelta(days=i + 1), datetime.min.time())))
            db.commit()

        def rules():
            rs = c.get(f"/api/components/{comp['id']}/rules", headers=h).json()
            return next(r for r in rs if r["label"] == "Belagstärke prüfen"), next(r for r in rs if r["label"] == "Bremsbeläge wechseln")

        check, wear = rules()
        assert check["is_inspection"] and not wear["is_inspection"] and wear["assessment"] is None
        base = wear["progress"]  # 1200 von 1500 km: bald fällig
        assert base >= 0.8

        today = date.today().isoformat()
        good = c.post(f"/api/rules/{check['id']}/done", headers=h, json={"performed_at": today, "result": "good"}).json()
        assert good["result"] == "good"
        check, wear = rules()
        assert wear["assessment"]["result"] == "good" and wear["progress"] <= 0.55 and wear["status"] == "ok"
        assert wear["interval_km"] > 1500  # Intervall verlängert

        c.delete(f"/api/logs/{good['id']}", headers=h)
        c.post(f"/api/rules/{check['id']}/done", headers=h, json={"performed_at": today, "result": "watch"})
        check, wear = rules()
        assert wear["progress"] >= 0.8 and check["interval_km"] == 200  # 500 km * 0,4

        c.post(f"/api/rules/{check['id']}/done", headers=h, json={"performed_at": today, "result": "replace"})
        assert rules()[1]["status"] == "due"

        # Nach dem Wechsel zählt das alte Ergebnis nicht mehr
        c.post(f"/api/rules/{wear['id']}/done", headers=h, json={"performed_at": (date.today() + timedelta(days=1)).isoformat()})
        check, wear = rules()
        assert wear["assessment"] is None and check["assessment"] is None


def test_notification_settings_roundtrip():
    with TestClient(app) as c:
        h = _user(c, "notify@example.com")
        assert c.get("/api/settings/notifications", headers=h).json()["ntfy_topic"] == ""
        r = c.put("/api/settings/notifications", headers=h, json={"email": False, "ntfy_topic": "bikehelper-abc123"}).json()
        assert r["ntfy_topic"] == "bikehelper-abc123"
        assert c.put("/api/settings/notifications", headers=h, json={"email": False, "ntfy_topic": "zu kurz!"}).status_code == 422
        assert c.post("/api/settings/notifications/test", headers=_user(c, "n2@example.com")).status_code == 422


def test_goals_and_extra_stats_endpoints():
    with TestClient(app) as c:
        h = _user(c, "goals@example.com")
        uid = c.get("/api/me", headers=h).json()["id"]
        with SessionLocal() as db:
            for i in range(3):
                db.add(Activity(user_id=uid, name=f"r{i}", distance_km=50.0, moving_time_s=7200, elevation_m=400.0,
                                start_date=datetime(date.today().year, 1, 5 + i, 9)))
            db.commit()
        year = date.today().year
        g = c.put("/api/stats/goals", headers=h, json={"year": year, "targets": {"km": 1000, "rides": 2}}).json()
        assert {p["metric"] for p in g["progress"]} == {"km", "rides"}
        assert [p for p in g["progress"] if p["metric"] == "rides"][0]["reached_on"] is not None
        assert c.put("/api/stats/goals", headers=h, json={"year": year, "targets": {"foo": 1}}).status_code == 422
        g = c.put("/api/stats/goals", headers=h, json={"year": year, "targets": {"km": None}}).json()
        assert "km" not in g["targets"]
        ex = c.get("/api/stats/extra", headers=h).json()
        assert ex["totals"]["rides"] == 3 and len(ex["load"]["weekly"]) == 26
        rv = c.get(f"/api/stats/review?year={year}", headers=h).json()
        assert rv["totals"]["km"] == 150.0 and rv["years_available"] == [year]


def test_inventory_install_replaces_part_and_counts_down():
    with TestClient(app) as c:
        h = _user(c, "inv@example.com")
        bike = c.post("/api/bikes", headers=h, json={"name": "Gravel", "type": "gravel", "with_defaults": True}).json()
        old = [x for x in c.get(f"/api/components?bike_id={bike['id']}", headers=h).json() if x["category"] == "chain"]
        assert len(old) == 1 and old[0]["retired_at"] is None
        item = c.post("/api/inventory", headers=h, json={"category": "chain", "name": "KMC X11", "quantity": 2, "min_quantity": 2, "price_eur": 30}).json()
        assert item["low"] is False
        r = c.post(f"/api/inventory/{item['id']}/install", headers=h, json={"bike_id": bike["id"], "installed_at": date.today().isoformat()}).json()
        assert r["replaced"] == old[0]["name"] and r["item"]["quantity"] == 1 and r["item"]["low"] is True
        comps = c.get(f"/api/components?bike_id={bike['id']}", headers=h).json()
        chains = [x for x in comps if x["category"] == "chain"]
        assert sum(1 for x in chains if x["retired_at"] is None) == 1
        rules = c.get(f"/api/components/{r['component_id']}/rules", headers=h).json()
        assert any(x["label"] == "Kette wechseln" and x["guides"] for x in rules)
        inv = c.get("/api/inventory", headers=h).json()
        assert inv["totals"]["value_eur"] == 30.0 and inv["totals"]["low"] == 1
        # nicht vorhandenes Lager und fremdes Rad
        c.post(f"/api/inventory/{item['id']}/install", headers=h, json={"bike_id": bike["id"], "installed_at": date.today().isoformat()})
        assert c.post(f"/api/inventory/{item['id']}/install", headers=h, json={"bike_id": bike["id"], "installed_at": date.today().isoformat()}).status_code == 409
        other = _user(c, "inv2@example.com")
        assert c.delete(f"/api/inventory/{item['id']}", headers=other).status_code == 404


def test_bike_purchase_date_is_install_date_fallback():
    with TestClient(app) as c:
        h = _user(c, "buy@example.com")
        uid = c.get("/api/me", headers=h).json()["id"]
        bought = date.today() - timedelta(days=40)
        bike = c.post("/api/bikes", headers=h, json={"name": "Neu", "type": "road", "with_defaults": False,
                                                    "purchased_at": bought.isoformat()}).json()
        assert bike["purchased_at"] == bought.isoformat()
        comp = c.post("/api/components", headers=h, json={"bike_id": bike["id"], "category": "chain", "name": "Kette"}).json()
        assert comp["installed_at"] is None and comp["installed_inherited"] is True
        assert comp["installed_effective"] == bought.isoformat()
        rule = c.post(f"/api/components/{comp['id']}/rules", headers=h, json={"label": "Wechseln", "interval_km": 1000}).json()
        with SessionLocal() as db:
            db.add(Activity(user_id=uid, bike_id=bike["id"], name="alt", distance_km=100.0,
                            start_date=datetime.combine(bought - timedelta(days=5), datetime.min.time())))
            db.add(Activity(user_id=uid, bike_id=bike["id"], name="neu", distance_km=60.0,
                            start_date=datetime.combine(bought + timedelta(days=3), datetime.min.time())))
            db.commit()
        state = [r for r in c.get(f"/api/components/{comp['id']}/rules", headers=h).json() if r["id"] == rule["id"]][0]
        assert state["km_since"] == 60.0 and state["status"] != "unknown"  # Fahrten vor dem Kauf zählen nicht
        # eigenes Einbaudatum hat Vorrang
        own = date.today() - timedelta(days=1)
        body = {k: v for k, v in comp.items() if k not in ("id", "km", "status", "installed_effective", "installed_inherited")}
        body["installed_at"] = own.isoformat()
        upd = c.put(f"/api/components/{comp['id']}", headers=h, json=body).json()
        assert upd["installed_effective"] == own.isoformat() and upd["installed_inherited"] is False


def test_heatmap_has_days_for_time_lapse_and_tires_are_no_default_components():
    with TestClient(app) as c:
        h = _user(c, "time@example.com")
        uid = c.get("/api/me", headers=h).json()["id"]
        bike = c.post("/api/bikes", headers=h, json={"name": "Rad", "type": "gravel", "with_defaults": True}).json()
        cats = {x["category"] for x in c.get(f"/api/components?bike_id={bike['id']}", headers=h).json()}
        assert "chain" in cats and "tire_front" not in cats and "tire_rear" not in cats
        assert "tire_front" not in c.get("/api/catalog", headers=h).json()["components"]
        with SessionLocal() as db:
            for i, day in enumerate((datetime(2025, 5, 3, 9), datetime(2025, 6, 7, 9))):
                db.add(Activity(user_id=uid, bike_id=bike["id"], name=f"t{i}", distance_km=30.0 + i,
                                start_date=day, polyline="_p~iF~ps|U_ulLnnqC_mqNvxq`@"))
            db.commit()
        d = c.get("/api/stats/heatmap", headers=h).json()
        assert len(d["lines"]) == len(d["days"]) == len(d["km"]) == 2
        assert d["days"][0] != d["days"][1] and all(len(t) == 3 for t in d["tiles"])
