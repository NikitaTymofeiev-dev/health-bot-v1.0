import logging
from health_bot.config import load_settings
from health_bot.logging_setup import setup_logging
from health_bot.db import connect, init_db


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    log = logging.getLogger("health_bot.init_db")

    conn = connect(settings.db_path)
    init_db(conn)
    conn.close()

    log.info("DB initialized at %s", settings.db_path)


if __name__ == "__main__":
    main()