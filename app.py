import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# -------------------- KONFIGURÁCIA --------------------
database_url = os.environ['DATABASE_URL']

# Ak URL začína "postgres://", nahraď ju správnym prefixom pre psycopg 3
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Tajný kľúč pre Flask sessions
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'devkey')

# Inicializácia databázy
db = SQLAlchemy(app)
# -------------------- MODELY --------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)

# -------------------- ROUTES --------------------
@app.route('/')
def index():
    users = User.query.all()
    return render_template('index.html', users=users)

@app.route('/add', methods=['POST'])
def add_user():
    username = request.form.get('username')
    if username:
        user = User(username=username)
        db.session.add(user)
        db.session.commit()
    return "User added!"

# -------------------- SPAUSTENIE --------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
