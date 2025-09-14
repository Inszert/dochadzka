import os
from datetime import datetime
from flask import Flask, request, render_template_string, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# DB URL
database_url = os.environ.get("DATABASE_URL", "postgresql://user:pass@localhost/dbname")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "fallback_secret")

db = SQLAlchemy(app)

# MODELY
class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    surname = db.Column(db.String(50), nullable=False)
    attendances = db.relationship("Attendance", backref="employee", lazy=True)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False)

with app.app_context():
    db.create_all()

# HLAVNÁ STRÁNKA - zamestnanci
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        name = request.form.get("name")
        surname = request.form.get("surname")
        if name and surname:
            new_emp = Employee(name=name, surname=surname)
            db.session.add(new_emp)
            db.session.commit()
            return redirect("/")
    employees = Employee.query.all()
    return render_template_string("""
        <h1>Dochádzka</h1>
        <a href="{{ url_for('attendance') }}">Prejsť na dochádzku</a>
        <h2>Pridaj zamestnanca</h2>
        <form method="POST">
            <input name="name" placeholder="Meno" required>
            <input name="surname" placeholder="Priezvisko" required>
            <button type="submit">Pridaj</button>
        </form>

        <h2>Zoznam zamestnancov</h2>
        <ul>
        {% for emp in employees %}
            <li>{{ emp.name }} {{ emp.surname }}</li>
        {% endfor %}
        </ul>
    """, employees=employees)

# PODSTRÁNKA - dochádzka
@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    employees = Employee.query.all()
    if request.method == "POST":
        emp_id = request.form.get("employee_id")
        date_str = request.form.get("date")
        start_str = request.form.get("start_time")
        end_str = request.form.get("end_time")
        if emp_id and date_str and start_str and end_str:
            date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.strptime(end_str, "%H:%M").time()
            new_att = Attendance(
                employee_id=int(emp_id),
                date=date,
                start_time=start_time,
                end_time=end_time
            )
            db.session.add(new_att)
            db.session.commit()
            return redirect("/attendance")

    # Na zobrazenie dochádzky
    attendance_data = []
    for emp in employees:
        total_hours = 0
        records = []
        for att in emp.attendances:
            start_dt = datetime.combine(att.date, att.start_time)
            end_dt = datetime.combine(att.date, att.end_time)
            hours = (end_dt - start_dt).total_seconds() / 3600
            total_hours += hours
            records.append({
                "date": att.date,
                "start_time": att.start_time,
                "end_time": att.end_time,
                "hours": hours
            })
        attendance_data.append({
            "employee": emp,
            "records": records,
            "total_hours": total_hours
        })

    return render_template_string("""
        <h1>Dochádzka - Talcilod štýl</h1>
        <a href="{{ url_for('index') }}">Späť na hlavnú</a>
        <h2>Pridaj dochádzku</h2>
        <form method="POST">
            <select name="employee_id" required>
                {% for emp in employees %}
                <option value="{{ emp.id }}">{{ emp.name }} {{ emp.surname }}</option>
                {% endfor %}
            </select>
            <input type="date" name="date" required>
            <input type="time" name="start_time" required>
            <input type="time" name="end_time" required>
            <button type="submit">Pridaj</button>
        </form>

        <h2>Dochádzka zamestnancov</h2>
        {% for data in attendance_data %}
            <h3>{{ data.employee.name }} {{ data.employee.surname }} - Celkovo hodín: {{ "%.2f"|format(data.total_hours) }}</h3>
            <ul>
                {% for rec in data.records %}
                    <li>{{ rec.date }} | {{ rec.start_time }} - {{ rec.end_time }} | Hodín: {{ "%.2f"|format(rec.hours) }}</li>
                {% endfor %}
            </ul>
        {% endfor %}
    """, employees=employees, attendance_data=attendance_data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
