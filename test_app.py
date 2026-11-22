# ==============================================================================
# Module: test_app.py
# Author: Yunzhe Yu (Backend & DevOps)
# Description: Automated pytest suite covering persistent SQLite auth, saved 
#              search history, invalid SKU handling, and scraper timeout fallback.
# ==============================================================================

import asyncio
from unittest.mock import AsyncMock, patch
import pytest

import app as flask_app
import database
import scraper


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_sneaker.db")
    monkeypatch.setattr(database, "DB_PATH", test_db)
    database.init_db()
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as test_client:
        yield test_client


# --- 1. Authentication & Persistence Tests ---

def test_signup_and_duplicate_rejection(client):
    res = client.post("/api/signup", json={"username": "tester1", "password": "secret123"})
    assert res.status_code == 201

    dup = client.post("/api/signup", json={"username": "tester1", "password": "secret123"})
    assert dup.status_code == 409


def test_login_and_invalid_credentials(client):
    client.post("/api/signup", json={"username": "tester2", "password": "mypassword"})

    bad = client.post("/api/login", json={"username": "tester2", "password": "wrong"})
    assert bad.status_code == 401

    ok = client.post("/api/login", json={"username": "tester2", "password": "mypassword"})
    assert ok.status_code == 200
    payload = ok.get_json()
    assert payload["username"] == "tester2"
    assert isinstance(payload["token"], str) and len(payload["token"]) == 64


# --- 2. Invalid / Empty Input QA Scenarios ---

def test_search_empty_sku_returns_400(client):
    res = client.get("/api/search?sku=   ")
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_search_invalid_sku_returns_404(client):
    with patch("app.aggregate_prices", new=AsyncMock(return_value=[])):
        res = client.get("/api/search?sku=NONEXISTENT_XYZ_999999")
        assert res.status_code == 404
        assert res.get_json()["results"] == []


# --- 3. Graceful Fallback on Marketplace Timeout ---

def test_scraper_graceful_fallback_when_platform_times_out():
    mock_goat = {
        "platform": "GOAT",
        "price": 153.0,
        "size": "9",
        "url": "https://www.goat.com/sneakers/yeezy-slides-bone-2022-fz5897",
        "slug": "yeezy-slides-bone-2022-fz5897",
        "sku": "FZ5897",
        "name": "Yeezy Slide Bone"
    }
    mock_fc = {
        "platform": "Flight Club",
        "price": 165.0,
        "size": None,
        "url": "https://www.flightclub.com/yeezy-slides-bone-2022-fz5897"
    }

    with patch.object(scraper, "fetch_goat", new=AsyncMock(return_value=mock_goat)), \
         patch.object(scraper, "fetch_stadium_goods", new=AsyncMock(side_effect=TimeoutError("Timed out"))), \
         patch.object(scraper, "fetch_flight_club", new=AsyncMock(return_value=mock_fc)):
        results = asyncio.run(scraper.aggregate_prices("Yeezy Slide Bone"))

    assert len(results) == 2
    assert results[0]["platform"] == "GOAT"
    assert results[0]["price"] == 153.0
    assert results[1]["platform"] == "Flight Club"
    assert results[1]["price"] == 165.0


# --- 4. Saved Search History & Logout Tests ---

def test_authenticated_search_saves_history_and_logout_revokes(client):
    client.post("/api/signup", json={"username": "buyer", "password": "password123"})
    token = client.post("/api/login", json={"username": "buyer", "password": "password123"}).get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    mock_results = [
        {"platform": "GOAT", "price": 153.0, "size": "9", "url": "https://www.goat.com/sneakers/test"}
    ]
    with patch("app.aggregate_prices", new=AsyncMock(return_value=mock_results)):
        search_res = client.get("/api/search?sku=Yeezy+Slide+Bone", headers=headers)
        assert search_res.status_code == 200

    hist_res = client.get("/api/history", headers=headers)
    assert hist_res.status_code == 200
    history = hist_res.get_json()["history"]
    assert len(history) == 1
    assert history[0]["query"] == "Yeezy Slide Bone"
    assert history[0]["lowest_price"] == 153.0

    # Revoke token via logout and verify history endpoint blocks access
    client.post("/api/logout", headers=headers)
    blocked = client.get("/api/history", headers=headers)
    assert blocked.status_code == 401

def test_favorites_and_profile_endpoints(client):
    client.post("/api/signup", json={"username": "collector", "password": "password123"})
    token = client.post("/api/login", json={"username": "collector", "password": "password123"}).get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Save favorite
    add_res = client.post("/api/favorites", headers=headers, json={
        "query": "Jordan 4 Bred",
        "lowest_price": 245.0,
        "platform": "GOAT",
        "url": "https://www.goat.com/sneakers/air-jordan-4-retro-bred-reimagined-fv5029-006"
    })
    assert add_res.status_code == 201
    fav_id = add_res.get_json()["id"]

    # Fetch full profile
    prof_res = client.get("/api/profile", headers=headers)
    assert prof_res.status_code == 200
    profile = prof_res.get_json()["profile"]
    assert profile["username"] == "collector"
    assert len(profile["favorites"]) == 1
    assert profile["favorites"][0]["query"] == "Jordan 4 Bred"

    # Delete favorite
    del_res = client.delete(f"/api/favorites/{fav_id}", headers=headers)
    assert del_res.status_code == 200
    assert len(client.get("/api/favorites", headers=headers).get_json()["favorites"]) == 0