import logging
from health_bot.config import load_settings
from health_bot.logging_setup import setup_logging
from health_bot.db import connect, init_db
from health_bot.seed import ensure_household, seed_habits_from_fields


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    log = logging.getLogger("health_bot.seed_habits")

    conn = connect(settings.db_path)

    # Safety: ensure schema exists
    init_db(conn)

    household_id = ensure_household(conn, "Family")

    inserted = seed_habits_from_fields(
        conn,
        household_id=household_id,
        fields_path="fields.txt",
    )
    conn.close()

    if inserted == 0:
        log.info("Habits already exist for household 'Family' — nothing to seed.")
    else:
        log.info("Seeded %s habits into household 'Family' (id=%s).", inserted, household_id)


if __name__ == "__main__":
    main()