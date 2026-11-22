"""Welche Nässe auf welches Teil wirkt, und die Restreichweite als Spanne."""
import os
import tempfile
from datetime import date, datetime, timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["WEATHER_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Activity, Bike, Component, MaintenanceLog, MaintenanceRule, WashEvent  # noqa: E402
from app.services import rule_state, soaks  # noqa: E402


def _register(c, email):
    c.post("/api/auth/register", json={"email": email, "password": "geheim1234"})
    token = c.post("/api/auth/login", json={"email": email, "password": "geheim1234"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _setup(email, *, wet_minutes=0.0, stand_wet_km=0.0, washes=0):
    """Rad mit 1.000 km in zehn Fahrten, dazu wahlweise Regen, Standzeit im Nassen und Nass-Putzen."""
    with TestClient(app) as c:
        h = _register(c, email)
        bike = c.post("/api/bikes", headers=h, json={"name": "Testrad", "type": "road"}).json()
        with SessionLocal() as db:
            b = db.get(Bike, bike["id"])
            for i in range(10):
                db.add(Activity(user_id=b.user_id, bike_id=b.id, name=f"Fahrt {i}",
                                start_date=datetime.now() - timedelta(days=30 - i), distance_km=100,
                                moving_time_s=3600 * 4, wet_minutes=wet_minutes, stand_wet_km=stand_wet_km))
            for i in range(washes):
                db.add(WashEvent(user_id=b.user_id, bike_id=b.id, at=datetime.now() - timedelta(days=20 - i),
                                 chain_dried=False, wet_km=30.0))
            db.commit()
        return bike["id"]


def _state(bike_id, category, label, interval_km=1000.0, wet_factor=2.0, installed_days=60):
    with SessionLocal() as db:
        b = db.get(Bike, bike_id)
        comp = Component(user_id=b.user_id, bike_id=b.id, category=category, name=category,
                         installed_at=date.today() - timedelta(days=installed_days))
        comp.rules = [MaintenanceRule(label=label, interval_km=interval_km, wet_factor=wet_factor)]
        db.add(comp)
        db.commit()
        return rule_state(db, comp, comp.rules[0]), comp.id


def test_standing_and_washing_do_not_wear_brake_pads():
    """Ein nasses Rad, das herumsteht oder geputzt wird, altert den Antrieb, nicht die Bremsbeläge."""
    bike = _setup("soak@example.com", stand_wet_km=40.0, washes=5)
    chain, _ = _state(bike, "chain", "Kette wechseln")
    pads, _ = _state(bike, "pads_front", "Bremsbeläge vorn wechseln")
    assert chain["km_since"] == pads["km_since"] == 1000
    # Antrieb: 400 km Standnässe und 150 km Putzen kommen als Zuschlag dazu
    assert chain["effective_km"] > 1500 and chain["breakdown"]["stand"] > 0 and chain["breakdown"]["wash"] > 0
    # Bremsbeläge: kein Zuschlag, die Rechnung bleibt bei den gefahrenen Kilometern
    assert pads["effective_km"] == 1000 and pads["breakdown"]["stand"] == 0 and pads["breakdown"]["wash"] == 0
    assert pads["breakdown"]["soak"] is False and chain["breakdown"]["soak"] is True
    assert soaks(type("C", (), {"category": "chain"})) and not soaks(type("C", (), {"category": "pads_rear"}))


def test_riding_in_the_rain_still_counts_for_pads():
    """Bremsen im Regen nutzt die Beläge sehr wohl ab."""
    bike = _setup("rain@example.com", wet_minutes=120.0)      # 2 h von 4 h Fahrzeit im Regen
    pads, _ = _state(bike, "pads_front", "Bremsbeläge vorn wechseln")
    assert pads["km_since"] == 1000
    assert 1450 < pads["effective_km"] < 1550                  # halbe Strecke nass, Faktor 2
    assert pads["breakdown"]["ride_wet"] > 0


def test_remaining_km_is_a_range():
    """Trocken reicht das Teil weiter als bei Dauernässe, die Schätzung liegt dazwischen."""
    bike = _setup("left@example.com", wet_minutes=120.0)
    st, _ = _state(bike, "pads_front", "Bremsbeläge vorn wechseln", interval_km=3000.0)
    left = st["left"]
    rest_eff = 3000 - st["effective_km"]                       # wirksame km bis zum Intervall
    assert left["km_dry"] == round(rest_eff)                   # jeder weitere km zählt einfach
    assert left["km_wet"] == round(rest_eff / 2)               # jeder weitere km zählt doppelt
    assert left["km_wet"] < left["km"] < left["km_dry"]        # Mischung aus der bisherigen Strecke
    assert left["mix"] == round(st["effective_km"] / st["km_since"], 2)


def test_remaining_km_is_negative_when_overdue():
    bike = _setup("over@example.com")
    st, _ = _state(bike, "pads_front", "Bremsbeläge vorn wechseln", interval_km=800.0)
    assert st["status"] == "due" and st["left"]["km"] == -200


def test_check_does_not_claim_a_changed_interval():
    """Liegt die Schätzung schon über der Schwelle, ändert ein „im Auge behalten“ das Intervall nicht mehr."""
    bike = _setup("insp@example.com")
    with SessionLocal() as db:
        b = db.get(Bike, bike)
        comp = Component(user_id=b.user_id, bike_id=b.id, category="pads_front", name="Beläge",
                         installed_at=date.today() - timedelta(days=60))
        comp.rules = [
            MaintenanceRule(label="Belagstärke prüfen vorn", interval_km=500, wet_factor=2.0),
            MaintenanceRule(label="Bremsbeläge vorn wechseln", interval_km=800, wet_factor=2.0),
        ]
        db.add(comp)
        db.commit()
        check = next(r for r in comp.rules if r.label.startswith("Belagstärke"))
        wear = next(r for r in comp.rules if r.label.startswith("Bremsbeläge"))

        db.add(MaintenanceLog(component_id=comp.id, rule_id=check.id, performed_at=date.today(), result="watch"))
        db.commit()
        st = rule_state(db, comp, wear)
        a = st["assessment"]
        # 1.000 gefahrene km auf 800 km Intervall: die Prüfung bestätigt nur, sie verkürzt nichts
        assert a["result"] == "watch" and a["changed"] is False and a["interval_km"] == 800
        assert st["status"] == "due" and a["km_left"] == 0

        # Umgekehrt: früh geprüft und "im Auge behalten" verkürzt das Intervall wirklich
        db.query(MaintenanceLog).delete()
        wear.interval_km = 5000
        check.interval_km = 1000
        db.add(MaintenanceLog(component_id=comp.id, rule_id=check.id, performed_at=date.today(), result="watch"))
        db.commit()
        db.expire_all()
        a2 = rule_state(db, comp, wear)["assessment"]
        assert a2["changed"] is True and a2["interval_km"] < 5000
