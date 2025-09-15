from extensions import db
from datetime import datetime

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    surname = db.Column(db.String(50), nullable=False)
    # workplace removed from here

    def __repr__(self):
        return f'<Employee {self.name} {self.surname}>'

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    work_location = db.Column(db.String(100), nullable=False)  # workplace moved here
    
    employee = db.relationship("Employee", backref="attendances")

    def hours_worked(self):
        start = datetime.combine(self.date, self.start_time)
        end = datetime.combine(self.date, self.end_time)
        delta = end - start
        return round(delta.total_seconds() / 3600, 2)

    def __repr__(self):
        return f'<Attendance {self.employee_id} {self.date}>'