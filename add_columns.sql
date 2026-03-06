USE vehicle_monitoring;

-- Try to add columns, ignore errors if they exist
SET @sql1 = 'ALTER TABLE vehicle_records ADD COLUMN tracking_id INT DEFAULT 0';
SET @sql2 = 'ALTER TABLE vehicle_records ADD COLUMN location VARCHAR(255) DEFAULT ''Highway Sector 4''';
SET @sql3 = 'ALTER TABLE vehicle_records ADD COLUMN evidence_image_path VARCHAR(500)';
SET @sql4 = 'ALTER TABLE vehicle_records ADD COLUMN challan_generated TINYINT DEFAULT 0';
SET @sql5 = 'ALTER TABLE vehicle_records ADD COLUMN challan_amount FLOAT DEFAULT 0';
SET @sql6 = 'ALTER TABLE vehicle_records ADD COLUMN notification_sent TINYINT DEFAULT 0';

PREPARE stmt1 FROM @sql1;
EXECUTE stmt1;
DEALLOCATE PREPARE stmt1;

PREPARE stmt2 FROM @sql2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

PREPARE stmt3 FROM @sql3;
EXECUTE stmt3;
DEALLOCATE PREPARE stmt3;

PREPARE stmt4 FROM @sql4;
EXECUTE stmt4;
DEALLOCATE PREPARE stmt4;

PREPARE stmt5 FROM @sql5;
EXECUTE stmt5;
DEALLOCATE PREPARE stmt5;

PREPARE stmt6 FROM @sql6;
EXECUTE stmt6;
DEALLOCATE PREPARE stmt6;

SELECT 'Columns added successfully!' AS Status;
DESCRIBE vehicle_records;
