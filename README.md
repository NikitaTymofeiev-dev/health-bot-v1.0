# 🧠 health_bot

A personal Telegram habit-tracking bot built for family use.

Tracks daily routines, weekly reflections, streaks, and generates simple local dashboards from SQLite.

Designed to be lightweight, private, and running 24/7 on a Mac mini.

---

## 🚀 Features

### ✅ Daily Tracking
- Boolean habits (✅ / ❌)
- Choice habits (😊 / 😐 / 😞)
- Success % calculation
- Tracked % calculation
- Streak tracking
- Category grouping (Nutrition, Activity, Sleep, etc.)

### 📅 Weekly Check-in
- Weekly weight
- Week rating (1–10)
- Notes

### 👨‍👩‍👧 Multi-user Household
- Invite / join flow
- Per-user reminders
- Family summary

### ⏰ Smart Reminders
- Per-user reminder time
- Enable / disable reminders
- Reminder wizard

### 📊 Local Dashboard
- Success % charts
- Tracked % charts
- Weekly weight trend
- Weekly rating trend
- Generated directly from SQLite

---

## 🏗 Project Structure

```
src/health_bot/
    main.py
    bot.py
    db.py
    config.py
    scheduler.py
    handlers/

scripts/
    init_db.py
    seed_habits.py
    dashboard.py

 db/
    health_bot.sqlite3
```

---

## ⚙️ Setup

### 1️⃣ Create virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2️⃣ Install dependencies

```bash
pip install -r requirements.txt
```

### 3️⃣ Configure environment

Create `.env` file:

```
BOT_TOKEN=your_telegram_bot_token
TIMEZONE=Europe/Kiev
DB_PATH=db/health_bot.sqlite3
```

---

## 🧱 Initialize Database

```bash
PYTHONPATH=src python3 scripts/init_db.py
PYTHONPATH=src python3 scripts/seed_habits.py
```

---

## ▶️ Run Bot

```bash
PYTHONPATH=src python -m health_bot.main
```

For Mac auto-start via LaunchAgent (recommended for 24/7):

Use `caffeinate -i` to prevent throttling when laptop is locked.

---

## 📊 Generate Dashboard

```bash
python3 scripts/dashboard.py
```

Charts will be saved into `dashboards/` directory.

---

## 🔐 Philosophy

- No cloud dependency required
- SQLite-based
- Private
- Lightweight
- Designed for real daily use

---

## 🛠 Future Ideas

- Webhook mode
- Web dashboard
- Google Sheets sync
- AI habit recommendations
- Automated weekly report to Telegram

---

## 📄 License

Private project (for personal/family use).
