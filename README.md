# 🤖 Autonomous Smart Warehouse Robot — Complete System Guide

## PROJECT STRUCTURE
```
warehouse_robot/
├── esp32/
│   └── warehouse_robot.ino        ← Arduino IDE sketch (upload to ESP32)
├── vision_server/
│   ├── vision_server.py           ← Flask + OpenCV server (run on laptop)
│   ├── requirements.txt           ← Python dependencies
│   └── debug_zone1/2/3.jpg        ← Auto-generated debug images
└── dashboard/
    └── index.html                 ← Open in browser (no server needed)
```

---

## STEP 1 — HARDWARE WIRING

### Motor Driver (L298N) → ESP32
| L298N Pin | ESP32 GPIO |
|-----------|-----------|
| IN1       | 27        |
| IN2       | 26        |
| IN3       | 25        |
| IN4       | 33        |
| ENA       | 14        |
| ENB       | 12        |
| VCC       | 5V        |
| GND       | GND       |

### Ultrasonic (HC-SR04) → ESP32
| HC-SR04 | ESP32 |
|---------|-------|
| TRIG    | 5     |
| ECHO    | 18    |
| VCC     | 5V    |
| GND     | GND   |

### Touch Sensor → ESP32
| Touch Sensor | ESP32  |
|--------------|--------|
| OUT          | GPIO 4 |
| VCC          | 3.3V   |
| GND          | GND    |

> Note: GPIO4 on ESP32 is also Touch0 (capacitive touch). If using capacitive
> touch directly, no resistor is needed — touch pin with your finger to trigger.

---

## STEP 2 — FIND YOUR IP ADDRESSES

### Your Laptop IP (for ESP32 to call)
```bash
# Windows
ipconfig
# Look for: IPv4 Address . . . . : 192.168.X.X

# Mac/Linux
ifconfig | grep "inet "
# or: ip addr show
```

### Your Phone IP (for IP Webcam stream)
- Open **IP Webcam** app (Android) or **DroidCam**
- Tap **Start Server**
- Note the IP shown: e.g. `192.168.1.101:8080`

> ⚠️ All devices (ESP32, laptop, phone) MUST be on the SAME WiFi network.

---

## STEP 3 — CONFIGURE EACH FILE

### ESP32 (warehouse_robot.ino) — Lines 14–18:
```cpp
const char* WIFI_SSID     = "YOUR_WIFI_SSID";      // ← Your WiFi name
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";  // ← Your WiFi password
const char* LAPTOP_IP     = "192.168.1.100";        // ← Your laptop IP
```

### Python (vision_server.py) — Line 28:
```python
IP_WEBCAM_URL = "http://192.168.1.101:8080/video"  # ← Your phone IP:port/video
```

### Dashboard (index.html) — Line ~310:
```javascript
const SERVER = 'http://localhost:5000';  // ← If browser on same laptop (default OK)
// OR: const SERVER = 'http://192.168.1.100:5000'; // if on different device
```

---

## STEP 4 — PYTHON SERVER SETUP

```bash
# 1. Install Python 3.8+ if not installed
# 2. Navigate to vision_server folder
cd warehouse_robot/vision_server

# 3. Create virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate        # Mac/Linux
# OR: venv\Scripts\activate     # Windows

# 4. Install dependencies
pip install -r requirements.txt

# 5. Verify OpenCV installed
python -c "import cv2; print(cv2.__version__)"
```

---

## STEP 5 — ARDUINO IDE SETUP

```
1. Install Arduino IDE 2.x (https://arduino.cc)
2. Add ESP32 board:
   File → Preferences → Additional Board URLs:
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json

3. Tools → Board Manager → Search "esp32" → Install by Espressif

4. Install libraries (Tools → Manage Libraries):
   - WiFi (built-in with ESP32)
   - HTTPClient (built-in with ESP32)

5. Open warehouse_robot.ino
6. Edit WiFi credentials and laptop IP (see Step 3)
7. Tools → Board → ESP32 Dev Module
8. Tools → Port → (select your COM port)
9. Upload (→)
```

---

## RUN ORDER (EXACT SEQUENCE)

### 1️⃣ Start IP Webcam on Phone
- Open IP Webcam app
- Start server
- Note the URL (e.g. http://192.168.1.101:8080)
- Test in browser: open http://192.168.1.101:8080/video — should see live feed

### 2️⃣ Start Python Vision Server
```bash
cd warehouse_robot/vision_server
python vision_server.py
```
Expected output:
```
==================================================
  Warehouse Robot Vision Server
==================================================
  IP Webcam:   http://192.168.1.101:8080/video
  Flask API:   http://0.0.0.0:5000
==================================================
[STARTUP] Testing camera connection...
[STARTUP] Camera OK! Frame: (480, 640, 3)
```
> If camera fails: fix IP Webcam URL, then restart server.

### 3️⃣ Open Dashboard in Browser
```
Open: warehouse_robot/dashboard/index.html
(Double-click the file OR drag into Chrome)
```
- Server indicator should turn GREEN (online)
- Zones should show PENDING

### 4️⃣ Upload and Run ESP32
- Upload sketch via Arduino IDE
- Open Serial Monitor (115200 baud)
- Touch the touch sensor to start
- Watch robot move and Serial Monitor output

---

## INTEGRATION FLOW (HOW IT ALL CONNECTS)

```
┌─────────────────────────────────────────────────────┐
│  PHONE (IP Webcam)                                  │
│  Streams video → http://192.168.1.101:8080/video    │
└────────────────────────┬────────────────────────────┘
                         │ OpenCV reads stream
                         ▼
┌─────────────────────────────────────────────────────┐
│  LAPTOP (Python Flask + OpenCV)                     │
│  vision_server.py @ port 5000                       │
│  Endpoints:                                         │
│    GET /detect?zone=N  ← ESP32 calls this           │
│    GET /latest         ← Dashboard polls this       │
│    GET /snapshot       ← Debug camera view          │
│    POST /reset         ← Dashboard reset button     │
└────────┬───────────────────────────┬────────────────┘
         │ HTTP GET /detect?zone=N   │ HTTP GET /latest
         │ (ESP32 → Laptop)          │ (Browser → Laptop, every 1.5s)
         ▼                           ▼
┌──────────────────┐    ┌────────────────────────────┐
│  ESP32 ROBOT     │    │  DASHBOARD (index.html)     │
│  - WiFi client   │    │  - Polls /latest endpoint   │
│  - HTTP requests │    │  - Shows zone + PASS/FAIL   │
│  - Motor control │    │  - History log              │
│  - Ultrasonic    │    │  - Auto-updates, no refresh │
│  - Touch start   │    └────────────────────────────┘
└──────────────────┘

FLOW:
  Touch sensor → ESP32 starts
  ESP32 drives to Zone 1
  ESP32 sends GET /detect?zone=1 to laptop
  Flask captures frame from IP Webcam
  OpenCV detects green color
  Returns {"zone":1,"status":"PASS","confidence":0.87}
  Latest result stored in memory
  Dashboard polls /latest every 1.5s
  Dashboard updates Zone 1 → PASS
  Repeat for Zone 2 (circle) and Zone 3 (blue square)
```

---

## CALIBRATION GUIDE

### Turn Duration (TURN_MS)
The ESP32 turns for `TURN_MS` milliseconds. You need to calibrate for 90°:
```
1. Set TURN_MS = 500
2. Upload and test turn
3. If robot turns less than 90° → increase TURN_MS
4. If robot turns more than 90° → decrease TURN_MS
5. Typical range: 500–900ms depending on battery and surface
```

### Forward Duration (FORWARD_MS)
```
Set FORWARD_MS to match your zone spacing:
- 2000ms ≈ 30-40cm (depends on motor speed)
- Adjust MOTOR_SPEED (0-255) to change speed
```

### Touch Sensor Threshold
```cpp
if (touchVal < 40)  // Tune: capacitive touch returns ~10-20 when touched
```
Use Serial Monitor to see raw values: `Touch value: 15`

### OpenCV HSV Ranges
Test with debug images (auto-saved as debug_zone1/2/3.jpg):
```python
# Zone 1 Green: [35,50,50] → [85,255,255]  
# If not detecting: try [40,60,60] → [80,255,200]

# Zone 3 Blue: [100,80,50] → [130,255,255]
# If not detecting: try [90,50,50] → [140,255,255]
```

---

## DEBUG CHECKLIST

### ❌ Camera Not Working
```
1. Open http://[PHONE_IP]:8080/video in laptop browser
   → If no image: phone and laptop on different networks
   → Fix: Connect both to same WiFi

2. Test in Python:
   python -c "import cv2; cap=cv2.VideoCapture('http://192.168.1.101:8080/video'); print(cap.read()[0])"
   → Should print: True

3. Check: IP_WEBCAM_URL uses /video not /shot.jpg for stream
   → Some apps use /video, some use /videofeed — check your app

4. Firewall: Windows Firewall may block port 8080
   → Temporarily disable or add exception

5. Check startup_test.jpg in vision_server/ folder
   → If black/empty: camera stream not working
```

### ❌ ESP32 Not Connecting to WiFi
```
1. Serial Monitor → look for dots: "........."
   After 15 dots, WiFi failed

2. Check: SSID is EXACTLY correct (case-sensitive)
   Check: Password is correct
   Check: Router allows 2.4GHz (ESP32 doesn't support 5GHz)

3. If connected but can't reach server:
   - Ping laptop from another device: ping 192.168.1.100
   - Check LAPTOP_IP in .ino is correct
   - Check Flask is running: visit http://192.168.1.100:5000/status in browser

4. HTTP Error -1 in Serial Monitor:
   - Flask server not started
   - Wrong port (should be 5000)
   - Laptop firewall blocking port 5000
   → Windows: netsh advfirewall firewall add rule name="Flask" dir=in action=allow protocol=TCP localport=5000
```

### ❌ Detection Not Working
```
1. Check debug_zoneX.jpg saved in vision_server/ folder
   → Open the image to see what OpenCV is seeing

2. Zone 1 (Green) not detecting:
   → Not enough green in frame: ensure green object fills >2% of image
   → Wrong lighting: HSV thresholds change with light
   → Adjust lower_green/upper_green in detect_green()

3. Zone 2 (Circle) not detecting:
   → Circle not clear enough: ensure clear circular object
   → Tune param2 (lower = more sensitive): try param2=25
   → Ensure minRadius/maxRadius match your object size

4. Zone 3 (Blue Square) not detecting:
   → Not enough blue: ensure object is clearly blue
   → Object not square enough: aspect ratio check > 0.5
   → Area too small: lower threshold from 1500 to 500
   → Check mask in debug image: should show white on blue areas

5. Test detection manually:
   curl "http://localhost:5000/detect?zone=1"
   → Should return JSON with status
```

### ❌ Dashboard Not Updating
```
1. Check browser console (F12 → Console tab) for errors

2. Common error: "Failed to fetch" → CORS or server offline
   → Ensure vision_server.py is running
   → flask-cors must be installed: pip install flask-cors
   → Check SERVER variable in index.html matches Flask address

3. Dashboard shows OFFLINE (red dot):
   → Python server not running
   → Wrong SERVER address in index.html

4. If Flask runs on different machine than dashboard:
   → Change: const SERVER = 'http://192.168.1.100:5000';
   → Also: open index.html via http:// not file:// (use live server or python -m http.server)

5. Serving dashboard via Python (avoids file:// CORS issues):
   cd warehouse_robot/dashboard
   python -m http.server 8000
   → Open http://localhost:8000
```

### ❌ Motors Not Moving
```
1. Check L298N power: Motor VCC needs separate 6-12V supply (not 3.3V!)
2. Check EN pins are connected to PWM pins (ENA=14, ENB=12)
3. Test motors independently in Serial Monitor by calling moveForward() in setup()
4. If one motor wrong direction: swap IN1/IN2 for that motor
5. If turns wrong direction: swap IN1↔IN3, IN2↔IN4
```

---

## QUICK TEST COMMANDS

```bash
# Test Flask server is running
curl http://localhost:5000/status

# Manually trigger zone detection
curl "http://localhost:5000/detect?zone=1"
curl "http://localhost:5000/detect?zone=2"
curl "http://localhost:5000/detect?zone=3"

# View latest result (what dashboard sees)
curl http://localhost:5000/latest

# View live camera snapshot in browser
http://localhost:5000/snapshot

# Reset system
curl -X POST http://localhost:5000/reset
```

---

## ZONE DETECTION SUMMARY

| Zone | Detection Method | Object Needed | Key Parameter |
|------|-----------------|---------------|---------------|
| 1    | Green color (HSV) | Any green object | HSV: [35-85, 50-255, 50-255] |
| 2    | Hough Circles | Any circular object | minRadius: 20, maxRadius: 200 |
| 3    | Blue square contour | Blue square/rectangle | HSV: [100-130], 4 corners |

---

*Built for robotics hackathon. All code complete and runnable.*
