import logging
from health_bot.config import load_settings
from health_bot.logging_setup import setup_logging
from health_bot.bot import build_application
from health_bot.scheduler import schedule_daily_reminders, schedule_weekly_reminders


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    log = logging.getLogger("health_bot")
    log.info("Starting health_bot")

    app = build_application(settings)

    app.bot_data["db_path"] = settings.db_path
    app.bot_data["timezone"] = settings.timezone
    app.bot_data["default_reminder_hour"] = 21
    app.bot_data["default_reminder_minute"] = 0

    schedule_daily_reminders(
        app,
        db_path=settings.db_path,
        timezone=settings.timezone,
        default_hour=21,
        default_minute=0,
    )
    schedule_weekly_reminders(
        app,
        db_path=settings.db_path,
        timezone=settings.timezone,
        hour=12,
        minute=0,
    )

    app.run_polling()

if __name__ == "__main__":
    main()