from flask import render_template, request, redirect, url_for, flash, jsonify
from app import app
from models import db, Employee, Attendance
from datetime import datetime

@app.route("/")
def home():
    return render_template("index.html")

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

# API endpoint for ESP32 to start shift
@app.route("/api/start_shift", methods=["POST"])
def api_start_shift():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        employee_id = data.get("employee_id")
        work_location = data.get("work_location", "Zoo")
        
        if not employee_id:
            return jsonify({"error": "Employee ID is required"}), 400
        
        # Create new attendance record with start time only
        now = datetime.now()
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
            "message": "Shift started successfully"
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API endpoint for ESP32 to end shift
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
        else:
            # Find the latest active shift for this employee
            record = Attendance.query.filter_by(
                employee_id=employee_id, 
                status='active'
            ).order_by(Attendance.id.desc()).first()
        
        if not record:
            return jsonify({"error": "No active shift found"}), 404
        
        # Update with end time
        now = datetime.now()
        record.end_time = now.time()
        record.status = 'completed'
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "hours_worked": record.hours_worked(),
            "message": "Shift ended successfully"
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Web interface for starting shift# ... existing imports and code ...

@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    if request.method == "POST":
        # Check which form was submitted
        if 'start_shift' in request.form:
            # Start shift only
            employee_id = request.form.get("employee_id")
            work_location = request.form.get("work_location")
            
            if employee_id and work_location:
                now = datetime.now()
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
    work_locations = ["Zoo", "Spa", "Kancelária", "Sklad", "Predajňa", "Restaurácia", "Hotel", "Divadlo"]
    
    # Get today's date for the form
    today = datetime.now().strftime('%Y-%m-%d')
    
    return render_template("attendance.html", records=records, employees=employees, 
                         work_locations=work_locations, today=today)

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

# ... keep the other routes the same ...

# Web interface for ending shift
@app.route("/end_shift/<int:record_id>")
def end_shift(record_id):
    record = Attendance.query.get_or_404(record_id)
    
    if record.end_time:
        flash("Táto smena už bola ukončená", "warning")
    else:
        now = datetime.now()
        record.end_time = now.time()
        record.status = 'completed'
        db.session.commit()
        flash("Koniec smeny bol zaznamenaný", "success")
    
    return redirect("/attendance")

@app.route("/edit_attendance/<int:record_id>", methods=["GET", "POST"])
def edit_attendance(record_id):
    record = Attendance.query.get_or_404(record_id)
    employees = Employee.query.all()
    work_locations = ["Zoo", "Spa", "Kancelária", "Sklad", "Predajňa", "Restaurácia", "Hotel", "Divadlo"]
    
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
                          work_locations=work_locations,
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
        emp.workplace = request.form.get("workplace")
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

# Additional route for filtering attendance by date
@app.route("/attendance_filter", methods=["GET", "POST"])
def attendance_filter():
    records = Attendance.query
    employees = Employee.query.all()
    work_locations = ["Zoo", "Spa", "Kancelária", "Sklad", "Predajňa", "Restaurácia", "Hotel", "Divadlo"]
    
    if request.method == "POST":
        start_date_str = request.form.get("start_date")
        end_date_str = request.form.get("end_date")
        employee_id = request.form.get("employee_id")
        location = request.form.get("location")
        
        if start_date_str:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            records = records.filter(Attendance.date >= start_date)
        
        if end_date_str:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            records = records.filter(Attendance.date <= end_date)
            
        if employee_id and employee_id != "all":
            records = records.filter(Attendance.employee_id == employee_id)
            
        if location and location != "all":
            records = records.filter(Attendance.work_location == location)
    
    records = records.order_by(Attendance.date.desc()).all()
    
    return render_template("attendance.html", records=records, employees=employees, work_locations=work_locations)