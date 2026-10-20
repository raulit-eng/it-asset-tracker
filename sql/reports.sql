-- IT Asset Tracker reports
-- Every report starts with "-- name:" and a short description. Both run_reports.py and
-- the dashboard read this file, so a change here shows up everywhere.
-- "Today" comes from the settings table, so the sample results never change.

-- name: assets_by_site
-- Active assets at each site, by type (anything not retired or lost)
SELECT s.name AS site, a.asset_type, COUNT(*) AS assets
FROM assets a
JOIN sites s ON s.site_id = a.site_id
WHERE a.status IN ('In Use', 'In Stock', 'In Repair')
GROUP BY s.name, a.asset_type
ORDER BY s.site_id, a.asset_type;

-- name: refresh_due
-- In-use devices older than their lifecycle in the refresh policy
SELECT a.asset_tag, a.asset_type, a.manufacturer || ' ' || a.model AS model,
       COALESCE(e.full_name, 'Shared') AS assigned_to, s.name AS site,
       a.purchase_date,
       ROUND((julianday(t.today) - julianday(a.purchase_date)) / 365.25, 1) AS age_years,
       p.lifecycle_years, p.replacement_cost
FROM assets a
JOIN refresh_policy p ON p.asset_type = a.asset_type
JOIN sites s ON s.site_id = a.site_id
LEFT JOIN employees e ON e.employee_id = a.assigned_to
CROSS JOIN (SELECT value AS today FROM settings WHERE key = 'as_of_date') t
WHERE a.status = 'In Use'
  AND date(a.purchase_date, '+' || p.lifecycle_years || ' years') <= t.today
ORDER BY age_years DESC;

-- name: refresh_forecast
-- What's coming due for replacement each year, and what it will cost
SELECT CASE WHEN date(a.purchase_date, '+' || p.lifecycle_years || ' years') <= t.today
            THEN 'Overdue now'
            ELSE strftime('%Y', date(a.purchase_date, '+' || p.lifecycle_years || ' years')) END AS due,
       COUNT(*) AS devices,
       SUM(p.replacement_cost) AS estimated_cost
FROM assets a
JOIN refresh_policy p ON p.asset_type = a.asset_type
CROSS JOIN (SELECT value AS today FROM settings WHERE key = 'as_of_date') t
WHERE a.status = 'In Use'
GROUP BY due
ORDER BY due = 'Overdue now' DESC, due
LIMIT 5;

-- name: warranty_expiring
-- In-use devices whose warranty ends in the next 90 days
SELECT a.asset_tag, a.asset_type, a.manufacturer || ' ' || a.model AS model,
       COALESCE(e.full_name, 'Shared') AS assigned_to, s.name AS site, a.warranty_end,
       CAST(julianday(a.warranty_end) - julianday(t.today) AS INTEGER) AS days_left
FROM assets a
JOIN sites s ON s.site_id = a.site_id
LEFT JOIN employees e ON e.employee_id = a.assigned_to
CROSS JOIN (SELECT value AS today FROM settings WHERE key = 'as_of_date') t
WHERE a.status = 'In Use'
  AND a.warranty_end BETWEEN t.today AND date(t.today, '+90 days')
ORDER BY a.warranty_end;

-- name: compliance_issues
-- Managed devices in use that are missing MDM, missing encryption, or haven't checked in for 30+ days
SELECT a.asset_tag, a.asset_type, a.manufacturer || ' ' || a.model AS model,
       COALESCE(e.full_name, 'Shared') AS assigned_to, s.name AS site,
       CASE WHEN a.mdm IS NULL THEN 'Not enrolled in MDM'
            WHEN a.encrypted = 0 THEN 'Disk not encrypted'
            ELSE 'No check-in for ' || CAST(julianday(t.today) - julianday(a.last_checkin) AS INTEGER) || ' days'
       END AS issue
FROM assets a
JOIN refresh_policy p ON p.asset_type = a.asset_type
JOIN sites s ON s.site_id = a.site_id
LEFT JOIN employees e ON e.employee_id = a.assigned_to
CROSS JOIN (SELECT value AS today FROM settings WHERE key = 'as_of_date') t
WHERE a.status = 'In Use' AND p.needs_mdm = 1
  AND (a.mdm IS NULL
       OR (p.needs_encryption = 1 AND a.encrypted = 0)
       OR julianday(t.today) - julianday(a.last_checkin) > 30)
ORDER BY issue, s.name;

-- name: offboarding_gaps
-- Devices still assigned to people who have left the company
SELECT e.full_name AS former_employee, e.end_date AS left_on,
       CAST(julianday(t.today) - julianday(e.end_date) AS INTEGER) AS days_since_leaving,
       a.asset_tag, a.asset_type, a.manufacturer || ' ' || a.model AS model, s.name AS site
FROM assets a
JOIN employees e ON e.employee_id = a.assigned_to
JOIN sites s ON s.site_id = a.site_id
CROSS JOIN (SELECT value AS today FROM settings WHERE key = 'as_of_date') t
WHERE e.status = 'Terminated' AND a.status = 'In Use'
ORDER BY days_since_leaving DESC;

-- name: fleet_age
-- How old the in-use fleet is, by device type
SELECT a.asset_type,
       CASE WHEN age < 1 THEN 'Under 1 yr'
            WHEN age < 3 THEN '1-3 yrs'
            WHEN age < 5 THEN '3-5 yrs'
            ELSE '5+ yrs' END AS age_band,
       COUNT(*) AS devices
FROM (SELECT asset_type, (julianday(t.today) - julianday(purchase_date)) / 365.25 AS age
      FROM assets CROSS JOIN (SELECT value AS today FROM settings WHERE key = 'as_of_date') t
      WHERE status = 'In Use') a
GROUP BY a.asset_type, age_band
ORDER BY a.asset_type,
         CASE age_band WHEN 'Under 1 yr' THEN 1 WHEN '1-3 yrs' THEN 2 WHEN '3-5 yrs' THEN 3 ELSE 4 END;

-- name: spend_by_year
-- What was spent on hardware each year
SELECT strftime('%Y', purchase_date) AS year, COUNT(*) AS devices, ROUND(SUM(purchase_cost), 2) AS spent
FROM assets
GROUP BY year
ORDER BY year;

-- name: asset_history
-- Full history for one device (change the tag to look up another)
SELECT ev.event_date, ev.event_type, COALESCE(e.full_name, '') AS employee, COALESCE(ev.notes, '') AS notes
FROM asset_events ev
LEFT JOIN employees e ON e.employee_id = ev.employee_id
WHERE ev.asset_tag = 'AT-000001'
ORDER BY ev.event_date;
