"""
config.py — Centralized configuration for the CCTV AI Core Processing Engine.

All tuneable parameters, zone definitions, employee profiles, and I/O paths
are declared here so the rest of the codebase never contains magic numbers.
"""

import os
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Camera / Video Source Settings
# ---------------------------------------------------------------------------

# Primary source. Options:
#   0, 1, 2 ...    → local USB webcam / laptop camera index
#   "rtsp://..."   → IP camera RTSP URL
#   "/path/..."    → local video file (mp4, avi, etc.)
CAMERA_SOURCE: str | int = 0

# Fallback: if the primary source cannot be opened, the engine tries these in
# order until one succeeds. If all fail, synthetic matrix frames are generated.
FALLBACK_SOURCES: List[str | int] = [
    "sample_video.mp4",   # bundled sample clip
]

# Target processing resolution (width, height). Smaller → faster inference.
# Laptop veb-kameralari uchun 960x540 tezlik va aniqlik tomonlama eng maqbul o'lchamdir.
FRAME_WIDTH: int  = 960
FRAME_HEIGHT: int = 540

# Frames processed per second (0 = unlimited / as fast as possible).
# 15 FPS protsessorga ortiqcha yuklama bermasdan silliq ishlashni ta'minlaydi.
TARGET_FPS: int = 15

# ---------------------------------------------------------------------------
# YOLO Object Detection
# ---------------------------------------------------------------------------

# YOLOv8/v11 model name. Ultralytics downloads it automatically on first use.
# "yolov8n.pt" is the nano (fastest) variant.
YOLO_MODEL: str = "yolov8n.pt"

# Confidence threshold for accepting a detection.
DETECTION_CONFIDENCE: float = 0.45

# COCO class IDs for detection.
COCO_PERSON_CLASS: int       = 0    # "person"
COCO_CELL_PHONE_CLASS: int   = 67   # "cell phone"

# ---------------------------------------------------------------------------
# Spatial Zone Definitions (x1, y1, x2, y2 in pixel coordinates)
# ---------------------------------------------------------------------------

# "Register / Kassa 1" — Ekranning o'ng tomoni (X: 600 dan 960 gacha)
# Agar yuzingiz shu koordinatalar ichiga kirsa, tizim sizni avtomatik Kassir deb hisoblaydi.
REGISTER_ZONE: Tuple[int, int, int, int] = (600, 0, 960, 540)

# "Customer Zone" — Ekranning chap va markaziy qismi (X: 0 dan 600 gacha)
# Sinab ko'rish uchun noutbuk kamerasining chaprog'ida tursangiz, tizim "Customer: 1" deb hisoblaydi.
CUSTOMER_ZONE: Tuple[int, int, int, int] = (0, 0, 600, 540)

# ---------------------------------------------------------------------------
# Employee Profiles & Face Recognition
# ---------------------------------------------------------------------------

# Kelajakda tizimga real yuz embeddings ma'lumotlarini ulash uchun tayyor ro'yxat.
# Test rejimida birinchi aniqlangan xodim avtomatik ro'yxatdagi birinchisiga (Alice) uylanadi.
EMPLOYEES: List[Dict] = [
    {
        "employee_id": "EMP001",
        "name": "Alice Jansen",
        "role": "Cashier",
        "mock_embedding": [0.9, 0.1, 0.8, 0.2, 0.7, 0.3, 0.6, 0.4],
    },
    {
        "employee_id": "EMP002",
        "name": "Bob de Vries",
        "role": "Manager",
        "mock_embedding": [0.2, 0.8, 0.3, 0.7, 0.4, 0.6, 0.5, 0.5],
    },
    {
        "employee_id": "EMP003",
        "name": "Clara Smit",
        "role": "Stock Associate",
        "mock_embedding": [0.5, 0.5, 0.1, 0.9, 0.2, 0.8, 0.3, 0.7],
    },
]

# Similarity threshold above which a face region is considered a known employee.
FACE_SIMILARITY_THRESHOLD: float = 0.70

# ---------------------------------------------------------------------------
# Business Logic & Rules
# ---------------------------------------------------------------------------

# Telefonda uzluksiz o'tirish limiti (sekund). 5 sekunddan oshsa qoidabuzarlik yoziladi.
PHONE_ABUSE_SECONDS: float = 5.0

# Telefoni odamga tegishli deb hisoblash uchun piksel masofasi.
PHONE_PROXIMITY_PIXELS: int = 120

# ---------------------------------------------------------------------------
# Security & Blacklist Settings
# ---------------------------------------------------------------------------

# Shubhali shaxslar ro'yxati fayli yo'li.
BLACKLIST_PATH: str = os.path.join(os.path.dirname(__file__), "blacklist.json")

# Qora ro'yxatga moslik darajasi.
BLACKLIST_SIMILARITY_THRESHOLD: float = 0.75

# ---------------------------------------------------------------------------
# Data Storage & Local Persistence
# ---------------------------------------------------------------------------

# SQLite ma'lumotlar bazasi fayli yo'li.
SQLITE_DB_PATH: str = os.path.join(os.path.dirname(__file__), "local_telemetry.db")

# JSON formatida log yozib boriladigan fayl yo'li (NDJSON).
JSON_LOG_PATH: str = os.path.join(os.path.dirname(__file__), "live_stream_events.json")

# Mijozlar soni o'zgarmasa ham, har necha sekundda bazaga yangilanish yuborish kerakligi.
CUSTOMER_COUNT_INTERVAL_SECONDS: float = 30.0

# ---------------------------------------------------------------------------
# GUI Visuals & Colors (BGR format for OpenCV)
# ---------------------------------------------------------------------------

# OpenCV vizual oynasini yoqish/o'chirish.
ENABLE_GUI: bool = True

GUI_WINDOW_TITLE: str = "CCTV AI Core — Retail Monitor"

# Kadrdagi ramkalar ranglari (Ko'k, Yashil, Qizil tartibida).
COLOR_EMPLOYEE: Tuple[int, int, int]   = (0,   200, 0  )   # Yashil
COLOR_CUSTOMER: Tuple[int, int, int]   = (200, 200, 0  )   # Havorang / Och ko'k
COLOR_PHONE:    Tuple[int, int, int]   = (0,   0,   255)   # Qizil
COLOR_BLACKLIST: Tuple[int, int, int]  = (0,   0,   200)   # To'q qizil
COLOR_ZONE:      Tuple[int, int, int]  = (255, 128, 0  )   # To'q sariq chiziqlar
COLOR_TEXT:      Tuple[int, int, int]  = (255, 255, 255)   # Oq matn

# Terminal (CLI) interfeysini har nechta kadrda yangilab turish.
CLI_REFRESH_EVERY_N_FRAMES: int = 30

# ---------------------------------------------------------------------------
# Remote API Bridge (Kelajakda Supabase/Veb-saytga ulash qismi)
# ---------------------------------------------------------------------------
# Sayt va ilova tayyor bo'lgach, faqat shu yerga URL va KEY yoziladi.
# Backend API ulangan zahoti local ma'lumotlar real-time bulutga ham ketadi.
REMOTE_API_ENDPOINT: Optional[str] = None   # Masalan: "https://xyz.supabase.co/rest/v1/events"
REMOTE_API_KEY: Optional[str]      = None   # Supabase anon/service_role key