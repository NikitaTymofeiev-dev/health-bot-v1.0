from dataclasses import dataclass
from dotenv import load_dotenv
import os


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    timezone: str
    db_path: str
    log_level: str


def load_settings() -> Settings:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    return Settings(
        telegram_bot_token=token,
        timezone=os.getenv("TIMEZONE", "Europe/Kiev").strip(),
        db_path=os.getenv("DB_PATH", "db/health_bot.sqlite3").strip(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip(),
    )