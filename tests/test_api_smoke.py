from fastapi.testclient import TestClient
from apps.api.main import app


def test_routes_200():
    client = TestClient(app)
    r = client.post("/api/maowise/v1/predict", json={"description": "MAO 300 V 10 min alpha 0.2 epsilon 0.8"})
    assert r.status_code == 200

