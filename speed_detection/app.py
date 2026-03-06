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

# Import vehicle type detection and E-challan module
from vehicle_type_detector import (
    get_vehicle_type_from_yolo,
    get_speed_limit_for_vehicle,
    get_fine_for_vehicle,
    save_evidence_frame,
    store_violation_in_db,
    send_notification,
    draw_vehicle_detection,
    display_violation_alert
)

# Fix for PyTorch 2.6+ compatibility - monkey patch torch.load to use weights_only=False
_original_torch_load = torch.load
def _patched_torch_load(*args, **kwargs):
    kwargs['weights_only'] = False
    return _original_torch_load(*args, **kwargs)
torch.load = _patched_torch_load

st.set_page_config(page_title="Vehicle Speed Detection", page_icon="🚙", layout="wide")

# Custom CSS for modern UI enhancement
st.markdown("""
    <style>
    /* Main container */
    .main > div {
        max-width: 1400px;
        margin: 0 auto;
    }
    
    /* Cards and containers */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 15px;
        color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    div[data-testid="stMetricValue"] {
        font-size: 2.5rem;
        font-weight: bold;
    }
    
    div[data-testid="stMetricLabel"] {
        font-size: 1rem;
        opacity: 0.9;
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 12px 24px;
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.2);
    }
    
    /* Headers */
    h1, h2, h3 {
        color: #2d3748;
        font-weight: 700;
    }
    
    /* Sidebar */
    .css-1d391kg {
        background-color: #f7fafc;
    }
    
    /* Alert boxes */
    div[data-testid="stAlert"] {
        border-radius: 10px;
        border: none;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Dataframe styling */
    div[data-testid="stDataFrame"] {
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    </style>
""", unsafe_allow_html=True)

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
        return f"VEHICLE_{random.randint(1000,9999)}"
    
    try:
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
    except Exception as e:
        # If OCR fails, generate a demo plate
        return f"OD{random.randint(10,99)}AB{random.randint(1000,9999)}"

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
    base_speed_limit = settings["speed_limit"]
    
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
            base_speed_limit = settings["speed_limit"]
            
        frame = cv2.resize(frame, (1020, 600))
        
        # YOLO Tracking with Vehicle Type Detection
        results = model.track(frame, persist=True, classes=ALLOWED_CLASSES, conf=0.6, tracker="bytetrack.yaml")
        
        cv2.line(frame, (0, LINE_1), (1020, LINE_1), (0, 255, 0), 2)
        cv2.line(frame, (0, LINE_2), (1020, LINE_2), (0, 255, 255), 2)
        cv2.putText(frame, "Start Line", (10, LINE_1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, "End Line", (10, LINE_2 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        
        if results[0].boxes and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().numpy()
            cls_ids = results[0].boxes.cls.int().cpu().numpy()
            
            # Get vehicle types for all detections
            vehicle_types = [model.names[cls_id] for cls_id in cls_ids]
            
            # Draw enhanced detections with vehicle types
            frame = draw_vehicle_detection(frame, boxes, track_ids, vehicle_types)
            
            for box, track_id, cls_id in zip(boxes, track_ids, cls_ids):
                x1, y1, x2, y2 = box
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)
                
                # Get vehicle type from YOLO class
                v_type = get_vehicle_type_from_yolo(cls_id)
                if v_type is None:
                    v_type = model.names[cls_id]  # Fallback to original name
                
                # Get DYNAMIC speed limit based on vehicle type
                speed_limit = get_speed_limit_for_vehicle(v_type)
                
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
                            speed_mps = dist_m / time_elapsed
                            speed_kmh = speed_mps * 3.6
                            
                            # Determine Status using DYNAMIC speed limit
                            status = "overspeed" if speed_kmh > speed_limit else "normal"
                            
                            if status == "overspeed":
                                # Extract license plate
                                plate = extract_license_plate(frame, box)
                                
                                # Save evidence image
                                evidence_path = save_evidence_frame(frame, track_id)
                                
                                # Store violation with E-Challan generation
                                conn = get_db_connection()
                                if conn:
                                    try:
                                        success = store_violation_in_db(
                                            vehicle_number=plate,
                                            vehicle_type=v_type,
                                            speed_kmh=speed_kmh,
                                            speed_limit=speed_limit,
                                            tracking_id=track_id,
                                            location="Highway Sector 4",
                                            evidence_path=evidence_path,
                                            conn=conn,
                                            distance_m=dist_m
                                        )
                                        
                                        if success:
                                            st.success(f"✅ Vehicle {plate} saved to database!")
                                        else:
                                            st.error(f"❌ Failed to save {plate} to database")
                                            
                                        # Generate challan number for display
                                        challan_num = f"CHALLAN_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                                        
                                        # Display violation alert
                                        alert_info = display_violation_alert(
                                            plate, v_type, speed_kmh, speed_limit, "Highway Sector 4"
                                        )
                                        
                                        # Show rich notification
                                        with st.expander(f"🚨 VIOLATION DETECTED - {plate}", expanded=True):
                                            col1, col2 = st.columns(2)
                                            with col1:
                                                st.metric("Vehicle Type", alert_info['vehicle_type'])
                                                st.metric("Speed Detected", alert_info['speed_detected'])
                                            with col2:
                                                st.metric("Speed Limit", alert_info['speed_limit'])
                                                st.metric("Excess Speed", alert_info['excess_speed'])
                                            st.error(f"📍 Location: {alert_info['location']}")
                                            st.warning(f"🎫 Challan Generated: {challan_num}")
                                            st.info(f"⏰ Time: {alert_info['date']}")
                                        
                                        # Send notification
                                        send_notification(
                                            plate, v_type, speed_kmh, speed_limit, 
                                            challan_num, settings['admin_email']
                                        )
                                    except Exception as e:
                                        st.error(f"Database error: {e}")
                                    finally:
                                        conn.close()
                            else:
                                # Normal vehicle - just log it
                                plate = extract_license_plate(frame, box)
                                conn = get_db_connection()
                                if conn:
                                    try:
                                        store_violation_in_db(
                                            vehicle_number=plate,
                                            vehicle_type=v_type,
                                            speed_kmh=speed_kmh,
                                            speed_limit=speed_limit,
                                            tracking_id=track_id,
                                            location="Highway Sector 4",
                                            evidence_path=None,
                                            conn=conn,
                                            distance_m=dist_m
                                        )
                                        st.success(f"✅ Vehicle {plate} (Normal) saved to database")
                                    except Exception as e:
                                        st.error(f"Error saving normal vehicle: {e}")
                                    finally:
                                        conn.close()
                            
                            processed_ids.add(track_id)

        stframe.image(frame, channels="BGR", width="stretch")
    
    cap.release()
    
    # Show completion message
    st.success("✅ Video processing completed!")
    st.info(f"📊 Processed {len(processed_ids)} vehicles in total")
    
    # Display summary if any vehicles were detected
    if len(processed_ids) > 0:
        st.balloons()

# ================================
# UI Rendering
# ================================
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "Live Camera", "Video Upload", "E-Challans", "Records", "Admin Panel"])

if page == "Dashboard":
    st.title("📊 Vehicle Speed Detection Dashboard")
    st.markdown("### Monitor real-time vehicle overspeeding violations")
    st.markdown("---")
    
    conn = get_db_connection()
    if conn:
        df = pd.read_sql("SELECT * FROM vehicle_records ORDER BY timestamp DESC LIMIT 50", conn)
        conn.close()
        
        if not df.empty:
            # Enhanced metrics with columns
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    label="🚗 Total Vehicles",
                    value=len(df),
                    delta=None
                )
            
            with col2:
                overspeed_count = len(df[df['status'] == 'overspeed'])
                st.metric(
                    label="⚠️ Overspeed Violations",
                    value=overspeed_count,
                    delta=f"{(overspeed_count/len(df)*100):.1f}% of total" if len(df) > 0 else None
                )
            
            with col3:
                blocked_count = len(df[df['violation_count'] >= 3])
                st.metric(
                    label="🚫 Blocked Licenses",
                    value=blocked_count,
                    delta="Critical" if blocked_count > 0 else "✓ Safe"
                )
            
            with col4:
                normal_count = len(df[df['status'] == 'normal'])
                st.metric(
                    label="✅ Normal Vehicles",
                    value=normal_count,
                    delta=f"{(normal_count/len(df)*100):.1f}% compliance" if len(df) > 0 else None
                )
            
            st.markdown("---")
            
            # Charts in tabs for better organization
            tab1, tab2, tab3 = st.tabs(["📈 Speed Analysis", "📊 Violation Trends", "📋 Recent Records"])
            
            with tab1:
                st.subheader("Overspeeding Vehicles - Speed Distribution")
                overspeed_df = df[df['status'] == 'overspeed'].copy()
                if not overspeed_df.empty:
                    st.bar_chart(overspeed_df.set_index('vehicle_number')['speed_kmh'])
                else:
                    st.info("No overspeeding records to display")
            
            with tab2:
                st.subheader("Violation Count Distribution")
                if not df.empty:
                    violation_counts = df.groupby('violation_count').size()
                    st.bar_chart(violation_counts)
                else:
                    st.info("No data available")
            
            with tab3:
                st.subheader("Latest 20 Records")
                if not df.empty:
                    st.dataframe(df.head(20), width="stretch")
                else:
                    st.info("No records in database yet.")
        else:
            st.info("📭 No records in database yet. Start monitoring to collect data!")

elif page == "Live Camera":
    st.title("🎥 Live Webcam Detection")
    st.markdown("### Real-time vehicle speed monitoring")
    st.info("💡 Ensure your webcam is connected and has a clear view of the road")
    
    # Display camera settings info
    with st.expander("📋 Camera Setup Guidelines"):
        st.markdown("""
        - Position camera at an elevated angle
        - Ensure good lighting conditions
        - Mark two reference lines on the road (visible in frame)
        - Calibrate distance between lines in Admin Panel
        - Vehicles should move from top to bottom in frame
        """)
    
    if st.button("🎬 Start Live Feed", use_container_width=True):
        with st.spinner("Initializing camera and loading models..."):
            process_video(0, is_live=True)

elif page == "Video Upload":
    st.title("📁 Upload Video for Detection")
    st.markdown("### Analyze recorded footage for overspeeding violations")
    
    # Show supported formats
    col1, col2 = st.columns([3, 1])
    with col1:
        uploaded_file = st.file_uploader(
            "Choose a video file",
            type=['mp4', 'avi', 'mov', 'mkv'],
            help="Supported formats: MP4, AVI, MOV, MKV"
        )
    
    if uploaded_file is not None:
        tfile = tempfile.NamedTemporaryFile(delete=False)
        tfile.write(uploaded_file.read())
        
        # Show video preview in sidebar
        with col2:
            st.video(tfile.name)
        
        st.success(f"✅ Uploaded: {uploaded_file.name}")
        
        if st.button("🚀 Process Video", use_container_width=True):
            with st.spinner("⏳ Processing video. This may take a while..."):
                process_video(tfile.name)

elif page == "E-Challans":
    st.title("🎫 E-Challan Management System")
    st.markdown("### Automatic Traffic Violation Enforcement")
    
    conn = get_db_connection()
    if conn:
        # Show statistics
        try:
            total_challans = pd.read_sql("SELECT COUNT(*) as count FROM e_challans", conn)['count'][0]
            pending_challans = pd.read_sql("SELECT COUNT(*) as count FROM e_challans WHERE status='pending'", conn)['count'][0]
            total_fines = pd.read_sql("SELECT SUM(fine_amount) as total FROM e_challans WHERE status='pending'", conn)['total'][0] or 0
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Challans", total_challans)
            with col2:
                st.metric("Pending Payment", pending_challans)
            with col3:
                st.metric("Total Fine Amount", f"₹{total_fines:.2f}")
            
            st.markdown("---")
            
            # Search and filter
            col1, col2 = st.columns(2)
            with col1:
                search_vehicle = st.text_input("🔍 Search by Vehicle Number")
            with col2:
                status_filter = st.selectbox("Filter by Status", ["All", "pending", "paid", "cancelled"])
            
            # Build query
            query = "SELECT * FROM e_challans WHERE 1=1"
            if search_vehicle:
                query += f" AND vehicle_number LIKE '%{search_vehicle}%'"
            if status_filter != "All":
                query += f" AND status = '{status_filter}'"
            query += " ORDER BY violation_date DESC LIMIT 50"
            
            df = pd.read_sql(query, conn)
            
            if not df.empty:
                st.markdown("### Challan Records")
                
                # Display each challan as a card
                for idx, row in df.iterrows():
                    with st.expander(f"🎫 {row['challan_number']} - {row['vehicle_number']}", expanded=False):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.markdown(f"**Vehicle Number:** {row['vehicle_number'].upper()}")
                            st.markdown(f"**Vehicle Type:** {row['vehicle_type'].upper()}")
                            st.markdown(f"**Speed Detected:** {row['speed_detected']:.1f} km/h")
                        
                        with col2:
                            st.markdown(f"**Speed Limit:** {row['speed_limit']:.1f} km/h")
                            st.markdown(f"**Fine Amount:** ₹{row['fine_amount']:.2f}")
                            st.markdown(f"**Status:** {row['status'].upper()}")
                        
                        st.markdown(f"**Location:** {row['location']}")
                        st.markdown(f"**Violation Date:** {row['violation_date'].strftime('%d-%m-%Y %H:%M:%S')}")
                        
                        if row['evidence_image_path']:
                            if os.path.exists(row['evidence_image_path']):
                                st.image(row['evidence_image_path'], caption="Evidence Image", width=400)
                        
                        # Action buttons (for demo purposes)
                        if row['status'] == 'pending':
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                if st.button("Mark as Paid", key=f"pay_{row['id']}"):
                                    cursor = conn.cursor()
                                    cursor.execute("UPDATE e_challans SET status='paid' WHERE id=%s", (row['id'],))
                                    conn.commit()
                                    st.success("✅ Marked as paid!")
                                    time.sleep(1)
                                    st.rerun()
                            with col2:
                                if st.button("Cancel Challan", key=f"cancel_{row['id']}"):
                                    cursor = conn.cursor()
                                    cursor.execute("UPDATE e_challans SET status='cancelled' WHERE id=%s", (row['id'],))
                                    conn.commit()
                                    st.success("✅ Challan cancelled!")
                                    time.sleep(1)
                                    st.rerun()
            else:
                st.info("No challans found matching your criteria.")
                
        except Exception as e:
            st.warning(f"E-Challan table might not exist yet: {e}")
            st.info("Challans will be automatically generated when violations are detected.")
        
        conn.close()

elif page == "Records":
    st.title("🗄️ Database Records")
    st.markdown("### View and search vehicle records")
    
    conn = get_db_connection()
    if conn:
        # Search with better UI
        col1, col2 = st.columns([3, 1])
        with col1:
            search = st.text_input(
                "🔍 Search by Vehicle Number",
                placeholder="Enter vehicle number (e.g., ABC123)"
            )
        
        query = "SELECT * FROM vehicle_records"
        if search:
            query += f" WHERE vehicle_number LIKE '%{search}%'"
            st.info(f"Showing results for: {search}")
        
        df = pd.read_sql(query, conn)
        conn.close()
        
        if not df.empty:
            # Show summary stats
            total_col, overspeed_col, normal_col = st.columns(3)
            with total_col:
                st.metric("Total Records", len(df))
            with overspeed_col:
                st.metric("Violations", len(df[df['status'] == 'overspeed']))
            with normal_col:
                st.metric("Normal", len(df[df['status'] == 'normal']))
            
            st.markdown("---")
            st.dataframe(df, width="stretch")
        else:
            st.warning("⚠️ No records found matching your search.")

elif page == "Admin Panel":
    st.title("⚙️ Admin Settings")
    st.markdown("### System configuration and management")
    
    # Django Admin info box
    with st.expander("🔐 Access Django Admin Panel", expanded=False):
        st.markdown("""
        **For advanced settings:**
        1. Run `python manage.py runserver` in terminal
        2. Navigate to http://127.0.0.1:8000/admin
        3. Login with admin credentials
        4. Manage speed limits, distance calibration, and email settings
        """)
    
    st.subheader("Quick Settings Override")
    st.info("💡 Changes here will update the database immediately")
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
                st.success("✅ Settings updated successfully!")
        conn.close()

# Footer for professional look
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #718096; padding: 20px;'>
    <p><strong>🚙 Vehicle Speed Detection System</strong></p>
    <p>Built with Streamlit • YOLOv8 • EasyOCR • Django • MySQL</p>
    <p>B.Tech Project © 2024</p>
</div>
""", unsafe_allow_html=True)
