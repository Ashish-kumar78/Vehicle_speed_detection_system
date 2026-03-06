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
    distance_m FLOAT NOT NULL,
    tracking_id INT DEFAULT 0,
    location VARCHAR(255) DEFAULT 'Highway Sector 4',
    evidence_image_path VARCHAR(500),
    challan_generated BOOLEAN DEFAULT FALSE,
    challan_amount FLOAT DEFAULT 0.0,
    notification_sent BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS system_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    speed_limit FLOAT DEFAULT 60.0,
    distance_calibration FLOAT DEFAULT 10.0,
    admin_email VARCHAR(255) DEFAULT 'admin@example.com'
);

-- Create E-Challan table for detailed violation records
CREATE TABLE IF NOT EXISTS e_challans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    challan_number VARCHAR(50) UNIQUE NOT NULL,
    vehicle_number VARCHAR(20) NOT NULL,
    vehicle_type ENUM('car', 'truck', 'bike', 'bus') NOT NULL,
    speed_detected FLOAT NOT NULL,
    speed_limit FLOAT NOT NULL,
    location VARCHAR(255) DEFAULT 'Highway Sector 4',
    violation_date DATETIME NOT NULL,
    fine_amount FLOAT DEFAULT 500.0,
    status ENUM('pending', 'paid', 'cancelled') DEFAULT 'pending',
    evidence_image_path VARCHAR(500),
    notification_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default settings
INSERT INTO system_settings (speed_limit, distance_calibration, admin_email) 
SELECT 60.0, 10.0, 'admin@example.com' 
WHERE NOT EXISTS (SELECT 1 FROM system_settings);
