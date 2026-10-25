import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ.setdefault("WEATHER_ENABLED", "false")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402


def test_frame_policy_from_settings():
    with TestClient(app) as c:
        from app.models import User
        from app.security import create_token
        c.post("/api/auth/register", json={"email": "embed@example.com", "password": "geheim1234"})
        with SessionLocal() as db:
            admin = {"Authorization": f"Bearer {create_token(db.scalar(select(User).order_by(User.id).limit(1)))}"}
        assert "x-bh-frame-ancestors" not in c.get("/api/frame-policy").headers
        r = c.put("/api/admin/settings", headers=admin, json={"values": {"frame_ancestors": "https://HA.example.de/lovelace/0, http://192.168.1.20:8123"}})
        assert r.status_code == 200, r.text
        h = c.get("/api/frame-policy")
        assert h.status_code == 204 and h.headers["x-bh-frame-ancestors"] == "'self' https://ha.example.de http://192.168.1.20:8123"
        assert c.put("/api/admin/settings", headers=admin, json={"values": {"frame_ancestors": "https://x.de; script-src *"}}).status_code == 422
        c.put("/api/admin/settings", headers=admin, json={"values": {"frame_ancestors": ""}})
        assert "x-bh-frame-ancestors" not in c.get("/api/frame-policy").headers
