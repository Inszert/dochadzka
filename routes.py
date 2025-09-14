from flask import request, jsonify, render_template_string, redirect
from app import app, db
from models import Employee, Attendance
from datetime import datetime

# Pridanie zamestnanca
@app.route("/employee", methods=["POST"])
def add_employee():
    data = request.json
    if not data:
        return jsonify({"error": "Missing JSON"}), 400

    emp = Employee(
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        workplace=data.get("workplace")
    )
    db.session.add(emp)
    db.session.commit()
    return jsonify({"id": emp.id})

# Pridanie dochádzky
@app.route("/attendance", methods=["POST"])
def add_attendance():
    data = request.json
    if not data:
        return jsonify({"error": "Missing JSON"}), 400

    emp = Employee.query.get(data.get("employee_id"))
    if not emp:
        return jsonify({"error": "Employee not found"}), 404

    att = Attendance(
        employee_id=emp.id,
        date=datetime.strptime(data.get("date"), "%Y-%m-%d").date(),
        start_time=datetime.strptime(data.get("start_time"), "%H:%M").time(),
        end_time=datetime.strptime(data.get("end_time"), "%H:%M").time()
    )
    db.session.add(att)
    db.session.commit()
    return jsonify({"id": att.id})

# Zobrazenie dochádzky
@app.route("/attendance/<int:employee_id>")
def show_attendance(employee_id):
    emp = Employee.query.get_or_404(employee_id)
    attendances = emp.attendances
    total_hours = sum([a.hours_worked() for a in attendances])

    return render_template_string("""
    <h1>Dochádzka: {{ emp.first_name }} {{ emp.last_name }}</h1>
    <p>Pracovisko: {{ emp.workplace }}</p>
    <table border="1">
        <tr><th>Dátum</th><th>Od</th><th>Do</th><th>Odpracované hodiny</th></tr>
        {% for a in attendances %}
        <tr>
            <td>{{ a.date }}</td>
            <td>{{ a.start_time }}</td>
            <td>{{ a.end_time }}</td>
            <td>{{ "%.2f"|format(a.hours_worked()) }}</td>
        </tr>
        {% endfor %}
    </table>
    <p>Spolu hodiny: {{ "%.2f"|format(total_hours) }}</p>
    """, emp=emp, attendances=attendances, total_hours=total_hours)
