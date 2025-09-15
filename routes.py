from flask import render_template, request, redirect, url_for
from app import app
from models import db, Employee, Attendance
from datetime import datetime

@app.route("/")
def home():
    return render_template("index.html")

# zvyšné route definície
@app.route("/employees", methods=["GET", "POST"])
def employees():
    if request.method == "POST":
        # získanie dát z formulára
        name = request.form.get("name")
        position = request.form.get("position")

        if name and position:
            new_employee = Employee(name=name, position=position)
            db.session.add(new_employee)
            db.session.commit()

        return redirect(url_for("employees"))  # presmerovanie späť na zoznam

    # GET: zobrazenie všetkých zamestnancov
    all_employees = Employee.query.all()
    return render_template("employees.html", employees=all_employees)

@app.route("/attendance")
def attendance():
    records = Attendance.query.all()
    return render_template("attendance.html", records=records)
