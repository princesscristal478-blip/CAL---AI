"""
Cal AI – Authentication & Security Module
==========================================
  • PBKDF2-SHA256 password hashing (Werkzeug, 260k iterations)
  • Password strength validation + common-password blocklist
  • Account lockout after 5 failed attempts (15-min lock)
  • Login-attempt logging (IP + email)
  • TOTP Two-Factor Authentication (Google Authenticator)
  • Secure password-reset tokens (SHA-256, 60-min expiry, single-use)
  • HTML email via SMTP (Gmail app-password or any SMTP provider)
"""

import os, re, secrets, hashlib, smtplib, io, base64
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pyotp, qrcode
from werkzeug.security import generate_password_hash, check_password_hash as _check
from flask import session
from database.db import get_db

# ── Config ────────────────────────────────────────────────────────────────────
MAX_FAILED   = 5
LOCKOUT_MINS = 15
RESET_EXPIRY = 60   # minutes
MIN_PW_LEN   = 8

COMMON_PASSWORDS = {
    "password","123456","12345678","qwerty","abc123","monkey","letmein",
    "trustno1","dragon","iloveyou","master","sunshine","passw0rd","shadow",
    "123123","superman","football","password1","password123","admin","welcome",
    "hello","qwerty123","1q2w3e4r","zxcvbnm","123456789","1234567890",
}

# ── Password ──────────────────────────────────────────────────────────────────
def hash_password(p):
    return generate_password_hash(p, method='pbkdf2:sha256', salt_length=16)

def check_password(p, h):
    return _check(h, p)

def validate_password(p):
    if len(p) < MIN_PW_LEN:
        return f"Password must be at least {MIN_PW_LEN} characters."
    if not re.search(r'[A-Z]', p):
        return "Need at least one uppercase letter (A-Z)."
    if not re.search(r'[a-z]', p):
        return "Need at least one lowercase letter (a-z)."
    if not re.search(r'\d', p):
        return "Need at least one number."
    if not re.search(r'[^A-Za-z0-9]', p):
        return "Need at least one special character (!@#$%^&* etc.)."
    if p.lower() in COMMON_PASSWORDS:
        return "That password is too common. Please choose a stronger one."
    return None

def password_strength_score(p):
    score = 0
    if len(p) >= 8:  score += 1
    if len(p) >= 12: score += 1
    if re.search(r'[A-Z]', p) and re.search(r'[a-z]', p): score += 1
    if re.search(r'\d', p) and re.search(r'[^A-Za-z0-9]', p): score += 1
    labels = {0:'Very Weak',1:'Weak',2:'Fair',3:'Good',4:'Strong'}
    colors = {0:'#ef4444',1:'#f97316',2:'#eab308',3:'#22c55e',4:'#16a34a'}
    return {'score':score,'label':labels[score],'color':colors[score]}

# ── Lockout helpers ───────────────────────────────────────────────────────────
def _record_attempt(email, ip, success):
    db = get_db()
    db.execute('INSERT INTO login_attempts (ip_address,email,success) VALUES (%s,%s,%s)',
               (ip, email, 1 if success else 0))
    db.commit()

def _check_lockout(user):
    if not user.get('is_locked'):
        return None
    locked_until = user.get('locked_until')
    if locked_until and datetime.now() < locked_until:
        mins = int((locked_until - datetime.now()).total_seconds() / 60) + 1
        return f"Account locked after too many failed attempts. Try again in {mins} minute(s)."
    db = get_db()
    db.execute('UPDATE users SET is_locked=0,failed_attempts=0,locked_until=NULL WHERE id=%s', (user['id'],))
    db.commit()
    return None

def _on_failed(user):
    db = get_db()
    attempts = (user.get('failed_attempts') or 0) + 1
    locked, locked_until = 0, None
    if attempts >= MAX_FAILED:
        locked = 1
        locked_until = datetime.now() + timedelta(minutes=LOCKOUT_MINS)
    db.execute('UPDATE users SET failed_attempts=%s,is_locked=%s,locked_until=%s WHERE id=%s',
               (attempts, locked, locked_until, user['id']))
    db.commit()

def _on_success(user, ip):
    db = get_db()
    db.execute('UPDATE users SET failed_attempts=0,is_locked=0,locked_until=NULL,last_login=%s,last_login_ip=%s WHERE id=%s',
               (datetime.now(), ip, user['id']))
    db.commit()

# ── Register / Login / Logout ─────────────────────────────────────────────────
def register_user(username, email, password, age, weight, height, gender, goal, activity='moderate'):
    err = validate_password(password)
    if err:
        return None, err
    db = get_db()
    if db.execute('SELECT id FROM users WHERE email=%s OR username=%s', (email,username)).fetchone():
        return None, "Email or username already exists."
    cur = db.execute(
        'INSERT INTO users (username,email,password_hash,age,weight,height,gender,goal,activity) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
        (username, email, hash_password(password), age, weight, height, gender, goal, activity))
    db.commit()
    return db.execute('SELECT * FROM users WHERE id=%s', (cur.lastrowid,)).fetchone(), None

def login_user(email, password, ip='0.0.0.0'):
    if not email or not password:
        return None, "Email and password are required."
    db   = get_db()
    user = db.execute('SELECT * FROM users WHERE email=%s', (email,)).fetchone()
    if not user:
        _record_attempt(email, ip, False)
        return None, "Invalid email or password."
    lock_err = _check_lockout(user)
    if lock_err:
        _record_attempt(email, ip, False)
        return None, lock_err
    if not check_password(password, user['password_hash']):
        _on_failed(user)
        _record_attempt(email, ip, False)
        left = MAX_FAILED - ((user.get('failed_attempts') or 0) + 1)
        if left > 0:
            return None, f"Invalid email or password. {left} attempt(s) left before lockout."
        return None, "Too many failed attempts. Account locked for 15 minutes."
    _record_attempt(email, ip, True)
    _on_success(user, ip)
    return db.execute('SELECT * FROM users WHERE id=%s', (user['id'],)).fetchone(), None

def logout_user():
    session.clear()

# ── Two-Factor Auth (TOTP) ────────────────────────────────────────────────────
def generate_totp_secret():
    return pyotp.random_base32()

def get_totp_uri(secret, email):
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name='Cal AI')

def generate_totp_qr_b64(secret, email):
    img = qrcode.make(get_totp_uri(secret, email))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()

def verify_totp(secret, code):
    return pyotp.TOTP(secret).verify(code, valid_window=1)

def enable_totp(user_id, secret, code):
    if not verify_totp(secret, code):
        return False, "Invalid code. Please try again."
    db = get_db()
    db.execute('UPDATE users SET totp_secret=%s,totp_enabled=1 WHERE id=%s', (secret, user_id))
    db.commit()
    return True, "Two-factor authentication enabled!"

def disable_totp(user_id, password):
    db   = get_db()
    user = db.execute('SELECT password_hash FROM users WHERE id=%s', (user_id,)).fetchone()
    if not user or not check_password(password, user['password_hash']):
        return False, "Incorrect password."
    db.execute('UPDATE users SET totp_secret=NULL,totp_enabled=0 WHERE id=%s', (user_id,))
    db.commit()
    return True, "Two-factor authentication disabled."

def create_2fa_pending(user_id):
    token = secrets.token_urlsafe(32)
    db    = get_db()
    db.execute('DELETE FROM two_factor_pending WHERE user_id=%s', (user_id,))
    db.execute('INSERT INTO two_factor_pending (user_id,token,expires_at) VALUES (%s,%s,%s)',
               (user_id, token, datetime.now() + timedelta(minutes=5)))
    db.commit()
    return token

def resolve_2fa_pending(token):
    db  = get_db()
    rec = db.execute('SELECT user_id,expires_at FROM two_factor_pending WHERE token=%s', (token,)).fetchone()
    if not rec:
        return None
    if datetime.now() > rec['expires_at']:
        db.execute('DELETE FROM two_factor_pending WHERE token=%s', (token,))
        db.commit()
        return None
    db.execute('DELETE FROM two_factor_pending WHERE token=%s', (token,))
    db.commit()
    return rec['user_id']

# ── Password Reset ─────────────────────────────────────────────────────────────
def _hash_tok(raw):
    return hashlib.sha256(raw.encode()).hexdigest()

def create_reset_token(email):
    db   = get_db()
    user = db.execute('SELECT id FROM users WHERE email=%s', (email,)).fetchone()
    if not user:
        return None, "No account found with that email address."
    db.execute('UPDATE password_reset_tokens SET used=1 WHERE user_id=%s', (user['id'],))
    raw   = secrets.token_urlsafe(48)
    db.execute('INSERT INTO password_reset_tokens (user_id,token_hash,expires_at) VALUES (%s,%s,%s)',
               (user['id'], _hash_tok(raw), datetime.now() + timedelta(minutes=RESET_EXPIRY)))
    db.commit()
    return raw, None

def verify_reset_token(raw):
    db  = get_db()
    rec = db.execute(
        'SELECT prt.user_id,prt.expires_at,prt.used,u.email,u.username '
        'FROM password_reset_tokens prt JOIN users u ON prt.user_id=u.id '
        'WHERE prt.token_hash=%s', (_hash_tok(raw),)
    ).fetchone()
    if not rec or rec['used'] or datetime.now() > rec['expires_at']:
        return None
    return rec

def consume_reset_token(raw, new_password):
    rec = verify_reset_token(raw)
    if not rec:
        return False, "This reset link is invalid or expired. Please request a new one."
    err = validate_password(new_password)
    if err:
        return False, err
    db = get_db()
    db.execute('UPDATE users SET password_hash=%s,failed_attempts=0,is_locked=0 WHERE id=%s',
               (hash_password(new_password), rec['user_id']))
    db.execute('UPDATE password_reset_tokens SET used=1 WHERE token_hash=%s', (_hash_tok(raw),))
    db.commit()
    return True, "Password updated! You can now sign in."

# ── Email ──────────────────────────────────────────────────────────────────────
def send_email(to, subject, html_body):
    cfg = {
        'host': os.environ.get('MAIL_HOST','smtp.gmail.com'),
        'port': int(os.environ.get('MAIL_PORT', 587)),
        'user': os.environ.get('MAIL_USER',''),
        'pw':   os.environ.get('MAIL_PASSWORD',''),
        'from': os.environ.get('MAIL_FROM', os.environ.get('MAIL_USER','noreply@calai.app')),
    }
    if not cfg['user'] or not cfg['pw']:
        return False, "Email not configured. Set MAIL_USER and MAIL_PASSWORD in .env"
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = f"Cal AI <{cfg['from']}>"
    msg['To']      = to
    msg.attach(MIMEText(html_body, 'html'))
    try:
        with smtplib.SMTP(cfg['host'], cfg['port'], timeout=10) as s:
            s.ehlo(); s.starttls(); s.login(cfg['user'], cfg['pw'])
            s.sendmail(cfg['from'], to, msg.as_string())
        return True, ""
    except smtplib.SMTPAuthenticationError:
        return False, "Email auth failed. Check MAIL_USER / MAIL_PASSWORD."
    except Exception as e:
        return False, f"Email error: {e}"

def send_reset_email(to, username, raw_token, base_url):
    url  = f"{base_url}/reset-password/{raw_token}"
    html = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;background:#0f172a;padding:2rem">
<div style="max-width:480px;margin:0 auto;background:#1e293b;border-radius:16px;padding:2rem;color:#f1f5f9">
  <div style="font-size:2rem">🥗 Cal AI</div>
  <h2 style="color:#22c55e">Reset Your Password</h2>
  <p>Hi <strong>{username}</strong>,</p>
  <p>Click below to reset your password. This link expires in <strong>60 minutes</strong>.</p>
  <a href="{url}" style="display:inline-block;margin:1rem 0;padding:.9rem 2rem;background:#22c55e;
     color:#fff;text-decoration:none;border-radius:12px;font-weight:700">Reset Password</a>
  <p style="color:#94a3b8;font-size:.85rem">If you didn't request this, ignore this email.</p>
  <p style="color:#64748b;font-size:.78rem;word-break:break-all">{url}</p>
</div></body></html>"""
    return send_email(to, "Reset your Cal AI password", html)
