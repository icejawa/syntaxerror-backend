import sys, os
sys.path.insert(0, r"C:\Users\minec\AppData\Local\hermes\hermes-agent\venv\Lib\site-packages")

from flask import Flask, render_template, request, jsonify, abort, session, redirect, url_for
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import HTTPException
from datetime import datetime, timedelta
import json, os, re, secrets, ipaddress
from functools import wraps
from collections import defaultdict

app = Flask(__name__)
CORS(app)
app.config['CORS_ORIGINS'] = '*'  # Required for cross-origin fetch from Surge

# ==========================
# CONFIGURATION
# ==========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
SUBMISSIONS_FILE = os.path.join(DATA_DIR, 'submissions.json')
os.makedirs(DATA_DIR, exist_ok=True)

# Security: session secret (change this before deploying!)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

# Admin credentials — CHANGE THESE
ADMIN_PASSWORD_HASH = generate_password_hash('SyntaxBoss2026!')

# Rate limiting store
rate_limit_store = defaultdict(list)
RATE_LIMIT_WINDOW = 300  # 5 minutes
RATE_LIMIT_MAX = 5       # max submissions per window per IP

# Allowed roles
ALLOWED_ROLES = [
    'Security Researcher',
    'Hardware Specialist',
    'Web Developer',
    'Community Manager',
    'Tutorial Creator',
    'Syntax Error Ambassador'
]

# Maximum form field lengths
MAX_LENGTHS = {
    'discord': 80,
    'email': 120,
    'location': 100,
    'motivation': 5000,
    'experience': 5000,
    'referral': 200,
    'notes': 1000
}


# ==========================
# SECURITY MIDDLEWARE
# ==========================

@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self'"
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response


@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return jsonify({'error': e.description}), e.code
    return jsonify({'error': 'Internal server error'}), 500


# ==========================
# RATE LIMITING
# ==========================

def get_client_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'


def check_rate_limit(ip):
    now = datetime.now().timestamp()
    window_start = now - RATE_LIMIT_WINDOW
    rate_limit_store[ip] = [t for t in rate_limit_store[ip] if t > window_start]
    if len(rate_limit_store[ip]) >= RATE_LIMIT_MAX:
        return False
    rate_limit_store[ip].append(now)
    return True


# ==========================
# VALIDATION
# ==========================

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email)) and len(email) <= MAX_LENGTHS['email']


def validate_field(name, value):
    if name not in MAX_LENGTHS:
        return False
    if not isinstance(value, str):
        return False
    if len(value) > MAX_LENGTHS[name]:
        return False
    if name == 'email' and not validate_email(value):
        return False
    if name == 'age':
        try:
            age = int(value)
            return 13 <= age <= 99
        except (ValueError, TypeError):
            return False
    if name == 'hours':
        try:
            hours = int(value)
            return 1 <= hours <= 168
        except (ValueError, TypeError):
            return False
    if name == 'role' and value not in ALLOWED_ROLES:
        return False
    return True


def validate_submission(data):
    required = ['discord', 'email', 'age', 'location', 'role', 'motivation', 'hours']
    for field in required:
        if field not in data or not data[field]:
            return False, f'Missing required field: {field}'
    for field, value in data.items():
        if field in MAX_LENGTHS and not validate_field(field, value):
            return False, f'Invalid field: {field}'
    return True, 'OK'


# ==========================
# AUTH DECORATOR
# ==========================

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_authenticated'):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


# ==========================
# DATA LAYER
# ==========================

def load_submissions():
    if not os.path.exists(SUBMISSIONS_FILE):
        return []
    with open(SUBMISSIONS_FILE, 'r') as f:
        return json.load(f)


def save_submissions(subs):
    with open(SUBMISSIONS_FILE, 'w') as f:
        json.dump(subs, f, indent=2)


def save_submission(data):
    subs = load_submissions()
    data['id'] = len(subs) + 1
    data['timestamp'] = datetime.now().isoformat()
    data['status'] = 'pending'
    data['notes'] = ''
    subs.append(data)
    save_submissions(subs)
    return data


# ==========================
# PUBLIC ROUTES
# ==========================

@app.route('/')
def index():
    sub_count = len(load_submissions())
    return render_template('form.html', sub_count=sub_count)


@app.route('/submit', methods=['POST'])
def submit():
    ip = get_client_ip()
    if not check_rate_limit(ip):
        return jsonify({'success': False, 'error': 'Too many submissions. Try again later.'}), 429

    if not request.is_json:
        return jsonify({'success': False, 'error': 'Invalid content type'}), 400

    data = request.json
    valid, msg = validate_submission(data)
    if not valid:
        return jsonify({'success': False, 'error': msg}), 400

    # Sanitize input to prevent injection
    for key in data:
        if isinstance(data[key], str):
            data[key] = data[key][:MAX_LENGTHS.get(key, 5000)]

    result = save_submission(data)

    # Deliver to Discord webhook (fire-and-forget)
    try:
        import requests as req
        WEBHOOK_URL = 'https://discord.com/api/webhooks/1520520858152468560/WRF7HitP8jm9p4U-M91F1mUDkyy1z9hr6EbFFq9w4KrJ2i1c9K-rCyN1OTSfPoGOTOxY'
        embed = {
            'title': '📋 New Staff Application',
            'color': 0xc084fc,
            'fields': [
                {'name': 'Discord', 'value': data.get('discord', 'N/A'), 'inline': True},
                {'name': 'Email', 'value': data.get('email', 'N/A'), 'inline': True},
                {'name': 'Age', 'value': str(data.get('age', 'N/A')), 'inline': True},
                {'name': 'Location', 'value': data.get('location', 'N/A'), 'inline': True},
                {'name': 'Role', 'value': data.get('role', 'N/A'), 'inline': False},
                {'name': 'Hours/wk', 'value': str(data.get('hours', 'N/A')), 'inline': True},
                {'name': 'Referral', 'value': data.get('referral', 'N/A') or 'Not provided', 'inline': True},
                {'name': 'Motivation', 'value': (data.get('motivation', 'N/A') or 'N/A')[:1024], 'inline': False},
                {'name': 'Experience', 'value': (data.get('experience', '') or 'None provided')[:1024] or 'None provided', 'inline': False}
            ],
            'timestamp': datetime.now().isoformat()
        }
        req.post(WEBHOOK_URL, json={'embeds': [embed]}, timeout=5)
    except Exception:
        pass  # Webhook failure shouldn't block submission

    return jsonify({'success': True, 'id': result['id']})


# ==========================
# ADMIN ROUTES
# ==========================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['admin_authenticated'] = True
            session.permanent = True
            app.permanent_session_lifetime = timedelta(hours=8)
            return redirect(url_for('admin'))
        return render_template('login.html', error='Invalid credentials')
    if session.get('admin_authenticated'):
        return redirect(url_for('admin'))
    return render_template('login.html')


@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('admin_authenticated', None)
    return redirect(url_for('admin_login'))


@app.route('/admin')
@require_admin
def admin():
    subs = load_submissions()
    return render_template('admin.html', submissions=subs)


@app.route('/api/admin/submissions')
@require_admin
def api_submissions():
    return jsonify(load_submissions())


@app.route('/api/admin/submission/<int:sub_id>', methods=['PATCH'])
@require_admin
def update_submission(sub_id):
    subs = load_submissions()
    for sub in subs:
        if sub['id'] == sub_id:
            if 'status' in request.json:
                status = request.json['status']
                if status not in ('pending', 'accepted', 'rejected'):
                    return jsonify({'success': False, 'error': 'Invalid status'}), 400
                sub['status'] = status
            if 'notes' in request.json:
                notes = request.json['notes']
                if len(notes) > 1000:
                    return jsonify({'success': False, 'error': 'Notes too long'}), 400
                sub['notes'] = notes
            save_submissions(subs)
            return jsonify({'success': True})
    return jsonify({'success': False}), 404





# ==========================
# BLOCKED ROUTES
# ==========================

@app.route('/submissions.json')
def block_json():
    abort(403)


@app.route('/data')
def block_data():
    abort(403)


# ==========================
# MAIN
# ==========================

if __name__ == '__main__':
    print(f"[*] Syntax Error Staff App starting on http://0.0.0.0:5000")
    print(f"[*] Admin: http://localhost:5000/admin/login")
    print(f"[*] Form:  http://localhost:5000/")
    app.run(host='0.0.0.0', port=5000, debug=False)
