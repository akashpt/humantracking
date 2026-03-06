# activity.py
import cv2, math, os
import mediapipe as mp
import joblib
from collections import deque, Counter
from django.conf import settings

MODEL_PATH = os.path.join(settings.BASE_DIR, "activity_model_one.pkl")
activity_model = joblib.load(MODEL_PATH)

mp_pose = mp.solutions.pose
pose = mp_pose.Pose(
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

BODY_LANDMARKS = range(11, 33)

bbox_history = {}
angle_history = {}
activity_history = {}

def knee_angle(h, k, a):
    v1 = (h.x-k.x, h.y-k.y)
    v2 = (a.x-k.x, a.y-k.y)
    dot = v1[0]*v2[0] + v1[1]*v2[1]
    mag = math.hypot(*v1) * math.hypot(*v2)
    if mag == 0: return 0
    return math.degrees(math.acos(max(min(dot/mag,1),-1)))

def bbox_moving(hist, th=35):
    if len(hist) < 4: return False
    x1,y1,_,_ = hist[0]
    x2,y2,_,_ = hist[-1]
    return abs(x1-x2)+abs(y1-y2) > th

def body_orientation(box):
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1
    if w > h * 1.25:
        return "horizontal"
    elif h > w * 1.3:
        return "vertical"
    return "unknown"


def is_falling(box, lm):
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1

    # 1️⃣ Strong horizontal check
    horizontal = w > h * 1.4

    # 2️⃣ Floor proximity (hip + shoulder very low)
    ls, rs = lm[11], lm[12]
    lh, rh = lm[23], lm[24]

    shoulder_y = (ls.y + rs.y) / 2
    hip_y = (lh.y + rh.y) / 2

    near_floor = hip_y > 0.80 and shoulder_y > 0.70

    # 3️⃣ Height extremely small compared to width
    flattened = h < w * 0.6

    return horizontal and near_floor and flattened

def detect_activity(frame, bbox, pid):
    x1, y1, x2, y2 = map(int, bbox)
    body = frame[y1:y2, x1:x2]
    if body.size == 0:
        return None

    bbox_history.setdefault(pid, deque(maxlen=10)).append(bbox)

    res = pose.process(cv2.cvtColor(body, cv2.COLOR_BGR2RGB))
    if not res.pose_landmarks:
        return None

    lm = res.pose_landmarks.landmark

    # ---------------- FALLING (TOP PRIORITY) ----------------
    if is_falling(bbox, lm):
        act = "falling"

    else:
        angle = (
            knee_angle(lm[23], lm[25], lm[27]) +
            knee_angle(lm[24], lm[26], lm[28])
        ) / 2

        angle_history.setdefault(pid, deque(maxlen=8)).append(angle)

        moving = bbox_moving(bbox_history[pid])
        leg_move = max(angle_history[pid]) - min(angle_history[pid]) > 15

        if moving and leg_move:
            act = "walking"

        elif angle < 110:
            act = "sitting"

        elif angle > 145:
            act = "standing"

        else:
            row = []
            for i in BODY_LANDMARKS:
                row.extend([lm[i].x, lm[i].y, lm[i].z])
            act = activity_model.predict([row])[0]

    activity_history.setdefault(pid, deque(maxlen=7)).append(act)
    return Counter(activity_history[pid]).most_common(1)[0][0]
