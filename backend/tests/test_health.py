import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client

def test_liveness_health_endpoint(client):
    """Test the liveness endpoint /api/v1/health."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "edrms-backend"
    assert "version" in data
    assert "environment" in data

def test_readiness_health_endpoint(client):
    """Test the readiness probe with database verification."""
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["service"] == "edrms-backend"
    assert data["database"]["status"] == "connected"
    # Ensure no credentials or connection details leak
    assert "postgresql" not in response.text
    assert "password" not in response.text
