import os
import cv2
import numpy as np

def scan_and_compare_face():
    """
    Captures a frame from the default webcam, detects face mesh landmarks using MediaPipe,
    generates a unique normalized embedding/hash (Face ID), saves the reference face ID,
    and then prompts/captures a second frame to compare against the reference face ID
    with a similarity score and match result.
    """
    try:
        import mediapipe as mp
    except Exception as e:
        return f"Error importing mediapipe: {e}"

    os.makedirs("captured_photos", exist_ok=True)
    
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return "Error: Could not open webcam."

    # Warm up camera
    for _ in range(5):
        cap.read()

    print("Step 1: Capturing reference Face ID... Look at the camera.")
    ret, frame1 = cap.read()
    if not ret:
        cap.release()
        return "Error: Failed to capture reference frame from webcam."
    
    ref_image_path = "captured_photos/face_id_reference.jpg"
    cv2.imwrite(ref_image_path, frame1)

    mp_face_mesh = mp.solutions.face_mesh
    
    def extract_face_embedding(img):
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        with mp_face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5
        ) as face_mesh:
            results = face_mesh.process(rgb_img)
            if not results.multi_face_landmarks:
                return None
            
            # Extract 478 3D landmarks (x, y, z)
            landmarks = results.multi_face_landmarks[0].landmark
            coords = np.array([[lm.x, lm.y, lm.z] for lm in landmarks], dtype=np.float32)
            
            # Normalize: center around nose tip (landmark 1) or mean, scale by max distance
            centroid = coords[1] # nose tip
            normalized = coords - centroid
            max_dist = np.max(np.linalg.norm(normalized, axis=1))
            if max_dist > 0:
                normalized /= max_dist
            
            return normalized.flatten()

    ref_embedding = extract_face_embedding(frame1)
    if ref_embedding is None:
        cap.release()
        return "Error: No face detected in the reference capture. Please ensure your face is clearly visible."

    # Generate unique hash representation for reference
    ref_hash = "".join([f"{val:+.4f}" for val in ref_embedding[:16]]) # preview string
    print(f"Reference Face ID generated successfully! Preview hash: {ref_hash[:30]}...")

    print("Step 2: Capturing comparison face... Please look at the camera again for verification.")
    # Brief pause/capture next frame
    for _ in range(10):
        cap.read()
    ret, frame2 = cap.read()
    if not ret:
        cap.release()
        return "Error: Failed to capture comparison frame from webcam."

    comp_image_path = "captured_photos/face_id_comparison.jpg"
    cv2.imwrite(comp_image_path, frame2)
    cap.release()

    comp_embedding = extract_face_embedding(frame2)
    if comp_embedding is None:
        return f"Error: No face detected in the comparison capture. Reference saved at {ref_image_path}, comparison at {comp_image_path}."

    # Compute Cosine Similarity between reference and comparison embeddings
    dot_product = np.dot(ref_embedding, comp_embedding)
    norm_ref = np.linalg.norm(ref_embedding)
    norm_comp = np.linalg.norm(comp_embedding)
    
    if norm_ref == 0 or norm_comp == 0:
        similarity = 0.0
    else:
        similarity = float(dot_product / (norm_ref * norm_comp))

    # Threshold for match (e.g., 0.90 similarity)
    match = similarity >= 0.90

    report = (
        f"Face ID Scan & Comparison Report:\n"
        f"- Reference Image saved to: {ref_image_path}\n"
        f"- Comparison Image saved to: {comp_image_path}\n"
        f"- Similarity Score: {similarity:.4f} ({similarity * 100:.2f}%)\n"
        f"- Match Result: {'MATCH (Authorized)' if match else 'NO MATCH (Unauthorized / Different Face)'}\n"
    )
    return report
