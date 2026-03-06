# Vehicle Speed Detection System 🚔📸
A complete B.Tech project integrating OpenCV, YOLOv8, Streamlit, Django, and MySQL to monitor overspeeding vehicles. 

## Features ✅
1. **Dual Detection Modes**: Run inference on Live Webcam or Uploaded Video.
2. **Speed Calculation**: Tracks cars using bounding boxes and calculates speed based on distance and frames.
3. **Database Logging**: MySQL Database `vehicle_monitoring` stores `vehicle_records`. 
4. **Django Admin Panel**: Used to update speed limits and view records securely at `/admin`.
5. **License Plate Capture**: Uses EasyOCR to scrape the number plate image if a vehicle violates the speed limit.
6. **Automatic Emailing**: Send SMTP emails to `admin@gmail.com` on offense.
7. **Responsive Dashboard**: Beautiful Streamlit interface.

### Project Structure 📂
```
vehicle_speed_system/
│
├── speed_detection/          # Streamlit Component
│   ├── app.py              # Main OpenCV + Streamlit Loop
│   └── requirements.txt    # Pip installations required
│
├── vehicle_monitoring/      # Django Component
│   ├── manage.py
│   ├── vehicle_monitoring/ # Settings
│   └── detection/          # App with Models and Admin Panel
│
└── database.sql           # MySQL Queries
```

## Step-by-Step Installation 🚀

### Step 1: Install MySQL Database
1. Download [XAMPP](https://www.apachefriends.org/index.html) or [MySQL Server](https://dev.mysql.com/downloads/installer/).
2. Start the **MySQL Server**.
3. Import the `database.sql` to create the schema:
   - Go to `http://localhost/phpmyadmin`
   - Click **Import** -> Select `database.sql` -> Go.

### Step 2: Set up Python Environment
Open a terminal inside the project folder:
```powershell
python -m venv venv
.\venv\Scripts\activate
cd vehicle_speed_system\speed_detection
pip install -r requirements.txt
```

### Step 3: Run the Django Backend
This acts as the backend control and admin panel.
```powershell
cd ..\vehicle_monitoring
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser  # Create an admin account
python manage.py runserver
```
Visit `http://127.0.0.1:8000/admin` to set your initial Speed Limit and Distance Calibration!

### Step 4: Run the Streamlit Dashboard
Open a **new** terminal window (keep Django running):
```powershell
.\venv\Scripts\activate
cd vehicle_speed_system\speed_detection
streamlit run app.py
```
This will open the shiny dashboard at `http://localhost:8501`. Have fun testing with your videos!

---
*Note for Email Testing*: Open `app.py` and modify `send_email_alert` logic to include your actual Gmail sender account + Google App Passwords for full automatic email firing.
