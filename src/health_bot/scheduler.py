import logging
from datetime import datetime, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo

from health_bot.db import connect

log = logging.getLogger("health_bot.scheduler")

def _week_start_date_str(tz_name: str) -> str:
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()
    monday = today - timedelta(days=today.weekday())  # Monday = 0
    return monday.isoformat()

def schedule_daily_reminders(
    app,
    *,
    db_path: str,
    timezone: str,
    default_hour: int = 21,
    default_minute: int = 0,
) -> None:
    """Per-user daily reminders using python-telegram-bot JobQueue.

    - Each user can set reminder_time (HH:MM) in their timezone.
    - reminders_enabled disables reminders per user.
    - Smart behavior: if user already saved at least one value today, skip.
    """

    # Remove previously scheduled per-user jobs
    for job in app.job_queue.jobs():
        if getattr(job, "name", "") and str(job.name).startswith("daily_checkin:"):
            job.schedule_removal()

    conn = connect(db_path)
    users = conn.execute(
        """
        SELECT id, telegram_user_id, chat_id, timezone, reminders_enabled, reminder_time
          FROM users
        """
    ).fetchall()
    conn.close()

    for u in users:
        try:
            if int(u["reminders_enabled"]) == 0:
                continue

            tz_name = (u["timezone"] or timezone).strip() or timezone
            tz = ZoneInfo(tz_name)

            hour, minute = default_hour, default_minute
            rt = (u["reminder_time"] or "").strip()
            if rt:
                parts = rt.split(":")
                if len(parts) == 2:
                    hour = int(parts[0])
                    minute = int(parts[1])

            when = dtime(hour=hour, minute=minute, tzinfo=tz)

            app.job_queue.run_daily(
                callback=_send_daily_reminder_one,
                time=when,
                name=f"daily_checkin:{int(u['id'])}",
                data={
                    "db_path": db_path,
                    "user_id": int(u["id"]),
                    "telegram_user_id": int(u["telegram_user_id"]),
                    "chat_id": int(u["chat_id"]),
                    "timezone": tz_name,
                },
            )

            log.info(
                "Daily reminder scheduled for user_id=%s at %02d:%02d (%s)",
                int(u["id"]),
                hour,
                minute,
                tz_name,
            )
        except Exception:
            log.exception("Failed to schedule reminder for user_id=%s", u.get("id"))


async def _send_daily_reminder_one(context) -> None:
    data = context.job.data
    db_path = data["db_path"]
    user_id = int(data["user_id"])
    chat_id = int(data["chat_id"])
    tz_name = (data.get("timezone") or "Europe/Kiev").strip()

    today = datetime.now(ZoneInfo(tz_name)).date().isoformat()

    conn = connect(db_path)
    entry = conn.execute(
        "SELECT id FROM daily_entries WHERE user_id = ? AND date = ?",
        (user_id, today),
    ).fetchone()

    if entry:
        value_count = conn.execute(
            "SELECT COUNT(1) AS c FROM daily_values WHERE daily_entry_id = ?",
            (entry["id"],),
        ).fetchone()["c"]

        # If user has at least one value saved today → skip reminder
        if int(value_count) > 0:
            conn.close()
            return

    conn.close()

    await context.bot.send_message(
        chat_id=chat_id,
        text="⏰ Time for your daily check-in 💪\n\nUse /checkin",
    )

def schedule_weekly_reminders(
    app,
    *,
    db_path: str,
    timezone: str,
    hour: int = 12,
    minute: int = 0,
) -> None:
    """Weekly reminder (Sunday) using JobQueue.

    Smart behavior: skip if weekly entry already exists for the current week.
    """

    # Remove previously scheduled weekly jobs
    for job in app.job_queue.jobs():
        if getattr(job, "name", "") and str(job.name).startswith("weekly_checkin:"):
            job.schedule_removal()

    conn = connect(db_path)
    users = conn.execute(
        """
        SELECT id, telegram_user_id, chat_id, timezone, reminders_enabled
          FROM users
        """
    ).fetchall()
    conn.close()

    for u in users:
        try:
            # Reuse reminders_enabled for now (simple v1 switch)
            if int(u["reminders_enabled"]) == 0:
                continue

            tz_name = (u["timezone"] or timezone).strip() or timezone
            tz = ZoneInfo(tz_name)
            when = dtime(hour=hour, minute=minute, tzinfo=tz)

            # Sunday = 6 (Mon=0)
            app.job_queue.run_daily(
                callback=_send_weekly_reminder_one,
                time=when,
                days=(6,),
                name=f"weekly_checkin:{int(u['id'])}",
                data={
                    "db_path": db_path,
                    "user_id": int(u["id"]),
                    "telegram_user_id": int(u["telegram_user_id"]),
                    "chat_id": int(u["chat_id"]),
                    "timezone": tz_name,
                },
            )
        except Exception:
            log.exception("Failed to schedule weekly reminder for user_id=%s", u.get("id"))

async def _send_weekly_reminder_one(context) -> None:
    data = context.job.data
    db_path = data["db_path"]
    user_id = int(data["user_id"])
    chat_id = int(data["chat_id"])
    tz_name = (data.get("timezone") or "Europe/Kiev").strip()

    week_start = _week_start_date_str(tz_name)

    conn = connect(db_path)
    row = conn.execute(
        "SELECT 1 FROM weekly_entries WHERE user_id = ? AND week_start_date = ?",
        (user_id, week_start),
    ).fetchone()
    conn.close()

    # Already done for this week → skip
    if row:
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text="📅 Weekly check-in time ✍️\n\nUse /weekly",
    )