-- Run in mysql as an administrator. Replace the password before execution.
CREATE DATABASE IF NOT EXISTS gdg_campus_monitor CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'gdg_monitor_app'@'localhost' IDENTIFIED BY 'CHANGE_ME';
CREATE USER IF NOT EXISTS 'gdg_monitor_app'@'127.0.0.1' IDENTIFIED BY 'CHANGE_ME';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES, DROP
  ON gdg_campus_monitor.* TO 'gdg_monitor_app'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES, DROP
  ON gdg_campus_monitor.* TO 'gdg_monitor_app'@'127.0.0.1';
-- Stored functions/triggers/views require these permissions during initial bootstrap:
GRANT CREATE ROUTINE, ALTER ROUTINE, EXECUTE, TRIGGER, CREATE VIEW, SHOW VIEW
  ON gdg_campus_monitor.* TO 'gdg_monitor_app'@'localhost';
GRANT CREATE ROUTINE, ALTER ROUTINE, EXECUTE, TRIGGER, CREATE VIEW, SHOW VIEW
  ON gdg_campus_monitor.* TO 'gdg_monitor_app'@'127.0.0.1';
-- After setup, remove unnecessary DDL privileges from runtime user for deployment.
