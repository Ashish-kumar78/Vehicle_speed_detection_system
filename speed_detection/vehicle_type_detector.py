"""
Vehicle Type Detection & E-Challan Generation Module
=====================================================
This module handles:
1. Vehicle type classification (Car, Truck, Bus, Motorcycle)
2. Dynamic speed limits based on vehicle type
3. Automatic E-Challan generation
4. Evidence image capture and storage
"""

import cv2
import numpy as np
from datetime import datetime
import mysql.connector
from mysql.connector import Error
import os


# YOLOv8 class mapping for vehicles
VEHICLE_CLASSES = {
    2: 'car',      # Car
    3: 'motorcycle',  # Motorcycle
    5: 'bus',      # Bus
    7: 'truck'     # Truck
}

# Dynamic speed limits based on vehicle type (km/h)
SPEED_LIMITS = {
    'car': 80.0,
    'motorcycle': 60.0,
    'bus': 70.0,
    'truck': 60.0
}

# Fine amounts for overspeeding
FINES = {
    'car': 500.0,
    'motorcycle': 300.0,
    'bus': 1000.0,
    'truck': 800.0
}


def get_vehicle_type_from_yolo(class_id):
    """
    Map YOLO class ID to vehicle type
    
    Args:
        class_id: Integer class ID from YOLO detection
        
    Returns:
        String vehicle type or None if not a vehicle
    """
    return VEHICLE_CLASSES.get(class_id, None)


def get_speed_limit_for_vehicle(vehicle_type):
    """
    Get dynamic speed limit based on vehicle type
    
    Args:
        vehicle_type: String ('car', 'truck', 'bike', 'bus')
        
    Returns:
        Float speed limit in km/h
    """
    return SPEED_LIMITS.get(vehicle_type, 60.0)


def get_fine_for_vehicle(vehicle_type):
    """
    Get fine amount based on vehicle type
    
    Args:
        vehicle_type: String ('car', 'truck', 'bike', 'bus')
        
    Returns:
        Float fine amount in INR
    """
    return FINES.get(vehicle_type, 500.0)


def generate_challan_number():
    """
    Generate unique challan number
    
    Returns:
        String challan number (e.g., CHALLAN_20260306_001)
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"CHALLAN_{timestamp}"


def save_evidence_image(frame, vehicle_bbox, vehicle_id, output_dir="evidence_images"):
    """
    Save evidence image of violating vehicle
    
    Args:
        frame: Current video frame
        vehicle_bbox: Bounding box [x1, y1, x2, y2]
        vehicle_id: Unique tracking ID
        output_dir: Directory to save images
        
    Returns:
        String path to saved image
    """
    # Create directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Extract vehicle region
    x1, y1, x2, y2 = map(int, vehicle_bbox)
    vehicle_crop = frame[y1:y2, x1:x2]
    
    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"vehicle_{vehicle_id}_{timestamp}.jpg"
    filepath = os.path.join(output_dir, filename)
    
    # Save image
    cv2.imwrite(filepath, vehicle_crop)
    
    return filepath


def save_evidence_frame(frame, vehicle_id, output_dir="evidence_images"):
    """
    Save full frame as evidence
    
    Args:
        frame: Current video frame
        vehicle_id: Unique tracking ID
        output_dir: Directory to save images
        
    Returns:
        String path to saved image
    """
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"frame_{vehicle_id}_{timestamp}.jpg"
    filepath = os.path.join(output_dir, filename)
    
    cv2.imwrite(filepath, frame)
    
    return filepath


def store_violation_in_db(vehicle_number, vehicle_type, speed_kmh, 
                          speed_limit, tracking_id=0, location="Highway Sector 4",
                          evidence_path=None, conn=None, distance_m=10.0):
    """
    Store violation record in database with E-Challan
    
    Args:
        vehicle_number: Detected license plate number
        vehicle_type: Type of vehicle (car, truck, bike, bus)
        speed_kmh: Detected speed
        speed_limit: Speed limit for this vehicle type
        tracking_id: Unique tracking ID
        location: Location string
        evidence_path: Path to evidence image
        conn: MySQL connection object
        distance_m: Distance between detection lines in meters
        
    Returns:
        Boolean success status
    """
    # Convert numpy types to Python native types to avoid MySQL conversion errors
    if hasattr(speed_kmh, 'item'):
        speed_kmh = float(speed_kmh.item())
    else:
        speed_kmh = float(speed_kmh)
    
    if hasattr(speed_limit, 'item'):
        speed_limit = float(speed_limit.item())
    else:
        speed_limit = float(speed_limit)
    
    if hasattr(tracking_id, 'item'):
        tracking_id = int(tracking_id.item())
    else:
        tracking_id = int(tracking_id)
    
    if conn is None:
        try:
            conn = mysql.connector.connect(
                host="localhost",
                user="root",
                password="MySQL@ashish",
                database="vehicle_monitoring"
            )
            auto_conn = True
        except Error as e:
            print(f"Error connecting to database: {e}")
            return False
    else:
        auto_conn = False
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Determine status
        status = "overspeed" if speed_kmh > speed_limit else "normal"
        
        # Check if vehicle exists
        cursor.execute(
            "SELECT * FROM vehicle_records WHERE vehicle_number = %s",
            (vehicle_number,)
        )
        existing_record = cursor.fetchone()
        
        violation_count = 1
        if existing_record:
            violation_count = existing_record['violation_count'] + 1
        
        # Insert/update vehicle record
        if existing_record:
            cursor.execute("""
                UPDATE vehicle_records 
                SET vehicle_type = %s, speed_kmh = %s, status = %s, 
                    timestamp = NOW(), violation_count = %s, 
                    tracking_id = %s, location = %s, 
                    evidence_image_path = %s, distance_m = %s
                WHERE vehicle_number = %s
            """, (vehicle_type, speed_kmh, status, violation_count, 
                  tracking_id, location, evidence_path, distance_m, vehicle_number))
        else:
            cursor.execute("""
                INSERT INTO vehicle_records 
                (vehicle_number, vehicle_type, speed_kmh, status, 
                 timestamp, violation_count, tracking_id, location, 
                 evidence_image_path, distance_m)
                VALUES (%s, %s, %s, %s, NOW(), %s, %s, %s, %s, %s)
            """, (vehicle_number, vehicle_type, speed_kmh, status, 
                  violation_count, tracking_id, location, evidence_path, distance_m))
        
        # Generate E-Challan if overspeeding
        if status == "overspeed":
            challan_number = generate_challan_number()
            fine_amount = get_fine_for_vehicle(vehicle_type)
            
            cursor.execute("""
                INSERT INTO e_challans 
                (challan_number, vehicle_number, vehicle_type, 
                 speed_detected, speed_limit, location, violation_date, 
                 fine_amount, evidence_image_path)
                VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, %s)
            """, (challan_number, vehicle_number, vehicle_type, 
                  speed_kmh, speed_limit, location, fine_amount, evidence_path))
        
        conn.commit()
        
        if auto_conn:
            conn.close()
        
        return True
        
    except Error as e:
        print(f"Database error: {e}")
        if auto_conn:
            conn.close()
        return False


def send_notification(vehicle_number, vehicle_type, speed_kmh, 
                      speed_limit, challan_number, admin_email):
    """
    Send notification to traffic authority (placeholder)
    
    In production, integrate with:
    - Email system (SMTP)
    - SMS gateway
    - Traffic authority API
    """
    print(f"\n{'='*60}")
    print("🚨 VIOLATION NOTIFICATION 🚨")
    print(f"{'='*60}")
    print(f"Vehicle Number: {vehicle_number}")
    print(f"Vehicle Type: {vehicle_type.upper()}")
    print(f"Speed Detected: {speed_kmh:.2f} km/h")
    print(f"Speed Limit: {speed_limit:.2f} km/h")
    print(f"Challan Number: {challan_number}")
    print(f"Notification sent to: {admin_email}")
    print(f"{'='*60}\n")
    
    # TODO: Implement actual email/SMS sending
    # Example SMTP code in app.py send_email_alert function


def draw_vehicle_detection(frame, detections, tracker_ids, vehicle_types):
    """
    Draw vehicle detections with type labels and tracking IDs
    
    Args:
        frame: Video frame
        detections: List of bounding boxes
        tracker_ids: List of tracking IDs
        vehicle_types: List of vehicle types
        
    Returns:
        Annotated frame
    """
    colors = {
        'car': (0, 255, 0),      # Green
        'motorcycle': (255, 255, 0),  # Cyan
        'bus': (255, 0, 255),    # Magenta
        'truck': (0, 255, 255)   # Yellow
    }
    
    for i, (box, track_id, vtype) in enumerate(zip(detections, tracker_ids, vehicle_types)):
        x1, y1, x2, y2 = map(int, box)
        color = colors.get(vtype, (0, 0, 255))
        
        # Draw bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        # Draw label with type and ID
        label = f"{vtype.upper()} ID:{track_id}"
        cv2.putText(frame, label, (x1, y1 - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    
    return frame


def display_violation_alert(vehicle_number, vehicle_type, speed_kmh, 
                            speed_limit, location):
    """
    Display visual violation alert (for UI)
    
    Returns:
        Dictionary with violation details
    """
    return {
        'vehicle_number': vehicle_number,
        'vehicle_type': vehicle_type.upper(),
        'speed_detected': f"{speed_kmh:.2f} km/h",
        'speed_limit': f"{speed_limit:.2f} km/h",
        'location': location,
        'date': datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
        'status': "Challan Generated",
        'excess_speed': f"{speed_kmh - speed_limit:.2f} km/h over limit"
    }
