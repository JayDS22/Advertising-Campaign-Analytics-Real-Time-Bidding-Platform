"""End-to-end API smoke tests via FastAPI's TestClient."""
from fastapi.testclient import TestClient

from src.api.main import app


client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_home_serves_html():
    r = client.get("/")
    assert r.status_code == 200
    assert "Atlas" in r.text


def test_bid_endpoint():
    payload = {
        "user_id": "user-test",
        "device_type": "mobile",
        "geo_country": "US",
        "geo_city": "NYC",
        "site_domain": "example.com",
        "ad_slot_id": "s1",
        "ad_format": "banner",
        "user_segments": ["sports_enthusiast"],
    }
    r = client.post("/api/bid", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert "decision_latency_ms" in body and body["decision_latency_ms"] >= 0


def test_simulate_and_metrics():
    r = client.post("/api/simulate?n=20")
    assert r.status_code == 200
    m = client.get("/api/metrics").json()
    assert "engine" in m and "monitoring" in m


def test_campaigns_list():
    r = client.get("/api/campaigns")
    assert r.status_code == 200
    assert "campaigns" in r.json() and len(r.json()["campaigns"]) > 0


def test_ab_test():
    r = client.post("/api/ab_test", json={
        "control_success": 480, "control_total": 20000,
        "treatment_success": 600, "treatment_total": 20000,
        "metric_name": "ctr", "alpha": 0.01,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["significant"] is True


def test_did_endpoint():
    r = client.post("/api/did", json={
        "n_units": 80, "pre_periods": 4, "post_periods": 4, "true_effect": 0.4,
    })
    assert r.status_code == 200
    assert "treatment_effect" in r.json()


def test_psm_endpoint():
    r = client.post("/api/psm", json={"n_users": 500, "treatment_effect": 0.1})
    assert r.status_code == 200
    assert "att" in r.json()
