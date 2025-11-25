import os
import datetime

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change_this_secret_key'

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

analyzer = SentimentIntensityAnalyzer()

class User(db.Model, UserMixin):
    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(120))
    email    = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role     = db.Column(db.String(20), default='user')  # 'user' or 'admin'

class Complaint(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    name        = db.Column(db.String(120))
    email       = db.Column(db.String(120))
    anonymous   = db.Column(db.Boolean, default=False)
    category    = db.Column(db.String(120))
    department  = db.Column(db.String(120))
    ctype       = db.Column(db.String(50))
    description = db.Column(db.Text)
    sentiment   = db.Column(db.String(20))
    priority    = db.Column(db.String(20), default='Normal')
    status      = db.Column(db.String(50), default='Submitted')
    created_at  = db.Column(db.DateTime, default=datetime.datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

PRIORITY_KEYWORDS = [
    'urgent', 'immediately', 'asap', 'safety', 'harass',
    'danger', 'broken', 'fire', 'accident', 'ragging'
]

def detect_priority(text: str) -> str:
    text = text.lower()
    for word in PRIORITY_KEYWORDS:
        if word in text:
            return 'High'
    return 'Normal'

def get_sentiment(text: str) -> str:
    vs = analyzer.polarity_scores(text)
    if vs['compound'] >= 0.05:
        return 'Positive'
    elif vs['compound'] <= -0.05:
        return 'Negative'
    return 'Neutral'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name     = request.form.get('name')
        email    = request.form.get('email')
        password = request.form.get('password')

        if User.query.filter_by(email=email).first():
            flash('Email already registered.')
            return redirect(url_for('register'))

        user = User(name=name, email=email, password=password, role='user')
        db.session.add(user)
        db.session.commit()
        flash('Registration successful. Please login.')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email, password=password).first()
        if not user:
            flash('Invalid credentials')
            return redirect(url_for('login'))

        login_user(user)
        return redirect(url_for('index'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/submit', methods=['GET', 'POST'])
def submit():
    departments = ['Academics', 'Hostel', 'Mess', 'Library', 'IT Support', 'Facilities', 'Administration']
    categories  = ['Infrastructure', 'Faculty', 'Mess Food', 'Ragging', 'Harassment', 'WiFi', 'Other']

    if request.method == 'POST':
        name       = request.form.get('name') or 'Anonymous'
        email      = request.form.get('email') or ''
        anonymous  = request.form.get('anonymous') == 'on'
        ctype      = request.form.get('ctype') or 'complaint'
        category   = request.form.get('category') or 'General'
        department = request.form.get('department') or 'General'
        desc       = request.form.get('description') or ''

        if anonymous:
            name  = 'Anonymous'
            email = ''

        sentiment = get_sentiment(desc)
        priority  = detect_priority(desc)

        user_id = current_user.id if current_user.is_authenticated else None

        comp = Complaint(
            user_id     = user_id,
            name        = name,
            email       = email,
            anonymous   = anonymous,
            category    = category,
            department  = department,
            ctype       = ctype,
            description = desc,
            sentiment   = sentiment,
            priority    = priority,
            status      = 'Submitted'
        )
        db.session.add(comp)
        db.session.commit()

        flash(f'Submitted successfully. Reference ID: {comp.id}')
        return redirect(url_for('submit'))

    return render_template(
        'submit.html',
        departments=departments,
        categories=categories
    )

@app.route('/dashboard')
@login_required
def dashboard():
    complaints = Complaint.query.filter_by(user_id=current_user.id).order_by(
        Complaint.created_at.desc()
    ).all()
    return render_template('dashboard.html', complaints=complaints)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email    = request.form.get('email')
        password = request.form.get('password')

        admin = User.query.filter_by(email=email, password=password, role='admin').first()
        if not admin:
            flash('Invalid admin credentials')
            return redirect(url_for('admin_login'))

        login_user(admin)
        return redirect(url_for('admin_panel'))

    return render_template('admin_login.html')

@app.route('/admin/panel')
@login_required
def admin_panel():
    if current_user.role != 'admin':
        flash('Unauthorized')
        return redirect(url_for('index'))

    complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()

    total = len(complaints)
    pending = sum(1 for c in complaints if c.status != 'Resolved')
    resolved = sum(1 for c in complaints if c.status == 'Resolved')

    return render_template(
        'admin_dashboard.html',
        complaints=complaints,
        total=total,
        pending=pending,
        resolved=resolved
    )

@app.route('/admin/complaint/<int:cid>', methods=['POST'])
@login_required
def update_complaint_status(cid):
    if current_user.role != 'admin':
        flash('Unauthorized')
        return redirect(url_for('index'))

    comp = Complaint.query.get_or_404(cid)
    new_status = request.form.get('status')
    comp.status = new_status
    db.session.commit()

    flash('Status updated')
    return redirect(url_for('admin_panel'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(role='admin').first():
            admin = User(
                name='Administrator',
                email='admin@example.com',
                password='admin',
                role='admin'
            )
            db.session.add(admin)
            db.session.commit()
    app.run(debug=True)
