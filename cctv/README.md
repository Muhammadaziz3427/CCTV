# CCTV AI Core Processing Engine

A standalone Python engine for retail store video intelligence — object detection, employee tracking, phone-abuse monitoring, and customer security — designed to run locally and push events to an external database (Supabase, PostgreSQL, etc.) later.

---

## Project Structure

```
cctv/
├── engine.py          — Entry point & main processing loop
├── config.py          — All tunable parameters (zones, employees, thresholds…)
├── data_store.py      — SQLite + JSON event persistence layer
├── requirements.txt   — Python dependencies
├── blacklist.json     — Auto-created on first run (mock blacklist entries)
├── local_telemetry.db — Auto-created SQLite database (events log)
└── live_stream_events.json — Auto-created NDJSON event log
```

---

## Quick Start

### 1 — Install dependencies

```bash
cd cctv
pip install -r requirements.txt
```

> **GPU note:** `ultralytics` pulls in PyTorch automatically. For CUDA acceleration, install the CUDA-enabled torch wheel *before* running pip install. CPU inference works out of the box but is slower.

### 2 — Run the engine

```bash
# Default: USB webcam index 0  (falls back to synthetic frames if no camera)
python engine.py

# Specific webcam index
python engine.py --source 1

# IP camera over RTSP
python engine.py --source rtsp://admin:password@192.168.1.100:554/stream

# Local video file (for testing)
python engine.py --source sample_video.mp4

# Headless / server mode (no GUI window)
python engine.py --no-gui

# Use a larger, more accurate model
python engine.py --model yolov8s.pt

# All options
python engine.py --help
```

---

## Fallback Chain (Cloud / No-Camera Environments)

If the engine cannot open any real video source, it automatically enters **SYNTHETIC MODE** — generating animated matrix-style frames that simulate moving people. This lets the engine run continuously on servers or CI pipelines without any hardware.

Priority order:
1. Primary source (`--source` / `CAMERA_SOURCE` in config.py)
2. `sample_video.mp4` in the cctv/ directory
3. Synthetic matrix frames ← always available

---

## Business Logic Pipeline

Every processed frame runs three parallel routines:

### A — Employee Role & Attendance Tracking
- Compares face embeddings (mock, or real model drop-in) against the `EMPLOYEES` list in `config.py`.
- Logs `EMPLOYEE_PRESENT` events every 10 seconds per visible employee.
- Tracks time spent in the **Kassa 1 / Register zone**.
- Logs `CASHIER_MISSING` if no cashier is detected for > 60 seconds.
- Accumulates total presence time per employee.

### B — Phone Abuse Detection
- Uses YOLO to detect `cell phone` objects.
- Associates phones to employees by proximity (pixel distance).
- If an employee holds a phone for ≥ 5 continuous seconds → `PHONE_ABUSE` event.

### C — Customer & Security Monitoring
- Counts persons in the customer zone.
- Emits `CUSTOMER_COUNT_UPDATE` events every 30 seconds.
- Matches all face crops against `blacklist.json`.
- Emits `BLACKLIST_SPOTTED` if a match exceeds the similarity threshold.

---

## Event Schema

All events written to `local_telemetry.db` (SQLite) and `live_stream_events.json` (NDJSON) follow this structure — ready to push to Supabase/PostgreSQL:

```json
{
  "timestamp":  "2025-07-02T14:32:01.123Z",
  "event_type": "PHONE_ABUSE",
  "details": {
    "employee_id":            "EMP001",
    "employee_name":          "Alice Jansen",
    "phone_duration_seconds": 6.2,
    "severity":               "WARNING"
  }
}
```

| `event_type`            | Trigger |
|-------------------------|---------|
| `EMPLOYEE_PRESENT`      | Employee visible (every 10 s) |
| `CASHIER_MISSING`       | Cashier not seen for > 60 s |
| `PHONE_ABUSE`           | Phone held ≥ 5 s by employee |
| `CUSTOMER_COUNT_UPDATE` | Every 30 s |
| `BLACKLIST_SPOTTED`     | Blacklisted face detected |
| `SESSION_SUMMARY`       | On engine shutdown |

---

## Configuring Employees

Edit the `EMPLOYEES` list in `config.py`. Each entry's `mock_embedding` is an 8-dimensional vector used for matching. To use a real face recognition model (e.g. InsightFace, DeepFace):

1. Replace `_extract_mock_embedding()` in `engine.py` with your model's embedding function.
2. Store real 128-d (or 512-d) face vectors in each employee's `mock_embedding` field.
3. Adjust `FACE_SIMILARITY_THRESHOLD` as needed.

---

## Configuring Zones

Zone coordinates are `(x1, y1, x2, y2)` in pixels at the `FRAME_WIDTH × FRAME_HEIGHT` resolution:

```python
# config.py
REGISTER_ZONE  = (600, 200, 960, 540)   # Cash register area
CUSTOMER_ZONE  = (0,   0,   600, 540)   # Shop floor
```

To find the right values for your camera: run the engine with a test video, note the pixel coordinates of the areas in the GUI window, and update `config.py`.

---

## Integration Bridge (Supabase / PostgreSQL)

Set these two variables in `config.py` to enable remote push:

```python
REMOTE_API_ENDPOINT = "https://xyz.supabase.co/rest/v1/telemetry_events"
REMOTE_API_KEY      = "your-anon-key"
```

The `DataStore.log_event()` method is the single callsite — replace its body with an HTTP POST to forward events to any backend without touching the engine logic.

---

## Blacklist Schema (`blacklist.json`)

```json
[
  {
    "blacklist_id": "BL001",
    "alias": "Suspect-Alpha",
    "risk_level": "HIGH",
    "mock_embedding": [0.95, 0.05, 0.85, 0.15, 0.75, 0.25, 0.65, 0.35],
    "reason": "Prior shoplifting incident (2024-11-03)"
  }
]
```

---

## Requirements

- Python 3.10+
- `opencv-python` ≥ 4.9
- `ultralytics` ≥ 8.0 (YOLOv8/v11, downloads model weights automatically on first run)
- `numpy` ≥ 1.26
- Standard library: `sqlite3`, `json`, `threading`, `logging`, `argparse`
