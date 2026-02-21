from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from health_bot.config import Settings
from health_bot.handlers import (
    start_handler,
    help_handler,
    invite_handler,
    join_handler,
    checkin_handler,
    checkin_callback_handler,
    today_handler,
    summary_handler,
    set_reminder_handler, reminders_on_handler, reminders_off_handler,
    weekly_handler, weekly_cancel_handler, weekly_input_handler,
    family_summary_handler, streaks_handler, weekly_show_handler,
    menu_router_handler,
    menu_handler
)


def build_application(settings: Settings) -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("invite", invite_handler))
    app.add_handler(CommandHandler("join", join_handler))
    app.add_handler(CommandHandler("menu", menu_handler))

    # NEW
    app.add_handler(CommandHandler("checkin", checkin_handler))
    app.add_handler(CallbackQueryHandler(checkin_callback_handler, pattern=r"^(hc|hcp):"))
    app.add_handler(CommandHandler("today", today_handler))
    app.add_handler(CommandHandler("summary", summary_handler))
    app.add_handler(CommandHandler("set_reminder", set_reminder_handler))
    app.add_handler(CommandHandler("reminders_on", reminders_on_handler))
    app.add_handler(CommandHandler("reminders_off", reminders_off_handler))
    app.add_handler(CommandHandler("weekly", weekly_handler))
    app.add_handler(CommandHandler("weekly_cancel", weekly_cancel_handler))
    app.add_handler(CommandHandler("weekly_show", weekly_show_handler))
    app.add_handler(CommandHandler("family_summary", family_summary_handler))
    app.add_handler(CommandHandler("streaks", streaks_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router_handler))

    return app