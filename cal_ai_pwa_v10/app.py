from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory
from database.db import init_db, get_db
from auth.auth import (register_user, login_user, logout_user,
    validate_password, password_strength_score,
    generate_totp_secret, generate_totp_qr_b64, verify_totp, enable_totp, disable_totp,
    create_2fa_pending, resolve_2fa_pending,
    create_reset_token, verify_reset_token, consume_reset_token, send_reset_email)
from ml.predictor import predict_calories, get_food_suggestions
from functools import wraps
import os, json, base64, requests

# ── Load .env FIRST so all os.environ.get() calls below pick up the values ───
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'), override=False)
except ImportError:
    # dotenv not installed — manually parse .env so the app still works
    _env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(_env_path):
        with open(_env_path) as _ef:
            for _line in _ef:
                _line = _line.strip()
                if _line and not _line.startswith('#') and '=' in _line:
                    _k, _, _v = _line.partition('=')
                    if _k.strip() not in os.environ:          # don't override real env vars
                        os.environ[_k.strip()] = _v.strip()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')  # Set your Groq API key here
GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'

# VAPID keys for push notifications
# VAPID keys are auto-generated on first run using the cryptography library.
# ── VAPID Keys ────────────────────────────────────────────────────────────────
_VAPID_PUBLIC  = os.environ.get('VAPID_PUBLIC_KEY',  '').strip()
_VAPID_PRIVATE = os.environ.get('VAPID_PRIVATE_KEY', '').strip()

# Auto-generate VAPID keys on first run if not set in .env
_VAPID_PLACEHOLDERS = {'', 'YOUR_VAPID_PUBLIC_KEY_HERE', 'YOUR_VAPID_PUBLIC_KEY',
                        'YOUR_VAPID_PRIVATE_KEY_HERE', 'YOUR_VAPID_PRIVATE_KEY'}
if _VAPID_PUBLIC in _VAPID_PLACEHOLDERS or _VAPID_PRIVATE in _VAPID_PLACEHOLDERS:
    try:
        import base64 as _b64
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.backends import default_backend

        def _generate_vapid_keys():
            """
            Generate VAPID key pair directly using cryptography library.
            Returns (public_key_urlsafe_b64, private_key_urlsafe_b64).
            This avoids py-vapid 1.x/2.x API incompatibilities entirely.
            """
            private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
            private_numbers = private_key.private_numbers()
            private_int = private_numbers.private_value
            private_bytes = private_int.to_bytes(32, byteorder='big')
            private_b64 = _b64.urlsafe_b64encode(private_bytes).rstrip(b'=').decode()

            public_key = private_key.public_key()
            public_numbers = public_key.public_numbers()
            # Uncompressed EC point: 0x04 + x (32 bytes) + y (32 bytes)
            x_bytes = public_numbers.x.to_bytes(32, byteorder='big')
            y_bytes = public_numbers.y.to_bytes(32, byteorder='big')
            public_bytes = b'\x04' + x_bytes + y_bytes
            public_b64 = _b64.urlsafe_b64encode(public_bytes).rstrip(b'=').decode()

            return public_b64, private_b64

        _VAPID_PUBLIC, _VAPID_PRIVATE = _generate_vapid_keys()

        os.environ['VAPID_PUBLIC_KEY']  = _VAPID_PUBLIC
        os.environ['VAPID_PRIVATE_KEY'] = _VAPID_PRIVATE

        # Persist to .env so they survive restarts
        _env_path = os.path.join(os.path.dirname(__file__), '.env')
        if os.path.exists(_env_path):
            with open(_env_path, 'r') as _f:
                _env_content = _f.read()
            for _ph in ('YOUR_VAPID_PUBLIC_KEY_HERE', 'YOUR_VAPID_PUBLIC_KEY', ''):
                if _ph:
                    _env_content = _env_content.replace(f'VAPID_PUBLIC_KEY={_ph}',
                                                        f'VAPID_PUBLIC_KEY={_VAPID_PUBLIC}')
            for _ph in ('YOUR_VAPID_PRIVATE_KEY_HERE', 'YOUR_VAPID_PRIVATE_KEY', ''):
                if _ph:
                    _env_content = _env_content.replace(f'VAPID_PRIVATE_KEY={_ph}',
                                                        f'VAPID_PRIVATE_KEY={_VAPID_PRIVATE}')
            with open(_env_path, 'w') as _f:
                _f.write(_env_content)
        print(f'[VAPID] ✅ Auto-generated VAPID keys. Public: {_VAPID_PUBLIC[:20]}...')
    except ImportError:
        print('[VAPID] ❌ cryptography library hindi naka-install!')
        print('[VAPID]   I-install: pip install cryptography pywebpush')
    except Exception as _e:
        print(f'[VAPID] ❌ Key generation failed: {_e}')
        import traceback; traceback.print_exc()

VAPID_PUBLIC_KEY  = _VAPID_PUBLIC
VAPID_PRIVATE_KEY = _VAPID_PRIVATE
VAPID_CLAIMS      = {"sub": "mailto:admin@calai.app"}

def _send_webpush(subscription_info, data_dict):
    """Send a Web Push notification. Returns (ok: bool, error: str|None)."""
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return False, 'pywebpush hindi naka-install. I-run: pip install pywebpush'
    if not VAPID_PRIVATE_KEY:
        return False, 'VAPID keys hindi pa na-generate. I-restart ang server.'
    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(data_dict),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS,
        )
        return True, None
    except Exception as e:
        err = str(e)
        status = None
        if hasattr(e, 'response') and e.response is not None:
            status = e.response.status_code
        if status in (404, 410) or '410' in err or '404' in err:
            return False, 'SUBSCRIPTION_EXPIRED'
        return False, err

with app.app_context():
    init_db()

# ─── PWA Files ──────────────────────────────────────────────────────────────

@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def service_worker():
    response = send_from_directory('static/js', 'sw.js')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response

# ─── Auth Decorator ──────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ─── Auth Routes ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/offline')
def offline():
    return render_template('offline.html')

@app.route('/offline-dashboard')
def offline_dashboard():
    """Standalone offline dashboard — served from SW cache, reads IndexedDB."""
    return render_template('offline_dashboard.html')

@app.route('/api/dashboard-cache')
@login_required
def api_dashboard_cache():
    """Returns the current user's dashboard data as JSON so the SW can cache it."""
    db  = get_db()
    uid = session['user_id']

    today_logs = db.execute('''
        SELECT fl.id, fl.quantity, fl.meal_type,
               f.name, f.calories, f.protein, f.carbs, f.fat, f.category
        FROM food_logs fl JOIN foods f ON fl.food_id = f.id
        WHERE fl.user_id = %s AND DATE(fl.logged_at) = CURDATE()
        ORDER BY fl.logged_at DESC
    ''', (uid,)).fetchall()

    totals = db.execute('''
        SELECT
            COALESCE(SUM(f.calories * fl.quantity / 100), 0) as total_cal,
            COALESCE(SUM(f.protein  * fl.quantity / 100), 0) as total_protein,
            COALESCE(SUM(f.carbs    * fl.quantity / 100), 0) as total_carbs,
            COALESCE(SUM(f.fat      * fl.quantity / 100), 0) as total_fat
        FROM food_logs fl JOIN foods f ON fl.food_id = f.id
        WHERE fl.user_id = %s AND DATE(fl.logged_at) = CURDATE()
    ''', (uid,)).fetchone()

    user = db.execute('SELECT * FROM users WHERE id = %s', (uid,)).fetchone()
    goal_calories = calculate_goal(user)

    return jsonify({
        'totals': dict(totals),
        'today_logs': [dict(r) for r in today_logs],
        'goal_calories': goal_calories,
        'cached_at': int(__import__('time').time() * 1000),
    })

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        ip       = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
        user, error = login_user(email, password, ip=ip)
        if user:
            # If 2FA is enabled, redirect to verification step
            if user.get('totp_enabled'):
                pending_token = create_2fa_pending(user['id'])
                session['2fa_email'] = email
                session['2fa_password'] = password
                return redirect(url_for('verify_2fa', token=pending_token))
            session['user_id']  = user['id']
            session['username'] = user['username']
            session['email']    = email
            session['pending_cache_login'] = {'email': email, 'password': password}
            flash(f"👋 Welcome back, {user['username']}!", 'success')
            return redirect(url_for('dashboard'))
        return render_template('login.html', error=error)
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = {k: request.form.get(k, '').strip() for k in
                ['username','email','password','confirm_password','age','weight','height','gender','goal','activity','goal_weight']}
        if data['password'] != data['confirm_password']:
            return render_template('register.html', error='Passwords do not match.')
        # Store goal_weight if provided
        goal_weight = data.get('goal_weight') or None
        user, error = register_user(**{k: data[k] for k in
                ['username','email','password','age','weight','height','gender','goal','activity']})
        if user:
            if goal_weight:
                get_db().execute('UPDATE users SET goal_weight=%s WHERE id=%s', (goal_weight, user['id']))
                get_db().commit()
            session['user_id']  = user['id']
            session['username'] = user['username']
            session['email']    = user['email']
            flash('Welcome to Cal AI! Your account has been created.', 'success')
            # If user opted into 2FA during registration, redirect to setup
            if request.form.get('enable_2fa'):
                return redirect(url_for('setup_2fa'))
            return redirect(url_for('dashboard'))
        return render_template('register.html', error=error)
    return render_template('register.html')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            return render_template('forgot_password.html', error='Please enter your email address.')

        raw_token, err = create_reset_token(email)
        if raw_token:
            base_url = request.host_url.rstrip('/')
            user_row = get_db().execute('SELECT username FROM users WHERE email=%s', (email,)).fetchone()
            uname    = user_row['username'] if user_row else 'User'
            ok, mail_err = send_reset_email(email, uname, raw_token, base_url)
            if not ok:
                # Show the mail error inline so the user knows why it failed
                return render_template('forgot_password.html',
                                       error=f'Could not send reset email: {mail_err}')
        # Always show the success screen (don't reveal whether email exists)
        return render_template('forgot_password.html', success=True)
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    rec = verify_reset_token(token)
    if not rec:
        return render_template('reset_password.html', invalid=True)
    if request.method == 'POST':
        new_pw  = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if new_pw != confirm:
            return render_template('reset_password.html', token=token, error='Passwords do not match.')
        ok, msg = consume_reset_token(token, new_pw)
        if ok:
            flash('Password updated! Please sign in with your new password.', 'success')
            return redirect(url_for('login'))
        return render_template('reset_password.html', token=token, error=msg)
    return render_template('reset_password.html', token=token)


@app.route('/2fa/verify/<token>', methods=['GET', 'POST'])
def verify_2fa(token):
    if request.method == 'POST':
        code    = request.form.get('code', '').replace(' ', '')
        user_id = resolve_2fa_pending(token)
        if not user_id:
            return render_template('2fa_verify.html', token=token, error='Session expired. Please log in again.')
        user = get_db().execute('SELECT * FROM users WHERE id=%s', (user_id,)).fetchone()
        if not user or not verify_totp(user['totp_secret'], code):
            # Re-create the pending token so user can retry
            new_token = create_2fa_pending(user_id)
            return render_template('2fa_verify.html', token=new_token, error='Invalid code. Please try again.')
        email = session.pop('2fa_email', user['email'])
        pw    = session.pop('2fa_password', '')
        session['user_id']  = user['id']
        session['username'] = user['username']
        session['email']    = email
        session['pending_cache_login'] = {'email': email, 'password': pw}
        return redirect(url_for('dashboard'))
    return render_template('2fa_verify.html', token=token)


@app.route('/2fa/setup', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    uid  = session['user_id']
    user = get_db().execute('SELECT * FROM users WHERE id=%s', (uid,)).fetchone()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'enable':
            secret = request.form.get('secret', '')
            code   = request.form.get('code', '').replace(' ', '')
            ok, msg = enable_totp(uid, secret, code)
            if ok:
                flash(msg, 'success')
                return redirect(url_for('profile'))
            secret = generate_totp_secret()
            qr     = generate_totp_qr_b64(secret, user['email'])
            return render_template('2fa_setup.html', secret=secret, qr=qr, error=msg)
        elif action == 'disable':
            password = request.form.get('password', '')
            ok, msg  = disable_totp(uid, password)
            flash(msg, 'success' if ok else 'danger')
            return redirect(url_for('profile'))
    if user.get('totp_enabled'):
        return render_template('2fa_setup.html', already_enabled=True)
    secret = generate_totp_secret()
    qr     = generate_totp_qr_b64(secret, user['email'])
    return render_template('2fa_setup.html', secret=secret, qr=qr)


@app.route('/api/password-strength', methods=['POST'])
def api_password_strength():
    p = request.json.get('password', '')
    return jsonify(password_strength_score(p))


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# ─── Dashboard ───────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    uid = session['user_id']
    today_logs = db.execute('''
        SELECT fl.id, fl.quantity, fl.meal_type, fl.logged_at,
               f.name, f.calories, f.protein, f.carbs, f.fat, f.category
        FROM food_logs fl JOIN foods f ON fl.food_id = f.id
        WHERE fl.user_id = %s AND DATE(fl.logged_at) = CURDATE()
        ORDER BY fl.logged_at DESC
    ''', (uid,)).fetchall()

    totals = db.execute('''
        SELECT
            COALESCE(SUM(f.calories * fl.quantity / 100), 0) as total_cal,
            COALESCE(SUM(f.protein  * fl.quantity / 100), 0) as total_protein,
            COALESCE(SUM(f.carbs    * fl.quantity / 100), 0) as total_carbs,
            COALESCE(SUM(f.fat      * fl.quantity / 100), 0) as total_fat
        FROM food_logs fl JOIN foods f ON fl.food_id = f.id
        WHERE fl.user_id = %s AND DATE(fl.logged_at) = CURDATE()
    ''', (uid,)).fetchone()

    weekly = db.execute('''
        SELECT DATE(fl.logged_at) as log_date,
               COALESCE(SUM(f.calories * fl.quantity / 100), 0) as cal
        FROM food_logs fl JOIN foods f ON fl.food_id = f.id
        WHERE fl.user_id = %s AND fl.logged_at >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
        GROUP BY log_date ORDER BY log_date
    ''', (uid,)).fetchall()

    user = db.execute('SELECT * FROM users WHERE id = %s', (uid,)).fetchone()
    goal_calories = calculate_goal(user)

    # Pop the one-time offline credential caching token
    pending = session.pop('pending_cache_login', None)

    return render_template('dashboard.html',
        today_logs=today_logs, totals=totals,
        weekly=weekly, user=user, goal_calories=goal_calories,
        cache_login=pending)

# ─── Food Log ────────────────────────────────────────────────────────────────

@app.route('/log', methods=['GET', 'POST'])
@login_required
def log_food():
    db = get_db()
    if request.method == 'POST':
        food_id  = request.form.get('food_id')
        quantity = float(request.form.get('quantity', 100))
        meal     = request.form.get('meal', 'Snack')
        db.execute(
            'INSERT INTO food_logs (user_id, food_id, quantity, meal_type) VALUES (%s, %s, %s, %s)',
            (session['user_id'], food_id, quantity, meal))
        db.commit()
        return redirect(url_for('dashboard'))

    query = request.args.get('q', '')
    category = request.args.get('category', '')
    if query:
        foods = db.execute(
            "SELECT * FROM foods WHERE name LIKE %s ORDER BY name LIMIT 20",
            (f'%{query}%',)).fetchall()
    elif category:
        foods = db.execute(
            "SELECT * FROM foods WHERE category = %s ORDER BY name LIMIT 30",
            (category,)).fetchall()
    else:
        foods = db.execute("SELECT * FROM foods ORDER BY name LIMIT 30").fetchall()

    categories = db.execute("SELECT DISTINCT category FROM foods ORDER BY category").fetchall()
    suggestions = get_food_suggestions(session['user_id'])
    return render_template('log_food.html', foods=foods, query=query,
                           categories=categories, selected_category=category,
                           suggestions=suggestions)

@app.route('/log/delete/<int:log_id>', methods=['POST'])
@login_required
def delete_log(log_id):
    db = get_db()
    db.execute('DELETE FROM food_logs WHERE id = %s AND user_id = %s',
               (log_id, session['user_id']))
    db.commit()
    return jsonify({'ok': True})

# ─── AI Food Scanner (Groq + Llama 4 Vision) ─────────────────────────────────

@app.route('/scan')
@login_required
def scan():
    return render_template('scan.html')

@app.route('/api/scan', methods=['POST'])
@login_required
def api_scan():
    """Scan food image using Groq Llama 4 Vision."""
    data = request.get_json()
    image_b64 = data.get('image', '')

    if not GROQ_API_KEY:
        return jsonify({'error': 'groq_key_missing'}), 200

    prompt = """You are a nutrition expert AI. Analyze this food image and return ONLY a JSON object (no markdown, no explanation) with this exact structure:
{
  "food_name": "Name of the food",
  "confidence": 0.95,
  "calories_per_100g": 200,
  "protein_per_100g": 15,
  "carbs_per_100g": 25,
  "fat_per_100g": 8,
  "fiber_per_100g": 2,
  "category": "Filipino|Protein|Grains|Vegetables|Fruits|Dairy|Snacks|Beverages|General",
  "serving_size_g": 150,
  "description": "Brief description of the food",
  "meal_suggestion": "Breakfast|Lunch|Dinner|Snack"
}
If you cannot identify food, set food_name to "Unknown Food" and confidence to 0."""

    VISION_MODELS = [
        'meta-llama/llama-4-scout-17b-16e-instruct',
        'meta-llama/llama-4-maverick-17b-128e-instruct',
        'llama-3.2-90b-vision-preview',
        'llama-3.2-11b-vision-preview',
    ]
    last_err = None
    resp = None
    try:
        for model in VISION_MODELS:
            try:
                resp = requests.post(GROQ_API_URL,
                    headers={'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'},
                    json={
                        'model': model,
                        'messages': [{'role': 'user', 'content': [
                            {'type': 'text', 'text': prompt},
                            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{image_b64}'}}
                        ]}],
                        'max_tokens': 600,
                        'temperature': 0.1
                    }, timeout=30)
                if resp.status_code in (200, 201):
                    break
                last_err = f'Model {model} returned {resp.status_code}'
                resp = None
            except requests.exceptions.Timeout:
                last_err = f'Model {model} timed out'
                resp = None
        if resp is None:
            return jsonify({'error': last_err or 'All vision models unavailable. Check your Groq API key.'}), 500
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content'].strip()

        # Clean JSON if wrapped in markdown - robust extraction
        import re as _re
        json_match = _re.search(r'\{[\s\S]*\}', content)
        if json_match:
            content = json_match.group(0)
        elif '```' in content:
            for part in content.split('```'):
                part = part.strip()
                if part.startswith('json'):
                    part = part[4:].strip()
                if part.startswith('{'):
                    content = part
                    break

        result = json.loads(content)

        # Save to food DB if new food
        db = get_db()
        existing = db.execute('SELECT id FROM foods WHERE name = %s', (result['food_name'],)).fetchone()
        if not existing and result.get('confidence', 0) > 0.5:
            db.execute('''INSERT INTO foods (name, calories, protein, carbs, fat, fiber, category, source)
                          VALUES (%s, %s, %s, %s, %s, %s, %s, "AI-Scan")''',
                (result['food_name'], result['calories_per_100g'], result['protein_per_100g'],
                 result['carbs_per_100g'], result['fat_per_100g'], result.get('fiber_per_100g', 0),
                 result.get('category', 'General')))
            db.commit()
            new_food = db.execute('SELECT id FROM foods WHERE name = %s', (result['food_name'],)).fetchone()
            result['food_id'] = new_food['id'] if new_food else None
        elif existing:
            result['food_id'] = existing['id']

        return jsonify(result)

    except requests.exceptions.Timeout:
        return jsonify({'error': 'Groq API timeout. Try again.'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── AI Meal Planner (Groq) ───────────────────────────────────────────────────

@app.route('/planner')
@login_required
def planner():
    return render_template('planner.html')

@app.route('/api/meal-plan', methods=['POST'])
@login_required
def api_meal_plan():
    """Generate a meal plan using Groq."""
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = %s', (session['user_id'],)).fetchone()
    goal_calories = calculate_goal(user)

    data = request.get_json()
    days = int(data.get('days', 3))
    preferences = data.get('preferences', '')
    diet_type = data.get('diet_type', 'balanced')

    if not GROQ_API_KEY:
        return jsonify({'error': 'groq_key_missing'}), 200

    prompt = f"""You are a Filipino nutritionist AI. Create a {days}-day meal plan for:
- Goal: {user.get('goal', 'maintain')} weight
- Daily calories: {goal_calories} kcal
- Diet type: {diet_type}
- Preferences: {preferences or 'none'}
- Include Filipino foods when possible

Return ONLY a JSON array (no markdown) like this:
[
  {{
    "day": 1,
    "meals": {{
      "breakfast": {{"name": "Sinangag at Itlog", "calories": 350, "protein": 15, "carbs": 40, "fat": 12, "ingredients": ["2 cups garlic rice", "2 eggs", "1 tbsp oil"]}},
      "lunch": {{"name": "Sinigang na Baboy", "calories": 450, "protein": 28, "carbs": 20, "fat": 18, "ingredients": ["200g pork", "kangkong", "tamarind"]}},
      "dinner": {{"name": "Grilled Bangus", "calories": 380, "protein": 32, "carbs": 15, "fat": 16, "ingredients": ["1 medium bangus", "tomatoes", "onions"]}},
      "snack": {{"name": "Banana", "calories": 89, "protein": 1, "carbs": 23, "fat": 0, "ingredients": ["1 banana"]}}
    }},
    "total_calories": {goal_calories},
    "tip": "Health tip for the day"
  }}
]"""

    try:
        resp = requests.post(GROQ_API_URL,
            headers={'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'},
            json={
                'model': 'llama-3.3-70b-versatile',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 3000,
                'temperature': 0.7
            }, timeout=45)
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content'].strip()
        # Robust JSON extraction — handles markdown fences and extra text
        import re as _re
        json_match = _re.search(r'\[[\s\S]*\]', content)
        if json_match:
            content = json_match.group(0)
        elif '```' in content:
            for part in content.split('```'):
                part = part.strip()
                if part.startswith('json'):
                    part = part[4:].strip()
                if part.startswith('['):
                    content = part
                    break
        plan = json.loads(content)
        return jsonify({'plan': plan, 'goal_calories': goal_calories})
    except requests.exceptions.Timeout:
        return jsonify({'error': 'Groq API timeout. Please try again.'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── Analytics ───────────────────────────────────────────────────────────────

@app.route('/analytics')
@login_required
def analytics():
    db = get_db()
    uid = session['user_id']
    trend = db.execute('''
        SELECT DATE(fl.logged_at) as d,
               ROUND(SUM(f.calories * fl.quantity / 100), 1) as cal,
               ROUND(SUM(f.protein  * fl.quantity / 100), 1) as prot,
               ROUND(SUM(f.carbs    * fl.quantity / 100), 1) as carb,
               ROUND(SUM(f.fat      * fl.quantity / 100), 1) as fat
        FROM food_logs fl JOIN foods f ON fl.food_id = f.id
        WHERE fl.user_id = %s AND fl.logged_at >= DATE_SUB(CURDATE(), INTERVAL 29 DAY)
        GROUP BY d ORDER BY d
    ''', (uid,)).fetchall()

    top_foods = db.execute('''
        SELECT f.name, COUNT(*) as freq, ROUND(AVG(f.calories),1) as avg_cal
        FROM food_logs fl JOIN foods f ON fl.food_id = f.id
        WHERE fl.user_id = %s
        GROUP BY f.name ORDER BY freq DESC LIMIT 10
    ''', (uid,)).fetchall()

    by_cat = db.execute('''
        SELECT f.category, ROUND(SUM(f.calories * fl.quantity / 100),1) as total_cal
        FROM food_logs fl JOIN foods f ON fl.food_id = f.id
        WHERE fl.user_id = %s AND fl.logged_at >= DATE_SUB(CURDATE(), INTERVAL 29 DAY)
        GROUP BY f.category ORDER BY total_cal DESC
    ''', (uid,)).fetchall()

    from datetime import date, timedelta
    user = db.execute('SELECT * FROM users WHERE id = %s', (uid,)).fetchone()

    # Fill every day in the last 30 days (0 for days with no logs)
    row_map = {str(r['d']): dict(r) for r in trend}
    today   = date.today()
    trend   = []
    for i in range(29, -1, -1):
        day_str = str(today - timedelta(days=i))
        if day_str in row_map:
            trend.append(row_map[day_str])
        else:
            trend.append({'d': day_str, 'cal': 0, 'prot': 0, 'carb': 0, 'fat': 0})

    goal_calories = calculate_goal(user)
    return render_template('analytics.html', trend=trend, top_foods=top_foods,
                           by_cat=by_cat, goal_calories=goal_calories)

# ─── Profile ─────────────────────────────────────────────────────────────────

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = %s', (session['user_id'],)).fetchone()
    if request.method == 'POST':
        db.execute('''UPDATE users SET age=%s, weight=%s, height=%s, gender=%s, goal=%s, activity=%s, goal_weight=%s
                      WHERE id=%s''',
            (request.form['age'], request.form['weight'], request.form['height'],
             request.form['gender'], request.form['goal'], request.form['activity'],
             request.form.get('goal_weight') or None,
             session['user_id']))
        db.commit()
        return redirect(url_for('profile'))
    goal_calories = calculate_goal(user)
    return render_template('profile.html', user=user, goal_calories=goal_calories)

# ─── ML Predictor ─────────────────────────────────────────────────────────────

@app.route('/predict', methods=['GET', 'POST'])
@login_required
def predict():
    result = None
    if request.method == 'POST':
        result = predict_calories(
            float(request.form.get('age', 25)),
            float(request.form.get('weight', 70)),
            float(request.form.get('height', 170)),
            request.form.get('gender', 'male'),
            request.form.get('activity', 'moderate'),
            request.form.get('goal', 'maintain')
        )
    return render_template('predict.html', result=result)

# ─── Push Notifications ───────────────────────────────────────────────────────

@app.route('/api/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    db = get_db()
    sub = request.get_json()
    uid = session['user_id']
    sub_json = json.dumps(sub)
    db.execute('''INSERT INTO push_subscriptions (user_id, subscription_json)
                  VALUES (%s, %s)
                  ON DUPLICATE KEY UPDATE subscription_json=%s''',
               (uid, sub_json, sub_json))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/push/unsubscribe', methods=['POST'])
@login_required
def push_unsubscribe():
    db = get_db()
    db.execute('DELETE FROM push_subscriptions WHERE user_id = %s', (session['user_id'],))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/push/send-test', methods=['POST'])
@login_required
def send_test_push():
    """Send a test push notification to the current user."""
    db = get_db()
    sub = db.execute('SELECT subscription_json FROM push_subscriptions WHERE user_id = %s',
                     (session['user_id'],)).fetchone()
    if not sub:
        return jsonify({'error': 'Walang push subscription. I-enable muna ang notifications sa Profile page.'}), 404
    push_data = {
        'title': '🔔 Cal AI Test',
        'body': 'Gumagana ang push notifications! 🎉',
        'icon': '/static/icons/icon-192.png',
        'url': '/dashboard',
    }
    ok, err = _send_webpush(json.loads(sub['subscription_json']), push_data)
    if ok:
        return jsonify({'ok': True})
    if err == 'SUBSCRIPTION_EXPIRED':
        db.execute('DELETE FROM push_subscriptions WHERE user_id = %s', (session['user_id'],))
        db.commit()
        return jsonify({'error': 'Subscription expired. I-toggle ulit ang notifications.'}), 410
    return jsonify({'error': err or 'Push failed'}), 500

@app.route('/api/push/debug')
@login_required
def push_debug():
    """Debug endpoint — returns VAPID and subscription status."""
    db = get_db()
    sub = db.execute('SELECT subscription_json, created_at FROM push_subscriptions WHERE user_id = %s',
                     (session['user_id'],)).fetchone()
    vapid_ok = bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY and len(VAPID_PUBLIC_KEY) > 30)
    try:
        from pywebpush import webpush  # noqa
        pywebpush_ok = True
    except ImportError:
        pywebpush_ok = False
    return jsonify({
        'vapid_public_key_set': vapid_ok,
        'vapid_public_key_preview': VAPID_PUBLIC_KEY[:20] + '...' if VAPID_PUBLIC_KEY else None,
        'pywebpush_installed': pywebpush_ok,
        'subscribed': sub is not None,
        'subscription_created': str(sub['created_at']) if sub else None,
        'status': '✅ Ready' if (vapid_ok and pywebpush_ok and sub) else '❌ Not ready',
    })

# ─── AJAX APIs ───────────────────────────────────────────────────────────────


@app.route('/api/foods/all')
@login_required
def api_foods_all():
    """Return all foods for offline caching (called once after login)."""
    db    = get_db()
    foods = db.execute('SELECT id, name, calories, protein, carbs, fat, category FROM foods ORDER BY name').fetchall()
    return jsonify([dict(f) for f in foods])

@app.route('/api/foods/search')
@login_required
def api_search_foods():
    db       = get_db()
    q        = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()

    if q and category:
        foods = db.execute(
            "SELECT * FROM foods WHERE name LIKE %s AND category = %s ORDER BY name LIMIT 30",
            (f'%{q}%', category)).fetchall()
    elif q:
        foods = db.execute(
            "SELECT * FROM foods WHERE name LIKE %s ORDER BY name LIMIT 30",
            (f'%{q}%',)).fetchall()
    elif category:
        foods = db.execute(
            "SELECT * FROM foods WHERE category = %s ORDER BY name LIMIT 30",
            (category,)).fetchall()
    else:
        foods = db.execute("SELECT * FROM foods ORDER BY name LIMIT 30").fetchall()

    return jsonify([dict(f) for f in foods])

@app.route('/api/log/quick', methods=['POST'])
@login_required
def api_quick_log():
    """Quick log from scan page."""
    data = request.get_json()
    db = get_db()
    db.execute(
        'INSERT INTO food_logs (user_id, food_id, quantity, meal_type) VALUES (%s, %s, %s, %s)',
        (session['user_id'], data['food_id'], data.get('quantity', 100), data.get('meal', 'Snack')))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/vapid-public-key')
def get_vapid_key():
    return jsonify({'key': VAPID_PUBLIC_KEY})

# ─── Helpers ─────────────────────────────────────────────────────────────────

def calculate_goal(user):
    try:
        w = float(user['weight'] or 70)
        h = float(user['height'] or 170)
        a = float(user['age'] or 25)
        g = user['gender'] or 'male'
        goal = user['goal'] or 'maintain'
        activity = user.get('activity', 'moderate')
        if g == 'male':
            bmr = 10 * w + 6.25 * h - 5 * a + 5        # Mifflin-St Jeor
        else:
            bmr = 10 * w + 6.25 * h - 5 * a - 161
        af = {'sedentary':1.2,'light':1.375,'moderate':1.55,'active':1.725,'very_active':1.9}
        tdee = bmr * af.get(activity, 1.55)
        if goal == 'lose': tdee -= 500
        elif goal == 'gain': tdee += 500
        return round(tdee)
    except:
        return 2000


# ─── Streak ───────────────────────────────────────────────────────────────────

@app.route('/api/streak')
@login_required
def api_streak():
    db  = get_db()
    uid = session['user_id']
    # Fetch distinct logged dates descending
    rows = db.execute("""
        SELECT DISTINCT DATE(logged_at) as d
        FROM food_logs WHERE user_id = %s
        ORDER BY d DESC LIMIT 366
    """, (uid,)).fetchall()
    from datetime import date, timedelta
    dates = [r['d'] for r in rows]
    streak = 0
    check  = date.today()
    for d in dates:
        if d == check or d == check - timedelta(days=1):
            streak += 1
            check   = d - timedelta(days=1)
        else:
            break
    longest = 0
    run = 0
    prev = None
    for d in reversed(dates):
        if prev is None or d == prev + timedelta(days=1):
            run += 1
        else:
            longest = max(longest, run)
            run = 1
        prev = d
    longest = max(longest, run)
    return jsonify({'streak': streak, 'longest': longest, 'total_days': len(dates)})


# ─── Weight Tracking ──────────────────────────────────────────────────────────

@app.route('/api/weight', methods=['GET', 'POST'])
@login_required
def api_weight():
    db  = get_db()
    uid = session['user_id']
    if request.method == 'POST':
        data   = request.get_json() or {}
        weight = float(data.get('weight', 0))
        if not (20 < weight < 500):
            return jsonify({'error': 'Invalid weight'}), 400
        db.execute("""INSERT INTO weight_logs (user_id, weight)
                      VALUES (%s, %s)
                      ON DUPLICATE KEY UPDATE weight=%s""",
                   (uid, weight, weight))
        # Also update users.weight with the latest
        db.execute("UPDATE users SET weight=%s WHERE id=%s", (weight, uid))
        db.commit()
        return jsonify({'ok': True, 'weight': weight})
    rows = db.execute("""
        SELECT DATE(logged_at) as d, weight
        FROM weight_logs WHERE user_id = %s
        ORDER BY logged_at ASC LIMIT 120
    """, (uid,)).fetchall()
    user = db.execute("SELECT goal_weight, weight FROM users WHERE id=%s", (uid,)).fetchone()
    return jsonify({
        'logs': [{'d': str(r['d']), 'w': r['weight']} for r in rows],
        'goal_weight': user['goal_weight'],
        'current_weight': user['weight'],
    })


# ─── Offline Food Log Sync ────────────────────────────────────────────────────

@app.route('/api/offline-log-sync', methods=['POST'])
@login_required
def offline_log_sync():
    """Accept a batch of offline food-log entries and insert them."""
    db      = get_db()
    uid     = session['user_id']
    entries = request.get_json() or []
    inserted = 0
    for e in entries:
        food_id  = e.get('food_id')
        quantity = float(e.get('quantity', 100))
        meal     = e.get('meal_type', 'Snack')
        ts       = e.get('logged_at')   # ISO string from client
        if not food_id:
            continue
        if ts:
            db.execute("""INSERT IGNORE INTO food_logs (user_id, food_id, quantity, meal_type, logged_at)
                          VALUES (%s, %s, %s, %s, %s)""",
                       (uid, food_id, quantity, meal, ts))
        else:
            db.execute("""INSERT INTO food_logs (user_id, food_id, quantity, meal_type)
                          VALUES (%s, %s, %s, %s)""",
                       (uid, food_id, quantity, meal))
        inserted += 1
    db.commit()
    return jsonify({'ok': True, 'inserted': inserted})


# ─── Export ───────────────────────────────────────────────────────────────────

@app.route('/api/export/csv')
@login_required
def export_csv():
    import csv, io
    db  = get_db()
    uid = session['user_id']
    rows = db.execute("""
        SELECT DATE(fl.logged_at) as date, TIME(fl.logged_at) as time,
               fl.meal_type, f.name, fl.quantity,
               ROUND(f.calories * fl.quantity / 100, 1) as calories,
               ROUND(f.protein  * fl.quantity / 100, 1) as protein,
               ROUND(f.carbs    * fl.quantity / 100, 1) as carbs,
               ROUND(f.fat      * fl.quantity / 100, 1) as fat,
               f.category
        FROM food_logs fl JOIN foods f ON fl.food_id = f.id
        WHERE fl.user_id = %s
        ORDER BY fl.logged_at DESC
    """, (uid,)).fetchall()
    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(['Date','Time','Meal','Food','Quantity(g)',
                'Calories(kcal)','Protein(g)','Carbs(g)','Fat(g)','Category'])
    for r in rows:
        w.writerow([r['date'], r['time'], r['meal_type'], r['name'],
                    r['quantity'], r['calories'], r['protein'], r['carbs'],
                    r['fat'], r['category']])
    output = buf.getvalue()
    return output, 200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': 'attachment; filename=cal_ai_food_log.csv',
    }


@app.route('/api/export/pdf')
@login_required
def export_pdf():
    """Generate a simple PDF food log using reportlab."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        import io, datetime
    except ImportError:
        return "reportlab not installed. Run: pip install reportlab", 500

    db  = get_db()
    uid = session['user_id']
    user = db.execute("SELECT username FROM users WHERE id=%s", (uid,)).fetchone()
    rows = db.execute("""
        SELECT DATE(fl.logged_at) as date, fl.meal_type, f.name, fl.quantity,
               ROUND(f.calories * fl.quantity / 100, 1) as calories,
               ROUND(f.protein  * fl.quantity / 100, 1) as protein,
               ROUND(f.carbs    * fl.quantity / 100, 1) as carbs,
               ROUND(f.fat      * fl.quantity / 100, 1) as fat
        FROM food_logs fl JOIN foods f ON fl.food_id = f.id
        WHERE fl.user_id = %s ORDER BY fl.logged_at DESC LIMIT 500
    """, (uid,)).fetchall()

    buf  = io.BytesIO()
    doc  = SimpleDocTemplate(buf, pagesize=A4,
                              leftMargin=1.5*cm, rightMargin=1.5*cm,
                              topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story  = []
    story.append(Paragraph(f"🥗 Cal AI — Food Log", styles['Title']))
    story.append(Paragraph(f"User: {user['username']}  ·  Exported: {datetime.date.today()}", styles['Normal']))
    story.append(Spacer(1, 0.5*cm))

    header = ['Date','Meal','Food','Qty(g)','kcal','Prot','Carb','Fat']
    data   = [header]
    for r in rows:
        data.append([str(r['date']), r['meal_type'], r['name'][:28],
                     r['quantity'], r['calories'], r['protein'], r['carbs'], r['fat']])

    t = Table(data, repeatRows=1, colWidths=[2.2*cm,2*cm,5.5*cm,1.5*cm,1.5*cm,1.4*cm,1.4*cm,1.2*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1db954')),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0,0), (-1,-1), 8),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f0fdf4')]),
        ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t)
    doc.build(story)
    buf.seek(0)
    return buf.read(), 200, {
        'Content-Type': 'application/pdf',
        'Content-Disposition': 'attachment; filename=cal_ai_food_log.pdf',
    }


# ─── Scheduled Push Notifications ───────────────────────────────────────────

# Admin-level default times (fallback when user has no custom settings)
# NOTE: These must be defined BEFORE the routes that reference them.
ADMIN_DEFAULT_TIMES = {
    'breakfast': '07:00',
    'lunch':     '12:00',
    'dinner':    '18:30',
    'summary':   '21:00',
}

REMINDER_META = {
    'breakfast': {'label': '🌅 Breakfast',     'title': '🌅 Breakfast time!',   'body': "Don't forget to log your breakfast.", 'url': '/log'},
    'lunch':     {'label': '☀️ Lunch',         'title': '☀️ Lunch reminder',    'body': 'Time to log your lunch!',             'url': '/log'},
    'dinner':    {'label': '🌙 Dinner',        'title': '🌙 Dinner time!',      'body': 'Log your dinner to hit your daily goals.', 'url': '/log'},
    'summary':   {'label': '📊 Daily Summary', 'title': '📊 Daily summary',     'body': 'Check how you did today — tap to view your analytics.', 'url': '/analytics'},
}

# ─── Custom Reminder Times ────────────────────────────────────────────────────

@app.route('/api/push/reminder-times', methods=['GET', 'POST'])
@login_required
def reminder_times():
    db  = get_db()
    uid = session['user_id']
    if request.method == 'POST':
        data = request.get_json() or {}
        times_json = json.dumps({k: data.get(k, v) for k, v in ADMIN_DEFAULT_TIMES.items()})
        try:
            db.execute("""INSERT INTO user_settings (user_id, reminder_times)
                          VALUES (%s, %s)
                          ON DUPLICATE KEY UPDATE reminder_times=%s""",
                       (uid, times_json, times_json))
            db.commit()
        except Exception as e:
            print(f'[ReminderTimes] DB error: {e}')
            return jsonify({'error': f'Database error: {e}. Run migrate_add_reminder_times.sql'}), 500
        return jsonify({'ok': True})
    return jsonify(_get_user_times(uid))

def _get_admin_defaults():
    """Return admin-set global default times from DB, falling back to hardcoded defaults."""
    try:
        db = get_db()
        row = db.execute("SELECT reminder_times FROM user_settings WHERE user_id = 0").fetchone()
        if row and row['reminder_times']:
            saved = json.loads(row['reminder_times'])
            return {k: saved.get(k, v) for k, v in ADMIN_DEFAULT_TIMES.items()}
    except Exception:
        pass
    return dict(ADMIN_DEFAULT_TIMES)

def _get_user_times(user_id):
    """Return effective reminder times for a user (custom or admin default)."""
    defaults = _get_admin_defaults()
    try:
        db = get_db()
        row = db.execute("SELECT reminder_times FROM user_settings WHERE user_id = %s", (user_id,)).fetchone()
        if row and row['reminder_times']:
            saved = json.loads(row['reminder_times'])
            # Merge: user overrides take priority, fall back to admin defaults
            return {k: saved.get(k, defaults[k]) for k in defaults}
    except Exception:
        pass
    return defaults

def _push_to_user(user_id, sub_json, meal_id):
    """Send a push notification to one user for the given meal_id."""
    meta = REMINDER_META[meal_id]
    push_data = {
        'title': meta['title'],
        'body':  meta['body'],
        'icon':  '/static/icons/icon-192.png',
        'url':   meta['url'],
    }
    ok, err = _send_webpush(json.loads(sub_json), push_data)
    if ok:
        print(f'[Push] ✅ Sent {meal_id} reminder to user {user_id}')
    elif err == 'SUBSCRIPTION_EXPIRED':
        try:
            with app.app_context():
                db = get_db()
                db.execute('DELETE FROM push_subscriptions WHERE user_id = %s', (user_id,))
                db.commit()
            print(f'[Push] Removed expired subscription for user {user_id}')
        except Exception as ex:
            print(f'[Push] Could not remove expired sub for user {user_id}: {ex}')
    else:
        print(f'[Push] ❌ Failed for user {user_id}: {err}')

def _fire_reminder(meal_id, current_hhmm):
    """
    Called every minute by the scheduler.
    Sends push to every subscribed user whose custom time matches current_hhmm.
    """
    with app.app_context():
        try:
            db = get_db()
            subs = db.execute(
                'SELECT ps.user_id, ps.subscription_json FROM push_subscriptions ps'
            ).fetchall()
            for row in subs:
                uid = row['user_id']
                times = _get_user_times(uid)
                if times.get(meal_id) == current_hhmm:
                    _push_to_user(uid, row['subscription_json'], meal_id)
        except Exception as e:
            print(f'[Push] _fire_reminder({meal_id}) error: {e}')

def _check_all_reminders():
    """Run every minute — check which meal reminders should fire right now."""
    import datetime
    tz_name = os.environ.get('TZ', 'Asia/Manila')
    try:
        import pytz
        now = datetime.datetime.now(pytz.timezone(tz_name))
    except Exception:
        now = datetime.datetime.now()
    current_hhmm = now.strftime('%H:%M')
    for meal_id in REMINDER_META:
        _fire_reminder(meal_id, current_hhmm)

def start_scheduler():
    """Start APScheduler — fires every minute to check per-user reminder times."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        import pytz

        tz = pytz.timezone(os.environ.get('TZ', 'Asia/Manila'))
        scheduler = BackgroundScheduler(timezone=tz)

        # Check every minute — per-user times are matched inside _check_all_reminders
        scheduler.add_job(
            _check_all_reminders,
            IntervalTrigger(minutes=1),
            id='reminder_check',
            replace_existing=True,
        )

        scheduler.start()
        print('[Scheduler] Per-user reminder scheduler started (Asia/Manila).')
        return scheduler
    except ImportError:
        print('[Scheduler] APScheduler not installed — skipping. Run: pip install apscheduler pytz')
    except Exception as e:
        print(f'[Scheduler] Failed to start: {e}')

# ─── Notification Settings page ──────────────────────────────────────────────

@app.route('/notifications/settings')
@login_required
def notif_settings_page():
    uid          = session['user_id']
    user_times   = _get_user_times(uid)
    admin_times  = _get_admin_defaults()
    return render_template('notif_settings.html',
                           user_times=user_times,
                           admin_times=admin_times,
                           reminder_meta=REMINDER_META)

# ─── Admin: save global default times (user_id = 0 sentinel) ─────────────────

def _ensure_no_fk_on_user_settings():
    """Drop any FK on user_settings.user_id so user_id=0 sentinel can be inserted."""
    try:
        db = get_db()
        row = db.execute(
            "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_settings' "
            "AND COLUMN_NAME = 'user_id' AND REFERENCED_TABLE_NAME = 'users' LIMIT 1"
        ).fetchone()
        if row:
            fk_name = row['CONSTRAINT_NAME']
            db.execute(f"ALTER TABLE `user_settings` DROP FOREIGN KEY `{fk_name}`")
            print(f'[DB] Dropped FK {fk_name} from user_settings so user_id=0 is allowed.')
    except Exception as e:
        print(f'[DB] _ensure_no_fk_on_user_settings: {e}')


@app.route('/api/push/admin-defaults', methods=['POST'])
@login_required
def save_admin_defaults():
    # Only allow admin (user_id == 1 or username == 'admin')
    if session.get('user_id') != 1 and session.get('username') != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    data = request.get_json() or {}
    times_json = json.dumps({k: data.get(k, v) for k, v in ADMIN_DEFAULT_TIMES.items()})
    db = get_db()
    # Ensure FK is dropped so user_id=0 sentinel insert succeeds
    _ensure_no_fk_on_user_settings()
    try:
        db.execute("""INSERT INTO user_settings (user_id, reminder_times)
                      VALUES (0, %s)
                      ON DUPLICATE KEY UPDATE reminder_times=%s""",
                   (times_json, times_json))
        db.commit()
    except Exception as e:
        print(f'[AdminDefaults] DB error: {e}')
        return jsonify({'error': f'Database error: {e}'}), 500
    return jsonify({'ok': True})

@app.route('/api/push/reminders', methods=['GET', 'POST'])
@login_required
def push_reminders():
    """GET: return current reminder schedule. POST: update times for this user (future extension)."""
    schedule = [
        {'id': 'breakfast', 'label': '🌅 Breakfast',    'time': '07:00'},
        {'id': 'lunch',     'label': '☀️ Lunch',        'time': '12:00'},
        {'id': 'dinner',    'label': '🌙 Dinner',       'time': '18:30'},
        {'id': 'summary',   'label': '📊 Daily Summary','time': '21:00'},
    ]
    return jsonify({'schedule': schedule, 'timezone': os.environ.get('TZ', 'Asia/Manila')})

# ─── Auto-start scheduler ────────────────────────────────────────────────────
_scheduler_started = False

def _ensure_scheduler():
    global _scheduler_started
    if not _scheduler_started:
        start_scheduler()
        _scheduler_started = True
        if not os.environ.get('MAIL_USER') or not os.environ.get('MAIL_PASSWORD'):
            print('\n[WARNING] MAIL_USER / MAIL_PASSWORD not set in .env — '
                  'forgot-password emails will NOT be sent.\n'
                  '  → Copy .env.example to .env and fill in your Gmail App Password.\n')

with app.app_context():
    _ensure_scheduler()

if __name__ == '__main__':
    app.run(debug=True, port=5000, use_reloader=False)