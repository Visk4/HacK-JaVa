import streamlit as st
import cv2
import numpy as np
import time
from datetime import datetime
import pandas as pd
import pickle
import os
import mediapipe as mp
import face_recognition
from tensorflow.keras.models import load_model
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration
import av

# Importing the necessary functions from the face detection file
from import_face_recognition import load_known_faces, recognize_faces_live
known_encodings, known_names = load_known_faces()

mp_pose = mp.solutions.pose
pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
mp_draw = mp.solutions.drawing_utils

# Fixed model loading function with corrected path
def load_fight_model():
    try:
        # Fixing the file path
        return load_model(r'C:\Users\kriya\Desktop\face\lstm-fight-detection.h5')
    except Exception as e:
        st.error(f"Error loading model: {e}")
        st.stop()

model = load_fight_model()

# Global variables for fight detection
label = "unknown"
label_history = []
lm_list = []

# WebRTC configuration (use default STUN server)
RTC_CONFIGURATION = RTCConfiguration({"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})

class ViolenceProcessor(VideoProcessorBase):
    def __init__(self):
        self.label = "unknown"
        self.label_history = []
        self.lm_list = []

    def make_landmark_timestep(self, results):
        if results.pose_landmarks:
            c_lm = []
            for lm in results.pose_landmarks.landmark:
                c_lm.extend([lm.x, lm.y, lm.z])
            return c_lm
        return None

    def draw_landmark_on_image(self, mp_draw, results, frame):
        if results.pose_landmarks:
            mp_draw.draw_landmarks(frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
            for id, lm in enumerate(results.pose_landmarks.landmark):
                h, w, c = frame.shape
                cx, cy = int(lm.x * w), int(lm.y * h)
                cv2.circle(frame, (cx, cy), 3, (0, 255, 0), cv2.FILLED)
        return frame

    def detect(self, model, lm_list):
        if len(lm_list) >= 20:
            lm_array = np.array(lm_list[-20:])
            lm_array = np.expand_dims(lm_array, axis=0)
            try:
                result = model.predict(lm_array, verbose=0)[0]
                pred_label = "fight" if result[0] > 0.5 else "normal"
                # Heuristic: Rapid movement in wrists (15, 16) and elbows (13, 14)
                if len(lm_list) > 1 and lm_list[-1] and lm_list[-2]:
                    for idx in [15, 16, 13, 14]:
                        x_diff = lm_list[-1][idx*3] - lm_list[-2][idx*3]
                        y_diff = lm_list[-1][idx*3+1] - lm_list[-2][idx*3+1]
                        if abs(x_diff) > 0.07 or abs(y_diff) > 0.07:
                            pred_label = "fight"
                            break
                # Smoothing
                self.label_history.append(pred_label)
                if len(self.label_history) > 3:
                    self.label_history.pop(0)
                self.label = max(set(self.label_history), key=self.label_history.count) if self.label_history else pred_label
            except Exception as e:
                st.error(f"Prediction error: {e}")
                self.label = "ERROR"
        return self.label

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        frame_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = pose.process(frame_rgb)
        lm = self.make_landmark_timestep(results)
        if lm:
            self.lm_list.append(lm)
        img = self.draw_landmark_on_image(mp_draw, results, img)
        self.label = self.detect(model, self.lm_list)
        color = (0, 0, 255) if self.label == "fight" else (0, 255, 0)
        cv2.rectangle(img, (0, 0), (img.shape[1], img.shape[0]), color, 2)
        cv2.putText(img, self.label.upper(), (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        return av.VideoFrame.from_ndarray(img, format="bgr24")

# Function to process video (with WebRTC integration)
def process_video_with_webrtc():
    ctx = webrtc_streamer(
        key="violence-detection",
        video_processor_factory=ViolenceProcessor,
        rtc_configuration=RTC_CONFIGURATION,
        media_stream_constraints={"video": True, "audio": False},
        async_processing=True
    )
    if ctx.video_processor:
        return ctx.video_processor.label
    return "unknown"

def detect_gender(frame):
    """Placeholder for gender identification model."""
    gender = np.random.choice(["Male", "Female"])
    alert = "Male detected in girls' hostel" if gender == "Male" else None
    return gender, alert

def detect_guard_attentiveness(frame):
    """Placeholder for guard attentiveness model."""
    attentive = np.random.choice([True, False])
    alert = "Guard not attentive" if not attentive else None
    return attentive, alert

# Load encodings once globally
known_encodings, known_names = load_known_faces()

def detect_face(frame):
    """Detects faces in the frame using the custom face recognition model."""
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    face_detector = mp.solutions.face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5)
    results = face_detector.process(rgb_frame)

    face_names = []
    face_locations = []

    if results.detections:
        for detection in results.detections:
            bbox = detection.location_data.relative_bounding_box
            ih, iw, _ = frame.shape
            x = max(0, int(bbox.xmin * iw))
            y = max(0, int(bbox.ymin * ih))
            w = int(bbox.width * iw)
            h = int(bbox.height * ih)
            top, right, bottom, left = y, x + w, y + h, x
            face_locations.append((top, right, bottom, left))

        encodings = face_recognition.face_encodings(rgb_frame, face_locations)
        for face_encoding in encodings:
            name = "Unknown"
            distances = face_recognition.face_distance(known_encodings, face_encoding)
            if len(distances) > 0:
                best_match_index = np.argmin(distances)
                if distances[best_match_index] < 0.45:
                    name = known_names[best_match_index]
            face_names.append(name)

    alert = None
    if "Unknown" in face_names:
        alert = "Unknown face detected!"
        st.session_state.alerts.append([datetime.now(), "Face Detection", alert])

    # Draw bounding boxes
    for (top, right, bottom, left), name in zip(face_locations, face_names):
        color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.rectangle(frame, (left, bottom - 30), (right, bottom), color, cv2.FILLED)
        cv2.putText(frame, name, (left + 6, bottom - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    return frame, alert


def detect_crowd_density(frame):
    """Placeholder for crowd density monitoring model (fifth model)."""
    density = np.random.randint(0, 100)
    alert = "High crowd density detected" if density > 80 else None
    return density, alert

# Function to process video feed (placeholder for real-time video)
def process_video(model_func, model_name):
    stframe = st.empty()
    alert_placeholder = st.empty()
    cap = cv2.VideoCapture(1)  # Use default camera (0 for webcam)

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            st.error("Failed to capture video feed.")
            break

        # Process frame with the selected model
        result, alert = model_func(frame)

        # Display video frame
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        stframe.image(frame_rgb, channels="RGB", use_column_width=True)

        # Display alert
        if alert:
            alert_placeholder.error(f"ALERT: {alert} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            alert_placeholder.success(f"No issues detected at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Main function to start the app
def start_app():
    st.title("AI Surveillance System")
    options = ["Face Recognition", "Fight Detection", "Crowd Density", "Guard Attentiveness", "Gender Detection"]
    choice = st.sidebar.selectbox("Select Model", options)

    if choice == "Face Recognition":
        process_video(detect_face, "face_recognition")
    elif choice == "Fight Detection":
        process_video_with_webrtc()
    elif choice == "Crowd Density":
        process_video(detect_crowd_density, "crowd_density")
    elif choice == "Guard Attentiveness":
        process_video(detect_guard_attentiveness, "guard_attentiveness")
    elif choice == "Gender Detection":
        process_video(detect_gender, "gender_detection")

if __name__ == "__main__":
    start_app()
