from extensions import db
from datetime import datetime

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    surname = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f'<Employee {self.name} {self.surname}>'

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=True)  # Changed to allow NULL
    work_location = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='active')  # active, completed
    
    employee = db.relationship("Employee", backref="attendances")

    def hours_worked(self):
        if self.end_time:
            start = datetime.combine(self.date, self.start_time)
            end = datetime.combine(self.date, self.end_time)
            delta = end - start
            return round(delta.total_seconds() / 3600, 2)
        return 0

    def __repr__(self):
        return f'<Attendance {self.employee_id} {self.date}>'