
# ============================================================
# CONFIG — CHANGE THESE BEFORE DEPLOYING
# ============================================================
ADMIN_PASSWORD_HASH = "pbkdf2:sha256:260000$Kx8q2v9r$3b1c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3"  # generate with generate_password_hash('yourpassword')
SUBMISSIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'submissions.json')
MAX_FORM_LENGTH = 5000
RATE_LIMIT_WINDOW = 300  # seconds
RATE_LIMIT_MAX = 3       # submissions per window per IP
# ============================================================
