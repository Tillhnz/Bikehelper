import os
import tempfile
from datetime import date, datetime
from types import SimpleNamespace as NS

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/geo.db"
os.environ["WEATHER_ENABLED"] = "false"

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.geo import service as geo  # noqa: E402
from app.models import Activity, Place, PlaceVisit, User  # noqa: E402
from app.routers.places import build_places  # noqa: E402
from app.stats import tiles as T  # noqa: E402


def test_build_places_home_and_countries():
    places = {
        1: NS(id=1, name="Berlin", kind="city", state="Berlin", country="Deutschland", country_code="de", total_tiles=400),
        2: NS(id=2, name="Bernau", kind="town", state="Brandenburg", country="Deutschland", country_code="de", total_tiles=100),
        3: NS(id=3, name="Barnim", kind="county", state=None, country="Deutschland", country_code="de", total_tiles=900),
    }
    rows = [(NS(tiles=200, rides=10), places[1]), (NS(tiles=50, rides=30), places[2]), (NS(tiles=300, rides=40), places[3])]
    out = build_places(rows)
    assert out["home"]["name"] == "Bernau"  # Landkreise zählen nicht als Hauptstadt
    assert out["cities"][0]["name"] == "Barnim"
    de = out["countries"][0]
    assert de["code"] == "de" and de["tiles"] == 550 and de["total"] > 100_000 and de["places"] == 3
    assert [c for c in out["cities"] if c["name"] == "Berlin"][0]["percent"] == 50.0


def test_resolve_user_with_fake_reverse():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        u = User(email="geo@example.com", password_hash="x")
        db.add(u)
        db.flush()
        centre = (52.0, 13.05)
        tile = T.tile_of(*centre)
        tiles = {(tile[0] + dx, tile[1] + dy) for dx in range(-1, 2) for dy in range(-1, 2)}
        db.add(Activity(user_id=u.id, name="r", start_date=datetime(2026, 5, 1, 8), distance_km=40.0,
                        moving_time_s=5000, elevation_m=100.0, start_lat=centre[0], start_lng=centre[1],
                        tiles=T.encode(tiles)))
        db.commit()
        calls = []

        def fake(lat, lng):
            calls.append((lat, lng))
            return {"osm_type": "relation", "osm_id": 42, "name": "Testdorf",
                    "address": {"town": "Testdorf", "state": "Brandenburg", "country": "Deutschland", "country_code": "de"},
                    "geojson": {"type": "Polygon", "coordinates": [[[13.0, 51.97], [13.1, 51.97], [13.1, 52.03], [13.0, 52.03], [13.0, 51.97]]]}}

        res = geo.resolve_user(db, u.id, fake, max_requests=10, pause=0)
        assert res["unresolved"] == 0 and len(calls) == 1   # eine Anfrage deckt alle neun Kacheln ab
        visit = db.query(PlaceVisit).filter_by(user_id=u.id).one()
        assert visit.tiles == 9 and visit.rides == 1
        assert db.query(Place).one().total_tiles > 9
        # zweiter Lauf: kein Netzwerk nötig
        geo.resolve_user(db, u.id, lambda *_: (_ for _ in ()).throw(AssertionError("keine Anfrage erwartet")), 10, pause=0)
