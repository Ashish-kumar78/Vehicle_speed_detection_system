USE vehicle_monitoring;

-- Add missing columns to vehicle_records if they don't exist
ALTER TABLE vehicle_records ADD COLUMN tracking_id INT DEFAULT 0;
ALTER TABLE vehicle_records ADD COLUMN location VARCHAR(255) DEFAULT 'Highway Sector 4';
ALTER TABLE vehicle_records ADD COLUMN evidence_image_path VARCHAR(500);
ALTER TABLE vehicle_records ADD COLUMN challan_generated TINYINT(1) DEFAULT 0;
ALTER TABLE vehicle_records ADD COLUMN challan_amount FLOAT DEFAULT 0.0;
ALTER TABLE vehicle_records ADD COLUMN notification_sent TINYINT(1) DEFAULT 0;

-- Verify the changes
DESCRIBE vehicle_records;

SELECT 'Database schema updated successfully!' AS Status;
