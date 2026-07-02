"""
config.py — Centralized configuration for the CCTV AI Core Processing Engine.

All tuneable parameters, zone definitions, employee profiles, and I/O paths
are declared here so the rest of the codebase never contains magic numbers.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Camera / Video Source
# ---------------------------------------------------------------------------

# Primary source. Options:
#   0, 1, 2 …    → local USB webcam index
#   "rtsp://…"   → IP camera RTSP URL
#   "/path/…"    → local video file (mp4, avi, etc.)
CAMERA_SOURCE: str | int = 0

# Fallback: if the primary source cannot be opened, the engine tries these in
# order until one succeeds.  If all fail, synthetic matrix frames are generated.
FALLBACK_SOURCES: List[str | int] = [
    "sample_video.mp4",   # bundled sample clip (downloaded at first run if absent)
]

# Target processing resolution (width, height).  Smaller → faster inference.
FRAME_WIDTH: int  = 960
FRAME_HEIGHT: int = 540

# Frames processed per second (0 = unlimited / as fast as possible).
TARGET_FPS: int = 15

# ---------------------------------------------------------------------------
# YOLO Detection
# ---------------------------------------------------------------------------

# YOLOv8/v11 model name.  Ultralytics downloads it automatically on first use.
# "yolov8n.pt" is the nano (fastest) variant; swap for "yolov8s.pt" etc. if
# you have more compute budget.
YOLO_MODEL: str = "yolov8n.pt"

# Confidence threshold for accepting a detection.
DETECTION_CONFIDENCE: float = 0.45

# COCO class IDs we care about.
COCO_PERSON_CLASS: int       = 0    # "person"
COCO_CELL_PHONE_CLASS: int   = 67   # "cell phone"

# ---------------------------------------------------------------------------
# Zone Definitions  (x1, y1, x2, y2 in *pixel* coords at FRAME resolution)
# ---------------------------------------------------------------------------

# "Register / Kassa 1" — the area around the cash register where employees work.
# Adjust these to match the actual camera angle.
REGISTER_ZONE: Tuple[int, int, int, int] = (600, 200, 960, 540)

# Customer zone — the public area of the shop floor.
CUSTOMER_ZONE: Tuple[int, int, int, int] = (0, 0, 600, 540)

# ---------------------------------------------------------------------------
# Employee Profiles
# ---------------------------------------------------------------------------
# Each entry holds mock "face embedding" data.
# In a real deployment, replace `mock_embedding` with a 128-d float vector
# produced by an actual face recognition model.  The engine uses cosine
# similarity, so any fixed-length numeric vector works as a drop-in.
#
# `employee_id`  — stable identifier used in all log events.
# `name`         — human-readable display name.
# `role`         — job title (cashier, manager, stock …).
# `mock_embedding` — 8-dimensional placeholder (normalised on load).

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
# Range: 0.0 (never match) → 1.0 (exact match).  0.70 is a reasonable baseline.
FACE_SIMILARITY_THRESHOLD: float = 0.70

# ---------------------------------------------------------------------------
# Phone Abuse Detection
# ---------------------------------------------------------------------------

# Seconds a phone must be continuously detected near an employee before
# a PHONE_ABUSE event is logged.
PHONE_ABUSE_SECONDS: float = 5.0

# Pixel distance within which a phone box is considered "near" an employee box.
PHONE_PROXIMITY_PIXELS: int = 120

# ---------------------------------------------------------------------------
# Blacklist (Security Monitoring)
# ---------------------------------------------------------------------------
# Path to the JSON file containing blacklisted face "embeddings".
# See data_store.py for the expected schema.
BLACKLIST_PATH: str = os.path.join(os.path.dirname(__file__), "blacklist.json")

# Similarity threshold for a blacklist match.
BLACKLIST_SIMILARITY_THRESHOLD: float = 0.75

# ---------------------------------------------------------------------------
# Data Output
# ---------------------------------------------------------------------------

# SQLite telemetry database path.  The file is created automatically.
SQLITE_DB_PATH: str = os.path.join(os.path.dirname(__file__), "local_telemetry.db")

# JSON event log path.  Events are appended as newline-delimited JSON (NDJSON).
JSON_LOG_PATH: str = os.path.join(os.path.dirname(__file__), "live_stream_events.json")

# How often (seconds) to emit a CUSTOMER_COUNT_UPDATE event even if count is stable.
CUSTOMER_COUNT_INTERVAL_SECONDS: float = 30.0

# ---------------------------------------------------------------------------
# GUI / CLI
# ---------------------------------------------------------------------------

# Show OpenCV window when a display is available.  Set False to force headless.
ENABLE_GUI: bool = True

# Window title.
GUI_WINDOW_TITLE: str = "CCTV AI Core — Retail Monitor"

# Colours (BGR for OpenCV).
COLOR_EMPLOYEE: Tuple[int, int, int]  = (0,   200, 0  )   # green
COLOR_CUSTOMER: Tuple[int, int, int]  = (200, 200, 0  )   # cyan-ish
COLOR_PHONE:    Tuple[int, int, int]  = (0,   0,   255)   # red
COLOR_BLACKLIST:Tuple[int, int, int]  = (0,   0,   200)   # dark red
COLOR_ZONE:     Tuple[int, int, int]  = (255, 128, 0  )   # orange
COLOR_TEXT:     Tuple[int, int, int]  = (255, 255, 255)   # white

# CLI table refresh rate (lines between dashboard prints).
CLI_REFRESH_EVERY_N_FRAMES: int = 30

# ---------------------------------------------------------------------------
# Integration / API Bridge (future)
# ---------------------------------------------------------------------------
# When set, the engine will attempt to POST events to this URL in addition to
# writing them locally.  Leave as None to disable remote push.
REMOTE_API_ENDPOINT: Optional[str] = None   # e.g. "https://xyz.supabase.co/rest/v1/events"
REMOTE_API_KEY: Optional[str]      = None   # Bearer / anon key for Supabase etc.
