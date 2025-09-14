from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)

# DB connection z environment variable (Koyeb)
# Ak je DATABASE_URL vo formáte postgres://, SQLAlchemy ho potrebuje ako postgresql://
database_url = os.environ.get('DATABASE_URL', '')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# MODELS
class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    entries = db.relationship('Attendance', backref='employee', lazy=True)

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    entries = db.relationship('Attendance', backref='location', lazy=True)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)

# ROUTES
@app.route('/')
def index():
    return jsonify({'status': 'OK', 'message': 'Dochádzka API is running'})

@app.route('/employee/add', methods=['POST'])
def add_employee():
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({'error': 'Name required'}), 400
    emp = Employee(name=name)
    db.session.add(emp)
    db.session.commit()
    return jsonify({'id': emp.id, 'name': emp.name})

@app.route('/location/add', methods=['POST'])
def add_location():
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({'error': 'Name required'}), 400
    loc = Location(name=name)
    db.session.add(loc)
    db.session.commit()
    return jsonify({'id': loc.id, 'name': loc.name})

@app.route('/attendance/add', methods=['POST'])
def add_attendance():
    data = request.json
    emp_id = data.get('employee_id')
    loc_id = data.get('location_id')
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    if not all([emp_id, loc_id, start_time, end_time]):
        return jsonify({'error': 'Missing data'}), 400
    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)
    except:
        return jsonify({'error': 'Invalid datetime format'}), 400
    att = Attendance(employee_id=emp_id, location_id=loc_id,
                     start_time=start_dt, end_time=end_dt)
    db.session.add(att)
    db.session.commit()
    return jsonify({'id': att.id})

@app.route('/attendance/list', methods=['GET'])
def list_attendance():
    results = []
    atts = Attendance.query.all()
    for a in atts:
        results.append({
            'employee': a.employee.name,
            'location': a.location.name,
            'start_time': a.start_time.isoformat(),
            'end_time': a.end_time.isoformat(),
            'hours': (a.end_time - a.start_time).total_seconds() / 3600
        })
    return jsonify(results)

# CREATE DB TABLES
@app.before_first_request
def create_tables():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
