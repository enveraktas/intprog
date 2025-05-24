from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode
import io
import base64
import uuid
from functools import wraps
from sqlalchemy import func

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///visitors.db'
app.config['SECRET_KEY'] = 'gizli_anahtar'
db = SQLAlchemy(app)

class Visitor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    surname = db.Column(db.String(100))
    visit_date = db.Column(db.DateTime)
    exit_date = db.Column(db.DateTime, nullable=True)
    visit_duration = db.Column(db.Integer)  # dakika cinsinden
    qr_token = db.Column(db.String(100), unique=True, nullable=True)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)




def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password, password):
            session['admin'] = True
            session['admin_username'] = admin.username
            flash('Başarıyla giriş yaptınız.', 'success')
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Hatalı kullanıcı adı veya şifre!")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('admin', None)
    session.pop('admin_username', None)
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    query = Visitor.query
    name = ''
    surname = ''
    visit_date = ''
    exit_date = ''
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        surname = request.form.get('surname', '').strip()
        visit_date = request.form.get('visit_date', '').strip()
        exit_date = request.form.get('exit_date', '').strip()
        if name:
            query = query.filter(Visitor.name.ilike(f"%{name}%"))
        if surname:
            query = query.filter(Visitor.surname.ilike(f"%{surname}%"))
        if visit_date:
            from datetime import datetime
            date_obj = datetime.strptime(visit_date, '%Y-%m-%d')
            query = query.filter(db.func.date(Visitor.visit_date) == date_obj.date())
        if exit_date:
            from datetime import datetime
            date_obj = datetime.strptime(exit_date, '%Y-%m-%d')
            query = query.filter(db.func.date(Visitor.exit_date) == date_obj.date())
    visitors = query.order_by(Visitor.visit_date.desc()).all()
    return render_template('index.html', visitors=visitors, name=name, surname=surname, visit_date=visit_date, exit_date=exit_date)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_visitor():
    if request.method == 'POST':
        name = request.form['name']
        surname = request.form['surname']
        visit_date = request.form['visit_date']
        from datetime import datetime
        visit_date_obj = datetime.strptime(visit_date, '%Y-%m-%dT%H:%M')
        qr_token = str(uuid.uuid4())
        visitor = Visitor(name=name, surname=surname, visit_date=visit_date_obj, visit_duration=0, qr_token=qr_token)
        db.session.add(visitor)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('add_visitor.html')

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_visitor(id):
    visitor = Visitor.query.get_or_404(id)
    if request.method == 'POST':
        visitor.name = request.form['name']
        visitor.surname = request.form['surname']
        visit_date = request.form['visit_date']
        exit_date = request.form.get('exit_date')
        from datetime import datetime
        visitor.visit_date = datetime.strptime(visit_date, '%Y-%m-%dT%H:%M')
        if exit_date:
            visitor.exit_date = datetime.strptime(exit_date, '%Y-%m-%dT%H:%M')
            delta = visitor.exit_date - visitor.visit_date
            visitor.visit_duration = int(delta.total_seconds() // 60)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('edit_visitor.html', visitor=visitor)

@app.route('/delete/<int:id>')
@login_required
def delete_visitor(id):
    visitor = Visitor.query.get_or_404(id)
    db.session.delete(visitor)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # Aynı kullanıcı adı var mı kontrol et
        if Admin.query.filter_by(username=username).first():
            return render_template('register.html', error='Bu kullanıcı adı zaten alınmış!')
        hashed_password = generate_password_hash(password)
        admin = Admin(username=username, password=hashed_password)
        db.session.add(admin)
        db.session.commit()
        flash('Kayıt başarılı! Giriş yapabilirsiniz.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/visitor/<int:id>/qrcode')
@login_required
def visitor_qrcode(id):
    visitor = Visitor.query.get_or_404(id)
    if not visitor.qr_token:
        return "QR kodu bulunamadı", 404
    # QR kodu oluştur
    img = qrcode.make(visitor.qr_token)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return render_template('visitor_qrcode.html', visitor=visitor, img_b64=img_b64)

@app.route('/report')
@login_required
def report():
    # Günlük ziyaretçi sayısı
    stats = db.session.query(
        func.date(Visitor.visit_date),
        func.count(Visitor.id)
    ).group_by(func.date(Visitor.visit_date)).order_by(func.date(Visitor.visit_date)).all()
    # Chart.js için veri hazırla
    labels = [str(row[0]) for row in stats]
    counts = [row[1] for row in stats]
    return render_template('report.html', labels=labels, counts=counts)

@app.route('/visitor/<int:id>')
@login_required
def visitor_detail(id):
    visitor = Visitor.query.get_or_404(id)
    # Aynı isim ve soyad ile geçmiş ziyaretler (bu kaydı hariç)
    past_visits = Visitor.query.filter(
        Visitor.name == visitor.name,
        Visitor.surname == visitor.surname,
        Visitor.id != visitor.id
    ).order_by(Visitor.visit_date.desc()).all()
    return render_template('visitor_detail.html', visitor=visitor, past_visits=past_visits)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)