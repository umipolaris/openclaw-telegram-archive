import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from app.main import app, settings


def test_read_only_blocks_write_requests_for_api_paths():
    prev = settings.read_only_mode
    settings.read_only_mode = True
    try:
        client = TestClient(app)
        resp = client.post("/api/health")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "read-only mode enabled"
    finally:
        settings.read_only_mode = prev


def test_read_only_allows_login_path_exception():
    prev = settings.read_only_mode
    settings.read_only_mode = True
    try:
        client = TestClient(app)
        resp = client.post("/api/auth/login")
        # Allowed path should bypass read-only middleware; missing body triggers 422.
        assert resp.status_code != 503
        assert resp.status_code == 422
    finally:
        settings.read_only_mode = prev


def test_read_only_disabled_does_not_intercept():
    prev = settings.read_only_mode
    settings.read_only_mode = False
    try:
        client = TestClient(app)
        resp = client.post("/api/health")
        # No POST handler for /api/health
        assert resp.status_code == 405
    finally:
        settings.read_only_mode = prev
