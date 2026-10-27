from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.importers.parsers import Point, power_curve
from app.main import app
from app.stats import deep as D
from app.stats.overview import Row

TZ = ZoneInfo("Europe/Berlin")


def _rows(n=30):
    out = []
    t = datetime(2026, 5, 1, 8)
    for i in range(n):
        t += timedelta(days=1 + i % 3)
        km = 30 + i
        out.append(Row(
            id=i + 1, name=f"Runde {i}", bike_id=1 + i % 2, start=t, km=km, time_s=int(km / (24 + i % 5) * 3600),
            elev_m=km * 7, temp_c=5 + i % 20, wind_kmh=5 + i % 30, wet_minutes=0 if i % 4 else 40,
            avg_power=150 + i, curve={"300": 300, "1200": 240, "3600": 210},
        ))
    return out


def test_power_curve_from_points():
    t0 = datetime(2026, 1, 1)
    pts = [Point(time=t0 + timedelta(seconds=i), pwr=200 if i < 600 else 100) for i in range(1800)]
    pc = power_curve(pts)
    assert pc["300"] == 200 and pc["1200"] == 150
    assert power_curve(pts[:5]) is None  # zu kurz


def test_pause_does_not_fake_power():
    t0 = datetime(2026, 1, 1)
    pts = [Point(time=t0 + timedelta(seconds=i), pwr=300) for i in range(60)]
    pts += [Point(time=t0 + timedelta(seconds=600 + i), pwr=300) for i in range(60)]
    pc = power_curve(pts)
    assert pc["60"] == 300 and "300" in pc and pc["300"] < 300  # die Pause zählt als 0 W


def test_ftp_is_95_percent_of_20_minutes():
    ftp, basis = D.estimate_ftp({1200: 260, 3600: 200})
    assert round(ftp) == 247 and "20" in basis
    ftp, _ = D.estimate_ftp({1200: 200, 3600: 195})
    assert round(ftp) == 195  # beste Stunde, wenn sie höher liegt als 95 % der 20 Minuten
    assert D.estimate_ftp({300: 400}) == (None, None)


def test_power_block_has_ftp_zones_and_form():
    rows = _rows()
    out = D.build_power(rows, TZ, date(2026, 7, 1), 80)
    assert out["has_curve"] and out["ftp"] == 228 and out["ftp_wkg"] == 2.85
    assert [z["name"][:2] for z in out["zones"]] == ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"]
    assert out["form"] and set(out["form"][0]) == {"date", "tss", "fitness", "fatigue", "form"}


def test_power_block_without_data():
    rows = [Row(id=1, name="x", bike_id=None, start=datetime(2026, 5, 1), km=20, time_s=3600, elev_m=100)]
    assert D.build_power(rows, TZ, date(2026, 7, 1), None)["has_curve"] is False


def test_profile_curve_for_old_rides():
    prof = {"d": [i * 0.5 for i in range(1, 301)], "s": [30] * 300, "p": [200] * 150 + [250] * 150}
    assert D.curve_from_profile({"profile": prof})["300"] == 250
    assert D.curve_from_profile({"profile": {}}) is None


def test_conditions_patterns_bikes():
    rows = _rows()
    c = D.build_conditions(rows)
    assert c["rides"] == 30 and c["temp"] and c["wet_dry"]["wet_rides"] >= 3
    p = D.build_patterns(rows, TZ, date(2026, 7, 1))
    assert len(p["weekday"]) == 7 and p["median_pause_days"] is not None
    b = D.build_bike_compare(rows, {1: "A", 2: "B"}, {1: 2})
    assert {x["name"] for x in b["bikes"]} == {"A", "B"} and abs(sum(x["share"] for x in b["bikes"]) - 100) < 0.3


def test_routes_group_similar_rides_only():
    rows = _rows(8)
    base = [(52.0 + 0.0005 * k, 13.0 + 0.0003 * k) for k in range(200)]
    other = [(52.3 + 0.0005 * k, 13.3 + 0.0003 * k) for k in range(200)]
    for r in rows:
        r.km, r.time_s = 20.0, 3000
    paths = {r.id: (base if r.id <= 5 else other) for r in rows}
    out = D.build_routes(rows, paths, TZ)
    assert [x["rides"] for x in out["routes"]] == [5, 3]  # die drei anderen liegen 30 km entfernt: eigene Runde, nicht vermischt


def test_forecast_uses_pace():
    st = {"status": "ok", "progress": 0.5, "interval_km_eff": 3000, "effective_km": 1500, "months_since": 1, "interval_months": None}
    it = D.forecast_item("Kette", "K", "Rad", st, 100, date(2026, 7, 1))
    assert it["days"] == 105 and it["basis"] == "Kilometer" and it["km_left"] == 1500
    assert D.forecast_item("x", "K", "Rad", {"status": "unknown", "progress": 0}, 100, date(2026, 7, 1)) is None


def test_endpoints_answer_for_new_account():
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "deep@example.com", "password": "geheim1234"})
        t = c.post("/api/auth/login", json={"email": "deep@example.com", "password": "geheim1234"}).json()["access_token"]
        h = {"Authorization": f"Bearer {t}"}
        for path in ("power", "conditions", "patterns", "bikes", "routes", "forecast"):
            r = c.get(f"/api/stats/{path}", headers=h)
            assert r.status_code == 200, (path, r.text)
        assert c.get("/api/stats/power", headers=h).json()["has_curve"] is False
