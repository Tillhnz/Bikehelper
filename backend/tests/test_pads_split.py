"""Bremsbeläge: vorn und hinten sind eigene Komponenten, die alte Sammelkomponente wird einmalig aufgeteilt."""
import os
import tempfile
from datetime import date, timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["WEATHER_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.catalog import CATALOG, INSPECTIONS, categories_for  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AppSetting, Bike, Component, MaintenanceLog, MaintenanceRule  # noqa: E402
from app.services import PADS_MIGRATION_KEY, migrate_split_pads  # noqa: E402


def _register(c, email):
    c.post("/api/auth/register", json={"email": email, "password": "geheim1234"})
    token = c.post("/api/auth/login", json={"email": email, "password": "geheim1234"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_new_bikes_get_both_pads():
    with TestClient(app) as c:
        h = _register(c, "pads1@example.com")
        bike = c.post("/api/bikes", headers=h, json={"name": "Orca", "type": "road", "with_defaults": True}).json()
        cats = {x["category"] for x in c.get(f"/api/components?bike_id={bike['id']}", headers=h).json()}
        assert {"pads_front", "pads_rear"} <= cats and "brake_pads" not in cats
        assert "brake_pads" not in categories_for("road")
        # vorn ist das kürzere Intervall hinterlegt
        assert CATALOG["pads_front"].rules[1].interval_km < CATALOG["pads_rear"].rules[1].interval_km
        # beide haben ihre eigene Prüfregel
        assert INSPECTIONS["Belagstärke prüfen vorn"] == "Bremsbeläge vorn wechseln"
        assert INSPECTIONS["Belagstärke prüfen hinten"] == "Bremsbeläge hinten wechseln"


def test_old_component_is_split_once():
    with TestClient(app) as c:
        h = _register(c, "pads2@example.com")
        bike = c.post("/api/bikes", headers=h, json={"name": "Altes Rad", "type": "road"}).json()
        changed = date.today() - timedelta(days=40)

        with SessionLocal() as db:
            b = db.get(Bike, bike["id"])
            comp = Component(user_id=b.user_id, bike_id=b.id, category="brake_pads", name="Bremsbeläge",
                             brand="SwissStop", start_km=120.0, installed_at=date.today() - timedelta(days=200))
            comp.rules = [
                MaintenanceRule(label="Belagstärke prüfen", interval_km=500, wet_factor=2.0),
                MaintenanceRule(label="Bremsbeläge wechseln", interval_km=1500, wet_factor=2.0),
                MaintenanceRule(label="Eigene Regel", interval_km=900),
            ]
            db.add(comp)
            db.flush()
            db.add(MaintenanceLog(component_id=comp.id, performed_at=changed, note="beide neu"))
            check_rule = next(r for r in comp.rules if r.label == "Belagstärke prüfen")
            db.add(MaintenanceLog(component_id=comp.id, rule_id=check_rule.id, performed_at=date.today(), result="good"))
            own = next(r for r in comp.rules if r.label == "Eigene Regel")
            db.add(MaintenanceLog(component_id=comp.id, rule_id=own.id, performed_at=date.today()))
            flag = db.get(AppSetting, PADS_MIGRATION_KEY)   # Merker aus dem Start der App zurücksetzen
            if flag is not None:
                db.delete(flag)
            db.commit()
            comp_id = comp.id

            assert migrate_split_pads(db) == 1

        with SessionLocal() as db:
            front = db.get(Component, comp_id)
            assert front.category == "pads_front" and front.name == "Bremsbeläge vorn"
            labels = sorted(r.label for r in front.rules)
            assert labels == ["Belagstärke prüfen vorn", "Bremsbeläge vorn wechseln", "Eigene Regel"]
            # unveränderter Standard wird auf das kürzere Intervall für vorn gesetzt
            assert next(r for r in front.rules if r.label == "Bremsbeläge vorn wechseln").interval_km == 1200

            rear = db.scalars(select_rear(bike["id"])).one()
            assert rear.name == "Bremsbeläge hinten" and rear.start_km == 120.0 and rear.brand == "SwissStop"
            assert rear.installed_at == front.installed_at
            assert sorted(r.label for r in rear.rules) == ["Belagstärke prüfen hinten", "Bremsbeläge hinten wechseln"]
            # Vorgeschichte übernommen: der gemeinsame Wechsel und das Prüfergebnis, nicht die eigene Regel
            assert sorted(lg.performed_at for lg in rear.logs) == sorted([changed, date.today()])
            assert all("übernommen" in (lg.note or "") for lg in rear.logs)
            check = next(lg for lg in rear.logs if lg.rule_id is not None)
            assert db.get(MaintenanceRule, check.rule_id).label == "Belagstärke prüfen hinten"
            assert check.result == "good"

        with SessionLocal() as db:
            assert migrate_split_pads(db) == 0          # Merker gesetzt: läuft kein zweites Mal
            assert len(db.scalars(select_rear(bike["id"])).all()) == 1


def select_rear(bike_id):
    from sqlalchemy import select
    return select(Component).where(Component.bike_id == bike_id, Component.category == "pads_rear")


def test_split_keeps_wear_separate():
    """Nach dem Aufteilen laufen vorn und hinten mit eigenen Intervallen und eigenem Stand."""
    with TestClient(app) as c:
        h = _register(c, "pads3@example.com")
        bike = c.post("/api/bikes", headers=h, json={"name": "Trennung", "type": "road", "with_defaults": True}).json()
        comps = {x["category"]: x for x in c.get(f"/api/components?bike_id={bike['id']}", headers=h).json()}
        front, rear = comps["pads_front"], comps["pads_rear"]
        fr = c.get(f"/api/components/{front['id']}/rules", headers=h).json()
        rr = c.get(f"/api/components/{rear['id']}/rules", headers=h).json()
        wechsel = lambda rules: next(r for r in rules if "wechseln" in r["label"])  # noqa: E731
        assert wechsel(fr)["interval_km"] == 1200 and wechsel(rr)["interval_km"] == 1800
        # Wechsel nur vorn eintragen: hinten bleibt unberührt
        c.post(f"/api/rules/{wechsel(fr)['id']}/done", headers=h, json={"performed_at": date.today().isoformat()})
        fr2 = c.get(f"/api/components/{front['id']}/rules", headers=h).json()
        rr2 = c.get(f"/api/components/{rear['id']}/rules", headers=h).json()
        assert wechsel(fr2)["last_done"] is not None
        assert wechsel(rr2)["last_done"] is None
