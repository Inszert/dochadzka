"""
Deduplication tests for the two ESP32-facing endpoints.

Scenarios covered:
  1. shift_by_name duplicate within 5 min  → HTTP 200 + action "ignored"
  2. shift_by_name_with_time exact same employee+timestamp → HTTP 200 + action "ignored"
  3. cross-endpoint: shift_by_name then shift_by_name_with_time within 5 min → HTTP 200 + action "ignored"

Run with:  pytest test_dedup.py -v
"""
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Bratislava")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def flask_app():
    from app import app, db
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()
        from models import Employee
        if not Employee.query.filter_by(name="Dedup", surname="Testuser").first():
            db.session.add(Employee(name="Dedup", surname="Testuser"))
            db.session.commit()

    return app


@pytest.fixture(autouse=True)
def clean_state(flask_app):
    """Wipe dedup log and attendance records before every test."""
    from app import db
    from models import ShiftDedupLog, Attendance
    with flask_app.app_context():
        ShiftDedupLog.query.delete()
        Attendance.query.delete()
        db.session.commit()
    yield
    with flask_app.app_context():
        ShiftDedupLog.query.delete()
        Attendance.query.delete()
        db.session.commit()


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


# ---------------------------------------------------------------------------
# Rule 1 — shift_by_name same-endpoint dedup
# ---------------------------------------------------------------------------

def test_shift_by_name_duplicate_returns_200(client):
    """Second identical shift_by_name within 5 minutes must return 200 with action='ignored'."""
    payload = {"employee_name": "Dedup Testuser", "work_location": "Office"}

    r1 = client.post("/api/shift_by_name", json=payload)
    assert r1.status_code == 200, "First request should succeed"
    assert r1.get_json().get("action") != "ignored", "First request should not be ignored"

    r2 = client.post("/api/shift_by_name", json=payload)
    assert r2.status_code == 200, "Duplicate must return 200, not 4xx"
    data = r2.get_json()
    assert data["action"] == "ignored", f"Expected 'ignored', got: {data}"


# ---------------------------------------------------------------------------
# Rule 2 — shift_by_name_with_time exact timestamp dedup
# ---------------------------------------------------------------------------

def test_shift_by_name_with_time_exact_duplicate_returns_200(client):
    """Second shift_by_name_with_time with same employee+timestamp must return 200 with action='ignored'."""
    ts = datetime.now(TZ).isoformat()
    payload = {"employee_name": "Dedup Testuser", "work_location": "Office", "timestamp": ts}

    r1 = client.post("/api/shift_by_name_with_time", json=payload)
    assert r1.status_code == 200, "First request should succeed"
    assert r1.get_json().get("action") != "ignored", "First request should not be ignored"

    r2 = client.post("/api/shift_by_name_with_time", json=payload)
    assert r2.status_code == 200, "Duplicate must return 200, not 4xx"
    data = r2.get_json()
    assert data["action"] == "ignored", f"Expected 'ignored', got: {data}"


# ---------------------------------------------------------------------------
# Rule 3 — cross-endpoint dedup
# ---------------------------------------------------------------------------

def test_cross_endpoint_duplicate_returns_200(client):
    """shift_by_name_with_time arriving within 5 min after shift_by_name for the same employee must return 200 with action='ignored'."""
    ts = datetime.now(TZ).isoformat()

    r1 = client.post("/api/shift_by_name", json={"employee_name": "Dedup Testuser", "work_location": "Office"})
    assert r1.status_code == 200, "shift_by_name should succeed"
    assert r1.get_json().get("action") != "ignored"

    r2 = client.post("/api/shift_by_name_with_time", json={
        "employee_name": "Dedup Testuser",
        "work_location": "Office",
        "timestamp": ts,
    })
    assert r2.status_code == 200, "Cross-endpoint duplicate must return 200, not 4xx"
    data = r2.get_json()
    assert data["action"] == "ignored", f"Expected 'ignored', got: {data}"
