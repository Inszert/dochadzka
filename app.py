from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)

# DB connection z environment variable (Koyeb)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')  # PostgreSQL URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# MODELS
class Employee(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  name = db.Column(db.String(100), nullable=False)

class Location(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  name = db.Column(db.String(100), nullable=False)

class Attendance(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
  location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=False)
  start_time = db.Column(db.DateTime, nullable=False)
  end_time = db.Column(db.DateTime, nullable=False)

# ROUTES
@app.route('/')
def index():
  return "Dochádzka API je živá!"

@app.route('/employee/add', methods=['POST'])
def add_employee():
  data = request.json
  if not data or 'name' not in data:
    return jsonify({'error': 'Missing name'}), 400
  emp = Employee(name=data['name'])
  db.session.add(emp)
  db.session.commit()
  return jsonify({'id': emp.id, 'name': emp.name})

@app.route('/location/add', methods=['POST'])
def add_location():
  data = request.json
  if not data or 'name' not in data:
    return jsonify({'error': 'Missing name'}), 400
  loc = Location(name=data['name'])
  db.session.add(loc)
  db.session.commit()
  return jsonify({'id': loc.id, 'name': loc.name})

@app.route('/attendance/add', methods=['POST'])
def add_attendance():
  data = request.json
  try:
    att = Attendance(
      employee_id = data['employee_id'],
      location_id = data['location_id'],
      start_time = datetime.fromisoformat(data['start_time']),
      end_time = datetime.fromisoformat(data['end_time'])
    )
    db.session.add(att)
    db.session.commit()
    return jsonify({'id': att.id})
  except Exception as e:
    return jsonify({'error': str(e)}), 400

@app.route('/attendance/list', methods=['GET'])
def list_attendance():
  records = Attendance.query.all()
  result = []
  for r in records:
    result.append({
      'employee_id': r.employee_id,
      'employee_name': Employee.query.get(r.employee_id).name,
      'location_id': r.location_id,
      'location_name': Location.query.get(r.location_id).name,
      'start_time': r.start_time.isoformat(),
      'end_time': r.end_time.isoformat()
    })
  return jsonify(result)

if __name__ == '__main__':
  # vytvor DB tables, ak ešte neexistujú
  with app.app_context():
    db.create_all()
  app.run(host='0.0.0.0', port=8000, debug=True)
