-- MySQL 8.x: safe inspection only. No DDL, DML, user changes or lock changes.
USE gdg_campus_monitor;
SELECT 'readings' AS name, COUNT(*) AS total FROM monitor_reading
UNION ALL SELECT 'pending_readings', COUNT(*) FROM monitor_reading WHERE processed_at IS NULL
UNION ALL SELECT 'alerts', COUNT(*) FROM monitor_alert
UNION ALL SELECT 'audit_rows', COUNT(*) FROM monitor_alert_audit;
SELECT status, COUNT(*) AS count FROM monitor_alert GROUP BY status;
SELECT r.name AS rule_name, r.kind, COUNT(a.id) AS alerts
FROM monitor_rule r LEFT JOIN monitor_alert a ON a.rule_id = r.id
GROUP BY r.id, r.name, r.kind ORDER BY r.id;
SELECT INDEX_NAME, COLUMN_NAME, SEQ_IN_INDEX
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = 'gdg_campus_monitor' AND TABLE_NAME = 'monitor_reading'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
SELECT COUNT(*) AS pending_over_five_minutes
FROM monitor_reading
WHERE processed_at IS NULL AND received_at < UTC_TIMESTAMP() - INTERVAL 5 MINUTE;
