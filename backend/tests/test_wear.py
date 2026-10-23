from app.wear import project


def test_projection_extends_with_rate():
    p = project(0.25, 1500, 2250, 0.5, 3000)
    assert round(p.projected_pct, 3) == 0.375
    assert round(p.km_left) == 750
    assert 0.74 < p.ratio < 0.76


def test_zero_measure_uses_floor_rate():
    p = project(0.0, 100, 600, 0.5, 3000)
    assert p.projected_pct > 0 and p.km_left is not None


def test_over_limit():
    p = project(0.6, 2000, 2000, 0.5, 3000)
    assert p.ratio > 1 and p.km_left == 0
