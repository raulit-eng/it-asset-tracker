"""Checks that the sample data and reports agree with each other. Run with:  python -m pytest"""

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build_dashboard
import generate_sample_data
from run_reports import load_reports, run_report


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("data") / "assets.db"
    generate_sample_data.build(path, employee_count=400, seed=7)
    return path


def rows(db, name):
    conn = sqlite3.connect(db)
    columns, result = run_report(conn, load_reports()[name]["sql"])
    return [dict(zip(columns, r)) for r in result]


def test_every_report_runs(db):
    for name in load_reports():
        rows(db, name)


def test_refresh_due_only_includes_old_devices(db):
    for r in rows(db, "refresh_due"):
        assert r["age_years"] >= r["lifecycle_years"] - 0.01


def test_offboarding_gaps_are_former_employees(db):
    conn = sqlite3.connect(db)
    for r in rows(db, "offboarding_gaps"):
        status = conn.execute("SELECT status FROM employees WHERE full_name = ? AND end_date = ?",
                              (r["former_employee"], r["left_on"])).fetchone()[0]
        assert status == "Terminated"


def test_warranties_end_within_90_days(db):
    for r in rows(db, "warranty_expiring"):
        assert 0 <= r["days_left"] <= 90


def test_dashboard_numbers_add_up(db):
    data = build_dashboard.build(db)
    assert sum(i["count"] for i in data["compliance_summary"]) == data["kpis"]["compliance"]
    assert data["kpis"]["active"] == data["kpis"]["in_use"] + data["kpis"]["in_stock"] + data["kpis"]["in_repair"]
    site_total = sum(sum(s["values"].values()) for s in data["sites"])
    assert site_total == data["kpis"]["active"]


def test_sample_data_is_repeatable(tmp_path):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    generate_sample_data.build(a, 100, seed=1)
    generate_sample_data.build(b, 100, seed=1)
    q = "SELECT * FROM assets ORDER BY asset_tag"
    assert sqlite3.connect(a).execute(q).fetchall() == sqlite3.connect(b).execute(q).fetchall()
