import io
import os
import tempfile

os.environ["VENUE_DATABASE_URL"] = "sqlite://"
os.environ["VENUE_MEDIA_DIR"] = tempfile.mkdtemp()

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.main import app  # noqa: E402


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), (230, 230, 220)).save(buf, "PNG")
    return buf.getvalue()


def test_full_flow():
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"org_name": "Org", "email": "a@b.co", "password": "password1"}).json()
        h = {"Authorization": "Bearer " + tok["access_token"]}
        types = {t["name"]: t for t in c.get("/api/place-types", headers=h).json()}
        assert "Станция / стенд" in types

        v = c.post("/api/venues", json={"name": "ТЦ"}, headers=h).json()
        fl = c.post(f"/api/venues/{v['id']}/floors", json={"level": 1, "name": "1 этаж"}, headers=h).json()
        r = c.post(f"/api/floors/{fl['id']}/base", files={"file": ("p.png", png(), "image/png")}, headers=h)
        assert r.status_code == 200 and r.json()["base_url"].endswith(".webp")
        r = c.post(f"/api/floors/{fl['id']}/base/align",
                   json={"corners": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]}, headers=h)
        assert r.status_code == 200 and r.json()["base_w"] == 320
        assert c.get(r.json()["base_url"]).status_code == 200

        st = types["Станция / стенд"]
        poly = {"type": "polygon", "points": [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3]]}
        bad = c.post(f"/api/floors/{fl['id']}/places", headers=h,
                     json={"type_id": st["id"], "name": "A", "geometry": poly, "props": {"staff_phone": "abc"}})
        assert bad.status_code == 422 and "staff_phone" in bad.json()["errors"]
        pa = c.post(f"/api/floors/{fl['id']}/places", headers=h, json={
            "type_id": st["id"], "name": "Стенд A", "geometry": poly,
            "props": {"owner": "ООО", "staff_phone": "+7 999 123-45-67"}}).json()
        pb = c.post(f"/api/floors/{fl['id']}/places", headers=h, json={
            "type_id": st["id"], "name": "Стенд B", "geometry": poly}).json()
        assert c.patch(f"/api/places/{pa['id']}", json={"name": "Стенд A2"},
                       headers={**h, "If-Match": "99"}).status_code == 409

        ev = c.post(f"/api/venues/{v['id']}/events", headers=h,
                    json={"slug": "demo-fest", "title": "Фест"}).json()
        act = c.post(f"/api/events/{ev['id']}/activities", headers=h,
                     json={"title": "Мастер-класс", "place_id": pa["id"]}).json()
        assert c.get("/v/demo-fest/head").json() == {"rev": 0}
        assert c.post(f"/api/events/{ev['id']}/publish", json={}, headers=h).json()["rev"] == 1

        snap = c.get("/v/demo-fest/snapshots/1.json").json()
        assert snap["audience"] == "public"
        assert "staff_phone" not in next(p for p in snap["places"] if p["id"] == pa["id"])["props"]
        staff = c.get(f"/v/demo-fest/staff?token={ev['staff_token']}").json()
        assert "staff_phone" in next(p for p in staff["places"] if p["id"] == pa["id"])["props"]
        assert c.get("/v/demo-fest/staff?token=nope").status_code == 403

        moved = c.post(f"/api/activities/{act['id']}/move", json={"place_id": pb["id"]}, headers=h).json()
        assert moved["status"] == "moved" and moved["moved_from_id"] == pa["id"]
        assert c.get("/v/demo-fest/head").json() == {"rev": 2}
        snap2 = c.get("/v/demo-fest/snapshots/2.json").json()
        assert snap2["activities"][0]["place_id"] == pb["id"] and "переехала" in snap2["notices"][-1]["text"]

        assert c.post(f"/api/events/{ev['id']}/rollback/1", headers=h).json()["rev"] == 3
        assert c.get("/v/demo-fest/snapshots/3.json").json()["activities"][0]["place_id"] == pa["id"]
        assert c.get("/api/venues").status_code == 401
        assert c.get(f"/api/floors/{fl['id']}/original", headers=h).status_code == 200
        assert c.get("/app").status_code == 200 and c.get("/v/demo-fest").status_code == 200
