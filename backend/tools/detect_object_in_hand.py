import cv2
import os
import numpy as np

def detect_object_in_hand():
    """
    Captures a frame from the default webcam, crops the hand region (typically lower-center or center),
    saves the image, and uses simple analysis or returns the image path so the assistant can describe it.
    """
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return {"error": "Could not open webcam."}
    
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        return {"error": "Failed to capture frame from webcam."}
        
    os.makedirs("captured_photos", exist_ok=True)
    file_path = "captured_photos/hand_capture.jpg"
    cv2.imwrite(file_path, frame)
    
    return {
        "status": "success",
        "message": "Captured photo successfully.",
        "image_path": file_path
    }
