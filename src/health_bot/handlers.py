import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from health_bot.db import connect
from health_bot.seed import ensure_household
import secrets
import string
from datetime import datetime, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import re
from health_bot.scheduler import schedule_daily_reminders


log = logging.getLogger("health_bot.handlers")

# -------------------------
# Bottom menu (ReplyKeyboard)
# -------------------------

MENU_MAIN = "main"
MENU_DAILY = "daily"
MENU_WEEKLY = "weekly"
MENU_FAMILY = "family"
MENU_REMINDERS = "reminders"
MENU_SETUP = "setup"


def _menu_keyboard(menu: str) -> ReplyKeyboardMarkup:
    menu = menu or MENU_MAIN

    if menu == MENU_DAILY:
        buttons = [
            [KeyboardButton("📝 Check-in"), KeyboardButton("📊 Today")],
            [KeyboardButton("📈 Summary"), KeyboardButton("🔥 Streaks")],
            [KeyboardButton("🏠 Home"), KeyboardButton("⬅️ Back")],
        ]
    elif menu == MENU_WEEKLY:
        buttons = [
            [KeyboardButton("📅 Weekly"), KeyboardButton("📄 Weekly show")],
            [KeyboardButton("🛑 Weekly cancel")],
            [KeyboardButton("🏠 Home"), KeyboardButton("⬅️ Back")],
        ]
    elif menu == MENU_FAMILY:
        buttons = [
            [KeyboardButton("👨‍👩‍👧 Family summary")],
            [KeyboardButton("🏠 Home"), KeyboardButton("⬅️ Back")],
        ]
    elif menu == MENU_REMINDERS:
        buttons = [
            [KeyboardButton("🔔 Reminders on"), KeyboardButton("🔕 Reminders off")],
            [KeyboardButton("⏰ Set reminder"), KeyboardButton("✖️ Cancel")],
            [KeyboardButton("🏠 Home"), KeyboardButton("⬅️ Back")],
        ]
    elif menu == MENU_SETUP:
        buttons = [
            [KeyboardButton("➕ Invite"), KeyboardButton("🔗 Join")],
            [KeyboardButton("❓ Help")],
            [KeyboardButton("🏠 Home"), KeyboardButton("⬅️ Back")],
        ]
    else:
        # Main menu
        buttons = [
            [KeyboardButton("Daily ✅"), KeyboardButton("Weekly 📅")],
            [KeyboardButton("Family 👨‍👩‍👧"), KeyboardButton("Reminders ⏰")],
            [KeyboardButton("Setup ⚙️")],
        ]

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        is_persistent=True,
    )


def _set_menu_state(context: ContextTypes.DEFAULT_TYPE, menu: str) -> None:
    context.user_data["menu"] = menu


def _get_menu_state(context: ContextTypes.DEFAULT_TYPE) -> str:
    return str(context.user_data.get("menu") or MENU_MAIN)


def _normalize_menu_text(text: str) -> str:
    return (text or "").strip()

def _get_user_row(conn, telegram_user_id: int):
    return conn.execute(
        """
        SELECT id, household_id, timezone
          FROM users
         WHERE telegram_user_id = ?
        """,
        (telegram_user_id,),
    ).fetchone()


def _get_enabled_habits(conn, household_id: int):
    return conn.execute(
        """
        SELECT id, title, kind
          FROM habits
         WHERE household_id = ? AND enabled = 1
         ORDER BY sort_order ASC, id ASC
        """,
        (household_id,),
    ).fetchall()


def _today_date_str(tz_name: str) -> str:
    tz = ZoneInfo(tz_name)
    return datetime.now(tz).date().isoformat()


def _get_or_create_daily_entry_id(conn, user_id: int, date_str: str) -> int:
    row = conn.execute(
        "SELECT id FROM daily_entries WHERE user_id = ? AND date = ?",
        (user_id, date_str),
    ).fetchone()
    if row:
        return int(row["id"])

    cur = conn.execute(
        "INSERT INTO daily_entries (user_id, date) VALUES (?, ?)",
        (user_id, date_str),
    )
    return int(cur.lastrowid)


def _load_daily_values(conn, daily_entry_id: int) -> dict[int, str]:
    rows = conn.execute(
        "SELECT habit_id, value FROM daily_values WHERE daily_entry_id = ?",
        (daily_entry_id,),
    ).fetchall()
    return {int(r["habit_id"]): ("" if r["value"] is None else str(r["value"])) for r in rows}


def _set_daily_value(conn, daily_entry_id: int, habit_id: int, value: str) -> None:
    conn.execute(
        """
        INSERT INTO daily_values (daily_entry_id, habit_id, value)
        VALUES (?, ?, ?)
        ON CONFLICT(daily_entry_id, habit_id)
        DO UPDATE SET value = excluded.value,
                     updated_at = datetime('now')
        """,
        (daily_entry_id, habit_id, value),
    )
def _make_invite_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "JOIN-" + "".join(secrets.choice(alphabet) for _ in range(6))

def _week_start_date_str(tz_name: str) -> str:
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()
    monday = today - timedelta(days=today.weekday())  # Monday = 0
    return monday.isoformat()

def _current_week_start_for_user(tz_name: str) -> str:
    return _week_start_date_str(tz_name)

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id

    conn = connect(context.bot_data["db_path"])

    household_id = ensure_household(conn, "Family")

    row = conn.execute(
        "SELECT id FROM users WHERE telegram_user_id = ?",
        (user.id,),
    ).fetchone()

    if row:
        text = f"👋 Welcome back, {user.first_name}!"
    else:
        conn.execute(
            """
            INSERT INTO users (
                telegram_user_id,
                chat_id,
                household_id,
                timezone,
                first_name,
                username
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user.id,
                chat_id,
                household_id,
                context.bot_data["timezone"],
                user.first_name,
                user.username,
            ),
        )
        conn.commit()
        text = f"👋 Hi {user.first_name}! You’re registered."

    conn.close()
    _set_menu_state(context, MENU_MAIN)
    await update.message.reply_text(text, reply_markup=_menu_keyboard(MENU_MAIN))


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    # Bottom menu tip
    await update.message.reply_text(
        "📌 Commands (or use the bottom menu; /menu to show it)\n"
        "\n"
        "Daily\n"
        "  /checkin  – daily checklist (tap buttons)\n"
        "  /today    – today status (read-only)\n"
        "  /summary  – last 7 days (tracked vs success)\n"
        "  /streaks  – current streaks\n"
        "\n"
        "Weekly\n"
        "  /weekly        – weekly check-in\n"
        "  /weekly_cancel – cancel weekly check-in\n"
        "  /weekly_show   – show this week entry\n"
        "\n"
        "Family\n"
        "  /family_summary – household summary\n"
        "\n"
        "Reminders\n"
        "  /set_reminder HH:MM – set your daily reminder time\n"
        "  /reminders_on       – enable reminders\n"
        "  /reminders_off      – disable reminders\n"
        "\n"
        "Setup\n"
        "  /start   – register or reconnect\n"
        "  /invite  – create invite code\n"
        "  /join <code> – join household\n"
        "\n"
        "  /help – this help"
    )

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-show the current bottom menu keyboard."""
    if not update.message:
        return

    menu = _get_menu_state(context)
    await update.message.reply_text("📌 Menu", reply_markup=_menu_keyboard(menu))

async def invite_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    conn = connect(context.bot_data["db_path"])

    me = conn.execute(
        "SELECT id, household_id FROM users WHERE telegram_user_id = ?",
        (user.id,),
    ).fetchone()

    if not me or not me["household_id"]:
        conn.close()
        await update.message.reply_text("❌ You are not linked to a household. Use /start first.")
        return

    code = _make_invite_code()
    conn.execute(
        "INSERT INTO household_invites (household_id, code) VALUES (?, ?)",
        (int(me["household_id"]), code),
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Invite code created:\n\n`{code}`\n\n"
        f"Send it to your wife and ask her to run:\n`/join {code}`",
        parse_mode="Markdown",
    )


async def join_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id

    if not context.args:
        await update.message.reply_text("Usage: /join JOIN-XXXXXX")
        return

    code = context.args[0].strip()
    conn = connect(context.bot_data["db_path"])

    invite = conn.execute(
        "SELECT id, household_id, used_at FROM household_invites WHERE code = ?",
        (code,),
    ).fetchone()

    if not invite or invite["used_at"]:
        conn.close()
        await update.message.reply_text("❌ Invalid or already used invite code.")
        return

    # ensure user exists (in case they didn't run /start yet)
    row = conn.execute(
        "SELECT id FROM users WHERE telegram_user_id = ?",
        (user.id,),
    ).fetchone()

    if row:
        user_id = int(row["id"])
        conn.execute(
            """
            UPDATE users
               SET chat_id = ?, household_id = ?, timezone = ?, first_name = ?, username = ?
             WHERE id = ?
            """,
            (
                chat_id,
                int(invite["household_id"]),
                context.bot_data["timezone"],
                user.first_name,
                user.username,
                user_id,
            ),
        )
    else:
        cur = conn.execute(
            """
            INSERT INTO users (telegram_user_id, chat_id, household_id, timezone, first_name, username)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user.id,
                chat_id,
                int(invite["household_id"]),
                context.bot_data["timezone"],
                user.first_name,
                user.username,
            ),
        )
        user_id = int(cur.lastrowid)

    conn.execute(
        """
        UPDATE household_invites
           SET used_at = datetime('now'),
               used_by_user_id = ?
         WHERE id = ?
        """,
        (user_id, int(invite["id"])),
    )

    conn.commit()
    conn.close()

    _set_menu_state(context, MENU_MAIN)
    await update.message.reply_text(
        "✅ Joined the household! You’re ready for daily check-ins.",
        reply_markup=_menu_keyboard(MENU_MAIN),
    )

def _status_for_habit(kind: str, value: str) -> str:
    if not value:
        return "▫️"
    if kind == "boolean":
        return "✅" if value == "1" else "❌"
    if kind == "choice":
        return value
    return "▫️"

CHECKIN_PAGES = ["nutrition", "activity", "sleep", "discipline", "mental"]

def _page_index(page: str) -> int:
    try:
        return CHECKIN_PAGES.index(page)
    except ValueError:
        return 0

def _clamp_page(page: str) -> str:
    return page if page in CHECKIN_PAGES else CHECKIN_PAGES[0]

def _habits_for_page(habits, page: str):
    page = _clamp_page(page)
    return [h for h in habits if _habit_category(str(h["title"])) == page]

def _page_label(page: str) -> str:
    # Reuse your existing titles, but keep them short
    return _category_title(page)

def _habit_category(title: str) -> str:
    t = title.lower()

    # Mental
    if "настр" in t:
        return "mental"

    # Sleep & recovery
    if "сон" in t or "до сну" in t or "телефон" in t or "розтяж" in t or "віднов" in t:
        return "sleep"

    # Activity
    if "актив" in t or "шаг" in t or "крок" in t or "скакал" in t or "тренув" in t or "прогуля" in t:
        return "activity"

    # Nutrition
    if (
        "кави" in t or "кава" in t or "алког" in t or "вода" in t or "їсти" in t
        or "снідан" in t or "солод" in t or "тарілк" in t
    ):
        return "nutrition"

    # Discipline / relationship / misc
    return "discipline"


def _category_title(cat: str) -> str:
    return {
        "nutrition": "🥗 Nutrition",
        "activity": "🏃 Activity",
        "sleep": "😴 Sleep & recovery",
        "mental": "🧠 Mental",
        "discipline": "🧹 Discipline",
    }.get(cat, "🧩 Other")

def _count_done_in_habits(habits_subset, values_by_habit_id: dict[int, str]) -> tuple[int, int]:
    """Return (done, total) for a list of habit rows.

    Done means: value is non-empty ("1"/"0" for booleans, emoji for mood).
    """
    total = len(habits_subset)
    done = 0
    for h in habits_subset:
        hid = int(h["id"])
        v = values_by_habit_id.get(hid, "")
        if str(v).strip() != "":
            done += 1
    return done, total

def _build_checkin_text(date_str: str, habits, values_by_habit_id: dict[int, str], page: str) -> str:
    page = _clamp_page(page)
    page_habits = _habits_for_page(habits, page)
    page_num = _page_index(page) + 1
    total_pages = len(CHECKIN_PAGES)

    done, total = _count_done_in_habits(page_habits, values_by_habit_id)

    lines = [
        f"🗓️ Daily check-in — {date_str}",
        f"{_page_label(page)} (page {page_num}/{total_pages}) — {done}/{total}",
        "",
    ]

    for i, h in enumerate(page_habits, start=1):
        hid = int(h["id"])
        title = str(h["title"]).strip()
        kind = str(h["kind"])
        val = values_by_habit_id.get(hid, "")
        lines.append(f"{i}. {_status_for_habit(kind, val)} {title}")

    lines.append("")
    lines.append("Tap ✅/❌. Use ⬅️/➡️ to change section.")
    return "\n".join(lines)


def _build_checkin_keyboard(habits, values_by_habit_id: dict[int, str], page: str) -> InlineKeyboardMarkup:
    page = _clamp_page(page)
    page_habits = _habits_for_page(habits, page)

    rows: list[list[InlineKeyboardButton]] = []

    # Jump to section (compact row for phone UX)
    rows.append(
        [
            InlineKeyboardButton("🥗", callback_data="hcp:nutrition"),
            InlineKeyboardButton("🏃", callback_data="hcp:activity"),
            InlineKeyboardButton("😴", callback_data="hcp:sleep"),
            InlineKeyboardButton("🧹", callback_data="hcp:discipline"),
            InlineKeyboardButton("🧠", callback_data="hcp:mental"),
        ]
    )

    for h in page_habits:
        hid = int(h["id"])
        kind = str(h["kind"])
        current = values_by_habit_id.get(hid, "")

        if kind == "choice":
            rows.append(
                [
                    InlineKeyboardButton("😊✓" if current == "😊" else "😊", callback_data=f"hc:{hid}:😊:{page}"),
                    InlineKeyboardButton("😐✓" if current == "😐" else "😐", callback_data=f"hc:{hid}:😐:{page}"),
                    InlineKeyboardButton("😞✓" if current == "😞" else "😞", callback_data=f"hc:{hid}:😞:{page}"),
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton("✅✓" if current == "1" else "✅", callback_data=f"hc:{hid}:1:{page}"),
                    InlineKeyboardButton("❌✓" if current == "0" else "❌", callback_data=f"hc:{hid}:0:{page}"),
                ]
        )

    idx = _page_index(page)
    prev_page = CHECKIN_PAGES[idx - 1] if idx > 0 else None
    next_page = CHECKIN_PAGES[idx + 1] if idx < len(CHECKIN_PAGES) - 1 else None

    nav_row: list[InlineKeyboardButton] = []
    if prev_page:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"hcp:{prev_page}"))
    if next_page:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"hcp:{next_page}"))
    nav_row.append(InlineKeyboardButton("📊 Overview", callback_data=f"hc:0:overview:{page}"))
    nav_row.append(InlineKeyboardButton("✅ All", callback_data=f"hc:0:allok:{page}"))
    nav_row.append(InlineKeyboardButton("🔄 Refresh", callback_data=f"hc:0:refresh:{page}"))
    rows.append(nav_row)

    return InlineKeyboardMarkup(rows)

def _build_overview_text(date_str: str, habits, values_by_habit_id: dict[int, str]) -> str:
    lines = [f"🗓️ Daily check-in — {date_str}", "📊 Overview", ""]
    for p in CHECKIN_PAGES:
        page_habits = _habits_for_page(habits, p)
        if not page_habits:
            continue
        done, total = _count_done_in_habits(page_habits, values_by_habit_id)
        lines.append(f"{_page_label(p)} — {done}/{total}")
        for h in page_habits:
            hid = int(h["id"])
            title = str(h["title"]).strip()
            kind = str(h["kind"])
            val = values_by_habit_id.get(hid, "")
            lines.append(f"{_status_for_habit(kind, val)} {title}")
        lines.append("")
    lines.append("Use buttons below to jump to a section.")
    return "\n".join(lines)


def _build_overview_keyboard(current_page: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("🥗", callback_data="hcp:nutrition"),
            InlineKeyboardButton("🏃", callback_data="hcp:activity"),
            InlineKeyboardButton("😴", callback_data="hcp:sleep"),
            InlineKeyboardButton("🧹", callback_data="hcp:discipline"),
            InlineKeyboardButton("🧠", callback_data="hcp:mental"),
        ]
    ]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data=f"hcp:{_clamp_page(current_page)}")])
    return InlineKeyboardMarkup(rows)

async def checkin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    if not tg_user or not update.effective_chat or not update.message:
        return

    conn = connect(context.bot_data["db_path"])

    user_row = _get_user_row(conn, tg_user.id)
    if not user_row:
        conn.close()
        await update.message.reply_text("Please run /start first.")
        return

    user_id = int(user_row["id"])
    household_id = int(user_row["household_id"]) if user_row["household_id"] is not None else None
    tz_name = str(user_row["timezone"] or context.bot_data["timezone"])

    if not household_id:
        conn.close()
        await update.message.reply_text("You are not linked to a household. Use /start first.")
        return

    date_str = _today_date_str(tz_name)
    daily_entry_id = _get_or_create_daily_entry_id(conn, user_id, date_str)
    habits = _get_enabled_habits(conn, household_id)
    values = _load_daily_values(conn, daily_entry_id)

    conn.commit()
    conn.close()

    page = "nutrition"
    text = _build_checkin_text(date_str, habits, values, page)
    markup = _build_checkin_keyboard(habits, values, page)
    await update.message.reply_text(text, reply_markup=markup)


async def checkin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q:
        return

    data = q.data or ""

    # Defaults
    page = "nutrition"
    habit_id = 0
    value = "refresh"

    if data.startswith("hcp:"):
        page = data.split(":", 1)[1].strip() or "nutrition"
        value = "nav"   # IMPORTANT: navigation must re-render TEXT, not only markup
    else:
        # Update/refresh: hc:<habit_id>:<value>:<page>
        parts = data.split(":", 3)
        if len(parts) < 3:
            await q.answer()
            return

        try:
            habit_id = int(parts[1])
        except ValueError:
            await q.answer()
            return

        value = parts[2]
        if len(parts) == 4 and parts[3].strip():
            page = parts[3].strip()

    tg_user = update.effective_user
    if not tg_user:
        await q.answer()
        return

    conn = connect(context.bot_data["db_path"])
    user_row = _get_user_row(conn, tg_user.id)
    if not user_row or user_row["household_id"] is None:
        conn.close()
        await q.answer()
        return

    user_id = int(user_row["id"])
    household_id = int(user_row["household_id"])
    tz_name = str(user_row["timezone"] or context.bot_data["timezone"])
    date_str = _today_date_str(tz_name)

    daily_entry_id = _get_or_create_daily_entry_id(conn, user_id, date_str)

    # Persist only when it's a real habit update
    # Persist only when it's a real habit update
    if habit_id != 0 and value not in ("refresh", "overview", "allok"):
        _set_daily_value(conn, daily_entry_id, habit_id, value)

    habits = _get_enabled_habits(conn, household_id)
    values = _load_daily_values(conn, daily_entry_id)

    # ✅ All in this section: set all boolean habits in the current page to "1"
    if habit_id == 0 and value == "allok":
        page_habits = _habits_for_page(habits, page)
        for h in page_habits:
            if str(h["kind"]) != "boolean":
                continue
            hid = int(h["id"])
            _set_daily_value(conn, daily_entry_id, hid, "1")

        # Reload after bulk update
        values = _load_daily_values(conn, daily_entry_id)

    conn.commit()
    conn.close()

    text = _build_checkin_text(date_str, habits, values, page)
    markup = _build_checkin_keyboard(habits, values, page)

    # One answer per callback. Provide user feedback especially for refresh.
    toast = ""
    if habit_id == 0 and value == "refresh":
        toast = "Up to date ✅"
    elif habit_id == 0 and value == "allok":
        toast = "All set ✅"
    elif habit_id == 0 and value == "overview":
        toast = ""
    elif data.startswith("hcp:"):
        toast = ""
    else:
        toast = "Saved ✅"

    try:
        if habit_id == 0 and value == "refresh":
            await q.edit_message_reply_markup(reply_markup=markup)
        elif habit_id == 0 and value == "overview":
            overview_text = _build_overview_text(date_str, habits, values)
            overview_markup = _build_overview_keyboard(page)
            await q.edit_message_text(overview_text, reply_markup=overview_markup)
        else:
            await q.edit_message_text(text, reply_markup=markup)

        await q.answer(toast) if toast else await q.answer()

    except BadRequest as e:
        msg = str(e).lower()
        # Common for refresh / no-op edits
        if "not modified" in msg:
            await q.answer(toast or "Up to date ✅")
            return

        log.exception("Failed to edit check-in message")
        await q.answer("Error ❌")

    except Exception:
        log.exception("Failed to edit check-in message")
        await q.answer("Error ❌")

async def today_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    if not tg_user or not update.message:
        return

    conn = connect(context.bot_data["db_path"])

    user_row = _get_user_row(conn, tg_user.id)
    if not user_row:
        conn.close()
        await update.message.reply_text("Please run /start first.")
        return

    user_id = int(user_row["id"])
    household_id = int(user_row["household_id"])
    tz_name = str(user_row["timezone"] or context.bot_data["timezone"])

    date_str = _today_date_str(tz_name)

    entry = conn.execute(
        "SELECT id FROM daily_entries WHERE user_id = ? AND date = ?",
        (user_id, date_str),
    ).fetchone()

    habits = _get_enabled_habits(conn, household_id)

    if not entry:
        conn.close()
        await update.message.reply_text("📭 No check-in yet today.\nUse /checkin to start.")
        return

    values = _load_daily_values(conn, int(entry["id"]))
    conn.close()

    lines = [f"🗓️ Today — {date_str}", ""]
    for p in CHECKIN_PAGES:
        page_habits = _habits_for_page(habits, p)
        if not page_habits:
            continue
        lines.append(_page_label(p))
        for h in page_habits:
            hid = int(h["id"])
            title = str(h["title"]).strip()
            kind = str(h["kind"])
            val = values.get(hid, "")
            lines.append(f"{_status_for_habit(kind, val)} {title}")
        lines.append("")

    await update.message.reply_text("\n".join(lines))


def _last_n_dates(tz_name: str, n: int) -> list[str]:
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()
    return [(today - timedelta(days=i)).isoformat() for i in range(n)]


def _format_pct(numer: int, denom: int) -> str:
    if denom <= 0:
        return "0%"
    pct = int(round((numer / denom) * 100))
    return f"{pct}%"


async def summary_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    if not tg_user or not update.message:
        return

    conn = connect(context.bot_data["db_path"])

    user_row = _get_user_row(conn, tg_user.id)
    if not user_row:
        conn.close()
        await update.message.reply_text("Please run /start first.")
        return

    user_id = int(user_row["id"])
    household_id = int(user_row["household_id"])
    tz_name = str(user_row["timezone"] or context.bot_data["timezone"])

    habits = _get_enabled_habits(conn, household_id)
    total_habits = len(habits)

    habit_kind_by_id: dict[int, str] = {int(h["id"]): str(h["kind"]) for h in habits}
    total_boolean_habits = sum(1 for k in habit_kind_by_id.values() if k == "boolean")

    dates = _last_n_dates(tz_name, 7)

    placeholders = ",".join(["?"] * len(dates))
    rows = conn.execute(
        f"""
        SELECT de.date AS date,
               dv.habit_id AS habit_id,
               dv.value AS value
          FROM daily_entries de
          LEFT JOIN daily_values dv ON dv.daily_entry_id = de.id
         WHERE de.user_id = ?
           AND de.date IN ({placeholders})
        """,
        (user_id, *dates),
    ).fetchall()

    conn.close()

    tracked_by_date: dict[str, int] = {d: 0 for d in dates}
    success_by_date: dict[str, int] = {d: 0 for d in dates}

    for r in rows:
        d = str(r["date"])
        hid = r["habit_id"]
        v = r["value"]

        if v is None:
            continue
        v_str = str(v).strip()
        if v_str == "":
            continue

        tracked_by_date[d] = tracked_by_date.get(d, 0) + 1

        if hid is None:
            continue
        kind = habit_kind_by_id.get(int(hid))
        if kind == "boolean" and v_str == "1":
            success_by_date[d] = success_by_date.get(d, 0) + 1

    lines = ["📊 Summary — last 7 days", ""]
    for d in dates:
        tracked = tracked_by_date.get(d, 0)
        success = success_by_date.get(d, 0)
        lines.append(
            f"{d}: tracked {tracked}/{total_habits} ({_format_pct(tracked, total_habits)}) | "
            f"success {success}/{total_boolean_habits} ({_format_pct(success, total_boolean_habits)})"
        )

    overall_tracked = sum(tracked_by_date.values())
    overall_tracked_total = total_habits * len(dates)

    overall_success = sum(success_by_date.values())
    overall_success_total = total_boolean_habits * len(dates)

    lines.append("")
    lines.append(
        f"Total: tracked {overall_tracked}/{overall_tracked_total} ({_format_pct(overall_tracked, overall_tracked_total)}) | "
        f"success {overall_success}/{overall_success_total} ({_format_pct(overall_success, overall_success_total)})"
    )

    await update.message.reply_text("\n".join(lines))

async def reminder_wizard_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start reminder time wizard (menu UX)."""
    if not update.message:
        return

    # Start wizard
    context.user_data["reminder_step"] = "time"

    await update.message.reply_text(
        "⏰ Set daily reminder\n\n"
        "Send time (e.g. 21:30, 9:05, 21-30, 2130)\n"
        "Type 'cancel' to stop.",
        reply_markup=_menu_keyboard(MENU_REMINDERS),
    )

def _parse_time_hhmm(text: str) -> str | None:
    """Parse user time input and normalize to HH:MM (24h).

    Accepts: 9:05, 9.05, 09 05, 21-30, 2130, 21 30.
    Returns normalized 'HH:MM' or None if invalid.
    """
    t = (text or "").strip()
    if not t:
        return None

    # Normalize common separators to ':'
    for sep in (".", "-", " ", ";"):
        t = t.replace(sep, ":")

    # Handle 4 digits like 2130
    if re.match(r"^\d{4}$", t):
        t = t[:2] + ":" + t[2:]

    m = re.match(r"^(\d{1,2}):(\d{1,2})$", t)
    if not m:
        return None

    try:
        hour = int(m.group(1))
        minute = int(m.group(2))
    except ValueError:
        return None

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    return f"{hour:02d}:{minute:02d}"

async def reminder_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user input for reminder wizard."""
    if not update.message:
        return

    step = context.user_data.get("reminder_step")
    if step != "time":
        return

    tg_user = update.effective_user
    if not tg_user:
        return

    text = (update.message.text or "").strip()
    if text == "✖️ Cancel" or text.lower() in ("cancel", "/cancel"):
        context.user_data.pop("reminder_step", None)
        await update.message.reply_text("✅ Reminder setup cancelled.", reply_markup=_menu_keyboard(MENU_REMINDERS))
        return

    value = _parse_time_hhmm(text)
    if not value:
        await update.message.reply_text(
            "Invalid time. Examples: 21:30, 9:05, 21-30, 2130. Or type 'cancel'."
        )
        return

    conn = connect(context.bot_data["db_path"])
    user_row = _get_user_row(conn, tg_user.id)
    if not user_row:
        conn.close()
        await update.message.reply_text("Please run /start first.")
        return

    conn.execute(
        "UPDATE users SET reminder_time = ?, reminders_enabled = 1 WHERE id = ?",
        (value, int(user_row["id"])),
    )
    conn.commit()
    conn.close()

    # Reschedule jobs (simple v1 approach: reschedule all users)
    schedule_daily_reminders(
        context.application,
        db_path=context.bot_data["db_path"],
        timezone=context.bot_data["timezone"],
        default_hour=context.bot_data.get("default_reminder_hour", 21),
        default_minute=context.bot_data.get("default_reminder_minute", 0),
    )

    context.user_data.pop("reminder_step", None)
    await update.message.reply_text(f"✅ Reminder time set to {value}", reply_markup=_menu_keyboard(MENU_REMINDERS))

async def join_wizard_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start join-household wizard (menu UX)."""
    if not update.message:
        return

    context.user_data["join_step"] = "code"

    await update.message.reply_text(
        "🔗 Join household\n\n"
        "Send invite code like: JOIN-XXXXXX\n"
        "Type 'cancel' to stop.",
        reply_markup=_menu_keyboard(MENU_SETUP),
    )


async def join_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user input for join-household wizard."""
    if not update.message:
        return

    step = context.user_data.get("join_step")
    if step != "code":
        return

    text = (update.message.text or "").strip()

    if text == "✖️ Cancel" or text.lower() in ("cancel", "/cancel"):
        context.user_data.pop("join_step", None)
        await update.message.reply_text("✅ Join cancelled.", reply_markup=_menu_keyboard(MENU_SETUP))
        return

    code = text.upper().replace(" ", "")

    if not re.match(r"^JOIN-[A-Z0-9]{6}$", code):
        await update.message.reply_text("Invalid code. Send JOIN-XXXXXX or type 'cancel'.")
        return

    # Reuse existing /join handler by temporarily setting context.args
    old_args = getattr(context, "args", None)
    try:
        context.args = [code]
        await join_handler(update, context)
    finally:
        context.args = old_args if old_args is not None else []

    context.user_data.pop("join_step", None)

async def set_reminder_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    tg_user = update.effective_user
    if not tg_user:
        return

    if not context.args:
        await update.message.reply_text("Usage: /set_reminder HH:MM (e.g. /set_reminder 21:30)")
        return

    raw = context.args[0].strip()
    value = _parse_time_hhmm(raw)
    if not value:
        await update.message.reply_text(
            "Invalid time. Examples: /set_reminder 21:30, /set_reminder 9:05, /set_reminder 2130"
        )
        return

    conn = connect(context.bot_data["db_path"])
    user_row = _get_user_row(conn, tg_user.id)
    if not user_row:
        conn.close()
        await update.message.reply_text("Please run /start first.")
        return

    conn.execute(
        "UPDATE users SET reminder_time = ?, reminders_enabled = 1 WHERE id = ?",
        (value, int(user_row["id"])),
    )
    conn.commit()
    conn.close()

    # Reschedule jobs (simple v1 approach: reschedule all users)
    schedule_daily_reminders(
        context.application,
        db_path=context.bot_data["db_path"],
        timezone=context.bot_data["timezone"],
        default_hour=context.bot_data.get("default_reminder_hour", 21),
        default_minute=context.bot_data.get("default_reminder_minute", 0),
    )

    await update.message.reply_text(f"✅ Reminder time set to {value}")


async def reminders_off_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    tg_user = update.effective_user
    if not tg_user:
        return

    conn = connect(context.bot_data["db_path"])
    user_row = _get_user_row(conn, tg_user.id)
    if not user_row:
        conn.close()
        await update.message.reply_text("Please run /start first.")
        return

    conn.execute(
        "UPDATE users SET reminders_enabled = 0 WHERE id = ?",
        (int(user_row["id"]),),
    )
    conn.commit()
    conn.close()

    schedule_daily_reminders(
        context.application,
        db_path=context.bot_data["db_path"],
        timezone=context.bot_data["timezone"],
        default_hour=context.bot_data.get("default_reminder_hour", 21),
        default_minute=context.bot_data.get("default_reminder_minute", 0),
    )

    await update.message.reply_text("🔕 Reminders disabled")


async def reminders_on_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    tg_user = update.effective_user
    if not tg_user:
        return

    conn = connect(context.bot_data["db_path"])
    user_row = _get_user_row(conn, tg_user.id)
    if not user_row:
        conn.close()
        await update.message.reply_text("Please run /start first.")
        return

    conn.execute(
        "UPDATE users SET reminders_enabled = 1 WHERE id = ?",
        (int(user_row["id"]),),
    )
    conn.commit()
    conn.close()

    schedule_daily_reminders(
        context.application,
        db_path=context.bot_data["db_path"],
        timezone=context.bot_data["timezone"],
        default_hour=context.bot_data.get("default_reminder_hour", 21),
        default_minute=context.bot_data.get("default_reminder_minute", 0),
    )

    await update.message.reply_text("🔔 Reminders enabled")

async def weekly_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    tg_user = update.effective_user
    if not tg_user:
        return

    conn = connect(context.bot_data["db_path"])
    user_row = _get_user_row(conn, tg_user.id)
    if not user_row:
        conn.close()
        await update.message.reply_text("Please run /start first.")
        return

    tz_name = str(user_row["timezone"] or context.bot_data["timezone"])
    week_start = _week_start_date_str(tz_name)

    # start wizard
    context.user_data["weekly_step"] = "weight"
    context.user_data["weekly_week_start"] = week_start
    context.user_data["weekly_weight"] = None
    context.user_data["weekly_rating"] = None
    context.user_data["weekly_note"] = None

    conn.close()

    await update.message.reply_text(
        f"📅 Weekly check-in (week starting {week_start})\n\n"
        "1/3) Weight in kg? (example: 78.5)\n"
        "Reply with a number, or type `skip`.",
        parse_mode="Markdown",
    )


async def weekly_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    context.user_data.pop("weekly_step", None)
    context.user_data.pop("weekly_week_start", None)
    context.user_data.pop("weekly_weight", None)
    context.user_data.pop("weekly_rating", None)
    context.user_data.pop("weekly_note", None)

    await update.message.reply_text("✅ Weekly check-in cancelled.")


async def weekly_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    step = context.user_data.get("weekly_step")
    if not step:
        return  # not in weekly flow

    tg_user = update.effective_user
    if not tg_user:
        return

    text = (update.message.text or "").strip()

    # Step 1: weight
    if step == "weight":
        if text.lower() != "skip":
            try:
                context.user_data["weekly_weight"] = float(text.replace(",", "."))
            except ValueError:
                await update.message.reply_text("Please enter a number (e.g. 78.5) or `skip`.")
                return

        context.user_data["weekly_step"] = "rating"
        await update.message.reply_text(
            "2/3) Week rating 1–10?\nReply with a number or type `skip`.",
            parse_mode="Markdown",
        )
        return

    # Step 2: rating
    if step == "rating":
        if text.lower() != "skip":
            try:
                rating = int(text)
                if rating < 1 or rating > 10:
                    raise ValueError()
                context.user_data["weekly_rating"] = rating
            except ValueError:
                await update.message.reply_text("Please enter an integer 1–10 or `skip`.")
                return

        context.user_data["weekly_step"] = "note"
        await update.message.reply_text(
            "3/3) Any note for the week? (optional)\nReply with text or type `skip`.",
            parse_mode="Markdown",
        )
        return

    # Step 3: note -> save
    if step == "note":
        if text.lower() != "skip":
            context.user_data["weekly_note"] = text

        week_start = context.user_data.get("weekly_week_start")
        weight = context.user_data.get("weekly_weight")
        rating = context.user_data.get("weekly_rating")
        note = context.user_data.get("weekly_note")

        conn = connect(context.bot_data["db_path"])
        user_row = _get_user_row(conn, tg_user.id)
        if not user_row:
            conn.close()
            await update.message.reply_text("Please run /start first.")
            return

        user_id = int(user_row["id"])

        conn.execute(
            """
            INSERT INTO weekly_entries (user_id, week_start_date, weight_kg, week_rating, note)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, week_start_date)
            DO UPDATE SET
                weight_kg = excluded.weight_kg,
                week_rating = excluded.week_rating,
                note = excluded.note,
                updated_at = datetime('now')
            """,
            (user_id, week_start, weight, rating, note),
        )
        conn.commit()
        conn.close()

        # clear state
        context.user_data.pop("weekly_step", None)
        context.user_data.pop("weekly_week_start", None)
        context.user_data.pop("weekly_weight", None)
        context.user_data.pop("weekly_rating", None)
        context.user_data.pop("weekly_note", None)

        await update.message.reply_text(
            "✅ Weekly check-in saved:\n"
            f"- Week start: {week_start}\n"
            f"- Weight: {weight if weight is not None else '—'}\n"
            f"- Rating: {rating if rating is not None else '—'}\n"
            f"- Note: {note if note else '—'}"
        )
        return

async def weekly_show_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    tg_user = update.effective_user
    if not tg_user:
        return

    conn = connect(context.bot_data["db_path"])
    user_row = _get_user_row(conn, tg_user.id)
    if not user_row:
        conn.close()
        await update.message.reply_text("Please run /start first.")
        return

    user_id = int(user_row["id"])
    tz_name = str(user_row["timezone"] or context.bot_data["timezone"])
    week_start = _current_week_start_for_user(tz_name)

    row = conn.execute(
        """
        SELECT week_start_date, weight_kg, week_rating, note
          FROM weekly_entries
         WHERE user_id = ? AND week_start_date = ?
        """,
        (user_id, week_start),
    ).fetchone()
    conn.close()

    if not row:
        await update.message.reply_text(
            f"📭 No weekly check-in saved for week starting {week_start}.\nUse /weekly"
        )
        return

    await update.message.reply_text(
        "📅 Weekly check-in:\n"
        f"- Week start: {row['week_start_date']}\n"
        f"- Weight: {row['weight_kg'] if row['weight_kg'] is not None else '—'}\n"
        f"- Rating: {row['week_rating'] if row['week_rating'] is not None else '—'}\n"
        f"- Note: {row['note'] if row['note'] else '—'}"
    )

async def family_summary_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    tg_user = update.effective_user
    if not tg_user:
        return

    conn = connect(context.bot_data["db_path"])
    me = _get_user_row(conn, tg_user.id)
    if not me or me["household_id"] is None:
        conn.close()
        await update.message.reply_text("Please run /start first.")
        return

    household_id = int(me["household_id"])
    tz_name = str(me["timezone"] or context.bot_data["timezone"])

    users = conn.execute(
        """
        SELECT id, first_name, telegram_user_id
          FROM users
         WHERE household_id = ?
         ORDER BY first_name ASC, id ASC
        """,
        (household_id,),
    ).fetchall()

    habits = _get_enabled_habits(conn, household_id)
    total_habits = len(habits)
    habit_kind_by_id: dict[int, str] = {int(h["id"]): str(h["kind"]) for h in habits}
    total_boolean_habits = sum(1 for k in habit_kind_by_id.values() if k == "boolean")

    dates = _last_n_dates(tz_name, 7)
    placeholders = ",".join(["?"] * len(dates))

    lines = ["👨‍👩‍👧 Family summary — last 7 days", ""]

    for u in users:
        uid = int(u["id"])
        name = u["first_name"] or str(u["telegram_user_id"])

        rows = conn.execute(
            f"""
            SELECT dv.habit_id AS habit_id,
                   dv.value AS value
              FROM daily_entries de
              LEFT JOIN daily_values dv ON dv.daily_entry_id = de.id
             WHERE de.user_id = ?
               AND de.date IN ({placeholders})
            """,
            (uid, *dates),
        ).fetchall()

        tracked = 0
        success = 0

        for r in rows:
            v = r["value"]
            if v is None:
                continue
            v_str = str(v).strip()
            if not v_str:
                continue
            tracked += 1

            hid = r["habit_id"]
            if hid is not None and habit_kind_by_id.get(int(hid)) == "boolean" and v_str == "1":
                success += 1

        tracked_total = total_habits * len(dates)
        success_total = total_boolean_habits * len(dates)

        lines.append(
            f"{name}: tracked {tracked}/{tracked_total} ({_format_pct(tracked, tracked_total)}) | "
            f"success {success}/{success_total} ({_format_pct(success, success_total)})"
        )

    conn.close()
    await update.message.reply_text("\n".join(lines))

def _is_day_perfect(values_by_habit_id: dict[int, str], habits) -> bool:
    for h in habits:
        if str(h["kind"]) != "boolean":
            continue
        if values_by_habit_id.get(int(h["id"])) != "1":
            return False
    return True


async def streaks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    tg_user = update.effective_user
    if not tg_user:
        return

    conn = connect(context.bot_data["db_path"])
    user_row = _get_user_row(conn, tg_user.id)
    if not user_row or user_row["household_id"] is None:
        conn.close()
        await update.message.reply_text("Please run /start first.")
        return

    user_id = int(user_row["id"])
    household_id = int(user_row["household_id"])
    tz_name = str(user_row["timezone"] or context.bot_data["timezone"])

    habits = _get_enabled_habits(conn, household_id)

    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()

    lookback_days = 90
    start_date = (today - timedelta(days=lookback_days)).isoformat()

    entries = conn.execute(
        """
        SELECT id, date
          FROM daily_entries
         WHERE user_id = ?
           AND date >= ?
         ORDER BY date DESC
        """,
        (user_id, start_date),
    ).fetchall()

    entry_by_date: dict[str, int] = {str(e["date"]): int(e["id"]) for e in entries}

    def has_any_value(entry_id: int) -> bool:
        c = conn.execute(
            "SELECT COUNT(1) AS c FROM daily_values WHERE daily_entry_id = ?",
            (entry_id,),
        ).fetchone()["c"]
        return int(c) > 0

    def is_perfect(entry_id: int) -> bool:
        vals = _load_daily_values(conn, entry_id)
        return _is_day_perfect(vals, habits)

    def calc_streak(check_fn) -> int:
        streak = 0
        d = today
        for _ in range(lookback_days + 1):
            ds = d.isoformat()
            entry_id = entry_by_date.get(ds)
            if not entry_id:
                break
            if not check_fn(entry_id):
                break
            streak += 1
            d = d - timedelta(days=1)
        return streak

    checkin_streak = calc_streak(has_any_value)
    perfect_streak = calc_streak(is_perfect)

    conn.close()

    await update.message.reply_text(
        "🔥 Streaks:\n"
        f"- Check-in streak (any values): {checkin_streak} day(s)\n"
        f"- Perfect streak (all ✅ booleans): {perfect_streak} day(s)"
    )



# --- MENU ROUTER HANDLER ---

async def menu_router_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route bottom-menu button presses.

    Important: do NOT interfere with weekly wizard input.
    """
    if not update.message:
        return

    # If weekly wizard is active, route text to the wizard first
    if context.user_data.get("weekly_step"):
        await weekly_input_handler(update, context)
        return

    # If reminder wizard is active, route text to it
    if context.user_data.get("reminder_step"):
        await reminder_input_handler(update, context)
        return

    if context.user_data.get("join_step"):
        await join_input_handler(update, context)
        return

    text = _normalize_menu_text(update.message.text)

    # Global actions
    if text in ("❓ Help",):
        await help_handler(update, context)
        return

    if text == "🏠 Home":
        _set_menu_state(context, MENU_MAIN)
        await update.message.reply_text("🏠 Main", reply_markup=_menu_keyboard(MENU_MAIN))
        return

    # Back always returns to main
    if text == "⬅️ Back":
        _set_menu_state(context, MENU_MAIN)
        await update.message.reply_text("🏠 Main", reply_markup=_menu_keyboard(MENU_MAIN))
        return

    # Navigate between menu pages
    if text == "Daily ✅":
        _set_menu_state(context, MENU_DAILY)
        await update.message.reply_text("✅ Daily", reply_markup=_menu_keyboard(MENU_DAILY))
        return

    if text == "Weekly 📅":
        _set_menu_state(context, MENU_WEEKLY)
        await update.message.reply_text("📅 Weekly", reply_markup=_menu_keyboard(MENU_WEEKLY))
        return

    if text == "Family 👨‍👩‍👧":
        _set_menu_state(context, MENU_FAMILY)
        await update.message.reply_text("👨‍👩‍👧 Family", reply_markup=_menu_keyboard(MENU_FAMILY))
        return

    if text == "Reminders ⏰":
        _set_menu_state(context, MENU_REMINDERS)
        await update.message.reply_text("⏰ Reminders", reply_markup=_menu_keyboard(MENU_REMINDERS))
        return

    if text == "Setup ⚙️":
        _set_menu_state(context, MENU_SETUP)
        await update.message.reply_text("⚙️ Setup", reply_markup=_menu_keyboard(MENU_SETUP))
        return

    # Daily actions
    if text == "📝 Check-in":
        await checkin_handler(update, context)
        return
    if text == "📊 Today":
        await today_handler(update, context)
        return
    if text == "📈 Summary":
        await summary_handler(update, context)
        return
    if text == "🔥 Streaks":
        await streaks_handler(update, context)
        return

    # Weekly actions
    if text == "📅 Weekly":
        await weekly_handler(update, context)
        return
    if text == "📄 Weekly show":
        await weekly_show_handler(update, context)
        return
    if text == "🛑 Weekly cancel":
        await weekly_cancel_handler(update, context)
        return

    # Family actions
    if text == "👨‍👩‍👧 Family summary":
        await family_summary_handler(update, context)
        return

    # Reminders actions
    if text == "🔔 Reminders on":
        await reminders_on_handler(update, context)
        return
    if text == "🔕 Reminders off":
        await reminders_off_handler(update, context)
        return
    if text == "✖️ Cancel":
        if context.user_data.get("reminder_step"):
            context.user_data.pop("reminder_step", None)
            await update.message.reply_text("✅ Cancelled reminder setup.", reply_markup=_menu_keyboard(MENU_REMINDERS))
            return

        if context.user_data.get("join_step"):
            context.user_data.pop("join_step", None)
            await update.message.reply_text("✅ Cancelled join.", reply_markup=_menu_keyboard(MENU_REMINDERS))
            return

        await update.message.reply_text("Nothing to cancel.", reply_markup=_menu_keyboard(MENU_REMINDERS))
        return
    if text == "⏰ Set reminder":
        await reminder_wizard_start(update, context)
        return

    # Setup actions
    if text == "➕ Invite":
        await invite_handler(update, context)
        return
    if text == "🔗 Join":
        await join_wizard_start(update, context)
        return

    # Unknown text: ignore
    return