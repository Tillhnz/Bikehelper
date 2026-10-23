from app.stats import tiles as T


def test_tile_of_known_point():
    x, y = T.tile_of(0.0, 0.0)
    assert (x, y) == (8192, 8192)


def test_bounds_contain_point():
    x, y = T.tile_of(53.55, 9.99)
    s, w, n, e = T.tile_bounds(x, y)
    assert s <= 53.55 <= n and w <= 9.99 <= e


def test_long_segment_is_filled():
    pts = [(53.50, 10.0), (53.50, 10.30)]  # ca. 20 km nach Osten, keine Zwischenpunkte
    tiles = T.tiles_for_points(pts)
    xs = sorted(x for x, _ in tiles)
    assert xs == list(range(xs[0], xs[-1] + 1)) and len(xs) > 10


def test_encode_roundtrip():
    s = {(1, 2), (30, 4)}
    assert T.decode(T.encode(s)) == s and T.decode(None) == set()


def test_max_square():
    block = {(x, y) for x in range(5, 8) for y in range(10, 13)}
    size, at = T.max_square(block | {(20, 20), (21, 20)})
    assert size == 3 and at == (5, 10)
    assert T.max_square(set()) == (0, None)


def test_max_cluster_diagonal_counts():
    assert T.max_cluster({(0, 0), (1, 1), (2, 2), (9, 9)}) == 3
