import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
from django.conf import settings
from ultralytics import YOLO
from webapp.activity import detect_activity



# ================= CONFIG =================
GALLERY_FILE = "gallery_embeddings_cctv5.npz"

MATCH_THRESHOLD = 0.47
SIMILAR_THRESHOLD = 0.18
NO_FACE_MAX = 0.06 
CAPTURE_INTERVAL = 10 * 60   

SAVE_DIR = Path(settings.BASE_DIR) / "recognized_cctv"
SAVE_DIR.mkdir(exist_ok=True)

# ================= GLOBALS =================
app = None
gallery = None

# 🔥 ONLY ONE GLOBAL STATE
# key = (camera_name, person_key)


yolo_person = YOLO("yolov8n.pt")

def detect_person_boxes(image):
    """
    Returns list of (x1, y1, x2, y2) for each person
    """
    result = yolo_person(image, classes=[0], conf=0.4, verbose=False)[0]
    boxes = []
    for b in result.boxes:
        boxes.append(tuple(map(int, b.xyxy[0])))
    return boxes

# ================= DJANGO MODEL =================
def get_recognized_model():
    from webapp.models import RecognizedFace
    return RecognizedFace

# ================= LOAD INSIGHTFACE =================
def get_face_app():
    global app
    if app is None:
        import insightface
        app = insightface.app.FaceAnalysis(name="buffalo_l")
        app.prepare(ctx_id=0, det_size=(640, 640))
    return app

# ================= LOAD GALLERY =================
def load_gallery():
    global gallery
    if gallery is None:
        data = np.load(GALLERY_FILE, allow_pickle=True)
        gallery = {k: data[k].astype(np.float32) for k in data.files}
        print("📚 Gallery loaded:", list(gallery.keys()))

get_face_app()
load_gallery()

# ================= FACE RECOGNITION =================
def recognize_faces(image):
    detections = []
    faces = app.get(image)

    if not faces or gallery is None:
        return detections

    for face in faces:
        emb = face.normed_embedding.astype(np.float32)
        bbox = face.bbox
        

        best_score = -1.0
        best_id = None

        for emp_id, g_emb in gallery.items():
            score = float(np.dot(emb, g_emb))
            if score > best_score:
                best_score = score
                best_id = emp_id

        # ================= FINAL CLASSIFICATION =================
        if best_score >= MATCH_THRESHOLD:
            # KNOW
            emp_id = best_id
            similarity_id = None
            person_key = emp_id
            folder = emp_id
            label = emp_id

        elif SIMILAR_THRESHOLD <= best_score < MATCH_THRESHOLD:
            # SIMILARITY
            emp_id = None
            similarity_id = best_id
            person_key = similarity_id
            folder = f"similarity/{similarity_id}"
            label = similarity_id

        elif NO_FACE_MAX < best_score < SIMILAR_THRESHOLD:
            # UNKNOWN (face exists but not matched)
            emp_id = None
            similarity_id = "UNKNOWN"
            person_key = "UNKNOWN"
            folder = "unknown"
            label = "unknown"

        else:
            # NO FACE (backside / head down / not visible)
            emp_id = None
            similarity_id = "NO_FACE"
            person_key = "NO_FACE"
            folder = "no_face"
            label = "no_face"

        detections.append({
            "emp_id": emp_id,
            "similarity_id": similarity_id,
            "similarity_score": round(best_score, 2),
            "bbox": bbox,
            "folder": folder,
            "label": label,
            "person_key": person_key,
            "phone_detected": False,
            "phone_distance": None,
            "activity": None, 
            "helmet_detected": False
        })

    return detections


# ================= SAVE IMAGE + DB =================
def save_capture(camera_name, image, det):
    x1, y1, x2, y2 = map(int, det["bbox"])
    h, w = image.shape[:2]

    pad = 2.0
    bw = int((x2 - x1) * pad)
    bh = int((y2 - y1) * pad)

    x1 = max(0, x1 - bw)
    y1 = max(0, y1 - bh)
    x2 = min(w, x2 + bw)
    y2 = min(h, y2 + bh)

    # reduce top only
    y1 += int((y2 - y1) * 0.1)

    face = image[y1:y2, x1:x2]
    if face.size == 0:
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = SAVE_DIR / camera_name / det["folder"]
    out_dir.mkdir(parents=True, exist_ok=True)

    img_path = out_dir / f"{det['label']}_{ts}.jpg"
    cv2.imwrite(str(img_path), face)

    RecognizedFace = get_recognized_model()
    RecognizedFace.objects.create(
        camera_name=camera_name,
        emp_id=det["emp_id"],
        similarity_id=det["similarity_id"],
        similarity_score=det["similarity_score"],
        image_path=str(img_path),
        phone_detected=det.get("phone_detected", False),
        phone_distance=det.get("phone_distance"),
        activity=det.get("activity"),
        bbox=list(map(int, det["bbox"])),
        helmet_detected=det.get("helmet_detected")
        
    )

last_capture_time = {}   # (emp_id, camera_name) -> datetime
last_camera = {}         # emp_id -> last camera

# last_unknown_capture = {}   # (camera,label) -> datetime
# UNKNOWN_INTERVAL = 1   

# ================= CAPTURE LOGIC (FINAL) =================
def update_capture_logic(camera_name, image, detections):

    now = datetime.now()
    person_boxes = detect_person_boxes(image)

    for det in detections:

        emp_id = det["emp_id"]
        if emp_id is None:
            continue
        
        # if emp_id is None:
        #     key_u = (camera_name, det["label"])
        #     last = last_unknown_capture.get(key_u)

        #     if last is None:
        #         save_capture(camera_name, image, det)
        #         last_unknown_capture[key_u] = now
        #         continue

        #     diff = (now - last).total_seconds()

        #     if diff >= UNKNOWN_INTERVAL:
        #         save_capture(camera_name, image, det)
        #         last_unknown_capture[key_u] = now

        #     continue


        # -------- ACTIVITY ----------
        det["activity"] = None

        fx1, fy1, fx2, fy2 = map(int, det["bbox"])
        fcx, fcy = (fx1 + fx2)//2, (fy1 + fy2)//2

        for bx1, by1, bx2, by2 in person_boxes:
            bcx, bcy = (bx1 + bx2)//2, (by1 + by2)//2
            if abs(fcx-bcx)+abs(fcy-bcy) < 150:
                det["activity"] = detect_activity(
                    image,
                    (bx1,by1,bx2,by2),
                    emp_id
                )
                break


        # -------- KEY STATE ----------
        key = (emp_id, camera_name)

        last_time = last_capture_time.get(key)
        last_cam  = last_camera.get(emp_id)


        # =================================================
        # 📱 PHONE DETECT → PRIORITY CAPTURE
        # =================================================
        if det.get("phone_detected"):

            if last_time is None:
                save_capture(camera_name, image, det)
                last_capture_time[key] = now
                last_camera[emp_id] = camera_name
                continue

            diff = (now - last_time).total_seconds()

            if diff >= CAPTURE_INTERVAL:
                save_capture(camera_name, image, det)
                last_capture_time[key] = now
                last_camera[emp_id] = camera_name

            continue


        # =================================================
        # FIRST TIME EVER
        # =================================================
        if last_cam is None:
            save_capture(camera_name, image, det)
            last_capture_time[key] = now
            last_camera[emp_id] = camera_name
            continue


        # =================================================
        # CAMERA CHANGED
        # =================================================
        if last_cam != camera_name:
            save_capture(camera_name, image, det)
            last_capture_time[key] = now
            last_camera[emp_id] = camera_name
            continue


        # =================================================
        # SAME CAMERA → INTERVAL CHECK
        # =================================================
        if last_time is None:
            save_capture(camera_name, image, det)
            last_capture_time[key] = now
            continue


        diff = (now - last_time).total_seconds()

        if diff >= CAPTURE_INTERVAL:
            save_capture(camera_name, image, det)
            last_capture_time[key] = now





