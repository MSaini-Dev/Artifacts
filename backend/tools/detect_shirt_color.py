import cv2
import numpy as np
import json
import os

def detect_shirt_color():
    """
    Captures a frame from the default webcam, detects the dominant color in the 
    central region of the frame (where the user's shirt typically is), saves the 
    captured image to disk, and returns a detailed report including the detected shirt color.
    """
    # Open default camera (index 0)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return json.dumps({
            "success": False,
            "error": "Could not open webcam. Make sure a camera is connected and available."
        })

    # Warm up / read a few frames to let auto-exposure adjust
    for _ in range(5):
        ret, frame = cap.read()
    
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        return json.dumps({
            "success": False,
            "error": "Failed to capture image from webcam."
        })

    # Save the captured image
    output_dir = "captured_photos"
    os.makedirs(output_dir, exist_ok=True)
    image_path = os.path.join(output_dir, "shirt_capture.jpg")
    cv2.imwrite(image_path, frame)

    # Get dimensions
    height, width, _ = frame.shape

    # Define region of interest for shirt (typically center-bottom area of the frame)
    # e.g., middle 40% horizontally, vertical range from 45% to 75% down the frame
    y1 = int(height * 0.45)
    y2 = int(height * 0.75)
    x1 = int(width * 0.30)
    x2 = int(width * 0.70)

    roi = frame[y1:y2, x1:x2]

    # Convert ROI to HSV for better color analysis
    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    # Calculate average HSV values
    avg_h = np.mean(hsv_roi[:, :, 0])
    avg_s = np.mean(hsv_roi[:, :, 1])
    avg_v = np.mean(hsv_roi[:, :, 2])

    # Classify color based on HSV ranges
    # Hue: 0-180, Saturation: 0-255, Value: 0-255
    color_name = "Unknown"
    
    if avg_v < 50:
        color_name = "Black / Very Dark"
    elif avg_v > 200 and avg_s < 40:
        color_name = "White"
    elif avg_s < 40:
        if avg_v < 120:
            color_name = "Dark Gray"
        else:
            color_name = "Light Gray"
    else:
        # Check Hue
        if avg_h < 10 or avg_h > 170:
            color_name = "Red"
        elif 10 <= avg_h < 22:
            color_name = "Orange / Brown"
        elif 22 <= avg_h < 38:
            color_name = "Yellow"
        elif 38 <= avg_h < 85:
            color_name = "Green"
        elif 85 <= avg_h < 130:
            color_name = "Blue"
        elif 130 <= avg_h < 170:
            color_name = "Purple / Pink"
        else:
            color_name = "Red"

    # Also extract dominant color using k-means or simple average BGR
    avg_b = int(np.mean(roi[:, :, 0]))
    avg_g = int(np.mean(roi[:, :, 1]))
    avg_r = int(np.mean(roi[:, :, 2]))

    result = {
        "success": True,
        "message": f"Successfully captured image and analyzed shirt color!",
        "shirt_color": color_name,
        "image_saved_at": image_path,
        "average_hsv": [round(float(avg_h), 2), round(float(avg_s), 2), round(float(avg_v), 2)],
        "average_rgb": [avg_r, avg_g, avg_b]
    }

    return json.dumps(result, indent=2)
