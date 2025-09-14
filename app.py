from flask import Flask, render_template_string, request, redirect
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://koyeb-adm:npg_wzo2Xd3SAZYF@ep-cold-cloud-a2abkwup.eu-central-1.pg.koyeb.app/koyebdb'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Model pre Talcilod položky
class Item(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  name = db.Column(db.String(50), nullable=False)

with app.app_context():
    db.create_all()

# Hlavná stránka
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        name = request.form.get("name")
        if name:
            new_item = Item(name=name)
            db.session.add(new_item)
            db.session.commit()
            return redirect("/")
    
    items = Item.query.all()
    return render_template_string("""
        <h1>Talcilod Items</h1>
        <form method="POST">
            <input type="text" name="name" placeholder="Enter name">
            <button type="submit">Add</button>
        </form>
        <ul>
        {% for item in items %}
            <li>{{ item.name }}</li>
        {% endfor %}
        </ul>
    """, items=items)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
