PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS households (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  telegram_user_id INTEGER NOT NULL UNIQUE,
  chat_id INTEGER NOT NULL,
  household_id INTEGER REFERENCES households(id) ON DELETE SET NULL,
  timezone TEXT NOT NULL,
  first_name TEXT,
  username TEXT,
  reminders_enabled INTEGER NOT NULL DEFAULT 1,
  reminder_time TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS habits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  kind TEXT NOT NULL,          -- boolean | number | choice | text
  target TEXT,                 -- optional (e.g. "10000")
  enabled INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS daily_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  date TEXT NOT NULL,          -- YYYY-MM-DD (user timezone)
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(user_id, date)
);

CREATE TABLE IF NOT EXISTS daily_values (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  daily_entry_id INTEGER NOT NULL REFERENCES daily_entries(id) ON DELETE CASCADE,
  habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
  value TEXT,                  -- store as text; parse by habit.kind
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(daily_entry_id, habit_id)
);

CREATE TABLE IF NOT EXISTS weekly_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  week_start_date TEXT NOT NULL,  -- YYYY-MM-DD (Monday)
  weight_kg REAL,
  week_rating INTEGER,            -- 1..10
  note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(user_id, week_start_date)
);

CREATE TABLE IF NOT EXISTS household_invites (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  code TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  used_at TEXT,
  used_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
);