from flask import render_template, request, redirect
from app import app
from models import db, Employee, Attendance
from datetime import datetime, date, time

# Zobrazenie a pridanie zamestnanca
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

# Edit zamestnanca
@app.route("/edit_employee/<int:id>", methods=["GET", "POST"])
def edit_employee(id):
    emp = Employee.query.get_or_404(id)
    if request.method == "POST":
        emp.name = request.form.get("name")
        emp.surname = request.form.get("surname")
        emp.workplace = request.form.get("workplace")
        db.session.commit()
        return redirect("/employees")
    return render_template("edit_employee.html", emp=emp)

# Report zamestnanca
@app.route("/report/<int:employee_id>", methods=["GET", "POST"])
def report(employee_id):
    emp = Employee.query.get_or_404(employee_id)
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")

    query = Attendance.query.filter_by(employee_id=employee_id)
    if start_date:
        query = query.filter(Attendance.date >= start_date)
    if end_date:
        query = query.filter(Attendance.date <= end_date)
    
    records = query.all()

    total_hours = sum(
        (datetime.combine(date.min, rec.end_time) - datetime.combine(date.min, rec.start_time)).seconds / 3600
        for rec in records
    )

    return render_template("report.html", emp=emp, records=records, total_hours=total_hours)
