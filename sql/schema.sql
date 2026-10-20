-- IT Asset Tracker database schema (SQLite)
-- One row per site, employee and asset, plus a history of everything that happens to each asset.

PRAGMA foreign_keys = ON;

CREATE TABLE sites (
    site_id     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    city        TEXT NOT NULL
);

CREATE TABLE employees (
    employee_id INTEGER PRIMARY KEY,
    full_name   TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    department  TEXT NOT NULL,
    site_id     INTEGER NOT NULL REFERENCES sites(site_id),
    status      TEXT NOT NULL CHECK (status IN ('Active', 'Terminated')),
    start_date  TEXT NOT NULL,
    end_date    TEXT              -- set when someone leaves
);

-- How long each kind of device should last, and what a replacement costs.
-- Change these numbers and every refresh report updates.
CREATE TABLE refresh_policy (
    asset_type        TEXT PRIMARY KEY,
    lifecycle_years   INTEGER NOT NULL,
    replacement_cost  REAL NOT NULL,
    needs_mdm         INTEGER NOT NULL,   -- 1 if it should be enrolled in Jamf or Intune
    needs_encryption  INTEGER NOT NULL    -- 1 if disk encryption is required
);

CREATE TABLE assets (
    asset_tag       TEXT PRIMARY KEY,     -- e.g. AT-001234
    asset_type      TEXT NOT NULL REFERENCES refresh_policy(asset_type),
    manufacturer    TEXT NOT NULL,
    model           TEXT NOT NULL,
    serial_number   TEXT NOT NULL UNIQUE,
    purchase_date   TEXT NOT NULL,
    purchase_cost   REAL NOT NULL,
    warranty_end    TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('In Use', 'In Stock', 'In Repair', 'Retired', 'Lost')),
    assigned_to     INTEGER REFERENCES employees(employee_id),
    site_id         INTEGER NOT NULL REFERENCES sites(site_id),
    mdm             TEXT CHECK (mdm IN ('Jamf', 'Intune')),   -- NULL = not enrolled
    encrypted       INTEGER,                                  -- 1/0, NULL where it doesn't apply
    last_checkin    TEXT                                      -- last time the device reported to MDM
);

CREATE TABLE asset_events (
    event_id     INTEGER PRIMARY KEY,
    asset_tag    TEXT NOT NULL REFERENCES assets(asset_tag),
    event_date   TEXT NOT NULL,
    event_type   TEXT NOT NULL CHECK (event_type IN ('Purchased', 'Assigned', 'Returned', 'Sent for Repair', 'Retired', 'Reported Lost')),
    employee_id  INTEGER REFERENCES employees(employee_id),
    notes        TEXT
);

-- The "today" the reports are measured against, so sample results stay the same every run.
CREATE TABLE settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

CREATE INDEX idx_assets_assigned ON assets(assigned_to);
CREATE INDEX idx_assets_site ON assets(site_id);
CREATE INDEX idx_events_asset ON asset_events(asset_tag);
