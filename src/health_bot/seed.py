import sqlite3
from pathlib import Path


def normalize_title(title: str) -> str:
    """Normalize habit title for matching.

    We accept that `fields.txt` might contain accidental surrounding quotes.
    We also normalize DB titles to match previously-seeded rows.
    """
    return title.strip().strip('"').strip("'")


def ensure_household(conn: sqlite3.Connection, name: str = "Family") -> int:
    row = conn.execute("SELECT id FROM households WHERE name = ?", (name,)).fetchone()
    if row:
        return int(row["id"])

    cur = conn.execute("INSERT INTO households (name) VALUES (?)", (name,))
    conn.commit()
    return int(cur.lastrowid)


def infer_kind(title: str) -> str:
    """Infer habit kind from the title.

    v1 rule: everything is boolean except Mood (Настрій), which is a choice.
    """
    t = title.lower()

    if "настр" in t:
        return "choice"

    return "boolean"


def read_fields(fields_path: str) -> list[str]:
    p = Path(fields_path)
    lines = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        s = normalize_title(raw)
        if not s or s.startswith("#"):
            continue
        lines.append(s)
    return lines


def seed_habits_from_fields(
    conn: sqlite3.Connection,
    *,
    household_id: int,
    fields_path: str,
) -> int:
    titles = read_fields(fields_path)

    existing_rows = conn.execute(
        "SELECT id, title FROM habits WHERE household_id = ?",
        (household_id,),
    ).fetchall()

    # Map normalized title -> (id, stored_title)
    existing_by_title: dict[str, tuple[int, str]] = {
        normalize_title(r["title"]).lower(): (int(r["id"]), str(r["title"]))
        for r in existing_rows
    }

    inserted = 0
    updated = 0

    for idx, raw_title in enumerate(titles):
        title = normalize_title(raw_title)
        kind = infer_kind(title)
        key = title.lower()

        if key in existing_by_title:
            habit_id, stored_title = existing_by_title[key]

            # Update kind/order/enabled; also clean up previously stored titles with stray quotes
            conn.execute(
                """
                UPDATE habits
                   SET title = ?,
                       kind = ?,
                       enabled = 1,
                       sort_order = ?
                 WHERE id = ?
                """,
                (title, kind, idx, habit_id),
            )
            updated += 1
        else:
            conn.execute(
                """
                INSERT INTO habits (household_id, title, kind, target, enabled, sort_order)
                VALUES (?, ?, ?, NULL, 1, ?)
                """,
                (household_id, title, kind, idx),
            )
            inserted += 1

    conn.commit()
    return inserted + updated