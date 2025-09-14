import os
from flask import Flask, request, render_template_string, redirect
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# Získame URL databázy z environment premennej
database_url = os.environ.get("DATABASE_URL", "postgresql://user:pass@localhost/dbname")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "fallback_secret")

# Inicializácia SQLAlchemy
db = SQLAlchemy(app)

# Model pre zamestnanca
class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    surname = db.Column(db.String(50), nullable=False)

with app.app_context():
    db.create_all()

# Hlavná stránka s formulárom
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
        <form method="POST">
            <input name="name" placeholder="Meno">
            <input name="surname" placeholder="Priezvisko">
            <button type="submit">Pridaj zamestnanca</button>
        </form>

        <h2>Všetci zamestnanci</h2>
        <ul>
        {% for emp in employees %}
            <li>{{ emp.name }} {{ emp.surname }}</li>
        {% endfor %}
        </ul>
    """, employees=employees)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
