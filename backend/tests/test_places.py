from app.stats.places import bbox, contains, country_total_tiles, kind_and_name, percent, tile_area_km2, tiles_in
from app.stats.tiles import tile_bounds, tile_of

SQUARE = {"type": "Polygon", "coordinates": [[[13.0, 52.0], [13.1, 52.0], [13.1, 52.05], [13.0, 52.05], [13.0, 52.0]]]}
DONUT = {"type": "Polygon", "coordinates": [
    [[13.0, 52.0], [13.1, 52.0], [13.1, 52.05], [13.0, 52.05], [13.0, 52.0]],
    [[13.04, 52.02], [13.06, 52.02], [13.06, 52.03], [13.04, 52.03], [13.04, 52.02]],
]}


def test_contains_and_holes():
    assert contains(SQUARE, 52.02, 13.05)
    assert not contains(SQUARE, 52.1, 13.05)
    assert not contains(DONUT, 52.025, 13.05)
    assert contains(DONUT, 52.01, 13.02)


def test_multipolygon():
    multi = {"type": "MultiPolygon", "coordinates": [SQUARE["coordinates"], [[[14.0, 52.0], [14.1, 52.0], [14.1, 52.05], [14.0, 52.0]]]]}
    assert contains(multi, 52.02, 13.05)
    assert bbox(multi)[3] == 14.1


def test_tiles_in_square_match_area():
    t = tiles_in(SQUARE)
    area = 0.1 * 111.32 * 0.6157 * 0.05 * 111.2  # ca. 6,1 km x 5,6 km laut Gradnetz
    assert t and abs(len(t) * tile_area_km2(52.02) - area) / area < 0.25
    x, y = tile_of(52.02, 13.05)
    assert (x, y) in t
    s, w, n, e = tile_bounds(x, y)
    assert s < 52.02 < n and w < 13.05 < e


def test_country_estimate_and_helpers():
    assert 100_000 < country_total_tiles("DE") < 200_000
    assert country_total_tiles("xx") is None
    assert percent(50, 200) == 25.0 and percent(1, None) is None and percent(500, 200) == 100.0
    assert kind_and_name({"town": "Bernau", "county": "Barnim"}) == ("town", "Bernau")
    assert kind_and_name({}, "Irgendwo") == ("area", "Irgendwo")
