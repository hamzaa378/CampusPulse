-- Execute after simulator sends readings and worker processes them.
USE gdg_campus_monitor;
SHOW TABLES;
SHOW TRIGGERS;
SHOW PROCEDURE STATUS WHERE Db='gdg_campus_monitor';
SHOW FUNCTION STATUS WHERE Db='gdg_campus_monitor';
SELECT COUNT(*) AS total_readings FROM monitor_reading;
SELECT COUNT(*) AS queued_readings FROM monitor_reading WHERE processed_at IS NULL;
SELECT status,COUNT(*) AS count FROM monitor_alert GROUP BY status;
SELECT * FROM vw_rule_health;
SELECT * FROM vw_alert_overview ORDER BY created_at DESC LIMIT 10;
SELECT * FROM monitor_alert_audit ORDER BY changed_at DESC LIMIT 10;
SELECT fn_rule_matches(34.5000,'GT',30.0000) AS should_match;
SELECT fn_alert_priority('critical','open') AS should_be_three;
-- CALL sp_refresh_daily_summary(CURRENT_DATE());
-- SELECT * FROM vw_sensor_daily_summary;
-- CALL sp_sensor_alert_counts(1);
