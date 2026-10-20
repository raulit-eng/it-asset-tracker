"""
Run the SQL reports in sql/reports.sql against the asset database.

Usage:
    python run_reports.py                         # print every report
    python run_reports.py refresh_due             # print one report
    python run_reports.py --csv                   # also save each report to output/<name>.csv
    python run_reports.py --list                  # list the reports
"""

import argparse
import csv
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent
REPORTS_FILE = ROOT / "sql" / "reports.sql"


def load_reports(path: Path = REPORTS_FILE) -> dict[str, dict]:
    """Split reports.sql into {name: {"description": ..., "sql": ...}}."""
    reports = {}
    for block in re.split(r"\n(?=-- name:)", path.read_text(encoding="utf-8")):
        name = re.search(r"-- name:\s*(\w+)", block)
        if not name:
            continue
        lines = block.splitlines()
        comments = [l[2:].strip() for l in lines[1:] if l.startswith("--")]
        sql = "\n".join(l for l in lines if not l.startswith("--")).strip()
        reports[name.group(1)] = {"description": comments[0] if comments else "", "sql": sql}
    return reports


def run_report(conn: sqlite3.Connection, sql: str) -> tuple[list[str], list[tuple]]:
    cur = conn.execute(sql)
    return [c[0] for c in cur.description], cur.fetchall()


def print_table(columns: list[str], rows: list[tuple], limit: int = 15) -> None:
    shown = [tuple("" if v is None else str(v) for v in r) for r in rows[:limit]]
    widths = [max([len(c)] + [len(r[i]) for r in shown]) for i, c in enumerate(columns)]
    print("  ".join(c.ljust(w) for c, w in zip(columns, widths)))
    print("  ".join("-" * w for w in widths))
    for r in shown:
        print("  ".join(v.ljust(w) for v, w in zip(r, widths)))
    if len(rows) > limit:
        print(f"... and {len(rows) - limit} more rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("report", nargs="?", help="report name (default: all)")
    parser.add_argument("--db", default=str(ROOT / "data" / "assets.db"))
    parser.add_argument("--csv", action="store_true", help="save results to output/")
    parser.add_argument("--list", action="store_true", help="list the available reports")
    args = parser.parse_args()

    reports = load_reports()
    if args.list:
        for name, r in reports.items():
            print(f"{name:20} {r['description']}")
        return
    if args.report and args.report not in reports:
        raise SystemExit(f"Unknown report '{args.report}'. Try --list.")
    if not Path(args.db).exists():
        raise SystemExit(f"{args.db} not found - run generate_sample_data.py first.")

    conn = sqlite3.connect(args.db)
    for name, report in reports.items():
        if args.report and name != args.report:
            continue
        columns, rows = run_report(conn, report["sql"])
        print(f"\n=== {name}: {report['description']} ({len(rows)} rows) ===")
        print_table(columns, rows)
        if args.csv:
            out = ROOT / "output"
            out.mkdir(exist_ok=True)
            with open(out / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)


if __name__ == "__main__":
    main()
