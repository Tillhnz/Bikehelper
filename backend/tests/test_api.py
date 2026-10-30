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

        # Einstellungen für Nutzer gibt es nicht mehr: Der Schlüssel gehört dem Administrator
        assert c.put("/api/settings/map", headers=h, json={"carto_api_key": "abc123DEF-_456"}).status_code in (404, 405)


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


def _catalog_rules(c, h, comp):
    """Legt die Regeln aus dem Katalog an, so wie die Oberfläche beim Hinzufügen einer Komponente."""
    from app.catalog import CATALOG, chain_rules
    rules = chain_rules(None) if comp["category"] == "chain" else CATALOG[comp["category"]].rules
    for r in rules:
        c.post(f"/api/components/{comp['id']}/rules", headers=h, json={
            "label": r.label, "interval_km": r.interval_km, "interval_months": r.interval_months,
            "wet_factor": r.wet_factor, "hint": r.hint or None})


def test_brake_pad_inspection_result_adjusts_intervals():
    with TestClient(app) as c:
        h = _user(c, "pads@example.com")
        bike = c.post("/api/bikes", headers=h, json={"name": "Rad", "type": "road", "with_defaults": False}).json()
        uid = c.get("/api/me", headers=h).json()["id"]
        start = date.today() - timedelta(days=60)
        comp = c.post("/api/components", headers=h, json={
            "bike_id": bike["id"], "category": "brake_pads", "name": "Beläge", "installed_at": start.isoformat(),
        }).json()
        _catalog_rules(c, h, comp)
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


def test_visual_check_of_a_component_has_three_results():
    with TestClient(app) as c:
        h = _user(c, "visual@example.com")
        bike = c.post("/api/bikes", headers=h, json={"name": "Rad", "type": "road", "with_defaults": False}).json()
        uid = c.get("/api/me", headers=h).json()["id"]
        start = date.today() - timedelta(days=60)
        comp = c.post("/api/components", headers=h, json={
            "bike_id": bike["id"], "category": "chain", "name": "Kette", "installed_at": start.isoformat(),
        }).json()
        _catalog_rules(c, h, comp)
        with SessionLocal() as db:
            for i in range(3):
                db.add(Activity(user_id=uid, bike_id=bike["id"], name="x", distance_km=400.0,
                                start_date=datetime.combine(start + timedelta(days=i + 1), datetime.min.time())))
            db.commit()

        def wear():
            rs = c.get(f"/api/components/{comp['id']}/rules", headers=h).json()
            return next(r for r in rs if r["label"] == "Kette wechseln"), [r for r in rs if r["label"] != "Kette wechseln"]

        w0, others = wear()
        interval = w0["interval_km"]
        assert w0["assessment"] is None and round(w0["km_since"]) == 1200
        today = date.today().isoformat()

        assert c.post(f"/api/components/{comp['id']}/inspections", headers=h, json={"performed_at": today}).status_code == 422  # ohne Ergebnis
        # okay: das Intervall startet neu, das Teil gilt als geprüft
        good = c.post(f"/api/components/{comp['id']}/inspections", headers=h, json={"performed_at": today, "result": "good"}).json()
        w, others_good = wear()
        assert good["result"] == "good" and good["rule_id"] is None
        assert w["assessment"]["result"] == "good" and round(w["km_since"]) == 0 and w["progress"] < w0["progress"] and w["interval_km"] == interval
        assert all(round(r["km_since"]) == 1200 for r in others_good if "schmieren" in r["label"])  # Schmierregel läuft unabhängig weiter

        # im Auge behalten: Intervall startet neu und wird halbiert
        c.delete(f"/api/logs/{good['id']}", headers=h)
        c.post(f"/api/components/{comp['id']}/inspections", headers=h, json={"performed_at": today, "result": "watch"})
        w, _ = wear()
        assert w["assessment"]["result"] == "watch" and round(w["km_since"]) == 0 and w["interval_km"] == round(interval * 0.5)
        assert abs(w["assessment"]["km_left"] - w["interval_km"]) <= 1

        # austauschen: sofort fällig
        c.post(f"/api/components/{comp['id']}/inspections", headers=h, json={"performed_at": today, "result": "replace"})
        w, others_after = wear()
        assert w["status"] == "due" and w["assessment"]["result"] == "replace"
        assert all(r["assessment"] is None for r in others_after)  # Schmierregel bleibt unberührt

        # Nach dem Wechsel zählt die alte Sichtprüfung nicht mehr
        c.post(f"/api/rules/{w['id']}/done", headers=h, json={"performed_at": (date.today() + timedelta(days=1)).isoformat()})
        assert wear()[0]["assessment"] is None


def test_check_interval_marks_next_visual_check():
    with TestClient(app) as c:
        h = _user(c, "checkint@example.com")
        bike = c.post("/api/bikes", headers=h, json={"name": "Rad", "type": "road", "with_defaults": False}).json()
        uid = c.get("/api/me", headers=h).json()["id"]
        start = date.today() - timedelta(days=30)
        comp = c.post("/api/components", headers=h, json={
            "bike_id": bike["id"], "category": "chain", "name": "Kette", "installed_at": start.isoformat(),
        }).json()
        _catalog_rules(c, h, comp)
        with SessionLocal() as db:
            db.add(Activity(user_id=uid, bike_id=bike["id"], name="x", distance_km=400.0,
                            start_date=datetime.combine(start + timedelta(days=1), datetime.min.time())))
            db.commit()

        def rules():
            rs = c.get(f"/api/components/{comp['id']}/rules", headers=h).json()
            return next(r for r in rs if r["label"] == "Kette wechseln"), next(r for r in rs if "schmieren" in r["label"])

        wear, lube = rules()
        assert lube["check"] is None  # Schmieren hat keine Sichtprüfung
        assert wear["check"]["interval_km"] == 1000 and wear["check"]["km_left"] == 600 and not wear["check"]["due"]
        # Zustand prüfen setzt den Prüfzähler zurück
        c.post(f"/api/components/{comp['id']}/inspections", headers=h, json={"performed_at": date.today().isoformat(), "result": "good"})
        assert rules()[0]["check"]["km_left"] == 1000
        # eigenes Intervall, 0 schaltet ab
        r = c.put(f"/api/rules/{wear['id']}/check", headers=h, json={"check_interval_km": 300, "check_interval_months": None}).json()
        assert r["check"]["interval_km"] == 300
        r = c.put(f"/api/rules/{wear['id']}/check", headers=h, json={"check_interval_km": 0, "check_interval_months": 0}).json()
        assert r["check"] is None
        r = c.put(f"/api/rules/{wear['id']}/check", headers=h, json={}).json()
        assert r["check"]["interval_km"] == 1000


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


def test_logout_all_password_change_invites_and_account_deletion():
    from app import ratelimit
    ratelimit.reset()
    with TestClient(app) as c:
        h = _user(c, "sec-admin@example.com")
        # Passwortwechsel meldet alte Tokens ab
        assert c.put("/api/auth/password", headers=h, json={"current_password": "falsch", "new_password": "neuesPasswort1"}).status_code == 403
        assert c.get("/api/me", headers=h).status_code == 200  # falsches Passwort meldet nicht ab
        new = c.put("/api/auth/password", headers=h, json={"current_password": "geheim1234", "new_password": "neuesPasswort1"}).json()
        assert c.get("/api/me", headers=h).status_code == 401
        h2 = {"Authorization": f"Bearer {new['access_token']}"}
        assert c.get("/api/me", headers=h2).status_code == 200
        # Überall abmelden
        t2 = c.post("/api/auth/logout-all", headers=h2).json()
        assert c.get("/api/me", headers=h2).status_code == 401
        h3 = {"Authorization": f"Bearer {t2['access_token']}"}

        # Einladungen: nur Admin, nur einmal gültig
        other = _user(c, "sec-other@example.com")
        assert c.get("/api/admin/invites", headers=other).status_code == 403
        from sqlalchemy import select
        from app.models import User
        from app.security import create_token
        with SessionLocal() as db:  # Administrator ist der älteste Nutzer der Datenbank
            admin = {"Authorization": f"Bearer {create_token(db.scalar(select(User).order_by(User.id).limit(1)))}"}
        assert c.get("/api/me", headers=admin).json()["role"] == "admin"
        assert c.get("/api/me", headers=other).json()["role"] == "user"
        code = c.post("/api/admin/invites", headers=admin).json()["code"]
        from app.config import settings
        old = settings.allow_registration
        settings.allow_registration = False
        try:
            body = {"email": "sec-new@example.com", "password": "geheim1234"}
            assert c.post("/api/auth/register", json=body).status_code == 403
            assert c.post("/api/auth/register", json={**body, "invite": code}).status_code == 201
            assert c.post("/api/auth/register", json={"email": "sec-new2@example.com", "password": "geheim1234", "invite": code}).status_code == 403
        finally:
            settings.allow_registration = old

        # Konto löschen: Passwort nötig, danach sind die Daten weg
        bike = c.post("/api/bikes", headers=other, json={"name": "Weg", "type": "road"}).json()
        assert c.post("/api/me/delete", headers=other, json={"password": "falsch"}).status_code == 403
        assert c.post("/api/me/delete", headers=other, json={"password": "geheim1234"}).status_code == 204
        assert c.get("/api/me", headers=other).status_code == 401
        assert c.post("/api/auth/login", json={"email": "sec-other@example.com", "password": "geheim1234"}).status_code == 401
        assert bike["id"]


def test_login_is_throttled():
    from app import ratelimit
    ratelimit.reset()
    with TestClient(app) as c:
        _user(c, "throttle@example.com")
        for _ in range(ratelimit.LIMIT_PER_EMAIL):
            assert c.post("/api/auth/login", json={"email": "throttle@example.com", "password": "x" * 9}).status_code == 401
        assert c.post("/api/auth/login", json={"email": "throttle@example.com", "password": "geheim1234"}).status_code == 429
    ratelimit.reset()


def test_tire_catalog_import_search_and_tire_set_fields():
    with TestClient(app) as c:
        h = _user(c, "catalog@example.com")
        csv = (
            "brand;model;category;width_mm;tubeless;weight_g;watts;source_url\n"
            "Testmarke;Rennreifen A;road;28;tubeless;300;9,5;https://example.org/a\n"
            "Testmarke;Rennreifen A;road;30;tubeless;330;9,9;\n"
            "Testmarke;Kaputt;unbekannt;;;;;\n"
        )
        r = c.post("/api/tire-catalog/import", headers=h, json={"csv": csv}).json()
        assert r["added"] == 2 and r["error_count"] == 1
        # Erneut importieren aktualisiert statt zu verdoppeln
        assert c.post("/api/tire-catalog/import", headers=h, json={"csv": csv}).json()["updated"] == 2
        hits = c.get("/api/tire-catalog", headers=h, params={"q": "testmarke 28"}).json()["items"]
        assert len(hits) == 1 and hits[0]["watts"] == 9.5 and hits[0]["own"]
        # Nur für den eigenen Nutzer sichtbar
        other = _user(c, "catalog2@example.com")
        assert c.get("/api/tire-catalog", headers=other, params={"q": "testmarke"}).json()["items"] == []
        assert c.post("/api/tire-catalog/import", headers=h, json={"csv": "foo,bar\n1,2"}).status_code == 422

        bike = c.post("/api/bikes", headers=h, json={"name": "Rad", "type": "road", "with_defaults": False}).json()
        ts = c.post(f"/api/bikes/{bike['id']}/tire-sets", headers=h, json={
            "name": "Rennreifen A", "brand": "Testmarke", "width_mm": 28, "model_key": hits[0]["key"],
            "weight_g": 300, "watts": 9.5, "source_url": "https://example.org/a",
        }).json()
        assert ts["watts"] == 9.5 and ts["weight_g"] == 300 and ts["model_key"] == hits[0]["key"]
        assert c.post(f"/api/bikes/{bike['id']}/tire-sets", headers=h, json={"name": "x", "source_url": "javascript:alert(1)"}).status_code == 422
        assert c.delete("/api/tire-catalog/mine", headers=h).status_code == 204
        assert c.get("/api/tire-catalog", headers=h, params={"q": "testmarke"}).json()["items"] == []


def test_advisor_uses_casing_from_the_mounted_tire_set():
    with TestClient(app) as c:
        h = _user(c, "casing@example.com")
        bike = c.post("/api/bikes", headers=h, json={"name": "Rad", "type": "road", "with_defaults": False, "tire_width_mm": 28}).json()
        ts = c.post(f"/api/bikes/{bike['id']}/tire-sets", headers=h, json={
            "name": "Dünn", "width_mm": 28, "casing": "supple", "mount_from": date.today().isoformat(),
        }).json()
        assert ts["casing"] == "supple"
        defs = c.get("/api/advisor/defaults", headers=h).json()
        assert defs["bikes"][0]["tire_set"]["casing"] == "supple"
        assert c.post(f"/api/bikes/{bike['id']}/tire-sets", headers=h, json={"name": "x", "casing": "kaputt"}).status_code == 422


def test_tire_catalog_url_import_refuses_private_and_insecure_targets():
    with TestClient(app) as c:
        h = _user(c, "urlimport@example.com")
        for url in ("http://example.org/a.csv", "https://localhost/a.csv", "https://127.0.0.1/a.csv", "https://192.168.1.10/a.csv"):
            r = c.post("/api/tire-catalog/import-url", headers=h, json={"url": url})
            assert r.status_code == 422, url
        # Ohne Suchbegriff liefert der Katalog alle Größen (die Liste wird in der App nach Modell gruppiert)
        assert len(c.get("/api/tire-catalog", headers=h, params={"limit": 300}).json()["items"]) >= 40


def test_admin_user_list_and_removal_and_proxy_ip():
    with TestClient(app) as c:
        from sqlalchemy import select
        from app.models import User
        from app.security import create_token
        h = _user(c, "victim@example.com")
        with SessionLocal() as db:
            admin = {"Authorization": f"Bearer {create_token(db.scalar(select(User).order_by(User.id).limit(1)))}"}
            victim_id = db.scalar(select(User.id).where(User.email == "victim@example.com"))
        assert c.get("/api/admin/users", headers=h).status_code == 403
        users = c.get("/api/admin/users", headers=admin).json()
        assert users[0]["role"] == "admin" and any(u["email"] == "victim@example.com" for u in users)
        assert c.delete(f"/api/admin/users/{users[0]['id']}", headers=admin).status_code == 409  # sich selbst nicht
        assert c.delete(f"/api/admin/users/{victim_id}", headers=h).status_code == 403
        assert c.delete(f"/api/admin/users/{victim_id}", headers=admin).status_code == 204
        assert c.get("/api/me", headers=h).status_code == 401
        # Der Administrator kann sich nicht löschen, solange es andere Konten gibt
        assert c.post("/api/me/delete", headers=admin, json={"password": "irrelevant"}).status_code in (403, 409)


def test_roles_lock_settings_and_privacy():
    with TestClient(app) as c:
        from sqlalchemy import select
        from app.config import settings
        from app.models import User
        from app.security import create_token
        h = _user(c, "role-user@example.com")
        with SessionLocal() as db:
            admin = {"Authorization": f"Bearer {create_token(db.scalar(select(User).order_by(User.id).limit(1)))}"}
            uid = db.scalar(select(User.id).where(User.email == "role-user@example.com"))
        # Nutzer ohne Adminrechte kommen nicht an Einstellungen
        assert c.get("/api/admin/settings", headers=h).status_code == 403
        assert c.put("/api/admin/settings", headers=h, json={"values": {"smtp_host": "x"}}).status_code == 403
        # Die Kontenliste enthält keine persönlichen Inhalte
        row = next(u for u in c.get("/api/admin/users", headers=admin).json() if u["id"] == uid)
        assert set(row) == {"id", "email", "role", "active", "created_at", "is_me"}
        # Passwörter werden nie ausgegeben, null/leer-Semantik
        r = c.put("/api/admin/settings", headers=admin, json={"values": {"smtp_host": "smtp.test", "smtp_password": "topsecret"}})
        assert r.status_code == 200, r.text
        assert "topsecret" not in r.text and r.json()["fields"]["smtp_password"]["set"] is True
        assert settings.smtp_host == "smtp.test"
        assert c.put("/api/admin/settings", headers=admin, json={"values": {"smtp_port": 99999}}).status_code == 422
        assert c.put("/api/admin/settings", headers=admin, json={"values": {"smtp_host": "", "smtp_password": ""}}).status_code == 200
        assert c.get("/api/admin/settings", headers=admin).json()["fields"]["smtp_password"]["set"] is False
        # Rolle ändern, sperren, entsperren
        assert c.put(f"/api/admin/users/{uid}", headers=admin, json={"role": "admin"}).status_code == 200
        assert c.get("/api/admin/settings", headers=h).status_code == 200
        assert c.put(f"/api/admin/users/{uid}", headers=admin, json={"role": "user"}).status_code == 200
        assert c.put(f"/api/admin/users/{uid}", headers=admin, json={"active": False}).status_code == 200
        assert c.get("/api/me", headers=h).status_code == 401
        assert c.post("/api/auth/login", json={"email": "role-user@example.com", "password": "geheim1234"}).status_code == 403
        assert c.put(f"/api/admin/users/{uid}", headers=admin, json={"active": True}).status_code == 200
        assert c.post("/api/auth/login", json={"email": "role-user@example.com", "password": "geheim1234"}).status_code == 200


def test_update_endpoints_are_admin_only_and_report_missing_service():
    with TestClient(app) as c:
        from sqlalchemy import select
        from app.config import settings
        from app.models import User
        from app.security import create_token
        h = _user(c, "upd-user@example.com")
        with SessionLocal() as db:
            admin = {"Authorization": f"Bearer {create_token(db.scalar(select(User).order_by(User.id).limit(1)))}"}
        assert c.get("/api/admin/update", headers=h).status_code == 403
        assert c.post("/api/admin/update", headers=h).status_code == 403
        old = settings.updater_url
        settings.updater_url = ""
        try:
            r = c.get("/api/admin/update", headers=admin)
            assert r.status_code == 503 and "install.sh update" in r.json()["detail"]
            settings.updater_url = "http://127.0.0.1:9"  # nichts hört zu
            assert c.post("/api/admin/update", headers=admin).status_code == 503
        finally:
            settings.updater_url = old


def test_client_ip_uses_the_entry_added_by_the_trusted_proxy():
    from types import SimpleNamespace
    from app import ratelimit
    req = lambda xff: SimpleNamespace(headers={"x-forwarded-for": xff} if xff else {}, client=SimpleNamespace(host="172.18.0.5"))
    assert ratelimit.client_ip(req("6.6.6.6, 203.0.113.9, 172.18.0.2")) == "203.0.113.9"  # gefälschter Eintrag zählt nicht
    assert ratelimit.client_ip(req("")) == "172.18.0.5"


def _admin_headers():
    from sqlalchemy import select
    from app.models import User
    from app.security import create_token
    with SessionLocal() as db:
        return {"Authorization": f"Bearer {create_token(db.scalar(select(User).order_by(User.id).limit(1)))}"}


def test_audit_health_export_and_search():
    with TestClient(app) as c:
        h = _user(c, "ex-user@example.com")
        admin = _admin_headers()
        # Verwaltungsvorgänge landen im Protokoll, nur der Admin sieht es
        assert c.get("/api/admin/audit", headers=h).status_code == 403
        code = c.post("/api/admin/invites", headers=admin).json()["code"]
        entries = c.get("/api/admin/audit", headers=admin).json()
        assert any(e["action"] == "invite.create" and e["detail"] == code for e in entries)
        # Zustand: Update-Dienst ist im Test nicht da, der Rest meldet sich
        health = c.get("/api/admin/health", headers=admin).json()
        assert {k["key"] for k in health["checks"]} == {"db", "disk", "mail", "updater"}
        assert c.get("/api/admin/health", headers=h).status_code == 403
        # Export enthält eigene Daten, keine Zugangsdaten
        bike = c.post("/api/bikes", headers=h, json={"name": "Suchrad Zebra", "type": "road"}).json()
        r = c.get("/api/me/export", headers=h)
        assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
        data = r.json()
        assert [b["name"] for b in data["bikes"]] == ["Suchrad Zebra"] and data["account"]["email"] == "ex-user@example.com"
        assert "password_hash" not in r.text and "strava_client_secret" not in r.text
        # Suche findet nur eigene Daten
        found = c.get("/api/search", headers=h, params={"q": "zebra"}).json()
        assert [b["id"] for b in found["bikes"]] == [bike["id"]]
        assert c.get("/api/search", headers=admin, params={"q": "zebra"}).json()["bikes"] == []
        assert c.get("/api/search", headers=h, params={"q": "z"}).status_code == 422


def test_password_reset_flow(monkeypatch):
    from app import notify
    from app.config import settings
    sent = []
    monkeypatch.setattr(notify, "send_email", lambda to, title, body: sent.append((to, body)))
    with TestClient(app) as c:
        _user(c, "forgot@example.com")
        old = (settings.smtp_host, settings.smtp_from)
        settings.smtp_host, settings.smtp_from = "", ""
        try:
            assert c.post("/api/auth/forgot", json={"email": "forgot@example.com"}).status_code == 503
            assert c.get("/api/config").json()["password_reset"] is False
            settings.smtp_host, settings.smtp_from = "smtp.test", "bike@example.com"
            assert c.get("/api/config").json()["password_reset"] is True
            # Unbekannte Adressen bekommen dieselbe Antwort, aber keine Mail
            assert c.post("/api/auth/forgot", json={"email": "nobody@example.com"}).status_code == 202
            assert sent == []
            assert c.post("/api/auth/forgot", json={"email": "forgot@example.com"}).status_code == 202
        finally:
            settings.smtp_host, settings.smtp_from = old
        assert len(sent) == 1 and sent[0][0] == "forgot@example.com"
        token = sent[0][1].split("reset=")[1].split()[0]
        assert c.post("/api/auth/reset", json={"token": "x" * 40, "password": "neuesPasswort9"}).status_code == 400
        assert c.post("/api/auth/reset", json={"token": token, "password": "neuesPasswort9"}).status_code == 200
        assert c.post("/api/auth/reset", json={"token": token, "password": "nochmal12345"}).status_code == 400  # nur einmal
        assert c.post("/api/auth/login", json={"email": "forgot@example.com", "password": "neuesPasswort9"}).status_code == 200
        assert c.post("/api/auth/login", json={"email": "forgot@example.com", "password": "geheim1234"}).status_code == 401


def test_rides_day_filter():
    with TestClient(app) as c:
        h = _user(c, "day-user@example.com")
        from sqlalchemy import select
        from app.models import User
        with SessionLocal() as db:
            uid = db.scalar(select(User.id).where(User.email == "day-user@example.com"))
            for name, start in (("Morgens", datetime(2026, 5, 3, 7, 0)), ("Anderer Tag", datetime(2026, 5, 4, 12, 0))):
                db.add(Activity(user_id=uid, name=name, start_date=start, distance_km=10.0, moving_time_s=1800, elevation_m=0))
            db.commit()
        r = c.get("/api/activities", headers=h, params={"day": "2026-05-03"}).json()
        assert [a["name"] for a in r["items"]] == ["Morgens"]


def test_event_log_keeps_full_error_text_for_server_errors():
    from app.audit import scrub
    assert "a@b.de" not in scrub("Fehler für a@b.de von 10.1.2.3 [SQL: INSERT x] [parameters: ('geheim',)]")
    assert "geheim" not in scrub("Fehler [parameters: ('geheim',)]") and "<IP>" in scrub("von 10.1.2.3")

    def boom():
        raise RuntimeError("kaputt für test@example.com")

    app.add_api_route("/api/_boom", boom)
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            h = _user(c, "boom-user@example.com")
            assert c.get("/api/_boom", headers=h).status_code == 500
            rows = c.get("/api/admin/audit", headers=_admin_headers(), params={"limit": 50}).json()
            err = next(r for r in rows if r["action"] == "error")
            assert "Fehlercode 500" in err["error_text"] and "RuntimeError: kaputt" in err["error_text"] and "test@example.com" not in err["error_text"]
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/api/_boom"]


def test_event_log_records_logins_and_coarse_actions_without_content():
    with TestClient(app) as c:
        h = _user(c, "live-user@example.com")
        admin = _admin_headers()
        assert c.post("/api/auth/login", json={"email": "live-user@example.com", "password": "falsch-falsch"}).status_code == 401
        c.post("/api/bikes", headers=h, json={"name": "Geheimrad Quokka", "type": "road"})
        c.post("/api/inventory", headers=h, json={"category": "other", "name": "Geheimteil Okapi", "quantity": 1})
        rows = c.get("/api/admin/audit", headers=admin, params={"limit": 200}).json()
        mine = [r for r in rows if r["actor"] == "live-user@example.com"]
        actions = {r["action"] for r in mine}
        assert {"login", "login.fail", "act"} <= actions
        details = " ".join((r["detail"] or "") for r in mine)
        assert "Garage: neu oder ausgeführt" in details and "Lager: neu oder ausgeführt" in details
        # Keine Inhalte im Protokoll
        everything = str(rows)
        assert "Quokka" not in everything and "Okapi" not in everything
        # Live-Abfrage liefert nur Neueres
        newest = rows[0]["id"]
        assert c.get("/api/admin/audit", headers=admin, params={"after": newest}).json() == []
        c.delete(f"/api/inventory/{c.get('/api/inventory', headers=h).json()['items'][0]['id']}", headers=h)
        newer = c.get("/api/admin/audit", headers=admin, params={"after": newest}).json()
        assert any("Lager: gelöscht" in (r["detail"] or "") for r in newer)
