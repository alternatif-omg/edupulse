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

# Initialize Firebase if not already initialized
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

if not firebase_admin._apps:
    cred = credentials.Certificate(service_account_key)
    firebase_admin.initialize_app(cred, {
        'databaseURL': "https://faceattendance-a740a-default-rtdb.firebaseio.com/",
        'storageBucket': "faceattendance-a740a.appspot.com"
    })

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

# Function to get attendance data from Firebase
def get_attendance_data():
    ref = db.reference('Attendance')
    data = ref.get()
    return data

# Function to process attendance data
def process_attendance_data(data):
    processed_data = []
    today = datetime.now().date()
    for student_id, records in data.items():
        for record_id, record in records.items():
            if 'name' in record and 'status' in record and 'timestamp' in record:
                try:
                    record_date = datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M:%S').date()
                    if record_date == today:
                        processed_data.append({
                            'Name': record['name'],
                            'Status': record['status'],
                            'Time': record['timestamp']
                        })
                except ValueError:
                    continue
    return processed_data

def convert_df_to_csv(df):
    csv = df.to_csv(index=False)
    return csv

# Function to get attendance dates
def get_attendance_dates():
    ref = db.reference('Attendance')
    attendance_data = ref.get()
    attendance_dates = set()
    for student_id, records in attendance_data.items():
        for record_id, record in records.items():
            date = datetime.strptime(record['timestamp'].split()[0], "%Y-%m-%d").date()
            attendance_dates.add(date.isoformat())
    return list(attendance_dates)

# Function to get sorted student data
def get_sorted_student_data():
    ref = db.reference('interaksi')
    data = ref.get()
    if data:
        students = [{"Name": name, "points": info["points"], "last_updated": info["last_updated"]} for name, info in data.items()]
        students_sorted = sorted(students, key=lambda x: x["points"], reverse=True)
        return students_sorted
    else:
        return []

# Login function
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

# Function to load posture status
def load_posture_status():
    if os.path.exists('posture_status.json'):
        try:
            with open('posture_status.json', 'r') as json_file:
                data = json_file.read().strip()
                if not data:  # Handle empty file
                    return None
                return json.loads(data)
        except json.JSONDecodeError:
            st.error("Error reading posture status data. The file may be corrupted or empty.")
            return None
    return None

# Function to display notification
def display_notification(status, timestamp):
    if status == "slouching":
        notification.notify(
            title="Posture Alert",
            message=f"Student detected with poor posture (slouching) at {timestamp}",
            app_name="Posture Monitoring",
        )

# Function to show the dashboard
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
            students = students_ref.order_by_child('name').equal_to(user_data['name']).get()
            if students:
                user_id = list(students.keys())[0]
        else:
            teachers = teachers_ref.order_by_child('name').equal_to(user_data['name']).get()
            if teachers:
                user_id = list(teachers.keys())[0]

        if user_id:
            st.write(f"**ID:** {user_id}")
        else:
            st.warning("User ID not found")

        profile_picture_url = f"https://firebasestorage.googleapis.com/v0/b/faceattendance-a740a.appspot.com/o/Images%2F{user_id}.png?alt=media"
        st.image(profile_picture_url, caption="Profile Picture", use_column_width=True)

        st.write(f"**Name:** {user_data['name']}")
        st.write(f"**Email:** {user_data['email']}")
        if user_level == 'Student':
            st.write(f"**Class:** {user_data['class']}")
        else:
            st.write(f"**Subject:** {user_data['subject']}")

    # Show the correct section based on user level
    if user_level == 'Student':
        st.subheader("Selamat datang di aplikasi deteksi pose dan interaksi siswa!")
        st.write("Anda dapat menggunakan aplikasi ini untuk memantau kehadiran dan interaksi Anda di kelas.")

    elif user_level == 'Teacher':
        st.subheader("👨‍🏫 Panel Guru")
        col1, col2 = st.columns(2)

        with col1:
            st.write("### 📅 Kalender Kehadiran")
            dates = get_attendance_dates()
            calendar(selected=dates)

        with col2:
            st.write("### 🏆 Peringkat Interaksi Siswa")
            students_sorted = get_sorted_student_data()
            if students_sorted:
                df = pd.DataFrame(students_sorted)
                st.dataframe(df)

    st.write("### 📈 Status Postur Siswa")
    posture_data = load_posture_status()
    if posture_data:
        for status, timestamp in posture_data:
            display_notification(status, timestamp)
            st.write(f"**Posture Status:** {status} at {timestamp}")

    # Show attendance data
    st.write("### 📊 Data Kehadiran Hari Ini")
    attendance_data = get_attendance_data()
    if attendance_data:
        processed_data = process_attendance_data(attendance_data)
        if processed_data:
            df = pd.DataFrame(processed_data)
            st.dataframe(df)
            csv = convert_df_to_csv(df)
            st.download_button(label="📥 Download Data Kehadiran",
                               data=csv,
                               file_name='attendance_data.csv',
                               mime='text/csv')

# Main function to handle login and registration
def main():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['running'] = False

    if st.session_state['logged_in']:
        show_dashboard()
        if st.button("Log Out"):
            st.session_state['logged_in'] = False
            st.session_state['user'] = None
            st.session_state['level'] = None
            st.experimental_set_query_params()
    else:
        tab1, tab2 = st.tabs(["Login", "Register"])

        with tab1:
            st.header("Login")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            level = st.selectbox("Level", ["Student", "Teacher"])
            if st.button("Login"):
                login(email, password, level)

        with tab2:
            st.header("Register")
            id = st.text_input("ID")
            class_name = st.text_input("Class (for Students) / Subject (for Teachers)")
            email = st.text_input("Email")
            name = st.text_input("Name")
            password = st.text_input("Password", type="password")
            image = st.file_uploader("Profile Picture", type=["png", "jpg", "jpeg"])
            level = st.selectbox("Level", ["Student", "Teacher"])
            if st.button("Register"):
                register(id, class_name, email, name, password, image, level)

if __name__ == "__main__":
    main()
