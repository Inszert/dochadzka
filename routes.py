from flask import render_template, request, redirect, url_for, render_template_string
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
        workplace = request.form.get("workplace")
        
        if name and surname:
            emp = Employee(name=name, surname=surname, workplace=workplace)
            db.session.add(emp)
            db.session.commit()
            return redirect("/employees")
    
    all_emps = Employee.query.all()
    return render_template("employees.html", all_emps=all_emps)

@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    if request.method == "POST":
        employee_id = request.form.get("employee_id")
        date_str = request.form.get("date")
        start_time_str = request.form.get("start_time")
        end_time_str = request.form.get("end_time")
        
        if employee_id and date_str and start_time_str and end_time_str:
            date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.strptime(end_time_str, "%H:%M").time()
            
            record = Attendance(
                employee_id=employee_id,
                date=date,
                start_time=start_time,
                end_time=end_time
            )
            db.session.add(record)
            db.session.commit()
            return redirect("/attendance")
    
    records = Attendance.query.all()
    employees = Employee.query.all()
    return render_template("attendance.html", records=records, employees=employees)

@app.route("/edit_employee/<int:emp_id>", methods=["GET", "POST"])
def edit_employee(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    
    if request.method == "POST":
        emp.name = request.form.get("name")
        emp.surname = request.form.get("surname")
        emp.workplace = request.form.get("workplace")
        db.session.commit()
        return redirect("/employees")
    
    return render_template("edit_employee.html", emp=emp)

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
    
    records = records.all()
    for rec in records:
        total_hours += rec.hours_worked()
    
    return render_template("report.html", emp=emp, records=records, total_hours=total_hours)