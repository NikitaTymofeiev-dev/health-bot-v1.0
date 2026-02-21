#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _load_daily(conn: sqlite3.Connection, days: int) -> pd.DataFrame:
    # Pull last N days worth of values (boolean + choice) for all users
    q = """
    WITH dates AS (
        SELECT date
          FROM daily_entries
         GROUP BY date
         ORDER BY date DESC
         LIMIT ?
    )
    SELECT
        de.date,
        u.first_name AS user_name,
        u.telegram_user_id,
        h.id AS habit_id,
        h.title AS habit_title,
        h.kind AS habit_kind,
        dv.value AS value
    FROM daily_entries de
    JOIN dates d ON d.date = de.date
    JOIN users u ON u.id = de.user_id
    LEFT JOIN daily_values dv ON dv.daily_entry_id = de.id
    LEFT JOIN habits h ON h.id = dv.habit_id
    ORDER BY de.date ASC, u.first_name ASC
    """
    return pd.read_sql_query(q, conn, params=(days,))


def _load_weekly(conn: sqlite3.Connection, weeks: int) -> pd.DataFrame:
    q = """
    SELECT
        we.week_start_date,
        u.first_name AS user_name,
        we.weight_kg,
        we.week_rating,
        we.note
    FROM weekly_entries we
    JOIN users u ON u.id = we.user_id
    ORDER BY we.week_start_date DESC
    LIMIT ?
    """
    df = pd.read_sql_query(q, conn, params=(weeks,))
    # show oldest->newest on charts
    return df.sort_values(["week_start_date", "user_name"])


def _ensure_outdir(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)


def _plot_tracked_success(df: pd.DataFrame, out_dir: Path) -> None:
    """
    tracked%: any non-empty value per habit (includes choice + boolean)
    success%: only boolean == "1"
    """
    if df.empty:
        return

    # remove rows with missing habit_kind (can happen if dv is NULL and join didn't match)
    df2 = df.copy()
    df2["value_str"] = df2["value"].fillna("").astype(str).str.strip()
    df2 = df2[df2["habit_kind"].notna()].copy()

    # tracked = value not empty
    df2["tracked"] = (df2["value_str"] != "").astype(int)

    # success = boolean value == "1"
    df2["success"] = ((df2["habit_kind"] == "boolean") & (df2["value_str"] == "1")).astype(int)

    # totals:
    # - tracked_total counts ALL habits (boolean+choice) that appear in daily_values table for that date/user
    # - success_total counts only boolean habits that appear in daily_values table for that date/user
    grouped = df2.groupby(["date", "user_name"], as_index=False).agg(
        tracked=("tracked", "sum"),
        tracked_total=("tracked", "count"),
        success=("success", "sum"),
        success_total=("habit_kind", lambda s: int((s == "boolean").sum())),
    )

    grouped["tracked_pct"] = (grouped["tracked"] / grouped["tracked_total"] * 100).round(1)
    grouped["success_pct"] = grouped.apply(
        lambda r: round((r["success"] / r["success_total"] * 100), 1) if r["success_total"] else 0.0,
        axis=1,
    )

    # Plot tracked%
    plt.figure()
    for user_name, sub in grouped.groupby("user_name"):
        plt.plot(sub["date"], sub["tracked_pct"], marker="o", label=user_name)
    plt.title("Tracked % (last N days)")
    plt.ylabel("Percent")
    plt.xticks(rotation=45, ha="right")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "tracked_pct.png")
    plt.close()

    # Plot success%
    plt.figure()
    for user_name, sub in grouped.groupby("user_name"):
        plt.plot(sub["date"], sub["success_pct"], marker="o", label=user_name)
    plt.title("Success % (booleans only, last N days)")
    plt.ylabel("Percent")
    plt.xticks(rotation=45, ha="right")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "success_pct.png")
    plt.close()


def _plot_weight(df_weekly: pd.DataFrame, out_dir: Path) -> None:
    if df_weekly.empty:
        return

    dfw = df_weekly.copy()
    dfw = dfw[dfw["weight_kg"].notna()].copy()
    if dfw.empty:
        return

    plt.figure()
    for user_name, sub in dfw.groupby("user_name"):
        plt.plot(sub["week_start_date"], sub["weight_kg"], marker="o", label=user_name)
    plt.title("Weight (weekly)")
    plt.ylabel("kg")
    plt.xticks(rotation=45, ha="right")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "weight_weekly.png")
    plt.close()


def _plot_week_rating(df_weekly: pd.DataFrame, out_dir: Path) -> None:
    if df_weekly.empty:
        return

    dfw = df_weekly.copy()
    dfw = dfw[dfw["week_rating"].notna()].copy()
    if dfw.empty:
        return

    plt.figure()
    for user_name, sub in dfw.groupby("user_name"):
        plt.plot(sub["week_start_date"], sub["week_rating"], marker="o", label=user_name)
    plt.title("Week rating (weekly)")
    plt.ylabel("1–10")
    plt.xticks(rotation=45, ha="right")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "week_rating.png")
    plt.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Generate simple health_bot charts from SQLite.")
    p.add_argument("--db", default="db/health_bot.sqlite3", help="Path to sqlite DB")
    p.add_argument("--out", default="dashboards", help="Output folder for PNGs")
    p.add_argument("--days", type=int, default=30, help="How many recent days to chart")
    p.add_argument("--weeks", type=int, default=16, help="How many weekly points to chart")
    args = p.parse_args()

    db_path = Path(args.db)
    out_dir = Path(args.out)

    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    _ensure_outdir(out_dir)

    conn = _connect(db_path)
    daily = _load_daily(conn, args.days)
    weekly = _load_weekly(conn, args.weeks)
    conn.close()

    _plot_tracked_success(daily, out_dir)
    _plot_weight(weekly, out_dir)
    _plot_week_rating(weekly, out_dir)

    print(f"✅ Charts saved to: {out_dir.resolve()}")
    print(" - tracked_pct.png")
    print(" - success_pct.png")
    print(" - weight_weekly.png (if weekly weights exist)")
    print(" - week_rating.png (if weekly ratings exist)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())