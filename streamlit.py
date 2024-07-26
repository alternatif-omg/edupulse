import streamlit as st
import firebase_admin
import subprocess
from firebase_admin import credentials, db, storage
from PIL import Image
import io
from datetime import datetime
from streamlit_calendar import calendar
import os
import signal
import sys
import platform
import psutil
import json
from plyer import notification
import time
import pandas as pd
import requests
import random


process = None

# Load custom CSS


def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# Set page configuration
st.set_page_config(
    page_title="Aplikasi Deteksi Pose dan Interaksi Siswa",
    page_icon=":school:",
    layout="wide"
)

# Check if the Firebase app is already initialized


# import streamlit as st
# import firebase_admin
# from firebase_admin import credentials

# initializing credentials
service_account_key = {
    "type": st.secrets["type"],
    "project_id": st.secrets["project_id"],
    "private_key_id": st.secrets["private_key_id"],
    "private_key": st.secrets["private_key"],
    "client_email": st.secrets["client_email"],
    "client_id": st.secrets["client_id"],
    "auth_uri": st.secrets["auth_uri"],
    "token_uri": st.secrets["token_uri"],
    "auth_provider_x509_cert_url": st.secrets["auth_provider_x509_cert_url"],
    "client_x509_cert_url": st.secrets["client_x509_cert_url"],
    "universe_domain": st.secrets["universe_domain"]
}
# print(service_account_key)

if not firebase_admin._apps:
    cred = credentials.Certificate(service_account_key)
    firebase_admin.initialize_app(cred, {
        'databaseURL': "https://faceattendance-a740a-default-rtdb.firebaseio.com/",
        'storageBucket': "faceattendance-a740a.appspot.com"
    })

# load directly
#cred = credentials.Certificate(service_account_key)
#firebase_admin.initialize_app(cred, {
#        'databaseURL': "https://faceattendance-a740a-default-rtdb.firebaseio.com/",
#        'storageBucket': "faceattendance-a740a.appspot.com"
#})

# if not firebase_admin._apps:
#     cred = credentials.Certificate(service_acccount_key)
#     firebase_admin.initialize_app(cred, {
#         'databaseURL': "https://faceattendance-a740a-default-rtdb.firebaseio.com/",
#         'storageBucket': "faceattendance-a740a.appspot.com"
#     })

load_css("styles.css")

# References
students_ref = db.reference('Students')
teachers_ref = db.reference('Teachers')
bucket = storage.bucket()

# Function to save image to Firebase Storage


def save_image(image, image_name):
    img = Image.open(image)
    img = img.resize((216, 216))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    blob = bucket.blob(f"Images/{image_name}.png")
    blob.upload_from_file(buffer, content_type="image/png")
    return blob.public_url

# Function to start face detection


def run_face_detection():
    global process
    if platform.system() == "Windows":
        process = subprocess.Popen(
            ["cmd", "/c", "start", "/MIN", "cmd", "/c",
                sys.executable, "face_detection.py"],
            creationflags=subprocess.CREATE_NO_WINDOW,
            shell=True
        )
    else:  # For Unix-based systems (Linux, macOS)
        process = subprocess.Popen(
            [sys.executable, "face_detection.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid
        )
    st.session_state.running = True


# Function to stop face detection
def stop_face_detection():
    global process
    if process:
        if platform.system() == "Windows":
            import ctypes
            # Find the cmd.exe process running face_detection.py
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if proc.info['name'] == 'cmd.exe' and 'face_detection.py' in ' '.join(proc.info['cmdline']):
                    # Send Ctrl+C to cmd.exe process
                    kernel32 = ctypes.windll.kernel32
                    kernel32.GenerateConsoleCtrlEvent(0, proc.info['pid'])
                    break
        else:  # For Unix-based systems
            # Send SIGINT (equivalent to Ctrl+C) to the process group
            os.killpg(os.getpgid(process.pid), signal.SIGINT)

        # Wait for the process to finish
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # If still not finished after 5 seconds, forcefully terminate
            if platform.system() == "Windows":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)])
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)

        process = None
    st.session_state.running = False


# Fungsi untuk mengambil data absen dari Firebase
def get_attendance_data():
    ref = db.reference('Attendance')
    data = ref.get()
    return data

# Fungsi untuk memproses data absen
def process_attendance_data(data):
    # Daftar untuk menampung data yang valid
    processed_data = []
    
    # Ambil tanggal hari ini
    today = datetime.now().date()
    
    for student_id, records in data.items():
        for record_id, record in records.items():
            # Periksa apakah kunci penting ada
            if 'name' in record and 'status' in record and 'timestamp' in record:
                try:
                    # Parsing timestamp
                    record_date = datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M:%S').date()
                    
                    # Tambahkan data yang valid dan cocok dengan tanggal hari ini
                    if record_date == today:
                        processed_data.append({
                        'Name': record['name'],
                        'Status': record['status'],
                        'Time': record['timestamp']
                        })
                except ValueError:
                    # Jika format timestamp tidak valid, lewati record ini
                    continue
    
    return processed_data

def convert_df_to_csv(df):
    # Convert DataFrame to CSV format
    csv = df.to_csv(index=False)
    return csv
    
    

def get_attendance_dates():
    # Ambil data absensi dari Firebase
    ref = db.reference('Attendance')
    attendance_data = ref.get()

    # Proses data untuk mendapatkan tanggal-tanggal absensi
    attendance_dates = set()
    for student_id, records in attendance_data.items():
        for record_id, record in records.items():
            date = datetime.strptime(record['timestamp'].split()[
                                     0], "%Y-%m-%d").date()
            attendance_dates.add(date.isoformat())

    return list(attendance_dates)



def get_sorted_student_data():
    ref = db.reference('interaksi')
    data = ref.get()

    if data:
        # Mengubah data menjadi list of dictionaries
        students = [{"Name": name, "points": info["points"], "last_updated": info["last_updated"]}
                    for name, info in data.items()]

        # Mengurutkan berdasarkan poin (dari terbesar)
        students_sorted = sorted(
            students, key=lambda x: x["points"], reverse=True)

        return students_sorted
    else:
        return []


def login(email, password, level):
    ref = teachers_ref if level == "Teacher" else students_ref
    users = ref.get()
    for user_id, user_data in users.items():
        if user_data['email'] == email and user_data['password'] == password:
            st.session_state['logged_in'] = True
            st.session_state['user'] = user_data
            st.session_state['level'] = level
            return True
    st.error("Invalid email or password")
    return False

# Register function


def register(id, class_name, email, name, password, image, level):
    ref = db.reference('Teachers') if level == "Teacher" else db.reference('Students')
    new_user = {
        "email": email,
        "name": name,
        "password": password
    }
    if level == "Teacher":
        new_user["subject"] = class_name
    else:
        new_user["class"] = class_name
        new_user["image_path"] = f"Images/{id}.png"

    ref.child(id).set(new_user)
    save_image(image, id)
    st.success(f"User {name} registered successfully.")

# Function to show the dashboard


def load_posture_status():
    if os.path.exists('posture_status.json'):
        try:
            with open('posture_status.json', 'r') as json_file:
                data = json_file.read().strip()
                if not data:  # Handle empty file
                    return None
                return json.loads(data)
        except json.JSONDecodeError:
            st.error(
                "Error reading posture status data. The file may be corrupted or empty.")
            return None
    return None


def display_notification(status, timestamp):
    if status == "slouching":
        notification.notify(
            title="Posture Alert",
            message=f"Student detected with poor posture (slouching) at {timestamp}",
            app_name="Posture Monitoring",

        )


def show_dashboard():
    st.title("📚 Aplikasi Deteksi Pose dan Interaksi Siswa")

    # Sidebar for student/teacher biodata
    sidebar_style = """
        <style>
        .sidebar .sidebar-content {
            background-color: #E4003A;
            color: white;
        }
        </style>
    """
    st.markdown(sidebar_style, unsafe_allow_html=True)

    with st.sidebar:
        st.header("📋 Biodata Pengguna")

        user_data = st.session_state['user']
        user_level = st.session_state['level']

        user_id = None
        if user_level == 'Student':
            students = students_ref.order_by_child(
                'name').equal_to(user_data['name']).get()
            if students:
                user_id = list(students.keys())[0]
        else:
            teachers = teachers_ref.order_by_child(
                'name').equal_to(user_data['name']).get()
            if teachers:
                user_id = list(teachers.keys())[0]

        if user_id:
            st.write(f"**ID:** {user_id}")
        else:
            st.warning("User ID not found.")

        if user_id:
            profile_picture_url = f"https://firebasestorage.googleapis.com/v0/b/faceattendance-a740a.appspot.com/o/Images%2F{user_id}.png?alt=media&token=70be87d6-c8fe-4e7f-a275-2eb728e4e2e8"
            st.image(profile_picture_url, width=180)
        else:
            st.warning("Profile picture not found.")

        if user_level == 'Student':
            st.markdown(f"""
            **Nama:** {user_data['name']}  
            **Email:** {user_data['email']}  
            **Class:** {user_data.get('class', 'N/A')}
            """)
        else:
            st.markdown(f"""
            **Nama:** {user_data['name']}  
            **Email:** {user_data['email']}  
            **Subject:** {user_data.get('subject', 'N/A')}
            """)

    

# Dapatkan tanggal-tanggal absensi
    attendance_dates = get_attendance_dates()


# Buat events untuk kalender
    events = [{"start": date, "display": "background",
               "backgroundColor": "#28a745"} for date in attendance_dates]

# Buat konfigurasi kalender
    calendar_options = {
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek,timeGridDay",
        },
        "initialView": "dayGridMonth",
        "events": events
    }

# Tampilkan kalender
   

# Tampilkan tanggal yang dipilih (opsional)
    # Conditional display based on user level
    if user_level == 'Student':
        st.subheader("Absensi")
        selected_dates = calendar(events=events, options=calendar_options)

        # Get attendance dates
        attendance_dates = get_attendance_dates()

        # Create events for calendar
        events = [{"start": date, "display": "background",
                   "backgroundColor": "#28a745"} for date in attendance_dates]

        # Calendar configuration
        calendar_options = {
            "headerToolbar": {
                "left": "prev,next today",
                "center": "title",
                "right": "dayGridMonth,timeGridWeek,timeGridDay",
            },
            "initialView": "dayGridMonth",
            "events": events
        }

        

        # Add "Absen" button
        if st.button("Absen"):
            if selected_dates:
                run_face_detection()
            else:
                st.warning(
                    "Please select at least one date to mark attendance.")

        # Add "Stop" button
        if st.session_state.get('running', False):
            if st.button("Stop"):
                stop_face_detection()

        st.title("Student Points Leaderboard")

        students_data = get_sorted_student_data()

        if students_data:
            # Create DataFrame for display
            df = pd.DataFrame(students_data)
            # Generate HTML with CSS for styling
            html = df.to_html(classes='styled-table', index=False)

            # Add CSS styling for the table
            st.markdown("""
            <style>
            .styled-table {
                width: 100%;
                border-collapse: collapse;
                border: 1px solid #ddd;
            }
            .styled-table th, .styled-table td {
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }
            .styled-table tr:nth-child(even) {
                background-color: #f2f2f2;
            }
            .styled-table th {
                background-color: #FF4B4B;
                color: white;
            }
            </style>
            """, unsafe_allow_html=True)

            # Display the table with styling
            st.markdown(html, unsafe_allow_html=True)
        else:
            st.write("Tidak ada data siswa yang tersedia.")

        # Streamlit UI for notifications
        st.subheader("Notifications")

    elif user_level == 'Teacher':
        # Ambil data absen dari Firebase
        # Filter data untuk hari ini
        attendance_data = get_attendance_data()
        processed_data = process_attendance_data(attendance_data)
        
        
# Tampilkan data hasil filter dengan kolom name, status, timestamp
        st.header('Attendance Data Today')
        if processed_data:
    # Buat DataFrame dari data yang relevan
           df = pd.DataFrame(processed_data)
           st.write("""
        <style>
        .dataframe {
            width: 100%;
            border-collapse: collapse;
        }
        .dataframe th, .dataframe td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;  /* Menjaga teks rata kiri di sel tabel */
        }
        .dataframe th, .dataframe td {
            border: 1px solid #ddd;
            padding: 8px;
        }
        .dataframe tr:nth-child(even) {
            background-color: #f2f2f2;
        }
        .dataframe th {
            background-color:  #E4003A;
            color: white;
        }
        </style>
        """, unsafe_allow_html=True)
    
    # Hapus urutan angka (index) dari DataFrame
           st.write(df.to_html(classes='dataframe', index=False), unsafe_allow_html=True)
           # Menyediakan tombol unduh CSV
           csv = convert_df_to_csv(df)
           st.download_button(
              label="Download CSV",
              data=csv,
              file_name='attendance_data.csv',
              mime='text/csv'
           )
        else:
           st.write('No data available.')
        
        st.subheader("Student Points Leaderboard")

        students_data = get_sorted_student_data()

        if students_data:
            # Create DataFrame for display
            df = pd.DataFrame(students_data)
            # Generate HTML with CSS for styling
            html = df.to_html(classes='styled-table', index=False)

            # Add CSS styling for the table
            st.markdown("""
            <style>
            .styled-table {
                width: 100%;
                border-collapse: collapse;
                border: 1px solid #ddd;
            }
            .styled-table th, .styled-table td {
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }
            .styled-table tr:nth-child(even) {
                background-color: #f2f2f2;
            }
            .styled-table th {
                background-color: #FF4B4B;
                color: white;
            }
            </style>
            """, unsafe_allow_html=True)

            # Display the table with styling
            st.markdown(html, unsafe_allow_html=True)
        else:
            st.write("Tidak ada data siswa yang tersedia.")

        # Add feature for automatic and manual actions
        # Inisialisasi variabel global
       # ESP32_IP = "http://192.168.17.134"  # Ganti dengan IP ESP32 Anda

      #  st.title("Brightness")

# Mode selection
      #  mode = st.radio("Mode", ("Auto", "Manual"))

       # if mode == "Auto":
       #    requests.post(f"{ESP32_IP}/control", json={"mode": "auto"})
       # else:
         #  requests.post(f"{ESP32_IP}/control", json={"mode": "manual"})
         #  brightness = st.select_slider("Brightness", options=["Off", "Medium", "Bright"])
         #  brightness_value = {"Off": 0, "Medium": 1, "Bright": 2}[brightness]
         #  requests.post(f"{ESP32_IP}/control", json={"brightness": brightness_value})

# Display sensor data
        st.header("Sensor Data")
        lux_value = st.empty()
        distance_value = st.empty()

        lux_values = [611.00, 610.00, 612.00, 469.00, 428.00, 605.00, 603.00, 580.00, 563.00]
        distance_values = [1192.00, 7.00, 5.00, 67.00, 20.00, 8.00, 87.00, 75.00]

        while True:
           try:
              # Simulate fetching data from the ESP32
              lux = random.choice(lux_values)
              distance = random.choice(distance_values)
        
              lux_value.metric("Light Level (Lux)", f"{lux:.2f}")
              distance_value.metric("Distance (cm)", f"{distance:.2f}")
        
              time.sleep(1)
           except Exception as e:
             st.error(f"Failed to connect to ESP32: {e}")
             break

    # Implement manual action logic here

    def main():
        posture_status = load_posture_status()
        status = None
        timestamp = None

        if posture_status:
            status = posture_status.get("status")
            timestamp = posture_status.get("timestamp")

        if status == "slouching":
            st.markdown(
                f"""
              <div style='
                color: white;
                background-color: red;
                font-size: 18px;
                padding: 10px;
                border-radius: 5px;
              '>
                Student detected with poor posture (slouching) at {timestamp}
              </div>
              """,
                unsafe_allow_html=True
            )
            display_notification(status, timestamp)
        else:
            st.write("")

    if __name__ == "__main__":

        main()

    # Set polling interval
        polling_interval = 5  # in seconds

    # Poll for updates
        while True:
            time.sleep(polling_interval)
            st.experimental_rerun()


# Function to load posture status


# Initialize session state
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user'] = None
    st.session_state['level'] = None
    st.session_state['running'] = False

# Load and display notifications




if st.session_state['logged_in']:
    show_dashboard()
else:
     # Ganti 300 dengan lebar yang diinginkan
     # Streamlit app
    st.image("Group 7.png", width=250) 
    st.title("Welcome to Eduplus 👋")
    option = st.selectbox("Choose Login or Register", ["Login", "Register"])

    if option == "Login":
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        level = st.selectbox("Level", ["Student", "Teacher"])
        if st.button("Login"):
            if login(email, password, level):
                user_ref = teachers_ref if level == "Teacher" else students_ref
                user_data = user_ref.order_by_child(
                    'email').equal_to(email).get()
                st.session_state['user'] = list(user_data.values())[0]
                st.experimental_set_query_params()
                #st.experimental_rerun()

    elif option == "Register":
        id = st.text_input("ID")
        level = st.selectbox("Level", ["Student", "Teacher"])
        if level == "Student":
            class_name = st.selectbox("Class", ["A", "B", "C"])
        else:
            class_name = st.selectbox(
                "Subject", ["Math", "Science", "History"])
        
        email = st.text_input("Email")
        name = st.text_input("Name")
        password = st.text_input("Password", type="password")
        image = st.file_uploader("Upload Profile Picture", type=[
                                 "png", "jpg", "jpeg"])

        if st.button("Register"):
            if all([id,class_name, email, name, password, image, level]):
                register(id,class_name, email, name, password, image, level)
            else:
                st.error("Please fill out all fields and upload a profile picture")

# Stop the face detection process if the app stops
if st.session_state.get('running', False):
    stop_face_detection()
