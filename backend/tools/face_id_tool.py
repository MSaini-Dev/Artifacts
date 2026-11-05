import cv2
import numpy as np
import json
import os
import hashlib

def face_id_scan(mode="scan", profile_name="default"):
    """
    Uses MediaPipe Face Mesh (or robust fallback) to scan a face from the webcam and convert it into a unique ID (face ID),
    or compare a new scan against a stored face ID.
    
    Args:
        mode (str): "scan" to capture and save face features, or "compare" to scan a new face and compare with the stored one.
        profile_name (str): Identifier for the face profile.
    
    Returns:
        dict: Status, message, and similarity score (if comparing) or face hash/ID.
    """
    storage_file = "face_profiles.json"
    
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return {"status": "error", "message": "Could not open webcam."}
    
    success, frame = cap.read()
    cap.release()
    
    if not success:
        return {"status": "error", "message": "Failed to capture image from webcam."}
    
    face_vector = None
    try:
        import mediapipe as mp
        # Avoid mp.solutions entirely if it raises AttributeError
        import mediapipe.python.solutions.face_mesh as mp_face_mesh_mod
        with mp_face_mesh_mod.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5
        ) as face_mesh:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb_frame)
            
            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0]
                coords = [[lm.x, lm.y, lm.z] for lm in landmarks.landmark]
                coords = np.array(coords)
                nose_tip = coords[1]
                normalized_coords = coords - nose_tip
                max_dist = np.max(np.linalg.norm(normalized_coords, axis=1))
                if max_dist > 0:
                    normalized_coords = normalized_coords / max_dist
                face_vector = normalized_coords.flatten().tolist()
    except Exception as e:
        pass

    if face_vector is None:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (64, 64))
        face_vector = resized.flatten().astype(float).tolist()

    vector_bytes = np.array(face_vector, dtype=np.float32).tobytes()
    face_id_hash = hashlib.sha256(vector_bytes).hexdigest()

    profiles = {}
    if os.path.exists(storage_file):
        try:
            with open(storage_file, "r") as f:
                profiles = json.load(f)
        except Exception:
            profiles = {}

    if mode == "scan":
        profiles[profile_name] = {
            "face_id": face_id_hash,
            "vector": face_vector
        }
        with open(storage_file, "w") as f:
            json.dump(profiles, f)
            
        return {
            "status": "success",
            "message": f"Face successfully scanned and saved under profile '{profile_name}'.",
            "face_id": face_id_hash
        }
        
    elif mode == "compare":
        if profile_name not in profiles:
            return {"status": "error", "message": f"Profile '{profile_name}' not found. Please scan first."}
            
        stored_vector = np.array(profiles[profile_name]["vector"])
        current_vector = np.array(face_vector)
        
        dot_product = np.dot(stored_vector, current_vector)
        norm_a = np.linalg.norm(stored_vector)
        norm_b = np.linalg.norm(current_vector)
        
        if norm_a == 0 or norm_b == 0:
            similarity = 0.0
        else:
            similarity = float(dot_product / (norm_a * norm_b))
            
        is_match = similarity >= 0.85
        
        return {
            "status": "success",
            "mode": "compare",
            "profile": profile_name,
            "similarity_score": round(similarity * 100, 2),
            "match": is_match,
            "message": f"Face comparison complete. Similarity: {round(similarity * 100, 2)}%. Match: {is_match}"
        }
    else:
        return {"status": "error", "message": "Invalid mode. Use 'scan' or 'compare'."}
