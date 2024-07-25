import logging
import signal
import sys

# Konfigurasi logging
logging.basicConfig(filename='face_detection.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

try:
    import face_recognition
    logging.info('face_recognition imported successfully')
except ImportError as e:
    logging.error(f'Error importing face_recognition: {e}')
    raise

import os
import pickle
import numpy as np
import cv2
import face_recognition
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
from firebase_admin import storage
from datetime import datetime


# Initialize Firebase
try:
    cred = credentials.Certificate(os.getenv('FIREBASE_CREDENTIAL_PATH', 'faceattendance-a740a-firebase-adminsdk-rqxwq-0f6719139c.json'))
    firebase_admin.initialize_app(cred, {
        'databaseURL': os.getenv('FIREBASE_DB_URL', "https://faceattendance-a740a-default-rtdb.firebaseio.com/"),
        'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET', "faceattendance-a740a.appspot.com")
    })
    bucket = storage.bucket()
except Exception as e:
    print(f"Error initializing Firebase: {e}")
    exit(1)

def write_student_id(student_name):
    try:
        with open('student_id.txt', 'w') as f:
            f.write(f"{student_name}")
        print(f"Name {student_name} written to file.")
    except IOError as e:
        print(f"Error writing to file: {e}")

# Load encoding file
print("Loading Encode File ...")
try:
    with open('EncodeFile.p', 'rb') as file:
        encodeListKnownWithIds = pickle.load(file)
    encodeListKnown, studentIds = encodeListKnownWithIds
    print("Encode File Loaded")
except (IOError, pickle.PickleError) as e:
    print(f"Error loading encode file: {e}")
    exit(1)

# Initialize variables
id = -1
imgStudent = None
studentInfo = {}
attendance_marked = False

# Signal handler for graceful exit
def signal_handler(sig, frame):
    print('Stopping face detection...')
    if cap is not None:
        cap.release()  # Release the webcam
    cv2.destroyAllWindows()  # Close any OpenCV windows
    sys.exit(0)  # Exit the program

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler) 

def mark_attendance(student_id, student_name):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    attendance_ref = db.reference(f'Attendance/{student_id}')
    attendance_ref.push().set({
        'timestamp': current_time,
        'status': 'present',
        'name': student_name  # Include student name in the attendance record
    })
    print(f"Attendance marked for student {student_id} ({student_name}) at {current_time}")


# Open webcam
cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)

while True:
    success, img = cap.read()
    if not success:
        print("Failed to grab frame")
        break

    # Get image dimensions
    height, width, _ = img.shape

    # Resize image for faster processing
    small_frame = cv2.resize(img, (0, 0), fx=0.25, fy=0.25)

    # Convert the image from BGR color (which OpenCV uses) to RGB color
    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    # Find all face locations and face encodings in the current frame
    face_locations = face_recognition.face_locations(rgb_small_frame)
    face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

    # Draw facial landmarks and bounding boxes
    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        # Scale back up face locations since the frame we detected in was scaled to 1/4 size
        top *= 4
        right *= 4
        bottom *= 4
        left *= 4

        # Draw a box around the face
        cv2.rectangle(img, (left, top), (right, bottom), (0, 255, 0), 2)
        
        # Draw facial landmarks
        face_landmarks_list = face_recognition.face_landmarks(rgb_small_frame, [(top//4, right//4, bottom//4, left//4)])
        for face_landmarks in face_landmarks_list:
            for facial_feature in face_landmarks.values():
                for point in facial_feature:
                    pt = (point[0] * 4, point[1] * 4)
                    cv2.circle(img, pt, 2, (0, 0, 255), -1)  # Merah
        
        # Recognize face
        matches = face_recognition.compare_faces(encodeListKnown, face_encoding)
        faceDis = face_recognition.face_distance(encodeListKnown, face_encoding)
        matchIndex = np.argmin(faceDis)

        if matches[matchIndex]:
            id = studentIds[matchIndex]

        if id != -1 and not attendance_marked:
            if not studentInfo:
                try:
                    student_ref = db.reference(f'Students/{id}')
                    studentInfo = student_ref.get()

                    print(f"Student ID: {id}")
                    print(f"Name: {studentInfo['name']}")
                    print(f"Class: {studentInfo['class']}")
                    print(f"Email: {studentInfo['email']}")

                    write_student_id(studentInfo['name'])

                    # Mark attendance
                    mark_attendance(id, studentInfo['name'])

                    attendance_marked = True

                    # Fetch student image
                    blob = bucket.get_blob(f'Images/{id}.png')
                    if blob is not None:
                        array = np.frombuffer(blob.download_as_string(), np.uint8)
                        imgStudent = cv2.imdecode(array, cv2.IMREAD_COLOR)
                    else:
                        print(f"Error: Image for student ID {id} not found in Firebase Storage.")
                        imgStudent = np.zeros((216, 216, 3), np.uint8)
                except Exception as e:
                    print(f"Error fetching student data or marking attendance: {e}")
                    studentInfo = {}
                    imgStudent = np.zeros((216, 216, 3), np.uint8)

    # Display student info if available
    if studentInfo:
        # Membuat latar belakang untuk informasi di bagian bawah
        info_height = 120
        cv2.rectangle(img, (0, height - info_height), (width, height), (245, 245, 245), cv2.FILLED)
        cv2.rectangle(img, (0, height - info_height), (width, height), (0, 0, 0), 2)

        # Menampilkan gambar siswa
        if imgStudent is not None:
            imgStudent = cv2.resize(imgStudent, (100, 100))
            img[height - 110:height - 10, 10:110] = imgStudent
            cv2.rectangle(img, (5, height - 115), (115, height - 5), (255, 255, 255), 2)

        # Font settings
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        font_thickness = 1
        text_color = (0, 0, 0)

        # Menampilkan informasi siswa
        cv2.putText(img, f"Name: {studentInfo['name']}", (130, height - 95), font, font_scale, text_color, font_thickness)
        cv2.putText(img, f"ID: {id}", (130, height - 75), font, font_scale, text_color, font_thickness)
        cv2.putText(img, f"Class: {studentInfo['class']}", (130, height - 55), font, font_scale, text_color, font_thickness)
        cv2.putText(img, f"Email: {studentInfo['email']}", (130, height - 35), font, font_scale, text_color, font_thickness)

        # Menampilkan status login
        cv2.putText(img, "Login Status: Active", (130, height - 15), font, font_scale, (0, 255, 0), font_thickness)

        # Menambahkan judul
        cv2.putText(img, "Student Info", (5, height - info_height - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    
    cv2.imshow("Face Attendance", img)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
