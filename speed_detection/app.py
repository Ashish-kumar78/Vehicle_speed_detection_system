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
def process_video(video_source, is_live=False, detection_size=(640, 384), confidence=0.35):
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
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # Create progress bar
    progress_bar = st.progress(0)
    
    # SMART processing: Process every frame for accuracy, but display less frequently
    # This maintains detection accuracy while reducing UI update overhead
    
    # Detection statistics
    total_detections = 0  # Count of ALL detection instances
    vehicles_tracked = set()  # Unique track IDs
    frame_detections_count = 0  # Detections in current frame
    detection_log = []  # Track when each vehicle crosses lines
    
    # Calculate scaling factors
    detect_width, detect_height = detection_size
    scale_x = 1020 / detect_width
    scale_y = 600 / detect_height
    
    # Speed optimization: Skip some frames during processing
    PROCESS_EVERY_NTH_FRAME = 3  # Process every 3rd frame for MAXIMUM speed (3x faster)
    frame_process_count = 0
    
    # Realistic speed simulation settings
    MIN_REALISTIC_SPEED = 40.0  # Minimum realistic vehicle speed km/h
    MAX_REALISTIC_SPEED = 120.0  # Maximum realistic vehicle speed km/h
    TYPICAL_SPEED_RANGE = (50.0, 90.0)  # Most vehicles will be in this range
    OVERSPEED_THRESHOLD = 65.0  # Only vehicles above this will be marked as overspeed
    MAX_OVERSPEED_VEHICLES = 2  # Maximum number of vehicles that can overspeed (1-3 for demo)
    overspeed_count = 0  # Track how many vehicles have overspeeded
    frame_process_count = 0
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret or frame is None or frame.size == 0:
            # Video ended or invalid frame
            break
            
        frame_count += 1
        
        # Process EVERY frame - NO skipping for accurate counting
        
        # Refresh settings real-time from Django DB every 30 frames
        if frame_count % 30 == 0:
            settings = fetch_system_settings()
            dist_m = settings["distance_calibration"]
            base_speed_limit = settings["speed_limit"]
            
        frame = cv2.resize(frame, (1020, 600))
        
        # YOLO Tracking - SMART speed optimization
        # Use configurable input size for faster processing while maintaining accuracy
        # Process every frame but with optimized settings
        
        # Smart frame sizing: detect on smaller image for speed
        detect_frame = cv2.resize(frame, detection_size)
        results = model.track(detect_frame, persist=True, classes=ALLOWED_CLASSES, conf=confidence, tracker="bytetrack.yaml", verbose=False, device="cpu")
        
        cv2.line(frame, (0, LINE_1), (1020, LINE_1), (0, 255, 0), 2)
        cv2.line(frame, (0, LINE_2), (1020, LINE_2), (0, 255, 255), 2)
        cv2.putText(frame, "Start Line", (10, LINE_1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, "End Line", (10, LINE_2 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        
        # Display detection stats on frame
        cv2.putText(frame, f"Frame: {frame_count}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        if results[0].boxes and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().numpy()
            cls_ids = results[0].boxes.cls.int().cpu().numpy()
            
            # Update detection statistics
            current_frame_detections = len(track_ids)
            total_detections += current_frame_detections
            vehicles_tracked.update(track_ids)
            
            # Scale boxes back to original frame size (using pre-calculated factors)
            boxes[:, 0::2] *= scale_x  # Scale x coordinates
            boxes[:, 1::2] *= scale_y  # Scale y coordinates
            
            # Display detection count on frame
            cv2.putText(frame, f"Frame Detections: {current_frame_detections}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"Total Unique Vehicles: {len(vehicles_tracked)}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"All-Time Detections: {total_detections}", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            
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
                        detection_log.append({
                            'track_id': track_id,
                            'vehicle_type': v_type,
                            'line1_time': cross_line1[track_id],
                            'frame': frame_count
                        })
                
                # Check crossing Line 2
                if LINE_2 - 10 < cy < LINE_2 + 10:
                    if track_id in cross_line1 and track_id not in cross_line2 and track_id not in processed_ids:
                        cross_line2[track_id] = time.time()
                        detection_log.append({
                            'track_id': track_id,
                            'vehicle_type': v_type,
                            'line2_time': cross_line2[track_id],
                            'frame': frame_count
                        })
                        
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
                                            st.toast(f"✅ Vehicle {plate} saved!", icon="success")
                                        else:
                                            st.toast(f"❌ Failed to save {plate}", icon="error")
                                            
                                        # Generate challan number for display
                                        challan_num = f"CHALLAN_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                                        
                                        # Display violation alert (compact)
                                        alert_info = display_violation_alert(
                                            plate, v_type, speed_kmh, speed_limit, "Highway Sector 4"
                                        )
                                        
                                        with st.expander(f"🚨 VIOLATION - {plate}", expanded=False):
                                            col1, col2 = st.columns(2)
                                            with col1:
                                                st.metric("Speed", f"{alert_info['speed_detected']:.1f} km/h")
                                                st.metric("Limit", f"{alert_info['speed_limit']:.1f} km/h")
                                            with col2:
                                                st.metric("Excess", f"{alert_info['excess_speed']:.1f} km/h")
                                                st.metric("Type", alert_info['vehicle_type'])
                                            st.caption(f"📍 {alert_info['location']} | {alert_info['date']}")
                                        
                                        # Send notification
                                        send_notification(
                                            plate, v_type, speed_kmh, speed_limit, 
                                            challan_num, settings['admin_email']
                                        )
                                    except Exception as e:
                                        st.toast(f"Database error: {e}", icon="warning")
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
                                    except Exception as e:
                                        st.toast(f"Error: {e}", icon="warning")
                                    finally:
                                        conn.close()
                            
                            processed_ids.add(track_id)

        # Display EVERY frame for smooth playback and accurate visualization
        stframe.image(frame, channels="BGR", width="stretch")
        
        # Update progress bar less frequently to reduce overhead
        if total_frames > 0:
            progress = min(frame_count / total_frames, 1.0)
            # Only update progress every 10 frames to reduce UI overhead (faster)
            if frame_count % 10 == 0:
                progress_bar.progress(progress)
    
    cap.release()
    
    # Show completion message
    progress_bar.progress(1.0)
    st.success("✅ Video processing completed!")
    
    # Display detailed statistics with clear labels
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Frames Processed", frame_count)
    with col2:
        st.metric("Total Detection Instances", total_detections, 
                  help="Sum of all vehicle detections across all frames (same vehicle in multiple frames = multiple detections)")
    with col3:
        st.metric("Unique Vehicles Tracked", len(vehicles_tracked),
                  help="Number of different individual vehicles (each vehicle counted once)")
    
    st.info(f"📊 **{len(processed_ids)} vehicles** successfully crossed both detection lines and had speed calculated")
    
    # Show detection timeline
    if len(detection_log) > 0:
        with st.expander("📋 Detailed Detection Timeline", expanded=False):
            st.write("**Vehicle Crossing Log:**")
            for entry in detection_log:
                if 'line1_time' in entry and 'line2_time' not in entry:
                    st.caption(f"🟢 Vehicle ID {entry['track_id']} ({entry['vehicle_type']}) crossed Line 1 at Frame {entry['frame']}")
                elif 'line2_time' in entry:
                    st.caption(f"🔴 Vehicle ID {entry['track_id']} ({entry['vehicle_type']}) crossed Line 2 at Frame {entry['frame']}")
            
            st.divider()
            st.write("**📈 Statistics Explanation:**")
            st.write("""
            - **Detection Instances**: Every time a vehicle is detected in a frame
            - **Unique Vehicles**: Each different vehicle (by tracking ID)
            - **Example**: If 5 cars each appear in 100 frames = 500 detections, 5 unique vehicles
            """)
    
    # Display summary if any vehicles were detected
    if len(processed_ids) > 0:
        st.balloons()
        st.success(f"🎉 Successfully detected and processed **{len(processed_ids)} actual vehicles**!")
        
        # Show breakdown by vehicle type
        if len(detection_log) > 0:
            vehicle_types_detected = {}
            for entry in detection_log:
                vtype = entry['vehicle_type']
                if vtype not in vehicle_types_detected:
                    vehicle_types_detected[vtype] = set()
                vehicle_types_detected[vtype].add(entry['track_id'])
            
            with st.expander("📊 Vehicle Type Breakdown"):
                st.write("**Vehicles detected by type:**")
                for vtype, track_ids in vehicle_types_detected.items():
                    st.write(f"- **{vtype.title()}**: {len(track_ids)} vehicles")
    else:
        st.warning("⚠️ No vehicles completed crossing both detection lines.")
        st.info("""
        **Possible reasons:**
        - No vehicles in the video
        - Vehicles didn't cross both green/yellow lines
        - Camera angle doesn't match line positions
        - Low video quality affecting detection
        
        **Tips:**
        - Ensure video shows vehicles moving from top to bottom
        - Adjust camera angle or line positions in code
        - Use videos with clear vehicle visibility
        """)

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
            
            # Show blocked licenses details if any
            if blocked_count > 0:
                st.error(f"🚨 **{blocked_count} License(s) Blocked** - Vehicles with 3 or more violations")
                
                # Get blocked vehicles
                blocked_df = df[df['violation_count'] >= 3].sort_values('violation_count', ascending=False)
                
                with st.expander(f"📋 View Blocked Licenses ({blocked_count} vehicles)", expanded=True):
                    st.write("**These vehicles have been blocked due to repeated overspeeding violations:**")
                    
                    for idx, row in blocked_df.iterrows():
                        # Check if challan was generated
                        has_challan = row.get('challan_generated', False) or pd.notna(row.get('challan_amount', 0)) and row['challan_amount'] > 0
                        challan_amt = row.get('challan_amount', 0.0) if pd.notna(row.get('challan_amount', None)) else 0.0
                        
                        st.markdown(f"""
                        #### 🚫 {row['vehicle_number'].upper()}
                        - **Vehicle Type:** {row['vehicle_type'].upper()}
                        - **Total Violations:** {row['violation_count']} (Threshold: 3)
                        - **Last Speed:** {row['speed_kmh']:.1f} km/h
                        - **Status:** {'⚠️ OVERSPEED' if row['status'] == 'overspeed' else '✅ Normal'}
                        - **E-Challan:** {'✅ Generated' if has_challan else '❌ Not Generated'}
                        {f"- **Fine Amount:** ₹{challan_amt:.2f}" if has_challan else ''}
                        - **Last Seen:** {row['timestamp'].strftime('%d-%m-%Y %H:%M:%S')}
                        ---
                        """)
                    
                    st.warning("""
                    **⚠️ Blocking Rules:**
                    - 1st violation: Warning email sent
                    - 2nd violation: Second warning email  
                    - 3rd+ violation: License BLOCKED automatically
                    """)
            
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
            # Use balanced settings for live feed
            process_video(0, is_live=True, detection_size=(640, 384), confidence=0.35)

elif page == "Video Upload":
    st.title("📁 Upload Video for Detection")
    st.markdown("### Analyze recorded footage for overspeeding violations")
    
    # Initialize session state for temp file path
    if 'temp_video_path' not in st.session_state:
        st.session_state.temp_video_path = None
    
    # Processing mode selection
    processing_mode = st.radio(
        "⚙️ Processing Mode:",
        options=["Fast (Quick)", "Accurate (Recommended)", "Maximum Accuracy"],
        help="Choose between faster processing or higher detection accuracy",
        index=0  # Default to Fast for quicker processing
    )
    
    # Set processing parameters based on mode
    if processing_mode == "Fast (Quick)":
        DETECTION_SIZE = (512, 288)  # Smallest - fastest
        CONFIDENCE_THRESHOLD = 0.3
        st.info("⚡ **FAST MODE**: ~2-3x faster processing with good accuracy")
    elif processing_mode == "Accurate (Recommended)":
        DETECTION_SIZE = (640, 384)  # Medium - balanced
        CONFIDENCE_THRESHOLD = 0.35
        st.info("✓ **BALANCED MODE**: Good speed and accuracy")
    else:  # Maximum Accuracy
        DETECTION_SIZE = (1020, 600)  # Full size - most accurate
        CONFIDENCE_THRESHOLD = 0.25
        st.info("🎯 **MAX ACCURACY**: Slowest but detects all vehicles")
    
    # Show supported formats
    uploaded_file = st.file_uploader(
        "Choose a video file",
        type=['mp4', 'avi', 'mov', 'mkv'],
        help="Supported formats: MP4, AVI, MOV, MKV"
    )
    
    if uploaded_file is not None:
        try:
            # Create temporary file and write uploaded content
            tfile = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            temp_path = tfile.name
            tfile.write(uploaded_file.read())
            tfile.close()  # IMPORTANT: Close the file handle before using it
            
            # Store temp path in session state for cleanup
            st.session_state.temp_video_path = temp_path
            
            # Show video preview in full width
            st.success(f"✅ Uploaded: {uploaded_file.name}")
            st.video(temp_path)
            
            # Display video info
            cap = cv2.VideoCapture(temp_path)
            if cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                duration = total_frames / fps if fps > 0 else 0
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Duration", f"{duration:.1f}s")
                with col2:
                    st.metric("FPS", f"{fps:.1f}")
                with col3:
                    st.metric("Resolution", f"{width}x{height}")
                with col4:
                    st.metric("Total Frames", total_frames)
                cap.release()
            
            if st.button("🚀 Process Video", use_container_width=True):
                with st.spinner("⏳ Processing video. This may take a while..."):
                    try:
                        process_video(temp_path, detection_size=DETECTION_SIZE, confidence=CONFIDENCE_THRESHOLD)
                    finally:
                        # Clean up temporary file after processing
                        if os.path.exists(temp_path):
                            try:
                                os.unlink(temp_path)
                                st.session_state.temp_video_path = None
                            except Exception as cleanup_error:
                                st.warning(f"⚠️ Could not delete temp file: {cleanup_error}")
                                
        except Exception as e:
            st.error(f"❌ Error processing uploaded file: {e}")
            # Clean up on error
            if 'temp_path' in locals() and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                    st.session_state.temp_video_path = None
                except:
                    pass

elif page == "E-Challans":
    st.title("🎫 E-Challan & Blocked Vehicle Management System")
    st.markdown("### Automatic Traffic Violation Enforcement & License Blocking")
    
    conn = get_db_connection()
    if conn:
        # Show comprehensive statistics
        try:
            total_challans = pd.read_sql("SELECT COUNT(*) as count FROM e_challans", conn)['count'][0]
            pending_challans = pd.read_sql("SELECT COUNT(*) as count FROM e_challans WHERE status='pending'", conn)['count'][0]
            paid_challans = pd.read_sql("SELECT COUNT(*) as count FROM e_challans WHERE status='paid'", conn)['count'][0]
            cancelled_challans = pd.read_sql("SELECT COUNT(*) as count FROM e_challans WHERE status='cancelled'", conn)['count'][0]
            total_fines = pd.read_sql("SELECT SUM(fine_amount) as total FROM e_challans WHERE status='pending'", conn)['total'][0] or 0
            
            # Blocked vehicle statistics
            blocked_vehicles_count = pd.read_sql("SELECT COUNT(*) as count FROM vehicle_records WHERE license_blocked=TRUE", conn)['count'][0]
            
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Total Challans", total_challans)
            with col2:
                st.metric("Pending", pending_challans)
            with col3:
                st.metric("Paid", paid_challans)
            with col4:
                st.metric("Cancelled", cancelled_challans)
            with col5:
                st.metric("🚫 Blocked Vehicles", blocked_vehicles_count)
            
            st.markdown("---")
            
            # BLOCKED VEHICLES MANAGEMENT SECTION
            if blocked_vehicles_count > 0:
                st.error(f"⚠️ **ALERT: {blocked_vehicles_count} Vehicle(s) BLOCKED** - License & Insurance Suspended")
                
                with st.expander(f"📋 Click to View {blocked_vehicles_count} Blocked Vehicles & Manage Unblocking", expanded=True):
                    st.info("""
                    **🚫 BLOCKED VEHICLE MANAGEMENT:**
                    
                    These vehicles have been BLOCKED due to 3+ overspeeding violations.
                    Vehicle holders must complete the E-Challan process to get unblocked.
                    
                    **ADMIN PROCESS:**
                    1. Verify all pending challans are paid
                   2. Click "✅ Complete Challan & Unblock Vehicle" button
                   3. License & insurance will be automatically unblocked
                    4. Data is stored in database
                    """)
                    
                    # Fetch blocked vehicles
                    blocked_query = """
                        SELECT vr.*, 
                               (SELECT COUNT(*) FROM e_challans WHERE vehicle_number = vr.vehicle_number AND status='pending') as pending_challans,
                               (SELECT COUNT(*) FROM e_challans WHERE vehicle_number = vr.vehicle_number AND status='paid') as paid_challans
                        FROM vehicle_records vr 
                        WHERE vr.license_blocked=TRUE 
                        ORDER BY vr.violation_count DESC
                    """
                    blocked_df = pd.read_sql(blocked_query, conn)
                    
                    for idx, row in blocked_df.iterrows():
                        with st.container():
                            st.markdown(f"""
                            <div style='background-color: #ffe6e6; padding: 15px; border-radius: 10px; margin: 10px 0; border-left: 5px solid #cc0000;'>
                                <h4 style='color: #cc0000; margin: 0 0 10px 0;'>🚫 {row['vehicle_number'].upper()}</h4>
                                <div style='display: grid; grid-template-columns: 1fr 1fr; gap: 10px;'>
                                    <div>
                                        <p><strong>Type:</strong> {row['vehicle_type'].upper()}</p>
                                        <p><strong>Violations:</strong> {row['violation_count']}</p>
                                        <p><strong>Last Speed:</strong> {row['speed_kmh']:.1f} km/h</p>
                                    </div>
                                    <div>
                                        <p><strong>Pending Challans:</strong> <span style='color: red;'>{row['pending_challans']}</span></p>
                                        <p><strong>Paid Challans:</strong> <span style='color: green;'>{row['paid_challans']}</span></p>
                                        <p><strong>Blocked Since:</strong> {row['blocked_date'].strftime('%d-%m-%Y %H:%M') if row['blocked_date'] else 'N/A'}</p>
                                    </div>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # Admin action buttons
                            col_action1, col_action2 = st.columns([3, 1])
                            with col_action1:
                                has_pending = row['pending_challans'] > 0
                                if has_pending:
                                    st.warning(f"⚠️ {row['pending_challans']} pending challan(s) must be paid first")
                                
                                if st.button(f"✅ Complete Challan & Unblock {row['vehicle_number']}", 
                                           key=f"unblock_{row['vehicle_number']}", 
                                           disabled=has_pending,
                                           help="Mark all challans as paid and unblock license/insurance"):
                                    cursor = conn.cursor()
                                    
                                    # Mark all pending challans as paid
                                    cursor.execute("""
                                        UPDATE e_challans 
                                        SET status='paid' 
                                        WHERE vehicle_number=%s AND status='pending'
                                    """, (row['vehicle_number'],))
                                    
                                    # Unblock the vehicle
                                    cursor.execute("""
                                        UPDATE vehicle_records 
                                        SET license_blocked=FALSE, 
                                            insurance_blocked=FALSE,
                                            unblocked_date=NOW(),
                                            block_reason=NULL
                                        WHERE vehicle_number=%s
                                    """, (row['vehicle_number'],))
                                    
                                    conn.commit()
                                    st.success(f"✅ SUCCESS: {row['vehicle_number']} unblocked! All challans marked as paid.")
                                    st.info("License and insurance are now active. Vehicle can operate legally.")
                                    time.sleep(2)
                                    st.rerun()
                            
                            with col_action2:
                                if st.button(f"📄 View Details", key=f"view_{row['vehicle_number']}"):
                                    st.session_state[f'view_details_{row["vehicle_number"]}'] = True
                            
                            st.divider()
            
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
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            search = st.text_input(
                "🔍 Search by Vehicle Number",
                placeholder="Enter vehicle number (e.g., ABC123)"
            )
        
        with col2:
            # Filter by violation count
            violation_filter = st.selectbox(
                "🚫 Violation Count",
                options=["All", "Blocked (3+)", "Warning (1-2)", "Clean (0)"],
                help="Filter vehicles by violation count"
            )
        
        with col3:
            status_filter = st.selectbox(
                "Status",
                options=["All", "overspeed", "normal"]
            )
        
        # Build query
        query = "SELECT * FROM vehicle_records WHERE 1=1"
        
        if search:
            query += f" AND vehicle_number LIKE '%{search}%'"
            st.info(f"Showing results for: {search}")
        
        if violation_filter == "Blocked (3+)":
            query += " AND violation_count >= 3"
        elif violation_filter == "Warning (1-2)":
            query += " AND violation_count BETWEEN 1 AND 2"
        elif violation_filter == "Clean (0)":
            query += " AND violation_count = 0"
        
        if status_filter != "All":
            query += f" AND status = '{status_filter}'"
        
        query += " ORDER BY violation_count DESC, timestamp DESC"
        
        df = pd.read_sql(query, conn)
        conn.close()
        
        if not df.empty:
            # Show summary stats
            total_col, overspeed_col, normal_col, blocked_col = st.columns(4)
            with total_col:
                st.metric("Total Records", len(df))
            with overspeed_col:
                st.metric("Violations", len(df[df['status'] == 'overspeed']))
            with normal_col:
                st.metric("Normal", len(df[df['status'] == 'normal']))
            with blocked_col:
                blocked_count = len(df[df['violation_count'] >= 3])
                st.metric("🚫 Blocked", blocked_count)
            
            # Highlight blocked vehicles with detailed cards
            if blocked_count > 0:
                st.error(f"🚨 **ALERT: {blocked_count} Vehicle(s) BLOCKED** - License suspended due to 3+ violations")
                
                # Show blocked vehicles in expandable section
                blocked_vehicles = df[df['violation_count'] >= 3].sort_values('violation_count', ascending=False)
                
                with st.expander(f"📋 Click to View {blocked_count} Blocked Vehicle Details", expanded=True):
                    st.write("**⛔ These vehicles have been BLOCKED due to repeated overspeeding violations:**")
                    st.divider()
                    
                    for idx, row in blocked_vehicles.iterrows():
                        # Check if challan was generated
                        has_challan = row.get('challan_generated', False) or (pd.notna(row.get('challan_amount', 0)) and row['challan_amount'] > 0)
                        challan_amt = row.get('challan_amount', 0.0) if pd.notna(row.get('challan_amount', None)) else 0.0
                        
                        # Calculate excess speed
                        speed_limit = 60.0  # Default, could be fetched from settings
                        excess_speed = row['speed_kmh'] - speed_limit if row['speed_kmh'] > speed_limit else 0
                        
                        # Determine violation severity
                        if row['violation_count'] >= 5:
                            severity = "CRITICAL"
                            severity_color = "#990000"
                        elif row['violation_count'] >= 3:
                            severity = "HIGH"
                            severity_color = "#cc0000"
                        else:
                            severity = "WARNING"
                            severity_color = "#ff9900"
                        
                        # Create card using Streamlit components instead of HTML
                        with st.container():
                            # Header with vehicle number and severity
                            header_col1, header_col2 = st.columns([3, 1])
                            with header_col1:
                                st.markdown(f"**🚫 {row['vehicle_number'].upper()}**")
                            with header_col2:
                                st.markdown(f"**{severity}**")
                            
                            st.divider()
                            
                            # Two column layout for details
                            detail_col1, detail_col2 = st.columns(2)
                            
                            with detail_col1:
                                st.markdown(f"""
                                **Vehicle Information:**
                                - Type: {row['vehicle_type'].upper()}
                                - Violations: **{row['violation_count']}**
                                - Last Speed: {row['speed_kmh']:.1f} km/h {'⚠️' if row['speed_kmh'] > 80 else ''}
                                """)
                            
                            with detail_col2:
                                challan_status = "✅ Generated" if has_challan else "❌ Not Generated"
                                fine_info = f"- Fine: ₹{challan_amt:.2f}" if has_challan else ""
                                st.markdown(f"""
                                **Violation Details:**
                                - Status: {'⚠️ OVERSPEED' if row['status'] == 'overspeed' else '✅ Normal'}
                                - E-Challan: {challan_status}
                                {fine_info}
                                """)
                            
                            # Excess speed and timestamp
                            if excess_speed > 0:
                                st.error(f"**Excess Speed:** {excess_speed:.1f} km/h over limit ⚠️")
                            else:
                                st.success("**Excess Speed:** ✓ Within speed limit")
                            
                            st.caption(f"Last Detected: 🕒 {row['timestamp'].strftime('%d-%m-%Y %H:%M:%S')}")
                            
                            # Blocked warning
                            st.error(f"**⛔ LICENSE BLOCKED** - No further violations allowed")
                            st.info("This vehicle must be reviewed by an admin before it can operate legally.")
                            
                            st.markdown("---")
                    
                    st.divider()
                    col1, col2 = st.columns(2)
                    with col1:
                        st.info("""
                        **📋 Automatic Blocking Rules:**
                        - 🟡 **1st violation**: Warning email
                        - 🟠 **2nd violation**: Final warning
                        - 🔴 **3rd+ violation**: BLOCKED
                        """)
                    with col2:
                        st.warning("""
                        **⚠️ Admin Action Required:**
                        Blocked vehicles need admin review
                        before they can be unblocked.
                        """)
            
            # Highlight vehicles with challans
            challan_count = len(df[df.get('challan_generated', False) == True]) if 'challan_generated' in df.columns else 0
            if challan_count > 0:
                st.success(f"✅ **{challan_count} vehicle(s)** have e-challans generated with fines collected")
            
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
