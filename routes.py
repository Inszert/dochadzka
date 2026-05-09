from flask import render_template, request, redirect, flash, jsonify
from app import app
from models import db, Employee, Attendance
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import threading

# single source of truth for timezone
TZ = ZoneInfo("Europe/Bratislava")


def now_local():
    """Current datetime in Europe/Bratislava (DST-aware)."""
    return datetime.now(TZ)


# ---------------------------------------------------------------------------
# Deduplication
#
# Rules:
# 1. /api/shift_by_name repeated with same name in short time = blocked.
# 2. /api/shift_by_name_with_time repeated with same name/time = allowed.
# 3. Cross-endpoint:
#    - shift_by_name_with_time -> shift_by_name
#    - shift_by_name -> shift_by_name_with_time
#    If same employee name, request arrived within 1 minute, and event_time is
#    within +-1 minute, ignore the second one.
# 4. Different employee name = always normal.
# 5. Cross-endpoint memory resets after 1 minute.
# ---------------------------------------------------------------------------

_shift_request_lock = threading.Lock()

_recent_shift_by_name_requests: dict[str, datetime] = {}
_recent_cross_endpoint_requests = []

SHIFT_BY_NAME_DEDUP_WINDOW = timedelta(seconds=30)
CROSS_ENDPOINT_WINDOW = timedelta(minutes=1)
CROSS_ENDPOINT_TIME_TOLERANCE = timedelta(minutes=1)


def _normalize_dt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def _is_duplicate_shift_by_name(employee_name: str) -> bool:
    """
    Blocks repeated /api/shift_by_name requests for the same employee
    in a short amount of time.
    """
    key = employee_name.strip().lower()
    now = now_local()

    with _shift_request_lock:
        last_seen = _recent_shift_by_name_requests.get(key)

        if last_seen is not None and now - last_seen < SHIFT_BY_NAME_DEDUP_WINDOW:
            return True

        _recent_shift_by_name_requests[key] = now
        return False


def _clean_cross_endpoint_requests():
    now = now_local()
    _recent_cross_endpoint_requests[:] = [
        item for item in _recent_cross_endpoint_requests
        if now - item["created_at"] <= CROSS_ENDPOINT_WINDOW
    ]


def _is_duplicate_cross_endpoint(source: str, employee_name: str, event_time: datetime) -> bool:
    """
    Blocks only when matching request came from the OTHER endpoint.
    Same endpoint repeated calls are not blocked here.
    """
    key = employee_name.strip().lower()
    event_time = _normalize_dt(event_time)

    other_source = (
        "shift_by_name_with_time"
        if source == "shift_by_name"
        else "shift_by_name"
    )

    with _shift_request_lock:
        _clean_cross_endpoint_requests()

        for item in _recent_cross_endpoint_requests:
            if item["source"] != other_source:
                continue

            same_name = item["name_key"] == key
            close_time = abs(event_time - item["event_time"]) <= CROSS_ENDPOINT_TIME_TOLERANCE

            if same_name and close_time:
                return True

        return False


def _register_cross_endpoint_request(source: str, employee_name: str, event_time: datetime):
    key = employee_name.strip().lower()
    now = now_local()
    event_time = _normalize_dt(event_time)

    with _shift_request_lock:
        _clean_cross_endpoint_requests()

        _recent_cross_endpoint_requests.append({
            "source": source,
            "name_key": key,
            "event_time": event_time,
            "created_at": now
        })


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
            return jsonify({"error": "Invalid timestamp format. Use ISO 8601, e.g., 2026-02-17T14:30:00"}), 400

        if _is_duplicate_cross_endpoint("shift_by_name_with_time", employee_name, ts):
            return jsonify({
                "success": False,
                "action": "ignored",
                "message": "Duplicate request ignored. Matching shift_by_name request was already processed within 1 minute."
            }), 429

        _register_cross_endpoint_request("shift_by_name_with_time", employee_name, ts)

        name_parts = employee_name.strip().split(' ', 1)
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
            status='active'
        ).order_by(Attendance.id.desc()).first()

        if active_shift:
            active_shift.end_time = ts.time()
            active_shift.status = 'completed'
            hours_worked = active_shift.hours_worked()
            db.session.commit()

            return jsonify({
                "success": True,
                "action": "ended",
                "attendance_id": active_shift.id,
                "employee_id": employee.id,
                "employee_name": f"{employee.name} {employee.surname}",
                "hours_worked": hours_worked,
                "start_time": active_shift.start_time.strftime('%H:%M'),
                "end_time": active_shift.end_time.strftime('%H:%M'),
                "message": "Shift ended successfully"
            }), 200
        else:
            if not work_location:
                return jsonify({"error": "Work location is required to start a shift"}), 400

            record = Attendance(
                employee_id=employee.id,
                date=ts.date(),
                start_time=ts.time(),
                work_location=work_location,
                status='active'
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
                "start_time": record.start_time.strftime('%H:%M'),
                "message": "Shift started successfully"
            }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/shift", methods=["POST"])
def api_shift():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        employee_id = data.get("employee_id")
        work_location = data.get("work_location", "Unknown")
        
        if not employee_id:
            return jsonify({"error": "Employee ID is required"}), 400
        
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonify({"error": "Employee not found"}), 404
        
        active_shift = Attendance.query.filter_by(
            employee_id=employee_id, 
            status='active'
        ).order_by(Attendance.id.desc()).first()
        
        if active_shift:
            now = now_local()
            active_shift.end_time = now.time()
            active_shift.status = 'completed'
            hours_worked = active_shift.hours_worked()
            db.session.commit()
            
            return jsonify({
                "success": True,
                "action": "ended",
                "attendance_id": active_shift.id,
                "employee_name": f"{employee.name} {employee.surname}",
                "hours_worked": hours_worked,
                "start_time": active_shift.start_time.strftime('%H:%M'),
                "end_time": active_shift.end_time.strftime('%H:%M'),
                "message": "Shift ended successfully"
            }), 200
        else:
            if not work_location:
                return jsonify({"error": "Work location is required to start a shift"}), 400
            
            now = now_local()
            record = Attendance(
                employee_id=employee_id,
                date=now.date(),
                start_time=now.time(),
                work_location=work_location,
                status='active'
            )
            db.session.add(record)
            db.session.commit()
            
            return jsonify({
                "success": True,
                "action": "started",
                "attendance_id": record.id,
                "employee_name": f"{employee.name} {employee.surname}",
                "work_location": work_location,
                "start_time": record.start_time.strftime('%H:%M'),
                "message": "Shift started successfully"
            }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

        if _is_duplicate_shift_by_name(employee_name):
            return jsonify({
                "success": False,
                "action": "ignored",
                "message": "Duplicate shift_by_name request ignored. Please wait before submitting again."
            }), 429

        if _is_duplicate_cross_endpoint("shift_by_name", employee_name, now):
            return jsonify({
                "success": False,
                "action": "ignored",
                "message": "Duplicate request ignored. Matching shift_by_name_with_time request was already processed within 1 minute."
            }), 429

        _register_cross_endpoint_request("shift_by_name", employee_name, now)

        name_parts = employee_name.strip().split(' ', 1)
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
            status='active'
        ).order_by(Attendance.id.desc()).first()

        if active_shift:
            active_shift.end_time = now.time()
            active_shift.status = 'completed'
            hours_worked = active_shift.hours_worked()
            db.session.commit()

            return jsonify({
                "success": True,
                "action": "ended",
                "attendance_id": active_shift.id,
                "employee_id": employee.id,
                "employee_name": f"{employee.name} {employee.surname}",
                "hours_worked": hours_worked,
                "start_time": active_shift.start_time.strftime('%H:%M'),
                "end_time": active_shift.end_time.strftime('%H:%M'),
                "message": "Shift ended successfully"
            }), 200
        else:
            if not work_location:
                return jsonify({"error": "Work location is required to start a shift"}), 400

            record = Attendance(
                employee_id=employee.id,
                date=now.date(),
                start_time=now.time(),
                work_location=work_location,
                status='active'
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
                "start_time": record.start_time.strftime('%H:%M'),
                "message": "Shift started successfully"
            }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/start_shift", methods=["POST"])
def api_start_shift():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        employee_id = data.get("employee_id")
        work_location = data.get("work_location", "Unknown")
        
        if not employee_id:
            return jsonify({"error": "Employee ID is required"}), 400
        if not work_location:
            return jsonify({"error": "Work location is required"}), 400
        
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonify({"error": "Employee not found"}), 404
        
        now = now_local()
        record = Attendance(
            employee_id=employee_id,
            date=now.date(),
            start_time=now.time(),
            work_location=work_location,
            status='active'
        )
        db.session.add(record)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "attendance_id": record.id,
            "employee_name": f"{employee.name} {employee.surname}",
            "message": "Shift started successfully"
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/start_shift_by_name", methods=["POST"])
def api_start_shift_by_name():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        employee_name = data.get("employee_name")
        work_location = data.get("work_location", "Unknown")
        
        if not employee_name:
            return jsonify({"error": "Employee name is required"}), 400
        if not work_location:
            return jsonify({"error": "Work location is required"}), 400
        
        name_parts = employee_name.strip().split(' ', 1)
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
        
        now = now_local()
        record = Attendance(
            employee_id=employee.id,
            date=now.date(),
            start_time=now.time(),
            work_location=work_location,
            status='active'
        )
        db.session.add(record)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "attendance_id": record.id,
            "employee_id": employee.id,
            "employee_name": f"{employee.name} {employee.surname}",
            "message": "Shift started successfully"
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/end_shift", methods=["POST"])
def api_end_shift():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        attendance_id = data.get("attendance_id")
        employee_id = data.get("employee_id")
        
        if not attendance_id and not employee_id:
            return jsonify({"error": "Either attendance_id or employee_id is required"}), 400
        
        if attendance_id:
            record = Attendance.query.get(attendance_id)
            if not record:
                return jsonify({"error": "Attendance record not found"}), 404
        else:
            record = Attendance.query.filter_by(
                employee_id=employee_id, 
                status='active'
            ).order_by(Attendance.id.desc()).first()
            if not record:
                return jsonify({"error": "No active shift found for this employee"}), 404
        
        now = now_local()
        record.end_time = now.time()
        record.status = 'completed'
        db.session.commit()
        
        return jsonify({
            "success": True,
            "hours_worked": record.hours_worked(),
            "employee_name": f"{record.employee.name} {record.employee.surname}",
            "message": "Shift ended successfully"
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/end_shift_by_name", methods=["POST"])
def api_end_shift_by_name():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        employee_name = data.get("employee_name")
        
        if not employee_name:
            return jsonify({"error": "Employee name is required"}), 400
        
        name_parts = employee_name.strip().split(' ', 1)
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
        
        record = Attendance.query.filter_by(
            employee_id=employee.id, 
            status='active'
        ).order_by(Attendance.id.desc()).first()
        
        if not record:
            return jsonify({"error": "No active shift found for this employee"}), 404
        
        now = now_local()
        record.end_time = now.time()
        record.status = 'completed'
        db.session.commit()
        
        return jsonify({
            "success": True,
            "hours_worked": record.hours_worked(),
            "employee_name": f"{employee.name} {employee.surname}",
            "message": "Shift ended successfully"
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    if request.method == "POST":
        if 'start_shift' in request.form:
            employee_id = request.form.get("employee_id")
            work_location = request.form.get("work_location")
            
            if employee_id and work_location:
                now = now_local()
                record = Attendance(
                    employee_id=employee_id,
                    date=now.date(),
                    start_time=now.time(),
                    work_location=work_location,
                    status='active'
                )
                db.session.add(record)
                db.session.commit()
                flash("Začiatok smeny bol zaznamenaný", "success")
            else:
                flash("Všetky polia sú povinné", "danger")
        
        elif 'full_shift' in request.form:
            employee_id = request.form.get("employee_id_full")
            date_str = request.form.get("date")
            start_time_str = request.form.get("start_time")
            end_time_str = request.form.get("end_time")
            work_location = request.form.get("work_location_full")
            
            if employee_id and date_str and start_time_str and end_time_str and work_location:
                date = datetime.strptime(date_str, "%Y-%m-%d").date()
                start_time = datetime.strptime(start_time_str, "%H:%M").time()
                end_time = datetime.strptime(end_time_str, "%H:%M").time()
                
                record = Attendance(
                    employee_id=employee_id,
                    date=date,
                    start_time=start_time,
                    end_time=end_time,
                    work_location=work_location,
                    status='completed'
                )
                db.session.add(record)
                db.session.commit()
                flash("Celá smena bola zaznamenaná", "success")
            else:
                flash("Všetky polia sú povinné", "danger")
        
        return redirect("/attendance")
    
    records = Attendance.query.order_by(Attendance.date.desc(), Attendance.start_time.desc()).all()
    employees = Employee.query.all()
    today = now_local().strftime('%Y-%m-%d')
    
    return render_template("attendance.html", records=records, employees=employees, today=today)


@app.route("/end_shift_manual", methods=["POST"])
def end_shift_manual():
    attendance_id = request.form.get("attendance_id")
    end_time_str = request.form.get("end_time")
    
    if attendance_id and end_time_str:
        record = Attendance.query.get(attendance_id)
        if record:
            end_time = datetime.strptime(end_time_str, "%H:%M").time()
            record.end_time = end_time
            record.status = 'completed'
            db.session.commit()
            flash("Koniec smeny bol manuálne zaznamenaný", "success")
        else:
            flash("Záznam nebol nájdený", "danger")
    else:
        flash("Čas konca je povinný", "danger")
    
    return redirect("/attendance")


@app.route("/end_shift/<int:record_id>")
def end_shift(record_id):
    record = Attendance.query.get_or_404(record_id)
    
    if record.end_time:
        flash("Táto smena už bola ukončená", "warning")
    else:
        now = now_local()
        record.end_time = now.time()
        record.status = 'completed'
        db.session.commit()
        flash("Koniec smeny bol zaznamenaný", "success")
    
    return redirect("/attendance")


@app.route("/edit_attendance/<int:record_id>", methods=["GET", "POST"])
def edit_attendance(record_id):
    record = Attendance.query.get_or_404(record_id)
    employees = Employee.query.all()
    
    if request.method == "POST":
        employee_id = request.form.get("employee_id")
        date_str = request.form.get("date")
        start_time_str = request.form.get("start_time")
        end_time_str = request.form.get("end_time")
        work_location = request.form.get("work_location")
        
        if employee_id and date_str and start_time_str and work_location:
            record.employee_id = employee_id
            record.date = datetime.strptime(date_str, "%Y-%m-%d").date()
            record.start_time = datetime.strptime(start_time_str, "%H:%M").time()
            record.work_location = work_location
            
            if end_time_str:
                record.end_time = datetime.strptime(end_time_str, "%H:%M").time()
                record.status = 'completed'
            else:
                record.end_time = None
                record.status = 'active'
            
            db.session.commit()
            flash("Záznam bol upravený", "success")
            return redirect("/attendance")
        else:
            flash("Zamestnanec, dátum, čas začiatku a miesto sú povinné", "danger")
    
    date_formatted = record.date.strftime('%Y-%m-%d')
    start_time_formatted = record.start_time.strftime('%H:%M')
    end_time_formatted = record.end_time.strftime('%H:%M') if record.end_time else ''
    
    return render_template("edit_attendance.html", 
                          record=record, 
                          employees=employees,
                          date_formatted=date_formatted,
                          start_time_formatted=start_time_formatted,
                          end_time_formatted=end_time_formatted)


@app.route("/delete_attendance/<int:record_id>")
def delete_attendance(record_id):
    record = Attendance.query.get_or_404(record_id)
    db.session.delete(record)
    db.session.commit()
    flash("Záznam bol odstránený", "success")
    return redirect("/attendance")


@app.route("/edit_employee/<int:emp_id>", methods=["GET", "POST"])
def edit_employee(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    
    if request.method == "POST":
        emp.name = request.form.get("name")
        emp.surname = request.form.get("surname")
        db.session.commit()
        flash("Zamestnanec bol upravený", "success")
        return redirect("/employees")
    
    return render_template("edit_employee.html", emp=emp)


@app.route("/delete_employee/<int:emp_id>")
def delete_employee(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    Attendance.query.filter_by(employee_id=emp_id).delete()
    db.session.delete(emp)
    db.session.commit()
    flash("Zamestnanec bol odstránený", "success")
    return redirect("/employees")


import requests
from datetime import date


@app.route("/report/<int:emp_id>", methods=["GET", "POST"])
def report(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    records_query = Attendance.query.filter_by(employee_id=emp_id)

    if request.method == "POST":
        start_date_str = request.form.get("start_date")
        end_date_str = request.form.get("end_date")
        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            records_query = records_query.filter(
                Attendance.date >= start_date,
                Attendance.date <= end_date
            )

    records = records_query.order_by(Attendance.date.desc()).all()

    years = set(rec.date.year for rec in records)
    holidays = set()

    for yr in years:
        try:
            url = f"https://date.nager.at/api/v3/PublicHolidays/{yr}/SK"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                for h in data:
                    d = datetime.strptime(h["date"], "%Y-%m-%d").date()
                    holidays.add(d)
        except Exception as e:
            print("Holiday API error:", e)

    total_hours = 0
    normal_hours = 0
    saturday_hours = 0
    sunday_hours = 0
    holiday_hours = 0

    for rec in records:
        hours = rec.hours_worked()
        total_hours += hours

        if rec.date in holidays:
            holiday_hours += hours
        elif rec.date.weekday() == 5:
            saturday_hours += hours
        elif rec.date.weekday() == 6:
            sunday_hours += hours
        else:
            normal_hours += hours

    return render_template(
        "report.html",
        emp=emp,
        records=records,
        total_hours=total_hours,
        normal_hours=normal_hours,
        saturday_hours=saturday_hours,
        sunday_hours=sunday_hours,
        holiday_hours=holiday_hours,
        holidays=holidays
    )