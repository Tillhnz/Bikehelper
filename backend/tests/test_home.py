from datetime import date, datetime

from app.routers.home import build_home_week


def test_week_overview():
    today = date(2026, 10, 22)  # Donnerstag
    rows = [
        (datetime(2026, 10, 19, 8), 40.0, 5000, 300.0),   # Montag dieser Woche
        (datetime(2026, 10, 22, 8), 60.0, 7000, 500.0),   # heute
        (datetime(2026, 10, 12, 8), 30.0, 3000, 100.0),   # Montag der Vorwoche
        (datetime(2026, 10, 17, 8), 90.0, 9000, 100.0),   # Samstag der Vorwoche, nach dem Vergleichspunkt
    ]
    w = build_home_week(rows, today)
    assert w["totals"]["km"] == 100.0 and w["totals"]["rides"] == 2
    assert [d["km"] for d in w["days"]][:4] == [40.0, 0.0, 0.0, 60.0]
    assert w["days"][3]["today"] and w["days"][4]["future"]
    assert w["last_week_same_point_km"] == 30.0 and w["last_week_km"] == 120.0
    assert len(w["weeks"]) == 8
