import json
import sqlite3
from datetime import datetime
from pathlib import Path


DB_PATH = Path("db/health_bot.sqlite3")
OUT_DIR = Path("exports")


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    data = {
        "meta": {
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "db_path": str(DB_PATH),
        },
        "households": rows_to_dicts(conn.execute("SELECT * FROM households").fetchall()),
        "users": rows_to_dicts(conn.execute("SELECT * FROM users").fetchall()),
        "habits": rows_to_dicts(conn.execute("SELECT * FROM habits").fetchall()),
        "daily_entries": rows_to_dicts(conn.execute("SELECT * FROM daily_entries").fetchall()),
        "daily_values": rows_to_dicts(conn.execute("SELECT * FROM daily_values").fetchall()),
        "weekly_entries": rows_to_dicts(conn.execute("SELECT * FROM weekly_entries").fetchall()),
    }

    conn.close()

    out_file = OUT_DIR / f"health_bot_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ Exported to: {out_file}")


if __name__ == "__main__":
    main()