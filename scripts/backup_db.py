import sqlite3
from datetime import datetime
from pathlib import Path
import shutil


DB_PATH = Path("db/health_bot.sqlite3")
BACKUP_DIR = Path("backups")
KEEP_LAST_N = 30  # keep last 30 backups


def main() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"health_bot_{ts}.sqlite3"

    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(backup_path)

    # Online backup (consistent)
    src.backup(dst)

    dst.close()
    src.close()

    # Optional: also copy -wal/-shm if they exist (not required for the backup file itself)
    for suffix in ("-wal", "-shm"):
        p = Path(str(DB_PATH) + suffix)
        if p.exists():
            shutil.copy2(p, BACKUP_DIR / f"health_bot_{ts}.sqlite3{suffix}")

    # Retention (simple: keep latest N .sqlite3 backups)
    backups = sorted(BACKUP_DIR.glob("health_bot_*.sqlite3"))
    if len(backups) > KEEP_LAST_N:
        for old in backups[: len(backups) - KEEP_LAST_N]:
            old.unlink(missing_ok=True)

    print(f"✅ Backup created: {backup_path}")


if __name__ == "__main__":
    main()