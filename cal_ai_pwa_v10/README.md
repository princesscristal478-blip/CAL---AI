# 🥗 Cal AI — PWA Calorie Tracker

AI-powered calorie tracker na may Filipino food support, i-installable sa phone tulad ng app.

---

## ✨ Features

| Feature | Technology |
|---|---|
| 📷 AI Food Scanner | Groq API — Llama 4 Vision (LIBRE) |
| 🤖 AI Meal Planner | Groq API — Llama 3.3 70B (LIBRE) |
| 📊 Calorie + Macro Tracking | Mifflin-St Jeor formula |
| 🇵🇭 Filipino Food Database | 60+ Filipino foods pre-loaded |
| 🔔 Push Notifications | Web Push API + VAPID |
| 📴 Offline Mode | Service Worker caching |
| 📱 PWA Install | Manifest + Service Worker |
| 🗄️ Database | MySQL via XAMPP |

---

## 🚀 Setup Guide

### 1. I-install ang XAMPP
- I-download sa https://www.apachefriends.org
- I-start ang **Apache** at **MySQL** sa XAMPP Control Panel

### 2. I-install ang Python dependencies
```bash
cd cal_ai_pwa
pip install -r requirements.txt
```

### 3. I-setup ang environment variables
```bash
# Kopyahin ang .env.example
copy .env.example .env   # Windows
cp .env.example .env     # Mac/Linux

# I-edit ang .env file:
```

**Kukuha ng Groq API Key (LIBRE):**
1. Pumunta sa https://console.groq.com
2. Mag-sign up (libre)
3. Gumawa ng API key
4. I-paste sa `.env`: `GROQ_API_KEY=gsk_...`

**Para sa Push Notifications (optional):**
```bash
pip install py-vapid
python -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); print('Public:', v.public_key); print('Private:', v.private_key)"
```
I-paste ang output sa `.env`.

### 4. I-run ang app
```bash
python app.py
```

Buksan sa browser: **http://localhost:5000**

---

## 📱 I-install bilang PWA

### Android (Chrome):
1. Buksan ang http://localhost:5000 sa Chrome
2. Menu (3 dots) → "Add to Home Screen"
3. I-tap "Install" → Done! May app icon na!

### iPhone (Safari):
1. Buksan ang site sa Safari
2. Share button → "Add to Home Screen"
3. I-tap "Add" → Done!

---

## 🗂️ Project Structure

```
cal_ai_pwa/
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variables template
├── generate_icons.py       # PWA icon generator
│
├── auth/
│   └── auth.py             # Authentication (login/register)
│
├── database/
│   └── db.py               # MySQL database + seeding
│
├── ml/
│   └── predictor.py        # Calorie calculator (Mifflin-St Jeor)
│
├── static/
│   ├── css/app.css         # Dark theme PWA styles
│   ├── js/
│   │   ├── app.js          # Main JS (PWA install, push notifs)
│   │   └── sw.js           # Service Worker (offline + push)
│   ├── icons/              # PWA icons (all sizes)
│   └── manifest.json       # PWA manifest
│
└── templates/
    ├── base.html           # Base template (nav, bottom bar)
    ├── login.html          # Login page
    ├── register.html       # Registration with profile setup
    ├── dashboard.html      # Home dashboard
    ├── scan.html           # AI Food Scanner
    ├── planner.html        # AI Meal Planner
    ├── log_food.html       # Manual food logging
    ├── analytics.html      # 30-day charts & analytics
    ├── profile.html        # Profile + push notification toggle
    └── predict.html        # Calorie calculator
```

---

## 🔧 MySQL Setup

Ang app ay awtomatikong gumawa ng database at tables sa unang run.
Default config (para sa XAMPP):
- Host: `localhost`
- Port: `3306`
- User: `root`
- Password: *(walang password — default ng XAMPP)*
- Database: `cal_ai` *(gagawin awtomatiko)*

Para gumamit ng password, i-edit ang `.env` file.

---

## 🤖 AI Features

### Food Scanner (Groq + Llama 4 Vision)
- Kumuha ng litrato ng pagkain (o mag-upload ng photo)
- I-analyze ng AI ang food, calories, at macros
- Awtomatikong nai-save sa food database
- Pwedeng direktang i-log pagkatapos ng scan

### Meal Planner (Groq + Llama 3.3)
- Pumili ng ilang araw (1, 3, 5, o 7 araw)
- Piliin ang diet type (balanced, high-protein, low-carb, etc.)
- Mag-generate ng personalized Filipino meal plan
- Kasama ang ingredients at health tips

---

## 🔔 Push Notifications

Para gumana ang push notifications:
1. Kailangan ng HTTPS (o localhost para sa dev)
2. I-generate ang VAPID keys (see setup step 3)
3. I-install ang `pywebpush`: `pip install pywebpush`
4. I-toggle ang notifications sa Profile page

---

## 📊 Food Database

Pre-loaded na may **65+ foods**:
- 🇵🇭 Filipino: Adobo, Sinigang, Kare-kare, Tinola, Lechon, Bangus, at marami pa
- 🍎 Fruits: 7 varieties
- 🥦 Vegetables: 15 varieties (kasama Kangkong, Ampalaya, Pechay)
- 🍚 Grains: Pandesal, Sinangag, Rice, Oatmeal
- 🍗 Protein: Chicken, Egg, Fish, Tofu, Legumes
- 🥛 Dairy: Whole milk, Milo, Eden Cheese
- 🍿 Snacks: Chicharon, Polvoron, at iba pa

Ang AI scanner ay awtomatikong nagdadagdag ng bagong foods sa database.

---

## 🐛 Troubleshooting

**"Can't connect to MySQL"**
→ Siguraduhing naka-start ang MySQL sa XAMPP Control Panel

**"Groq API error"**
→ I-check ang GROQ_API_KEY sa `.env` file
→ Pumunta sa console.groq.com para makita ang free tier limits

**"Push notifications not working"**
→ Kailangan ng VAPID keys sa `.env`
→ I-run: `pip install pywebpush py-vapid`

**Camera not working on scanner**
→ Kailangan ng HTTPS para sa camera access sa deployed version
→ Sa localhost, gumagana nang walang HTTPS


---

## 🔔 Push Notifications Setup

### 1. VAPID Keys — AWTOMATIKO na!

**Hindi na kailangan pang mag-generate ng VAPID keys manually.**  
Sa unang `python app.py`, awtomatiko itong gagawa ng keys at ise-save sa `.env`.

Basta i-install lang ang dependencies:

```bash
pip install -r requirements.txt
```

> **Kung may error pa rin:** Tingnan ang console output ng `app.py` para sa `[VAPID]` logs.  
> Debug endpoint: `http://localhost:5000/api/push/debug` (habang naka-login)

### 2. Set your timezone (optional)

The scheduler defaults to **Asia/Manila**. Override in `.env`:

```
TZ=Asia/Manila
```

### 3. Scheduled Meal Reminders

Once VAPID keys are set and users have subscribed to notifications (via the toggle in Profile), the server automatically sends:

| Time  | Notification |
|-------|-------------|
| 7:00 AM  | 🌅 Breakfast reminder |
| 12:00 PM | ☀️ Lunch reminder |
| 6:30 PM  | 🌙 Dinner reminder |
| 9:00 PM  | 📊 Daily summary |

Requires `apscheduler` and `pytz` (already in `requirements.txt`).

### 4. Test push manually

After logging in, go to **Profile → Notifications** and tap **Send Test**.

---

## 📴 Offline Mode

### Login offline
- Log in at least once online to cache your credentials.
- While offline, entering your email + password on the login page will verify locally (PBKDF2/IndexedDB) and redirect you to the **offline dashboard**.

### Register offline
- Filling the register form offline saves your account locally and queues the signup.
- It syncs automatically when you reconnect.
- You can immediately log in offline after registering.

### Dashboard offline
- The app caches your dashboard data (calories, macros, food log) after every online session.
- The offline dashboard (`/offline-dashboard`) reads this cached data from IndexedDB.
- When you come back online, it automatically redirects to the live dashboard.
