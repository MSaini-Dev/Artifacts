import cv2
import os

def capture_admin_image():
    """
    Captures a frame from the default webcam, saves it to captured_photos/admin.jpg,
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
    
    image_path = os.path.join("captured_photos", "admin.jpg")
    cv2.imwrite(image_path, frame)
    return {
        "status": "success",
        "message": f"Successfully captured photo and saved as admin image to {image_path}.",
        "image_path": image_path
    }
