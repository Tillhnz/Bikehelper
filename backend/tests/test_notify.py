from app.notify import format_message


def test_message_lists_due_first():
    items = [
        {"bike": "Gravel", "component": "Kette", "rule": "Kette wachsen", "status": "soon"},
        {"bike": "Gravel", "component": "Bremsbeläge", "rule": "Prüfen", "status": "due"},
    ]
    title, body = format_message(items)
    assert "1 Wartung fällig" in title
    assert body.splitlines()[0].startswith("Gravel: Bremsbeläge")
    assert "bald fällig" in body.splitlines()[1]


def test_message_only_soon():
    title, _ = format_message([{"bike": None, "component": "Kette", "rule": "x", "status": "soon"}])
    assert "bald fällig" in title
