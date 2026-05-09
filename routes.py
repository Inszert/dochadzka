
from flask import render_template, request, redirect, flash, jsonify
from app import app
from models import db, Employee, Attendance, ShiftDedupLog
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests

# single source of truth for timezone
TZ = ZoneInfo("Europe/Bratislava")


def now_local():
    """Current datetime in Europe/Bratislava (DST-aware)."""
    return datetime.now(TZ)


# ---------------------------------------------------------------------------
# DATABASE-BASED DEDUPLICATION
# ---------------------------------------------------------------------------

SHIFT_BY_NAME_DEDUP_WINDOW = timedelta(seconds=30)

CROSS_ENDPOINT_WINDOW = timedelta(minutes=1)
CROSS_ENDPOINT_TIME_TOLERANCE = timedelta(minutes=1)


def _normalize_dt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def _cleanup_dedup_logs():
    cutoff = now_local() - CROSS_ENDPOINT_WINDOW

    ShiftDedupLog.query.filter(
        ShiftDedupLog.created_at < cutoff
    ).delete()

    db.session.commit()


def _register_dedup_request(source: str, employee_name: str, event_time: datetime):
    event_time = _normalize_dt(event_time)

    log = ShiftDedupLog(
        source=source,
        name_key=employee_name.strip().lower(),
        event_time=event_time,
        created_at=now_local()
    )

    db.session.add(log)
    db.session.commit()


def _is_duplicate_shift_by_name(employee_name: str) -> bool:
    """
    Blocks repeated shift_by_name requests
    for the same employee within 30 seconds.
    """

    _cleanup_dedup_logs()

    key = employee_name.strip().lower()
    cutoff = now_local() - SHIFT_BY_NAME_DEDUP_WINDOW

    existing = ShiftDedupLog.query.filter(
        ShiftDedupLog.source == "shift_by_name",
        ShiftDedupLog.name_key == key,
        ShiftDedupLog.created_at >= cutoff
    ).first()

    return existing is not None


def _is_duplicate_cross_endpoint(
    source: str,
    employee_name: str,
    event_time: datetime
) -> bool:
    """
    Cross endpoint blocking:

    shift_by_name_with_time -> shift_by_name
    shift_by_name -> shift_by_name_with_time

    same name
    within 1 minute
    event_time +-1 minute
    """

    _cleanup_dedup_logs()

    key = employee_name.strip().lower()
    event_time = _normalize_dt(event_time)

    other_source = (
        "shift_by_name_with_time"
        if source == "shift_by_name"
        else "shift_by_name"
    )

    cutoff = now_local() - CROSS_ENDPOINT_WINDOW

    min_time = event_time - CROSS_ENDPOINT_TIME_TOLERANCE
    max_time = event_time + CROSS_ENDPOINT_TIME_TOLERANCE

    existing = ShiftDedupLog.query.filter(
        ShiftDedupLog.source == other_source,
        ShiftDedupLog.name_key == key,
        ShiftDedupLog.created_at >= cutoff,
        ShiftDedupLog.event_time >= min_time,
        ShiftDedupLog.event_time <= max_time
    ).first()

    return existing is not None


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/documentation")
def documentation():
    return render_template("docu.html")


@app.route("/employees", methods=["GET", "POST"])
def employees():
    if request.method == "POST":
        name = request.form.get("name")
        surname = request.form.get("surname")

        if name and surname:
            emp = Employee(name=name, surname=surname)
            db.session.add(emp)
            db.session.commit()
            flash("Zamestnanec bol pridaný", "success")
        else:
            flash("Meno a priezvisko sú povinné", "danger")

        return redirect("/employees")

    all_emps = Employee.query.all()
    return render_template("employees.html", all_emps=all_emps)


# ---------------------------------------------------------------------------
# shift_by_name_with_time
# ---------------------------------------------------------------------------

@app.route("/api/shift_by_name_with_time", methods=["POST"])
def api_shift_by_name_with_time():
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        employee_name = data.get("employee_name")
        work_location = data.get("work_location", "Unknown")
        timestamp_str = data.get("timestamp")

        if not employee_name:
            return jsonify({"error": "Employee name is required"}), 400

        if not timestamp_str:
            return jsonify({"error": "Timestamp is required"}), 400

        try:
            ts = datetime.fromisoformat(timestamp_str)

            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=TZ)
            else:
                ts = ts.astimezone(TZ)

        except ValueError:
            return jsonify({
                "error": "Invalid timestamp format. Use ISO 8601"
            }), 400

        # ------------------------------------------------------------
        # Cross-endpoint dedup only
        # ------------------------------------------------------------

        if _is_duplicate_cross_endpoint(
            "shift_by_name_with_time",
            employee_name,
            ts
        ):
            return jsonify({
                "success": False,
                "action": "ignored",
                "message": "Duplicate request ignored. Matching shift_by_name request was already processed within 1 minute."
            }), 429

        _register_dedup_request(
            "shift_by_name_with_time",
            employee_name,
            ts
        )

        # ------------------------------------------------------------

        name_parts = employee_name.strip().split(" ", 1)

        if len(name_parts) == 2:
            name, surname = name_parts

            employee = Employee.query.filter(
                Employee.name.ilike(name),
                Employee.surname.ilike(surname)
            ).first()

        else:
            search_name = name_parts[0]

            employee = Employee.query.filter(
                (Employee.name.ilike(f"%{search_name}%")) |
                (Employee.surname.ilike(f"%{search_name}%"))
            ).first()

        if not employee:
            return jsonify({"error": "Employee not found"}), 404

        active_shift = Attendance.query.filter_by(
            employee_id=employee.id,
            status="active"
        ).order_by(Attendance.id.desc()).first()

        if active_shift:
            active_shift.end_time = ts.time()
            active_shift.status = "completed"

            hours_worked = active_shift.hours_worked()

            db.session.commit()

            return jsonify({
                "success": True,
                "action": "ended",
                "attendance_id": active_shift.id,
                "employee_id": employee.id,
                "employee_name": f"{employee.name} {employee.surname}",
                "hours_worked": hours_worked,
                "start_time": active_shift.start_time.strftime("%H:%M"),
                "end_time": active_shift.end_time.strftime("%H:%M"),
                "message": "Shift ended successfully"
            }), 200

        else:
            if not work_location:
                return jsonify({
                    "error": "Work location is required to start a shift"
                }), 400

            record = Attendance(
                employee_id=employee.id,
                date=ts.date(),
                start_time=ts.time(),
                work_location=work_location,
                status="active"
            )

            db.session.add(record)
            db.session.commit()

            return jsonify({
                "success": True,
                "action": "started",
                "attendance_id": record.id,
                "employee_id": employee.id,
                "employee_name": f"{employee.name} {employee.surname}",
                "work_location": work_location,
                "start_time": record.start_time.strftime("%H:%M"),
                "message": "Shift started successfully"
            }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# shift_by_name
# ---------------------------------------------------------------------------

@app.route("/api/shift_by_name", methods=["POST"])
def api_shift_by_name():
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        employee_name = data.get("employee_name")
        work_location = data.get("work_location", "Unknown")

        if not employee_name:
            return jsonify({"error": "Employee name is required"}), 400

        now = now_local()

        # ------------------------------------------------------------
        # SAME-ENDPOINT DEDUP
        # ------------------------------------------------------------

        if _is_duplicate_shift_by_name(employee_name):
            return jsonify({
                "success": False,
                "action": "ignored",
                "message": "Duplicate shift_by_name request ignored."
            }), 429

        # ------------------------------------------------------------
        # CROSS-ENDPOINT DEDUP
        # ------------------------------------------------------------

        if _is_duplicate_cross_endpoint(
            "shift_by_name",
            employee_name,
            now
        ):
            return jsonify({
                "success": False,
                "action": "ignored",
                "message": "Duplicate request ignored. Matching shift_by_name_with_time request already exists."
            }), 429

        _register_dedup_request(
            "shift_by_name",
            employee_name,
            now
        )

        # ------------------------------------------------------------

        name_parts = employee_name.strip().split(" ", 1)

        if len(name_parts) == 2:
            name, surname = name_parts

            employee = Employee.query.filter(
                Employee.name.ilike(name),
                Employee.surname.ilike(surname)
            ).first()

        else:
            search_name = name_parts[0]

            employee = Employee.query.filter(
                (Employee.name.ilike(f"%{search_name}%")) |
                (Employee.surname.ilike(f"%{search_name}%"))
            ).first()

        if not employee:
            return jsonify({"error": "Employee not found"}), 404

        active_shift = Attendance.query.filter_by(
            employee_id=employee.id,
            status="active"
        ).order_by(Attendance.id.desc()).first()

        if active_shift:
            active_shift.end_time = now.time()
            active_shift.status = "completed"

            hours_worked = active_shift.hours_worked()

            db.session.commit()

            return jsonify({
                "success": True,
                "action": "ended",
                "attendance_id": active_shift.id,
                "employee_id": employee.id,
                "employee_name": f"{employee.name} {employee.surname}",
                "hours_worked": hours_worked,
                "start_time": active_shift.start_time.strftime("%H:%M"),
                "end_time": active_shift.end_time.strftime("%H:%M"),
                "message": "Shift ended successfully"
            }), 200

        else:
            if not work_location:
                return jsonify({
                    "error": "Work location is required to start a shift"
                }), 400

            record = Attendance(
                employee_id=employee.id,
                date=now.date(),
                start_time=now.time(),
                work_location=work_location,
                status="active"
            )

            db.session.add(record)
            db.session.commit()

            return jsonify({
                "success": True,
                "action": "started",
                "attendance_id": record.id,
                "employee_id": employee.id,
                "employee_name": f"{employee.name} {employee.surname}",
                "work_location": work_location,
                "start_time": record.start_time.strftime("%H:%M"),
                "message": "Shift started successfully"
            }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

