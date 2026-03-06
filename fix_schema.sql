USE vehicle_monitoring;

-- Check and add columns only if they don't exist (MySQL compatible way)
SET @dbname = DATABASE();
SET @tablename = 'vehicle_records';

-- Add tracking_id
SET @sql = CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN tracking_id INT DEFAULT 0');
SET @check = (SELECT COUNT(*) FROM information_schema.COLUMNS 
              WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = @tablename AND COLUMN_NAME = 'tracking_id');
IF @check = 0 THEN PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt; END IF;

-- Add location  
SET @sql = CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN location VARCHAR(255) DEFAULT ''Highway Sector 4''');
SET @check = (SELECT COUNT(*) FROM information_schema.COLUMNS 
              WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = @tablename AND COLUMN_NAME = 'location');
IF @check = 0 THEN PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt; END IF;

-- Add evidence_image_path
SET @sql = CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN evidence_image_path VARCHAR(500)');
SET @check = (SELECT COUNT(*) FROM information_schema.COLUMNS 
              WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = @tablename AND COLUMN_NAME = 'evidence_image_path');
IF @check = 0 THEN PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt; END IF;

-- Add challan_generated
SET @sql = CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN challan_generated TINYINT(1) DEFAULT 0');
SET @check = (SELECT COUNT(*) FROM information_schema.COLUMNS 
              WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = @tablename AND COLUMN_NAME = 'challan_generated');
IF @check = 0 THEN PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt; END IF;

-- Add challan_amount
SET @sql = CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN challan_amount FLOAT DEFAULT 0.0');
SET @check = (SELECT COUNT(*) FROM information_schema.COLUMNS 
              WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = @tablename AND COLUMN_NAME = 'challan_amount');
IF @check = 0 THEN PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt; END IF;

-- Add notification_sent
SET @sql = CONCAT('ALTER TABLE ', @tablename, ' ADD COLUMN notification_sent TINYINT(1) DEFAULT 0');
SET @check = (SELECT COUNT(*) FROM information_schema.COLUMNS 
              WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = @tablename AND COLUMN_NAME = 'notification_sent');
IF @check = 0 THEN PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt; END IF;

SELECT 'Schema updated successfully!' AS Status;
DESCRIBE vehicle_records;
