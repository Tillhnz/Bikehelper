import os
import tempfile
from datetime import date, datetime, timedelta, timezone

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["WEATHER_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app import habits, suggest  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Activity, Bike, User, WashEvent  # noqa: E402
from app.services import wear_between  # noqa: E402
from app.weather.core import Hour  # noqa: E402

HOME = (48.10, 11.50)
WORK = (48.15, 11.58)


def _register(c, email):
    c.post("/api/auth/register", json={"email": email, "password": "geheim1234"})
    token = c.post("/api/auth/login", json={"email": email, "password": "geheim1234"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _ride(user_id, bike_id, start, a, b, km=8.0, name="Fahrt"):
    return Activity(user_id=user_id, bike_id=bike_id, name=name, start_date=start, distance_km=km, moving_time_s=1800,
                    start_lat=a[0], start_lng=a[1], end_lat=b[0], end_lng=b[1])


def _commute_week(user_id, bike_id, days=(4, 5, 6)):
    out = []
    for d in days:
        day = datetime(2026, 5, d)
        out.append(_ride(user_id, bike_id, day.replace(hour=7, minute=30), HOME, WORK, name="Hin"))
        out.append(_ride(user_id, bike_id, day.replace(hour=16, minute=30), WORK, HOME, name="Zurück"))
    return out


def test_commute_needs_a_pattern_and_finds_pairs():
    with TestClient(app) as c:
        h = _register(c, "pendler@example.com")
        uid = c.get("/api/me", headers=h).json()["id"]
        with SessionLocal() as db:
            bike = Bike(user_id=uid, name="Stadtrad")
            db.add(bike)
            db.flush()
            db.add_all(_commute_week(uid, bike.id, days=(4, 5)))  # nur zwei Tage: noch kein Muster
            db.commit()
            rides = habits._load_rides(db, uid, timezone.utc)
            assert habits.commute_pairs(rides)[0] == []
            db.add_all(_commute_week(uid, bike.id, days=(6,)))
            db.commit()
            pairs, places = habits.commute_pairs(habits._load_rides(db, uid, timezone.utc))
            assert len(pairs) == 3 and len(places) == 1
            assert all((b.start - a.end).total_seconds() / 3600 > 8 for a, b in pairs)
            ov = habits.overview(db, db.get(User, uid))["places"]
            assert len(ov) == 1 and ov[0]["days"] == 3 and ov[0]["detected_on"] == "2026-05-06" and len(ov[0]["stands"]) == 3
            assert ov[0]["stands"][0]["from"] == "08:00" and ov[0]["stands"][0]["to"] == "16:30"


def test_standing_outdoors_adds_wet_km_only_if_configured():
    settings.weather_enabled = True
    try:
        series = {datetime(2026, 5, 3) + timedelta(hours=i): Hour(temp=10, precip=1.0, wind=5, wdir=0) for i in range(24 * 5)}
        with TestClient(app) as c:
            h = _register(c, "draussen@example.com")
            uid = c.get("/api/me", headers=h).json()["id"]
            with SessionLocal() as db:
                bike = Bike(user_id=uid, name="Pendlerrad")
                db.add(bike)
                db.flush()
                bike_id = bike.id
                db.add_all(_commute_week(uid, bike_id))
                db.commit()
                user = db.get(User, uid)
                res = habits.run_for_user(db, user, fetch=lambda client, w: series)
                assert res["commute_pairs"] == 3 and res["stands"] == 0  # Arbeitsplatz nicht als „im Freien“ eingestellt
                assert wear_between(db, bike_id, None, None, 2.0)[1] == 0.0
            assert c.put("/api/settings/workplace", headers=h, json={"storage": "outdoor"}).json()["storage"] == "outdoor"
            with SessionLocal() as db:
                res = habits.run_for_user(db, db.get(User, uid), fetch=lambda client, w: series)
                assert res["stands"] == 3
                km, wet, eff = wear_between(db, bike_id, None, None, 2.0)
                assert wet > 3 * 8 * habits.STAND_BASE_KM_PER_H and eff == km + wet  # Regen im Stand zählt, gefahrene km bleiben
            # Wechsel auf „trocken“ nimmt die Bewertung wieder zurück
            c.put("/api/settings/workplace", headers=h, json={"storage": "dry"})
            with SessionLocal() as db:
                assert wear_between(db, bike_id, None, None, 2.0)[1] == 0.0
    finally:
        settings.weather_enabled = False


def test_commute_rides_get_the_pendeln_tag_automatically():
    with TestClient(app) as c:
        h = _register(c, "tag-pendeln@example.com")
        uid = c.get("/api/me", headers=h).json()["id"]
        with SessionLocal() as db:
            bike = Bike(user_id=uid, name="R")
            db.add(bike)
            db.flush()
            db.add_all(_commute_week(uid, bike.id))
            db.commit()
            habits.run_for_user(db, db.get(User, uid))
        items = c.get("/api/activities?tag=Pendeln", headers=h).json()["items"]
        assert len(items) == 6 and all(t["auto"] for i in items for t in i["tags"])
        assert {i["pair"]["role"] for i in items} == {"out", "back"} and all(i["pair"]["hours"] == 8.5 for i in items)
        assert all(i["pair"]["from"] and i["pair"]["outdoor"] is False for i in items)  # Arbeitsplatz nicht als „im Freien“ gewählt


def test_manual_tags_are_learned_and_rejection_sticks():
    with TestClient(app) as c:
        h = _register(c, "lerner@example.com")
        uid = c.get("/api/me", headers=h).json()["id"]
        a, b = (48.20, 11.40), (48.22, 11.45)
        with SessionLocal() as db:
            rides = [_ride(uid, None, datetime(2026, 6, d, 18, 0), a, b, km=12.0) for d in (1, 2, 3, 4, 5)]
            db.add_all(rides)
            db.commit()
            ids = [r.id for r in rides]
        for aid in ids[:3]:
            assert c.post(f"/api/activities/{aid}/tags", headers=h, json={"tag": "Feierabendrunde"}).status_code == 200
        with SessionLocal() as db:
            habits.run_for_user(db, db.get(User, uid))
        tags = {i["id"]: i["tags"] for i in c.get("/api/activities", headers=h).json()["items"]}
        assert [t["auto"] for t in tags[ids[3]]] == [True] and [t["auto"] for t in tags[ids[0]]] == [False]
        # automatisches Tag entfernen: wird nicht erneut vergeben
        c.delete(f"/api/activities/{ids[3]}/tags/Feierabendrunde", headers=h)
        with SessionLocal() as db:
            habits.run_for_user(db, db.get(User, uid))
        tags = {i["id"]: i["tags"] for i in c.get("/api/activities", headers=h).json()["items"]}
        assert tags[ids[3]] == [] and len(tags[ids[4]]) == 1


def test_wash_counts_as_wet_wear_and_dried_chain_is_gentler():
    with TestClient(app) as c:
        h = _register(c, "putzer@example.com")
        bike = c.post("/api/bikes", headers=h, json={"name": "Gravel", "type": "gravel"}).json()
        r1 = c.post(f"/api/bikes/{bike['id']}/washes", headers=h, json={"chain_dried": True})
        r2 = c.post(f"/api/bikes/{bike['id']}/washes", headers=h, json={"chain_dried": False})
        assert r1.status_code == r2.status_code == 201 and r1.json()["wet_km"] < r2.json()["wet_km"]
        with SessionLocal() as db:
            km, wet, eff = wear_between(db, bike["id"], None, None, 2.0)
            assert km == 0 and wet == r1.json()["wet_km"] + r2.json()["wet_km"] and eff == wet
            assert wear_between(db, bike["id"], None, None, 1.0)[2] == 0  # ohne Nässe-Faktor kein Einfluss
        assert len(c.get(f"/api/bikes/{bike['id']}/washes", headers=h).json()) == 2
        assert c.delete(f"/api/washes/{r2.json()['id']}", headers=h).status_code == 204
        with SessionLocal() as db:
            assert db.query(WashEvent).filter_by(bike_id=bike["id"]).count() == 1
        assert c.post(f"/api/bikes/{bike['id']}/washes", headers=h, json={"day": (date.today() + timedelta(days=3)).isoformat()}).status_code == 422


def test_bike_is_assigned_automatically_but_not_against_your_choice():
    with TestClient(app) as c:
        h = _register(c, "auto@example.com")
        uid = c.get("/api/me", headers=h).json()["id"]
        bike = c.post("/api/bikes", headers=h, json={"name": "Einziges"}).json()
        with SessionLocal() as db:
            rides = [_ride(uid, None, datetime(2026, 6, d, 9), HOME, WORK) for d in (1, 2)]
            db.add_all(rides)
            db.commit()
            first, second = rides[0].id, rides[1].id
            assert suggest.auto_assign(db, uid) == 2
        a = {i["id"]: i for i in c.get("/api/activities", headers=h).json()["items"]}
        assert a[first]["bike_id"] == bike["id"] and a[first]["bike_auto"] is True and a[first]["bike_reason"]
        # bewusst ohne Rad gelassen: bleibt so
        c.put(f"/api/activities/{second}", headers=h, json={"bike_id": None})
        with SessionLocal() as db:
            db.get(Activity, second).bike_id = None  # (Zustand wie nach dem Leeren)
            db.commit()
            assert suggest.auto_assign(db, uid) == 0
        a = {i["id"]: i for i in c.get("/api/activities", headers=h).json()["items"]}
        assert a[second]["bike_id"] is None and a[first]["bike_auto"] is True
