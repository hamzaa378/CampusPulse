-- Run AFTER python manage.py migrate, using MySQL CLI (DELIMITER is a CLI directive).
USE gdg_campus_monitor;
DROP TRIGGER IF EXISTS trg_alert_open_audit;
DROP TRIGGER IF EXISTS trg_alert_state_audit;
DROP TRIGGER IF EXISTS trg_rule_validate_insert;
DROP TRIGGER IF EXISTS trg_rule_validate_update;
DROP PROCEDURE IF EXISTS sp_acknowledge_alert;
DROP PROCEDURE IF EXISTS sp_resolve_alert;
DROP PROCEDURE IF EXISTS sp_refresh_daily_summary;
DROP PROCEDURE IF EXISTS sp_sensor_alert_counts;
DROP FUNCTION IF EXISTS fn_rule_matches;
DROP FUNCTION IF EXISTS fn_alert_priority;

DELIMITER $$
CREATE FUNCTION fn_rule_matches(
    p_value DECIMAL(14,4), p_operator VARCHAR(4), p_threshold DECIMAL(14,4)
) RETURNS TINYINT DETERMINISTIC NO SQL
BEGIN
    RETURN CASE p_operator
        WHEN 'GT' THEN p_value > p_threshold
        WHEN 'GTE' THEN p_value >= p_threshold
        WHEN 'LT' THEN p_value < p_threshold
        WHEN 'LTE' THEN p_value <= p_threshold
        WHEN 'EQ' THEN p_value = p_threshold
        ELSE 0
    END;
END$$

CREATE FUNCTION fn_alert_priority(p_severity VARCHAR(12), p_status VARCHAR(16))
RETURNS INT DETERMINISTIC NO SQL
BEGIN
    IF p_status = 'resolved' THEN RETURN 0; END IF;
    RETURN CASE p_severity WHEN 'critical' THEN 3 WHEN 'warning' THEN 2 ELSE 1 END;
END$$

CREATE TRIGGER trg_rule_validate_insert
BEFORE INSERT ON monitor_rule FOR EACH ROW
BEGIN
    IF NEW.kind NOT IN ('instant','window') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid rule kind';
    END IF;
    IF NEW.kind = 'window' AND (NEW.window_seconds < 30 OR NEW.window_seconds > 86400 OR NEW.min_samples < 1) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid window rule settings';
    END IF;
END$$

CREATE TRIGGER trg_rule_validate_update
BEFORE UPDATE ON monitor_rule FOR EACH ROW
BEGIN
    IF NEW.kind NOT IN ('instant','window') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid rule kind';
    END IF;
    IF NEW.kind = 'window' AND (NEW.window_seconds < 30 OR NEW.window_seconds > 86400 OR NEW.min_samples < 1) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid window rule settings';
    END IF;
END$$

CREATE TRIGGER trg_alert_open_audit
AFTER INSERT ON monitor_alert FOR EACH ROW
BEGIN
    INSERT INTO monitor_alert_audit(alert_id, old_status, new_status, actor_id, changed_at)
    VALUES(NEW.id, NULL, NEW.status, NULL, UTC_TIMESTAMP(6));
END$$

CREATE TRIGGER trg_alert_state_audit
AFTER UPDATE ON monitor_alert FOR EACH ROW
BEGIN
    IF NOT (OLD.status <=> NEW.status) THEN
        INSERT INTO monitor_alert_audit(alert_id, old_status, new_status, actor_id, changed_at)
        VALUES(NEW.id, OLD.status, NEW.status,
               CASE WHEN NEW.status = 'acknowledged' THEN NEW.acknowledged_by_id
                    WHEN NEW.status = 'resolved' THEN NEW.resolved_by_id ELSE NULL END,
               UTC_TIMESTAMP(6));
    END IF;
END$$

CREATE PROCEDURE sp_acknowledge_alert(IN p_alert_id BIGINT, IN p_actor_id INT)
BEGIN
    DECLARE v_status VARCHAR(16) DEFAULT NULL;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
    START TRANSACTION;
    SELECT status INTO v_status FROM monitor_alert WHERE id=p_alert_id FOR UPDATE;
    IF v_status IS NULL OR v_status <> 'open' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Alert must exist and be open';
    END IF;
    UPDATE monitor_alert SET status='acknowledged', acknowledged_at=UTC_TIMESTAMP(6),
                             acknowledged_by_id=p_actor_id WHERE id=p_alert_id;
    COMMIT;
END$$

CREATE PROCEDURE sp_resolve_alert(IN p_alert_id BIGINT, IN p_actor_id INT)
BEGIN
    DECLARE v_status VARCHAR(16) DEFAULT NULL;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
    START TRANSACTION;
    SELECT status INTO v_status FROM monitor_alert WHERE id=p_alert_id FOR UPDATE;
    IF v_status IS NULL OR v_status='resolved' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Alert missing or already resolved';
    END IF;
    UPDATE monitor_alert SET status='resolved', resolved_at=UTC_TIMESTAMP(6),
                             resolved_by_id=p_actor_id WHERE id=p_alert_id;
    COMMIT;
END$$

CREATE PROCEDURE sp_sensor_alert_counts(IN p_sensor_id BIGINT)
BEGIN
    SELECT s.sensor_id, a.status, COUNT(*) AS alert_count,
           MAX(a.created_at) AS latest_alert
    FROM monitor_alert a JOIN monitor_sensor s ON s.id=a.sensor_id
    WHERE s.id=p_sensor_id
    GROUP BY s.sensor_id, a.status ORDER BY a.status;
END$$

-- CURSOR requirement: iterate sensor records and calculate daily per-metric aggregates.
-- Called explicitly / scheduled outside ingestion path to avoid slowing the API.
CREATE PROCEDURE sp_refresh_daily_summary(IN p_day DATE)
BEGIN
    DECLARE v_sensor_id BIGINT;
    DECLARE v_done INT DEFAULT 0;
    DECLARE sensor_cursor CURSOR FOR SELECT id FROM monitor_sensor WHERE is_active=1 ORDER BY id;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_done=1;
    OPEN sensor_cursor;
    sensor_loop: LOOP
        FETCH sensor_cursor INTO v_sensor_id;
        IF v_done = 1 THEN LEAVE sensor_loop; END IF;
        INSERT INTO monitor_daily_summary
          (sensor_id,metric_type,day,reading_count,avg_value,min_value,max_value,refreshed_at)
        SELECT v_sensor_id,r.metric_type,p_day,COUNT(*),AVG(r.value),MIN(r.value),MAX(r.value),UTC_TIMESTAMP(6)
        FROM monitor_reading r
        WHERE r.sensor_id=v_sensor_id AND r.recorded_at>=p_day
          AND r.recorded_at < DATE_ADD(p_day, INTERVAL 1 DAY)
        GROUP BY r.metric_type
        ON DUPLICATE KEY UPDATE
          reading_count=VALUES(reading_count),avg_value=VALUES(avg_value),
          min_value=VALUES(min_value),max_value=VALUES(max_value),refreshed_at=UTC_TIMESTAMP(6);
    END LOOP;
    CLOSE sensor_cursor;
END$$
DELIMITER ;

CREATE OR REPLACE VIEW vw_sensor_latest AS
SELECT s.id AS sensor_pk,s.sensor_id,s.name,s.location,s.is_active,
       MAX(r.recorded_at) AS last_reading_at,COUNT(r.id) AS total_readings
FROM monitor_sensor s LEFT JOIN monitor_reading r ON r.sensor_id=s.id
GROUP BY s.id,s.sensor_id,s.name,s.location,s.is_active;

CREATE OR REPLACE VIEW vw_alert_overview AS
SELECT a.id,a.created_at,a.occurred_at,a.status,a.severity,
       fn_alert_priority(a.severity,a.status) AS priority,
       s.sensor_id,r.name AS rule_name,a.metric_type,a.kind,a.trigger_value,a.threshold,a.message
FROM monitor_alert a JOIN monitor_sensor s ON a.sensor_id=s.id
JOIN monitor_rule r ON a.rule_id=r.id;

CREATE OR REPLACE VIEW vw_rule_health AS
SELECT r.id,r.name,r.kind,r.metric_type,r.operator,r.threshold,r.enabled,
       COUNT(a.id) AS alert_count,
       SUM(CASE WHEN a.status='open' THEN 1 ELSE 0 END) AS open_count
FROM monitor_rule r LEFT JOIN monitor_alert a ON a.rule_id=r.id
GROUP BY r.id,r.name,r.kind,r.metric_type,r.operator,r.threshold,r.enabled;

CREATE OR REPLACE VIEW vw_sensor_daily_summary AS
SELECT s.sensor_id,s.name,s.location,d.day,d.metric_type,d.reading_count,
       d.avg_value,d.min_value,d.max_value,d.refreshed_at
FROM monitor_daily_summary d JOIN monitor_sensor s ON s.id=d.sensor_id;
