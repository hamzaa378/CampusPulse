-- Demo seed, safe to re-run. Run after Django migrations and SQL routines.
USE gdg_campus_monitor;
INSERT INTO monitor_sensor(sensor_id,name,location,is_active,created_at) VALUES
('library-floor-2','Library Temperature','Main Library Floor 2',1,UTC_TIMESTAMP(6)),
('cafeteria-hall','Cafeteria Environment','Main Cafeteria',1,UTC_TIMESTAMP(6)),
('lab-block-a','Laboratory Air Quality','Academic Block A',1,UTC_TIMESTAMP(6))
ON DUPLICATE KEY UPDATE name=VALUES(name),location=VALUES(location);
INSERT INTO monitor_rule(name,sensor_id,metric_type,kind,operator,threshold,window_seconds,min_samples,severity,enabled,created_by_id,created_at,updated_at)
SELECT 'Library hot reading',s.id,'temperature','instant','GT',32.0000,600,2,'critical',1,NULL,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6)
FROM monitor_sensor s WHERE s.sensor_id='library-floor-2'
AND NOT EXISTS(SELECT 1 FROM monitor_rule r WHERE r.name='Library hot reading');
INSERT INTO monitor_rule(name,sensor_id,metric_type,kind,operator,threshold,window_seconds,min_samples,severity,enabled,created_by_id,created_at,updated_at)
SELECT 'Library ten minute mean',s.id,'temperature','window','GT',30.0000,600,2,'warning',1,NULL,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6)
FROM monitor_sensor s WHERE s.sensor_id='library-floor-2'
AND NOT EXISTS(SELECT 1 FROM monitor_rule r WHERE r.name='Library ten minute mean');
