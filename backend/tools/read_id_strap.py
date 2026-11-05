import cv2
import os

def read_id_strap():
    """
    Captures a frame from the webcam, saves it to captured_photos/id_strap_capture.jpg,
    and returns the image path and status.
    """
    os.makedirs("captured_photos", exist_ok=True)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return {"status": "error", "message": "Could not open webcam."}
    
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        return {"status": "error", "message": "Failed to capture frame from webcam."}
    
    image_path = os.path.join("captured_photos", "id_strap_capture.jpg")
    cv2.imwrite(image_path, frame)
    return {
        "status": "success",
        "message": f"Successfully captured photo and saved to {image_path}.",
        "image_path": image_path
    }
