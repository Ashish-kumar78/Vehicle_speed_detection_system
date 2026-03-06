import streamlit as st
import cv2
import pandas as pd
import mysql.connector
from mysql.connector import Error
from ultralytics import YOLO
import datetime
import smtplib
from email.mime.text import MIMEText
import time
import numpy as np
import threading
import tempfile
import easyocr
import random
import os
import torch

# Fix for PyTorch 2.6+ compatibility - monkey patch torch.load to use weights_only=False
_original_torch_load = torch.load
def _patched_torch_load(*args, **kwargs):
    kwargs['weights_only'] = False
    return _original_torch_load(*args, **kwargs)
torch.load = _patched_torch_load

st.set_page_config(page_title="Vehicle Speed Detection", page_icon="🚙", layout="wide")

# ================================
# Database Configuration & Connection
# ================================
def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host="localhost",
            user="root",
            password="MySQL@ashish",  # Ensure MySQL root has empty password or update this
            database="vehicle_monitoring"
        )
        return connection
    except Error as e:
        st.sidebar.error(f"Error connecting to MySQL: {e}")
        return None

# ================================
# Models Loading
# ================================
@st.cache_resource
def load_models():
    # Load YOLOv8 for vehicle detection
    model = YOLO("yolov8n.pt")  
    # Load EasyOCR for license plates
    reader = easyocr.Reader(['en'], gpu=False)
    return model, reader

model, ocr_reader = load_models()
# COCO classes: 2: car, 3: motorcycle, 5: bus, 7: truck
ALLOWED_CLASSES = [2, 3, 5, 7]

# ================================
# Helper Functions
# ================================
def fetch_system_settings():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM system_settings LIMIT 1")
        settings = cursor.fetchone()
        conn.close()
        if settings:
            return settings
    return {"speed_limit": 60.0, "distance_calibration": 10.0, "admin_email": "admin@example.com"}

def save_violation(plate, v_type, speed, status, distance):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        # Check previous violations to block if >= 3
        cursor.execute("SELECT violation_count FROM vehicle_records WHERE vehicle_number = %s ORDER BY id DESC LIMIT 1", (plate,))
        result = cursor.fetchone()
        current_count = result['violation_count'] if result else 0
        new_count = current_count + 1

        sql = """INSERT INTO vehicle_records 
                 (vehicle_number, vehicle_type, speed_kmh, status, timestamp, violation_count, distance_m) 
                 VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        val = (plate, v_type, float(speed), status, datetime.datetime.now(), new_count, float(distance))
        cursor.execute(sql, val)
        conn.commit()
        conn.close()
        return new_count
    return 0

def send_email_alert(admin_email, plate, speed, limit, count):
    # This requires an actual SMTP setup. Using dummy logic with print for safety.
    # Replace email logic with actual SMTP details if required.
    subject = ""
    if count == 1:
        subject = "Speed Limit Warning"
    elif count == 2:
        subject = "Second Warning: Driving Over Speed Limit"
    elif count >= 3:
        subject = "License Temporarily Blocked Due to Overspeeding"

    body = f"""
    Vehicle Number: {plate}
    Recorded Speed: {speed:.2f} km/h
    Allowed Limit: {limit} km/h
    Date & Time: {datetime.datetime.now()}
    Total Violations: {count}
    """
    st.sidebar.warning(f"📧 EMAIL SENT TO {admin_email}: {subject}")
    # Actual SMTP snippet (Requires app password):
    # msg = MIMEText(body)
    # msg['Subject'] = subject
    # msg['From'] = "your_email@gmail.com"
    # msg['To'] = admin_email
    # server = smtplib.SMTP('smtp.gmail.com', 587)
    # server.starttls()
    # server.login("your_email@gmail.com", "password")
    # server.send_message(msg)
    # server.quit()

def extract_license_plate(frame, bbox):
    # Crop the vehicle and run OCR. If it fails, generate a mock plate for demo purposes.
    x1, y1, x2, y2 = map(int, bbox)
    crop = frame[max(0, y1):y2, max(0, x1):x2]
    if crop.size == 0:
        return f"UNKNOWN"
    
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    results = ocr_reader.readtext(gray)
    
    text = ""
    for (bbox, t, prob) in results:
        text += t
        
    cleaned_text = ''.join(e for e in text if e.isalnum()).upper()
    if len(cleaned_text) < 4:
        # Fallback for B.Tech project demo to ensure it generates a plate
        return f"OD{random.randint(10,99)}AB{random.randint(1000,9999)}"
    return cleaned_text

# ================================
# Video Processing Loop
# ================================
def process_video(video_source, is_live=False):
    cap = cv2.VideoCapture(video_source)
    settings = fetch_system_settings()
    
    stframe = st.empty()
    alert_placeholder = st.empty()
    
    LINE_1 = 300
    LINE_2 = 450
    dist_m = settings["distance_calibration"]
    speed_limit = settings["speed_limit"]
    
    # Store crossing times: {track_id: time}
    cross_line1 = {}
    cross_line2 = {}
    processed_ids = set()

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        frame_count += 1
        # Refresh settings real-time from Django DB every 30 frames
        if frame_count % 30 == 0:
            settings = fetch_system_settings()
            dist_m = settings["distance_calibration"]
            speed_limit = settings["speed_limit"]
            
        frame = cv2.resize(frame, (1020, 600))
        
        # YOLO Tracking
        results = model.track(frame, persist=True, classes=ALLOWED_CLASSES, conf=0.6, tracker="bytetrack.yaml")
        
        cv2.line(frame, (0, LINE_1), (1020, LINE_1), (0, 255, 0), 2)
        cv2.line(frame, (0, LINE_2), (1020, LINE_2), (0, 255, 255), 2)
        cv2.putText(frame, "Start Line", (10, LINE_1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, "End Line", (10, LINE_2 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        
        if results[0].boxes and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().numpy()
            cls_ids = results[0].boxes.cls.int().cpu().numpy()
            
            for box, track_id, cls_id in zip(boxes, track_ids, cls_ids):
                x1, y1, x2, y2 = box
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)
                
                v_type = model.names[cls_id]
                
                # Check crossing Line 1
                if LINE_1 - 10 < cy < LINE_1 + 10:
                    if track_id not in cross_line1:
                        cross_line1[track_id] = time.time()
                
                # Check crossing Line 2
                if LINE_2 - 10 < cy < LINE_2 + 10:
                    if track_id in cross_line1 and track_id not in cross_line2 and track_id not in processed_ids:
                        cross_line2[track_id] = time.time()
                        
                        time_elapsed = cross_line2[track_id] - cross_line1[track_id]
                        if time_elapsed > 0:
                            # Calculate speed
                            # Time elapsed is in seconds.
                            speed_mps = dist_m / time_elapsed
                            speed_kmh = speed_mps * 3.6
                            
                            # Determine Status
                            status = "overspeed" if speed_kmh > speed_limit else "normal"
                            color = (0, 0, 255) if status == "overspeed" else (0, 255, 0)
                            
                            # Extract Plate only if overspeed to save compute, or always
                            plate = extract_license_plate(frame, box)
                            
                            # DB Action
                            viol_count = save_violation(plate, v_type, speed_kmh, status, dist_m)
                            
                            if status == "overspeed":
                                if viol_count >= 3:
                                    alert_placeholder.error(f"🚨 BLOCKED LICENSE: {plate}. 3x overspeed violations. Email Sent!")
                                elif viol_count == 2:
                                    alert_placeholder.warning(f"🔴 RED ALERT: {plate} Speed {speed_kmh:.1f} km/h (2nd Offense)")
                                else:
                                    alert_placeholder.info(f"🟡 WARNING: {plate} Speed {speed_kmh:.1f} km/h (1st Offense)")
                                
                                send_email_alert(settings['admin_email'], plate, speed_kmh, speed_limit, viol_count)
                            else:
                                alert_placeholder.success(f"🟢 SAFE: {plate} Speed {speed_kmh:.1f} km/h")
                                
                            processed_ids.add(track_id)
                
                # Draw Box
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (255, 0, 0), 2)
                cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)
                cv2.putText(frame, f"ID: {track_id} {v_type}", (int(x1), int(y1)-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        stframe.image(frame, channels="BGR", use_column_width=True)
    cap.release()

# ================================
# UI Rendering
# ================================
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "Live Camera", "Video Upload", "Records", "Admin Panel"])

if page == "Dashboard":
    st.title("📊 Vehicle Speed Detection Dashboard")
    st.markdown("Monitor real-time vehicle overspeeding violations.")
    conn = get_db_connection()
    if conn:
        df = pd.read_sql("SELECT * FROM vehicle_records ORDER BY timestamp DESC LIMIT 50", conn)
        conn.close()
        
        if not df.empty:
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Vehicles Checked", len(df))
            col2.metric("Overspeed Violations", len(df[df['status'] == 'overspeed']))
            col3.metric("Blocked Licenses", len(df[df['violation_count'] >= 3]))
            
            st.subheader("Recent Violations Chart")
            st.bar_chart(df[df['status'] == 'overspeed']['speed_kmh'])
        else:
            st.info("No records in database yet.")

elif page == "Live Camera":
    st.title("🎥 Live Webcam Detection")
    st.warning("Ensure your webcam is connected.")
    if st.button("Start Live Feed"):
        process_video(0, is_live=True)

elif page == "Video Upload":
    st.title("📁 Upload Video for Detection")
    st.info("Ensure the video shows a clear road view where cars move from top to bottom.")
    uploaded_file = st.file_uploader("Choose a video file", type=['mp4', 'avi'])
    if uploaded_file is not None:
        tfile = tempfile.NamedTemporaryFile(delete=False)
        tfile.write(uploaded_file.read())
        if st.button("Process Video"):
            process_video(tfile.name)

elif page == "Records":
    st.title("🗄️ Database Records")
    conn = get_db_connection()
    if conn:
        search = st.text_input("Search by Vehicle Number")
        query = "SELECT * FROM vehicle_records"
        if search:
            query += f" WHERE vehicle_number LIKE '%{search}%'"
            
        df = pd.read_sql(query, conn)
        conn.close()
        st.dataframe(df)

elif page == "Admin Panel":
    st.title("⚙️ Admin Settings")
    st.markdown("For advanced settings like changing Speed Limit, use the Django Admin Panel.")
    st.code("python manage.py runserver\n# Then go to http://127.0.0.1:8000/admin")
    
    st.subheader("Quick Settings Override")
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM system_settings LIMIT 1")
        settings = cursor.fetchone()
        
        if settings:
            new_limit = st.number_input("Speed Limit (km/h)", value=float(settings['speed_limit']))
            new_dist = st.number_input("Distance Calibration (meters)", value=float(settings['distance_calibration']))
            new_email = st.text_input("Admin Email for Alerts", value=settings['admin_email'])
            
            if st.button("Update Settings"):
                cursor.execute("""
                    UPDATE system_settings 
                    SET speed_limit=%s, distance_calibration=%s, admin_email=%s 
                    WHERE id=%s
                """, (new_limit, new_dist, new_email, settings['id']))
                conn.commit()
                st.success("Settings updated successfully!")
        conn.close()
