CREATE DATABASE IF NOT EXISTS vehicle_monitoring;
USE vehicle_monitoring;

CREATE TABLE IF NOT EXISTS vehicle_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_number VARCHAR(20) NOT NULL,
    vehicle_type ENUM('car', 'truck', 'bike', 'bus') NOT NULL,
    speed_kmh FLOAT NOT NULL,
    status ENUM('overspeed', 'normal') NOT NULL,
    timestamp DATETIME NOT NULL,
    violation_count INT DEFAULT 0,
    distance_m FLOAT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    speed_limit FLOAT DEFAULT 60.0,
    distance_calibration FLOAT DEFAULT 10.0,
    admin_email VARCHAR(255) DEFAULT 'admin@example.com'
);

-- Insert default settings
INSERT INTO system_settings (speed_limit, distance_calibration, admin_email) 
SELECT 60.0, 10.0, 'admin@example.com' 
WHERE NOT EXISTS (SELECT 1 FROM system_settings);
