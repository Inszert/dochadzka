from flask import render_template, request, redirect, url_for, flash, jsonify
from app import app
from models import db, Employee, Attendance
from datetime import datetime, timezone, timedelta

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

# Smart API endpoint that automatically starts or ends shift based on employee ID
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
        
        # Check if employee exists
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonify({"error": "Employee not found"}), 404
        
        # Check if employee has an active shift
        active_shift = Attendance.query.filter_by(
            employee_id=employee_id, 
            status='active'
        ).order_by(Attendance.id.desc()).first()
        
        if active_shift:
            # End the active shift
            now = datetime.now(timezone(timedelta(hours=1)))
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
            # Start a new shift
            if not work_location:
                return jsonify({"error": "Work location is required to start a shift"}), 400
            
            now = datetime.now(timezone(timedelta(hours=1)))
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

# Smart API endpoint that automatically starts or ends shift based on employee name
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
        
        # Find employee by name
        name_parts = employee_name.strip().split(' ', 1)
        if len(name_parts) == 2:
            name, surname = name_parts
            employee = Employee.query.filter_by(name=name, surname=surname).first()
        else:
            # Try to find by name only
            search_name = name_parts[0]
            employee = Employee.query.filter(
                (Employee.name.ilike(f"%{search_name}%")) | 
                (Employee.surname.ilike(f"%{search_name}%"))
            ).first()
        
        if not employee:
            return jsonify({"error": "Employee not found"}), 404
        
        # Check if employee has an active shift
        active_shift = Attendance.query.filter_by(
            employee_id=employee.id, 
            status='active'
        ).order_by(Attendance.id.desc()).first()
        
        if active_shift:
            # End the active shift
            now = datetime.now(timezone(timedelta(hours=1)))
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
            # Start a new shift
            if not work_location:
                return jsonify({"error": "Work location is required to start a shift"}), 400
            
            now = datetime.now(timezone(timedelta(hours=1)))
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

# API endpoint for ESP32 to start shift with employee ID
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
        
        # Check if employee exists
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonify({"error": "Employee not found"}), 404
        
        # Create new attendance record with start time only
        now = datetime.now(timezone(timedelta(hours=1)))
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

# API endpoint for ESP32 to start shift with employee name
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
        
        # Find employee by name (split into name and surname if possible)
        name_parts = employee_name.strip().split(' ', 1)
        if len(name_parts) == 2:
            name, surname = name_parts
            employee = Employee.query.filter_by(name=name, surname=surname).first()
        else:
            # Try to find by name only (search in both name and surname fields)
            search_name = name_parts[0]
            employee = Employee.query.filter(
                (Employee.name.ilike(f"%{search_name}%")) | 
                (Employee.surname.ilike(f"%{search_name}%"))
            ).first()
        
        if not employee:
            return jsonify({"error": "Employee not found"}), 404
        
        # Create new attendance record with start time only
        now = datetime.now(timezone(timedelta(hours=1)))
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

# API endpoint for ESP32 to end shift with employee ID
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
        
        # Find the active shift
        if attendance_id:
            record = Attendance.query.get(attendance_id)
            if not record:
                return jsonify({"error": "Attendance record not found"}), 404
        else:
            # Find the latest active shift for this employee
            record = Attendance.query.filter_by(
                employee_id=employee_id, 
                status='active'
            ).order_by(Attendance.id.desc()).first()
            if not record:
                return jsonify({"error": "No active shift found for this employee"}), 404
        
        # Update with end time
        now = datetime.now(timezone(timedelta(hours=1)))
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

# API endpoint for ESP32 to end shift with employee name
@app.route("/api/end_shift_by_name", methods=["POST"])
def api_end_shift_by_name():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        employee_name = data.get("employee_name")
        
        if not employee_name:
            return jsonify({"error": "Employee name is required"}), 400
        
        # Find employee by name
        name_parts = employee_name.strip().split(' ', 1)
        if len(name_parts) == 2:
            name, surname = name_parts
            employee = Employee.query.filter_by(name=name, surname=surname).first()
        else:
            # Try to find by name only
            search_name = name_parts[0]
            employee = Employee.query.filter(
                (Employee.name.ilike(f"%{search_name}%")) | 
                (Employee.surname.ilike(f"%{search_name}%"))
            ).first()
        
        if not employee:
            return jsonify({"error": "Employee not found"}), 404
        
        # Find the latest active shift for this employee
        record = Attendance.query.filter_by(
            employee_id=employee.id, 
            status='active'
        ).order_by(Attendance.id.desc()).first()
        
        if not record:
            return jsonify({"error": "No active shift found for this employee"}), 404
        
        # Update with end time
        now = datetime.now(timezone(timedelta(hours=1)))
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

# Web interface for starting shift
@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    if request.method == "POST":
        # Check which form was submitted
        if 'start_shift' in request.form:
            # Start shift only
            employee_id = request.form.get("employee_id")
            work_location = request.form.get("work_location")
            
            if employee_id and work_location:
                now = datetime.now(timezone(timedelta(hours=1)))
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
            # Full shift with manual times
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
    
    # Get today's date for the form
    today = datetime.now(timezone(timedelta(hours=1))).strftime('%Y-%m-%d')
    
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
        now = datetime.now(timezone(timedelta(hours=1)))
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
            
            # Handle end time (can be empty)
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
    
    # Format dates and times for the form inputs
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
    
    # First delete all attendance records for this employee
    Attendance.query.filter_by(employee_id=emp_id).delete()
    
    db.session.delete(emp)
    db.session.commit()
    flash("Zamestnanec bol odstránený", "success")
    return redirect("/employees")

@app.route("/report/<int:emp_id>", methods=["GET", "POST"])
def report(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    records = Attendance.query.filter_by(employee_id=emp_id)
    total_hours = 0
    
    if request.method == "POST":
        start_date_str = request.form.get("start_date")
        end_date_str = request.form.get("end_date")
        
        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            records = records.filter(Attendance.date >= start_date, Attendance.date <= end_date)
    
    records = records.order_by(Attendance.date.desc()).all()
    for rec in records:
        total_hours += rec.hours_worked()
    
    return render_template("report.html", emp=emp, records=records, total_hours=total_hours)
