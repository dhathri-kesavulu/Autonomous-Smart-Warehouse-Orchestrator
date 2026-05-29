"""
Autonomous Smart Warehouse Robot - Vision Server
Flask + OpenCV | Python 3.8+

DETECTION LOGIC:
  Zone 1 → Green color detection (HSV)
  Zone 2 → Circle shape detection (Hough Circles)
  Zone 3 → Blue square detection (contour analysis)

Run: python vision_server.py
API: GET /detect?zone=1  → {"zone":1,"status":"PASS","confidence":0.87}
     GET /status          → server health
     GET /latest          → last detection result (for dashboard polling)
"""

import cv2
import numpy as np
import json
import time
import threading
import requests
from flask import Flask, jsonify, request, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Allow dashboard to fetch from different origin

# ─── Config ──────────────────────────────────────────────────────────────────
IP_WEBCAM_URL  = "http://100.127.233.93:8080/video" 
DASHBOARD_PORT = 5000
FRAME_WIDTH    = 640
FRAME_HEIGHT   = 480

# ─── Shared state ────────────────────────────────────────────────────────────
latest_result = {
    "zone": 0,
    "status": "WAITING",
    "confidence": 0.0,
    "timestamp": time.time(),
    "history": []
}
result_lock = threading.Lock()

# ─── Camera ──────────────────────────────────────────────────────────────────
# Keep a persistent capture instance to avoid repeated expensive reconnects.
cap_lock = threading.Lock()
camera_cap = None


def _init_camera():
    global camera_cap
    if camera_cap is None:
        camera_cap = cv2.VideoCapture(IP_WEBCAM_URL)
        camera_cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        camera_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        camera_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not camera_cap.isOpened():
        print(f"[CAMERA] Cannot open stream {IP_WEBCAM_URL}")
        camera_cap.release() if camera_cap is not None else None
        camera_cap = None
        return False
    return True


def get_frame():
    """Grab a single frame from IP Webcam stream."""
    with cap_lock:
        if not _init_camera():
            return None

        # Skip buffered frames to get the freshest one
        for _ in range(3):
            camera_cap.read()

        ret, frame = camera_cap.read()

        if not ret or frame is None:
            print("[CAMERA] Failed to grab frame, reinitializing camera.")
            if camera_cap is not None:
                camera_cap.release()
            camera_cap = None
            return None

    return frame

def preprocess(frame):
    """Resize and blur for more stable detection."""
    frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
    blurred = cv2.GaussianBlur(frame, (5, 5), 0)
    return frame, blurred

# ─── Zone 1: Green Color Detection ───────────────────────────────────────────
def detect_green(frame):
    """
    Returns (pass:bool, confidence:float)
    PASS if green pixels exceed 2% of frame area.
    """
    _, blurred = preprocess(frame)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

    # Green HSV range (adjust hue if needed: 35–85 is typical green)
    lower_green = np.array([35, 50, 50])
    upper_green = np.array([85, 255, 255])

    mask = cv2.inRange(hsv, lower_green, upper_green)

    # Morphological cleanup
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    green_pixels = cv2.countNonZero(mask)
    total_pixels  = FRAME_WIDTH * FRAME_HEIGHT
    ratio = green_pixels / total_pixels

    print(f"[Zone1] Green ratio: {ratio:.4f} ({green_pixels} px)")

    # Save debug image
    debug = cv2.bitwise_and(frame, frame, mask=mask)
    cv2.imwrite("debug_zone1.jpg", debug)

    threshold = 0.02   # 2% of frame
    confidence = min(ratio / threshold, 1.0)
    return ratio >= threshold, round(confidence, 3)

# ─── Zone 2: Circle Shape Detection ─────────────────────────────────────────
def detect_circle(frame):
    """
    Returns (pass:bool, confidence:float)
    PASS if at least 1 circle detected via Hough Transform.
    """
    _, blurred = preprocess(frame)
    gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)

    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=60,
        param1=100,
        param2=35,
        minRadius=20,
        maxRadius=200
    )

    debug = frame.copy()
    if circles is not None:
        circles = np.uint16(np.around(circles))
        count = len(circles[0])
        print(f"[Zone2] Circles detected: {count}")

        for c in circles[0, :]:
            cv2.circle(debug, (c[0], c[1]), c[2], (0, 255, 0), 2)
            cv2.circle(debug, (c[0], c[1]), 2,    (0, 0, 255), 3)

        cv2.imwrite("debug_zone2.jpg", debug)
        confidence = min(count / 3.0, 1.0)
        return True, round(confidence, 3)
    else:
        print("[Zone2] No circles found.")
        cv2.imwrite("debug_zone2.jpg", debug)
        return False, 0.0

# ─── Zone 3: Blue Square Detection ───────────────────────────────────────────
def detect_blue_square(frame):
    """
    Returns (pass:bool, confidence:float)
    PASS if a blue rectangular/square contour is found.
    """
    _, blurred = preprocess(frame)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

    # Blue HSV range
    lower_blue = np.array([100, 80,  50])
    upper_blue = np.array([130, 255, 255])
    mask = cv2.inRange(hsv, lower_blue, upper_blue)

    # Cleanup
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    debug = frame.copy()
    best_score = 0.0
    found = False

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 1500:   # Ignore tiny blobs
            continue

        perimeter = cv2.arcLength(cnt, True)
        approx    = cv2.approxPolyDP(cnt, 0.04 * perimeter, True)

        if len(approx) == 4:
            # Check squareness: aspect ratio close to 1
            x, y, w, h = cv2.boundingRect(approx)
            aspect = min(w, h) / max(w, h) if max(w, h) > 0 else 0

            if aspect > 0.5:   # Reasonably square
                found = True
                score = aspect * min(area / 5000.0, 1.0)
                best_score = max(best_score, score)
                cv2.drawContours(debug, [approx], -1, (0, 255, 0), 3)
                cv2.putText(debug, f"BLUE SQ {aspect:.2f}", (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

    print(f"[Zone3] Blue square found: {found}, score: {best_score:.3f}")
    cv2.imwrite("debug_zone3.jpg", debug)

    return found, round(best_score, 3)

# ─── Main Detection Dispatcher ───────────────────────────────────────────────
def run_detection(zone: int):
    """Capture frame, run zone-specific detection, return result dict."""
    frame = get_frame()
    if frame is None:
        return {"zone": zone, "status": "ERROR", "confidence": 0.0,
                "message": "Camera unavailable"}

    if zone == 1:
        passed, confidence = detect_green(frame)
    elif zone == 2:
        passed, confidence = detect_circle(frame)
    elif zone == 3:
        passed, confidence = detect_blue_square(frame)
    else:
        return {"zone": zone, "status": "ERROR", "confidence": 0.0,
                "message": f"Unknown zone {zone}"}

    status = "PASS" if passed else "FAIL"
    result = {
        "zone":       zone,
        "status":     status,
        "confidence": confidence,
        "timestamp":  time.time()
    }
    print(f"[RESULT] Zone {zone}: {status} (confidence={confidence})")
    return result

# ─── Flask Routes ─────────────────────────────────────────────────────────────

@app.route("/detect", methods=["GET"])
def detect():
    """ESP32 calls this: GET /detect?zone=1"""
    zone_str = request.args.get("zone", "0")
    try:
        zone = int(zone_str)
    except ValueError:
        return jsonify({"error": "Invalid zone parameter"}), 400

    print(f"\n{'='*40}")
    print(f"[DETECT] Zone {zone} requested")
    print(f"{'='*40}")

    result = run_detection(zone)

    # Update global state for dashboard polling
    with result_lock:
        latest_result.update(result)
        # Append to history (keep last 10)
        history_entry = {
            "zone":      result["zone"],
            "status":    result["status"],
            "confidence": result["confidence"],
            "time":      time.strftime("%H:%M:%S", time.localtime(result["timestamp"]))
        }
        latest_result["history"].append(history_entry)
        latest_result["history"] = latest_result["history"][-10:]

    return jsonify(result)

@app.route("/latest", methods=["GET"])
def latest():
    """Dashboard polls this: GET /latest"""
    with result_lock:
        return jsonify(latest_result)

@app.route("/status", methods=["GET"])
def status():
    """Health check."""
    return jsonify({
        "server": "online",
        "camera": IP_WEBCAM_URL,
        "time":   time.strftime("%H:%M:%S")
    })

@app.route("/reset", methods=["POST"])
def reset():
    """Reset state for a new run."""
    with result_lock:
        latest_result.update({
            "zone": 0, "status": "WAITING",
            "confidence": 0.0,
            "timestamp": time.time(),
            "history": []
        })
    return jsonify({"message": "Reset OK"})

@app.route("/snapshot", methods=["GET"])
def snapshot():
    """Stream a live JPEG snapshot for debug view in browser."""
    frame = get_frame()
    if frame is None:
        return "Camera unavailable", 503
    _, buffer = cv2.imencode(".jpg", frame)
    return Response(buffer.tobytes(), mimetype="image/jpeg")

# ─── Entry Point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  Warehouse Robot Vision Server")
    print("=" * 50)
    print(f"  IP Webcam:   {IP_WEBCAM_URL}")
    print(f"  Flask API:   http://0.0.0.0:{DASHBOARD_PORT}")
    print(f"  Dashboard:   http://localhost:{DASHBOARD_PORT}/latest")
    print("=" * 50)

    # Quick camera check on startup
    print("\n[STARTUP] Testing camera connection...")
    test_frame = get_frame()
    if test_frame is not None:
        print(f"[STARTUP] Camera OK! Frame: {test_frame.shape}")
        cv2.imwrite("startup_test.jpg", test_frame)
    else:
        print("[STARTUP] WARNING: Camera not reachable. Check IP Webcam app.")

    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False, threaded=True)
