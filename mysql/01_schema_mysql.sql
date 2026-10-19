-- EXPLICIT MySQL DDL mirroring Django app migration 0001_initial.
-- PRIMARY INSTALL: execute python manage.py migrate; do NOT manually create the same tables first.
-- This standalone DDL is provided for SQL review, SQL-only recreation of app tables, and assessment.
-- Prerequisite: database gdg_campus_monitor and Django auth_user created by Django migrations.
-- Referential actions stay under Django ORM control for consistency with Django migrations.
USE gdg_campus_monitor;

CREATE TABLE IF NOT EXISTS monitor_sensor (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  sensor_id VARCHAR(80) NOT NULL UNIQUE,
  name VARCHAR(120) NOT NULL,
  location VARCHAR(160) NOT NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS monitor_rule (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  sensor_id BIGINT NULL,
  metric_type VARCHAR(24) NOT NULL,
  kind VARCHAR(12) NOT NULL DEFAULT 'instant',
  operator VARCHAR(4) NOT NULL DEFAULT 'GT',
  threshold DECIMAL(14,4) NOT NULL,
  window_seconds INT UNSIGNED NOT NULL DEFAULT 600,
  min_samples INT UNSIGNED NOT NULL DEFAULT 2,
  severity VARCHAR(12) NOT NULL DEFAULT 'warning',
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_by_id INT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  INDEX mon_rule_metric_idx(enabled, metric_type),
  INDEX mon_rule_sensor_fk_idx(sensor_id),
  INDEX mon_rule_creator_fk_idx(created_by_id),
  CONSTRAINT mon_rule_sensor_fk FOREIGN KEY(sensor_id) REFERENCES monitor_sensor(id),
  CONSTRAINT mon_rule_creator_fk FOREIGN KEY(created_by_id) REFERENCES auth_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS monitor_reading (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  event_id VARCHAR(64) NOT NULL UNIQUE,
  sensor_id BIGINT NOT NULL,
  metric_type VARCHAR(24) NOT NULL,
  value DECIMAL(14,4) NOT NULL,
  recorded_at DATETIME(6) NOT NULL,
  received_at DATETIME(6) NOT NULL,
  processed_at DATETIME(6) NULL,
  INDEX mon_read_queue_idx(processed_at, recorded_at, id),
  INDEX mon_read_timeseries_idx(sensor_id, metric_type, recorded_at),
  CONSTRAINT mon_read_sensor_fk FOREIGN KEY(sensor_id) REFERENCES monitor_sensor(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS monitor_alert (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  dedupe_key VARCHAR(64) NOT NULL UNIQUE,
  rule_id BIGINT NOT NULL,
  sensor_id BIGINT NOT NULL,
  reading_id BIGINT NULL,
  metric_type VARCHAR(24) NOT NULL,
  kind VARCHAR(12) NOT NULL,
  severity VARCHAR(12) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'open',
  trigger_value DECIMAL(14,4) NOT NULL,
  threshold DECIMAL(14,4) NOT NULL,
  message VARCHAR(300) NOT NULL,
  window_start DATETIME(6) NULL,
  window_end DATETIME(6) NULL,
  occurred_at DATETIME(6) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  acknowledged_at DATETIME(6) NULL,
  acknowledged_by_id INT NULL,
  resolved_at DATETIME(6) NULL,
  resolved_by_id INT NULL,
  INDEX mon_alert_status_idx(status, created_at DESC),
  INDEX mon_alert_sensor_idx(sensor_id, created_at DESC),
  INDEX mon_alert_rule_fk_idx(rule_id),
  INDEX mon_alert_reading_fk_idx(reading_id),
  INDEX mon_alert_ack_actor_fk_idx(acknowledged_by_id),
  INDEX mon_alert_res_actor_fk_idx(resolved_by_id),
  CONSTRAINT mon_alert_rule_fk FOREIGN KEY(rule_id) REFERENCES monitor_rule(id),
  CONSTRAINT mon_alert_sensor_fk FOREIGN KEY(sensor_id) REFERENCES monitor_sensor(id),
  CONSTRAINT mon_alert_reading_fk FOREIGN KEY(reading_id) REFERENCES monitor_reading(id),
  CONSTRAINT mon_alert_ack_actor_fk FOREIGN KEY(acknowledged_by_id) REFERENCES auth_user(id),
  CONSTRAINT mon_alert_res_actor_fk FOREIGN KEY(resolved_by_id) REFERENCES auth_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS monitor_alert_audit (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  alert_id BIGINT NOT NULL,
  old_status VARCHAR(16) NULL,
  new_status VARCHAR(16) NOT NULL,
  actor_id INT NULL,
  changed_at DATETIME(6) NOT NULL,
  INDEX mon_audit_alert_idx(alert_id, changed_at),
  INDEX mon_audit_actor_fk_idx(actor_id),
  CONSTRAINT mon_audit_alert_fk FOREIGN KEY(alert_id) REFERENCES monitor_alert(id),
  CONSTRAINT mon_audit_actor_fk FOREIGN KEY(actor_id) REFERENCES auth_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS monitor_daily_summary (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  sensor_id BIGINT NOT NULL,
  metric_type VARCHAR(24) NOT NULL,
  day DATE NOT NULL,
  reading_count INT UNSIGNED NOT NULL DEFAULT 0,
  avg_value DECIMAL(14,4) NULL,
  min_value DECIMAL(14,4) NULL,
  max_value DECIMAL(14,4) NULL,
  refreshed_at DATETIME(6) NOT NULL,
  CONSTRAINT mon_daily_unique UNIQUE(sensor_id, metric_type, day),
  CONSTRAINT mon_daily_sensor_fk FOREIGN KEY(sensor_id) REFERENCES monitor_sensor(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
