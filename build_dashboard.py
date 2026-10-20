"""
Build the dashboard: runs the SQL reports and writes a single HTML page you can open
in any browser, or publish for free with GitHub Pages (it's saved to docs/index.html).

Usage:
    python build_dashboard.py
    python build_dashboard.py --db data/assets.db --out docs/index.html
"""

import argparse
import json
import sqlite3
from pathlib import Path

from run_reports import load_reports, run_report

ROOT = Path(__file__).parent
TYPES = ["Laptop", "Desktop", "iPhone", "iPad", "Monitor", "Printer"]  # fixed order = fixed colors
AGE_BANDS = ["Under 1 yr", "1-3 yrs", "3-5 yrs", "5+ yrs"]

# Friendly column headers for the action list
HEADERS = {
    "asset_tag": "Asset tag", "asset_type": "Type", "model": "Model", "assigned_to": "Assigned to", "site": "Site",
    "purchase_date": "Purchased", "age_years": "Age (yrs)", "warranty_end": "Warranty ends", "days_left": "Days left",
    "issue": "Issue", "former_employee": "Former employee", "left_on": "Left on",
    "days_since_leaving": "Days since leaving",
}


def rows_as_dicts(conn, sql):
    columns, rows = run_report(conn, sql)
    return [dict(zip(columns, r)) for r in rows]


def action_tab(conn, sql, key, label, description, keep):
    columns, rows = run_report(conn, sql)
    idx = [columns.index(c) for c in keep]
    return {"key": key, "label": label, "description": description,
            "columns": [HEADERS.get(c, c) for c in keep],
            "rows": [[r[i] for i in idx] for r in rows]}


def build(db_path: Path) -> dict:
    reports = {name: r["sql"] for name, r in load_reports().items()}
    conn = sqlite3.connect(db_path)
    one = lambda sql: conn.execute(sql).fetchone()[0]

    # Devices by site, pivoted to one row per site
    sites = {}
    for r in rows_as_dicts(conn, reports["assets_by_site"]):
        sites.setdefault(r["site"], {})[r["asset_type"]] = r["assets"]

    fleet = {}
    for r in rows_as_dicts(conn, reports["fleet_age"]):
        fleet.setdefault(r["asset_type"], {})[r["age_band"]] = r["devices"]

    refresh = rows_as_dicts(conn, reports["refresh_due"])
    compliance = rows_as_dicts(conn, reports["compliance_issues"])
    offboarding = rows_as_dicts(conn, reports["offboarding_gaps"])
    warranty = rows_as_dicts(conn, reports["warranty_expiring"])

    issue_count = lambda prefix: sum(1 for c in compliance if c["issue"].startswith(prefix))

    return {
        "company": one("SELECT value FROM settings WHERE key = 'company'"),
        "as_of": one("SELECT value FROM settings WHERE key = 'as_of_date'"),
        "types": TYPES,
        "age_bands": AGE_BANDS,
        "kpis": {
            "active": one("SELECT COUNT(*) FROM assets WHERE status IN ('In Use','In Stock','In Repair')"),
            "in_use": one("SELECT COUNT(*) FROM assets WHERE status = 'In Use'"),
            "in_stock": one("SELECT COUNT(*) FROM assets WHERE status = 'In Stock'"),
            "in_repair": one("SELECT COUNT(*) FROM assets WHERE status = 'In Repair'"),
            "overdue": len(refresh),
            "overdue_cost": sum(r["replacement_cost"] for r in refresh),
            "offboarding_devices": len(offboarding),
            "offboarding_people": len({r["former_employee"] + r["left_on"] for r in offboarding}),
            "compliance": len(compliance),
            "warranty": len(warranty),
        },
        "sites": [{"label": name, "values": vals} for name, vals in sites.items()],
        "fleet_age": [{"label": t, "values": fleet.get(t, {})} for t in TYPES if t in fleet],
        "forecast": [{"due": r["due"], "devices": r["devices"], "cost": r["estimated_cost"]}
                     for r in rows_as_dicts(conn, reports["refresh_forecast"])],
        "compliance_summary": [
            {"label": "Not enrolled in MDM", "count": issue_count("Not enrolled"), "status": "critical"},
            {"label": "Disk not encrypted", "count": issue_count("Disk not"), "status": "critical"},
            {"label": "No MDM check-in for 30+ days", "count": issue_count("No check-in"), "status": "serious"},
        ],
        "actions": [
            action_tab(conn, reports["offboarding_gaps"], "offboarding", "Offboarding gaps",
                       "Devices still assigned to people who have left. Recover these first.",
                       ["former_employee", "left_on", "days_since_leaving", "asset_tag", "asset_type", "model", "site"]),
            action_tab(conn, reports["compliance_issues"], "compliance", "Compliance",
                       "Managed devices missing MDM enrollment, disk encryption, or a recent check-in.",
                       ["asset_tag", "asset_type", "model", "assigned_to", "site", "issue"]),
            action_tab(conn, reports["refresh_due"], "refresh", "Overdue for refresh",
                       "In-use devices older than their lifecycle, oldest first.",
                       ["asset_tag", "asset_type", "model", "assigned_to", "site", "purchase_date", "age_years"]),
            action_tab(conn, reports["warranty_expiring"], "warranty", "Warranty ending",
                       "Warranties that end in the next 90 days. Fix known issues while they're still covered.",
                       ["asset_tag", "asset_type", "model", "assigned_to", "site", "warranty_end", "days_left"]),
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=str(ROOT / "data" / "assets.db"))
    parser.add_argument("--out", default=str(ROOT / "docs" / "index.html"))
    args = parser.parse_args()

    if not Path(args.db).exists():
        raise SystemExit(f"{args.db} not found - run generate_sample_data.py first.")

    data = build(Path(args.db))
    template = (ROOT / "templates" / "dashboard_template.html").read_text(encoding="utf-8")
    payload = json.dumps(data).replace("</", "<\\/")  # safe to embed in a <script> tag
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(template.replace("/*__DATA__*/null", payload), encoding="utf-8")
    print(f"Dashboard written to {out} - open it in your browser.")


if __name__ == "__main__":
    main()
