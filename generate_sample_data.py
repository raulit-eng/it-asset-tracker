"""
Build the sample database: a fake company with about 400 employees across 9 sites,
and every laptop, desktop, phone, tablet, monitor and printer they use.

All names and devices are randomly generated. Nothing here is real company data.

Usage:
    python generate_sample_data.py                    # writes data/assets.db
    python generate_sample_data.py --employees 1200   # bigger company
"""

import argparse
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

AS_OF = date(2026, 10, 19)  # the "today" for the sample data, so results are repeatable

SITES = [
    ("Los Angeles HQ", "Los Angeles"), ("Long Beach", "Long Beach"), ("Santa Clarita", "Santa Clarita"),
    ("Palmdale", "Palmdale"), ("Burbank", "Burbank"), ("Pasadena", "Pasadena"),
    ("Torrance", "Torrance"), ("Ontario", "Ontario"), ("Irvine", "Irvine"),
]
SITE_WEIGHTS = [30, 12, 9, 7, 10, 8, 9, 8, 7]  # HQ is the biggest site

DEPARTMENTS = ["Operations", "Finance", "Sales", "HR", "IT", "Customer Service", "Marketing", "Warehouse", "Executive"]
DEPT_WEIGHTS = [22, 8, 14, 5, 4, 16, 6, 22, 3]

FIRST = ["Maria", "James", "Ana", "Michael", "Sofia", "David", "Linh", "Daniel", "Aisha", "Jose", "Emily", "Kevin",
         "Priya", "Carlos", "Grace", "Andre", "Nora", "Luis", "Hannah", "Omar", "Jasmine", "Ethan", "Rosa", "Tyler",
         "Mei", "Marcus", "Elena", "Brian", "Fatima", "Diego", "Chloe", "Samuel", "Yuki", "Jordan", "Valeria", "Isaac"]
LAST = ["Garcia", "Nguyen", "Smith", "Martinez", "Kim", "Johnson", "Lopez", "Patel", "Brown", "Hernandez", "Chen",
        "Williams", "Rodriguez", "Davis", "Okafor", "Flores", "Wilson", "Ramirez", "Tran", "Anderson", "Cruz",
        "Thomas", "Reyes", "Jackson", "Morales", "Lee", "Torres", "Walker", "Gutierrez", "Hall", "Rivera", "Young"]

# asset_type: lifecycle years, replacement cost, needs MDM, needs encryption
POLICY = {
    "Laptop":  (4, 1450, 1, 1),
    "Desktop": (5, 1100, 1, 1),
    "iPhone":  (3, 900, 1, 1),
    "iPad":    (4, 650, 1, 1),
    "Monitor": (6, 260, 0, 0),
    "Printer": (5, 850, 0, 0),
}

# asset_type -> (manufacturer, model, cost, warranty years, MDM it uses)
MODELS = {
    "Laptop": [("Dell", "Latitude 5450", 1350, 3, "Intune"), ("Lenovo", "ThinkPad T14", 1400, 3, "Intune"),
               ("Apple", "MacBook Air 13", 1200, 1, "Jamf"), ("Apple", "MacBook Pro 14", 2100, 3, "Jamf")],
    "Desktop": [("Dell", "OptiPlex 7020", 1050, 3, "Intune"), ("HP", "EliteDesk 800", 1100, 3, "Intune")],
    "iPhone": [("Apple", "iPhone 15", 800, 1, "Jamf"), ("Apple", "iPhone 16", 850, 1, "Jamf")],
    "iPad": [("Apple", "iPad 10th Gen", 450, 1, "Jamf"), ("Apple", "iPad Air", 650, 1, "Jamf")],
    "Monitor": [("Dell", "P2723DE 27in", 290, 3, None), ("LG", "27UP850 27in", 330, 1, None)],
    "Printer": [("HP", "LaserJet M611", 900, 1, None), ("Brother", "MFC-L8900", 650, 1, None)],
}

FROM_DATE = date(2019, 1, 1)


def rand_date(start: date, end: date) -> date:
    return start + timedelta(days=random.randint(0, max(0, (end - start).days)))


def add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # Feb 29
        return d.replace(year=d.year + years, day=28)


class Builder:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.next_tag = 1
        self.events = []

    def add_asset(self, asset_type, site_id, status, employee=None, purchase=None, problem=None):
        maker, model, cost, warranty_years, mdm = random.choice(MODELS[asset_type])
        purchase = purchase or rand_date(FROM_DATE, AS_OF - timedelta(days=30))
        tag = f"AT-{self.next_tag:06d}"
        self.next_tag += 1
        serial = f"{maker[:2].upper()}{random.randint(10**8, 10**9 - 1)}"
        needs_mdm, needs_enc = POLICY[asset_type][2:]

        encrypted = 1 if needs_enc else None
        last_checkin = None
        if needs_mdm and status in ("In Use", "In Stock"):
            last_checkin = AS_OF - timedelta(days=random.randint(0, 6) if status == "In Use" else random.randint(5, 25))
        if not needs_mdm:
            mdm = None

        # Plant the kinds of problems a real audit turns up
        if problem == "no_mdm":
            mdm, last_checkin = None, None
        elif problem == "unencrypted":
            encrypted = 0
        elif problem == "stale":
            last_checkin = AS_OF - timedelta(days=random.randint(35, 160))

        self.conn.execute(
            "INSERT INTO assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (tag, asset_type, maker, model, serial, purchase.isoformat(),
             round(cost * random.uniform(0.92, 1.08), 2), add_years(purchase, warranty_years).isoformat(),
             status, employee["id"] if employee else None, site_id, mdm, encrypted,
             last_checkin.isoformat() if last_checkin else None))

        self.events.append((tag, purchase, "Purchased", None, f"{maker} {model}"))
        if employee:
            assigned = max(purchase + timedelta(days=random.randint(1, 14)), employee["start"])
            self.events.append((tag, min(assigned, AS_OF), "Assigned", employee["id"], None))
        if status == "In Repair":
            self.events.append((tag, AS_OF - timedelta(days=random.randint(2, 20)), "Sent for Repair", None, "Hardware fault"))
        if status == "Retired":
            self.events.append((tag, rand_date(add_years(purchase, POLICY[asset_type][0]), AS_OF), "Retired", None, "End of life"))
        if status == "Lost":
            self.events.append((tag, AS_OF - timedelta(days=random.randint(10, 200)), "Reported Lost", None, None))
        return tag

    def save_events(self):
        self.events.sort(key=lambda e: e[1])
        self.conn.executemany(
            "INSERT INTO asset_events (asset_tag, event_date, event_type, employee_id, notes) VALUES (?,?,?,?,?)",
            [(t, d.isoformat(), kind, emp, note) for t, d, kind, emp, note in self.events])


def make_employees(conn, count):
    employees, used_emails = [], set()
    for i in range(1, count + 1):
        first, last = random.choice(FIRST), random.choice(LAST)
        email = f"{first[0].lower()}{last.lower()}"
        n = 2
        while email in used_emails:
            email = f"{first[0].lower()}{last.lower()}{n}"
            n += 1
        used_emails.add(email)
        site = random.choices(range(1, len(SITES) + 1), SITE_WEIGHTS)[0]
        start = rand_date(date(2016, 1, 1), AS_OF - timedelta(days=20))
        emp = {"id": i, "site": site, "start": start,
               "dept": random.choices(DEPARTMENTS, DEPT_WEIGHTS)[0], "status": "Active", "end": None}
        employees.append(emp)
        conn.execute("INSERT INTO employees VALUES (?,?,?,?,?,?,?,?)",
                     (i, f"{first} {last}", f"{email}@summitlogistics.example", emp["dept"], site,
                      "Active", start.isoformat(), None))
    return employees


def build(db_path: Path, employee_count: int, seed: int) -> None:
    random.seed(seed)
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript((Path(__file__).parent / "sql" / "schema.sql").read_text())

    conn.executemany("INSERT INTO sites VALUES (?,?,?)", [(i, n, c) for i, (n, c) in enumerate(SITES, 1)])
    conn.executemany("INSERT INTO refresh_policy VALUES (?,?,?,?,?)", [(t, *v) for t, v in POLICY.items()])
    conn.execute("INSERT INTO settings VALUES ('as_of_date', ?)", (AS_OF.isoformat(),))
    conn.execute("INSERT INTO settings VALUES ('company', 'Summit Logistics (sample data)')")

    employees = make_employees(conn, employee_count)
    b = Builder(conn)

    def problem_roll(asset_type):
        if not POLICY[asset_type][2]:
            return None
        r = random.random()
        computer = asset_type in ("Laptop", "Desktop")  # phones and tablets encrypt automatically
        if r < 0.03:
            return "no_mdm"
        if r < 0.05 and computer:
            return "unencrypted"
        return "stale" if r < 0.10 else None

    for emp in employees:
        office = emp["dept"] not in ("Warehouse",)
        main = "Desktop" if emp["dept"] in ("Customer Service", "Warehouse") and random.random() < 0.6 else "Laptop"
        start = max(emp["start"], FROM_DATE)
        b.add_asset(main, emp["site"], "In Use", emp, rand_date(start, AS_OF - timedelta(days=15)), problem_roll(main))
        if emp["dept"] in ("Sales", "Executive", "Operations", "IT") or random.random() < 0.35:
            b.add_asset("iPhone", emp["site"], "In Use", emp, rand_date(max(start, date(2021, 1, 1)), AS_OF - timedelta(days=15)),
                        problem_roll("iPhone"))
        if emp["dept"] in ("Warehouse", "Executive") and random.random() < 0.5:
            b.add_asset("iPad", emp["site"], "In Use", emp, rand_date(start, AS_OF - timedelta(days=15)), problem_roll("iPad"))
        if office:
            for _ in range(random.choice([1, 1, 2])):
                b.add_asset("Monitor", emp["site"], "In Use", emp, rand_date(start, AS_OF - timedelta(days=15)))

    # Shared printers, spares on the shelf, repairs, retirements and losses
    for site_id in range(1, len(SITES) + 1):
        for _ in range(random.randint(2, 5)):
            b.add_asset("Printer", site_id, "In Use")
        for kind in ("Laptop", "Laptop", "iPhone", "Monitor"):
            b.add_asset(kind, site_id, "In Stock", purchase=rand_date(date(2024, 6, 1), AS_OF - timedelta(days=30)))
    for _ in range(int(employee_count * 0.02)):
        b.add_asset(random.choice(["Laptop", "iPhone", "Laptop"]), random.randint(1, len(SITES)), "In Repair")
    for _ in range(int(employee_count * 0.15)):
        b.add_asset(random.choice(["Laptop", "Desktop", "iPhone", "Monitor"]), random.randint(1, len(SITES)), "Retired",
                    purchase=rand_date(date(2016, 1, 1), date(2020, 6, 1)))
    for _ in range(int(employee_count * 0.01)):
        b.add_asset(random.choice(["Laptop", "iPhone"]), random.randint(1, len(SITES)), "Lost")

    # Offboarding gaps: people who left but still have company devices
    leavers = random.sample(employees, k=max(3, employee_count // 45))
    for emp in leavers:
        end = rand_date(max(emp["start"] + timedelta(days=60), AS_OF - timedelta(days=150)), AS_OF - timedelta(days=5))
        end = min(end, AS_OF - timedelta(days=5))
        conn.execute("UPDATE employees SET status='Terminated', end_date=? WHERE employee_id=?", (end.isoformat(), emp["id"]))

    b.save_events()
    conn.commit()
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--employees", type=int, default=400)
    parser.add_argument("--db", default="data/assets.db")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    build(Path(args.db), args.employees, args.seed)

    conn = sqlite3.connect(args.db)
    assets = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    print(f"Built {args.db}: {args.employees} employees, {len(SITES)} sites, {assets:,} assets")


if __name__ == "__main__":
    main()
