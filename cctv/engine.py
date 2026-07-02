"""
engine.py — CCTV AI Core Processing Engine (entry point).

Architecture overview
─────────────────────
  ┌──────────────────────────────────────────────────────┐
  │  VideoSource   ← camera / file / synthetic fallback  │
  │       ↓                                              │
  │  YOLODetector  ← ultralytics YOLOv8/v11              │
  │       ↓                                              │
  │  ┌────────────────────────────────────┐              │
  │  │  BusinessLogicPipeline             │              │
  │  │  ├─ EmployeeTracker               │              │
  │  │  ├─ PhoneAbuseDetector            │              │
  │  │  └─ CustomerSecurityMonitor       │              │
  │  └────────────────────────────────────┘              │
  │       ↓                                              │
  │  DataStore → SQLite + JSON log                       │
  │       ↓                                              │
  │  Visualiser  ← CLI dashboard + optional cv2 window   │
  └──────────────────────────────────────────────────────┘

Run
───
  python engine.py                   # default camera
  python engine.py --source 0        # USB webcam index 0
  python engine.py --source video.mp4
  python engine.py --source rtsp://192.168.1.100:554/stream
  python engine.py --no-gui          # headless / server mode
"""

import argparse
import logging
import math
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

# Local modules — must be importable from the same directory.
import config
from data_store import DataStore

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("engine")

# ---------------------------------------------------------------------------
# Try importing ultralytics (optional import so the fallback path can still
# run without GPU-heavy deps if we are in synthetic mode only).
# ---------------------------------------------------------------------------
try:
    from ultralytics import YOLO as _YOLO
    _YOLO_AVAILABLE = True
except ImportError:
    _YOLO_AVAILABLE = False
    log.warning("ultralytics not installed — YOLO detection disabled.  "
                "Install via:  pip install ultralytics")


# ═══════════════════════════════════════════════════════════════════════════
# VideoSource — camera / file / synthetic fallback
# ═══════════════════════════════════════════════════════════════════════════

class VideoSource:
    """
    Wraps OpenCV VideoCapture with an automatic fallback chain:
      1. Try `primary` source (camera index / RTSP / file path).
      2. Try each path in config.FALLBACK_SOURCES in order.
      3. Fall back to synthetic matrix frames (no hardware required).
    """

    def __init__(self, primary: str | int = config.CAMERA_SOURCE) -> None:
        self._cap: Optional[cv2.VideoCapture] = None
        self._synthetic: bool = False
        self._frame_counter: int = 0
        self._open(primary)

    def _open(self, source: str | int) -> None:
        """Try to open `source`, then fallbacks, then synthetic."""
        candidates = [source] + list(config.FALLBACK_SOURCES)
        for src in candidates:
            log.info("Attempting video source: %s", src)
            cap = cv2.VideoCapture(src)
            if cap.isOpened():
                # Verify we can actually read a frame.
                ok, _ = cap.read()
                if ok:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
                    self._cap = cap
                    log.info("Video source opened: %s", src)
                    return
                cap.release()
            log.warning("Could not open source: %s", src)

        # All sources failed — use synthetic frames.
        log.warning("No real video source available — switching to SYNTHETIC mode.")
        self._synthetic = True

    def read(self) -> Tuple[bool, np.ndarray]:
        """Return (success, frame) — always succeeds in synthetic mode."""
        if self._synthetic:
            return True, self._make_synthetic_frame()

        ok, frame = self._cap.read()
        if not ok:
            # End of video file — loop back.
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
        if ok:
            frame = cv2.resize(frame, (config.FRAME_WIDTH, config.FRAME_HEIGHT))
        return ok, frame

    def _make_synthetic_frame(self) -> np.ndarray:
        """
        Generate a dark 'matrix-style' frame with animated green blobs
        representing people, so the business logic has something to track.
        """
        self._frame_counter += 1
        frame = np.zeros((config.FRAME_HEIGHT, config.FRAME_WIDTH, 3), dtype=np.uint8)

        # Scrolling green 'digital rain' effect.
        t = self._frame_counter * 0.05
        for col in range(0, config.FRAME_WIDTH, 20):
            brightness = int(40 + 40 * math.sin(t + col * 0.1))
            for row in range(0, config.FRAME_HEIGHT, 20):
                if (row // 20 + self._frame_counter // 5) % 5 == 0:
                    cv2.putText(
                        frame, chr(0x30A0 + (self._frame_counter + col + row) % 96),
                        (col, row + 15), cv2.FONT_HERSHEY_PLAIN, 0.6,
                        (0, brightness, 0), 1,
                    )

        # Animate 3 'person' blobs.
        blobs = [
            (int(150 + 100 * math.sin(t * 0.7)), 300),
            (int(480 + 80  * math.cos(t * 0.5)), 280),
            (int(750 + 60  * math.sin(t * 0.9 + 1)), 320),
        ]
        for (bx, by) in blobs:
            # Body rectangle.
            cv2.rectangle(frame, (bx - 25, by - 70), (bx + 25, by + 60),
                          (0, 180, 0), 2)
            # Head circle.
            cv2.circle(frame, (bx, by - 90), 20, (0, 150, 0), 2)

        # Overlay watermark.
        cv2.putText(frame, "SYNTHETIC MODE — no camera detected",
                    (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 200), 1)
        return frame

    def release(self) -> None:
        if self._cap:
            self._cap.release()

    @property
    def is_synthetic(self) -> bool:
        return self._synthetic


# ═══════════════════════════════════════════════════════════════════════════
# YOLODetector
# ═══════════════════════════════════════════════════════════════════════════

class Detection:
    """Lightweight struct for a single object detection."""
    __slots__ = ("class_id", "confidence", "x1", "y1", "x2", "y2")

    def __init__(self, class_id: int, confidence: float,
                 x1: int, y1: int, x2: int, y2: int) -> None:
        self.class_id   = class_id
        self.confidence = confidence
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2

    @property
    def cx(self) -> int:
        return (self.x1 + self.x2) // 2

    @property
    def cy(self) -> int:
        return (self.y1 + self.y2) // 2

    def center_distance(self, other: "Detection") -> float:
        return math.hypot(self.cx - other.cx, self.cy - other.cy)


class YOLODetector:
    """
    Wraps the Ultralytics YOLO model.
    Falls back to a simple colour-blob detector when YOLO is unavailable.
    """

    def __init__(self) -> None:
        self._model = None
        if _YOLO_AVAILABLE:
            log.info("Loading YOLO model: %s", config.YOLO_MODEL)
            self._model = _YOLO(config.YOLO_MODEL)
            log.info("YOLO model loaded.")
        else:
            log.warning("Running WITHOUT YOLO — using mock blob detections.")

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Return a list of Detection objects for the given frame."""
        if self._model is not None:
            return self._detect_yolo(frame)
        return self._detect_mock(frame)

    def _detect_yolo(self, frame: np.ndarray) -> List[Detection]:
        results = self._model(
            frame,
            conf=config.DETECTION_CONFIDENCE,
            classes=[config.COCO_PERSON_CLASS, config.COCO_CELL_PHONE_CLASS],
            verbose=False,
        )
        detections: List[Detection] = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                detections.append(Detection(
                    class_id=int(box.cls[0]),
                    confidence=float(box.conf[0]),
                    x1=x1, y1=y1, x2=x2, y2=y2,
                ))
        return detections

    def _detect_mock(self, frame: np.ndarray) -> List[Detection]:
        """
        Lightweight mock: find green-ish blobs in the synthetic frames,
        or return a small set of simulated detections in real frames.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        detections: List[Detection] = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < 800:
                continue
            x, y, w, h = cv2.boundingRect(c)
            detections.append(Detection(
                class_id=config.COCO_PERSON_CLASS,
                confidence=0.6,
                x1=x, y1=y, x2=x + w, y2=y + h,
            ))
        return detections[:6]   # cap to avoid noise


# ═══════════════════════════════════════════════════════════════════════════
# Face Recognition helpers (mock)
# ═══════════════════════════════════════════════════════════════════════════

def _extract_mock_embedding(frame: np.ndarray, box: Detection) -> np.ndarray:
    """
    Extract an 8-d normalised feature vector from a face/person crop.

    In production, replace with a real face embedding model
    (e.g. InsightFace, DeepFace, FaceNet).  Here we use the colour
    histogram of the bounding-box region as a cheap proxy.
    """
    crop = frame[box.y1:box.y2, box.x1:box.x2]
    if crop.size == 0:
        return np.zeros(8)

    # Resize to small patch, compute per-channel mean stats.
    patch = cv2.resize(crop, (32, 64))
    feat  = np.zeros(8)
    for c in range(3):
        ch           = patch[:, :, c].astype(float) / 255.0
        feat[c * 2]  = ch.mean()
        feat[c * 2 + 1] = ch.std()
    # Pad remaining dims with a simple edge measure.
    gray_p    = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY).astype(float) / 255.0
    feat[6]   = gray_p.mean()
    feat[7]   = gray_p.std()

    norm = np.linalg.norm(feat)
    return feat / norm if norm > 0 else feat


def _cosine_similarity(a: np.ndarray, b: List[float]) -> float:
    """Cosine similarity between a numpy vector and a plain list."""
    bv   = np.array(b, dtype=float)
    norm = np.linalg.norm(bv)
    bv   = bv / norm if norm > 0 else bv
    return float(np.dot(a, bv))


def _point_in_zone(cx: int, cy: int,
                   zone: Tuple[int, int, int, int]) -> bool:
    x1, y1, x2, y2 = zone
    return x1 <= cx <= x2 and y1 <= cy <= y2


# ═══════════════════════════════════════════════════════════════════════════
# A. Employee Tracker
# ═══════════════════════════════════════════════════════════════════════════

class EmployeeTracker:
    """
    Matches detected persons against the known employee roster using
    mock face embeddings.  Tracks presence time and cashier-zone coverage.
    """

    def __init__(self, store: DataStore) -> None:
        self._store  = store
        # {employee_id: total_presence_seconds}
        self._presence: Dict[str, float] = {}
        # {employee_id: timestamp of last 'seen' frame}
        self._last_seen: Dict[str, float] = {}
        # {employee_id: bool — was in register zone last frame?}
        self._in_register: Dict[str, bool] = {}
        self._last_event_time: Dict[str, float] = {}
        self._log_interval = 10.0   # seconds between EMPLOYEE_PRESENT events

        # Normalise stored embeddings once.
        self._profiles = []
        for emp in config.EMPLOYEES:
            vec  = np.array(emp["mock_embedding"], dtype=float)
            norm = np.linalg.norm(vec)
            self._profiles.append({**emp, "_vec": vec / norm if norm > 0 else vec})

    def process(
        self, frame: np.ndarray, persons: List[Detection], now: float
    ) -> Tuple[List[str], List[Detection]]:
        """
        Match persons to employees.

        Returns
        -------
        visible_ids : list[str]
            employee_ids that were matched in this frame.
        matched_detections : list[Detection]
            The Detection objects that were identified as employees
            (same order as visible_ids).  Used by downstream components
            to exclude employees from customer counts.
        """
        visible_ids: List[str]        = []
        matched_dets: List[Detection] = []

        for det in persons:
            emb  = _extract_mock_embedding(frame, det)
            best_sim, best_emp = 0.0, None

            for profile in self._profiles:
                sim = _cosine_similarity(emb, profile["_vec"])
                if sim > best_sim:
                    best_sim, best_emp = sim, profile

            if best_sim >= config.FACE_SIMILARITY_THRESHOLD and best_emp:
                eid = best_emp["employee_id"]
                visible_ids.append(eid)
                matched_dets.append(det)
                in_reg = _point_in_zone(det.cx, det.cy, config.REGISTER_ZONE)

                # Accumulate presence.
                if eid in self._last_seen:
                    delta = now - self._last_seen[eid]
                    self._presence[eid] = self._presence.get(eid, 0.0) + delta
                self._last_seen[eid]    = now
                self._in_register[eid]  = in_reg

                # Emit periodic EMPLOYEE_PRESENT event.
                last = self._last_event_time.get(eid, 0.0)
                if now - last >= self._log_interval:
                    self._store.log_event("EMPLOYEE_PRESENT", {
                        "employee_id":      eid,
                        "employee_name":    best_emp["name"],
                        "role":             best_emp["role"],
                        "in_register_zone": in_reg,
                        "presence_seconds": round(self._presence.get(eid, 0.0), 1),
                        "similarity_score": round(best_sim, 3),
                    })
                    self._last_event_time[eid] = now

        # Check for cashier missing from register.
        cashiers = [p for p in self._profiles if p["role"] == "Cashier"]
        for cashier in cashiers:
            eid = cashier["employee_id"]
            if eid not in visible_ids:
                last = self._last_event_time.get(f"missing_{eid}", 0.0)
                if now - last >= 60.0:   # emit at most once per minute
                    self._store.log_event("CASHIER_MISSING", {
                        "employee_id":   eid,
                        "employee_name": cashier["name"],
                        "last_seen_ago": round(now - self._last_seen.get(eid, now), 1),
                    })
                    self._last_event_time[f"missing_{eid}"] = now

        return visible_ids, matched_dets

    @property
    def presence_summary(self) -> Dict[str, float]:
        return dict(self._presence)

    @property
    def in_register(self) -> Dict[str, bool]:
        return dict(self._in_register)


# ═══════════════════════════════════════════════════════════════════════════
# B. Phone Abuse Detector
# ═══════════════════════════════════════════════════════════════════════════

class PhoneAbuseDetector:
    """
    Detects when an employee holds a cell phone for longer than the
    configured threshold and emits a PHONE_ABUSE event.
    """

    def __init__(self, store: DataStore) -> None:
        self._store = store
        # {employee_id: continuous_phone_start_time}
        self._phone_since: Dict[str, float] = {}
        self._abuse_logged: Dict[str, bool]  = {}

    def process(self, phones: List[Detection],
                persons: List[Detection],
                visible_employee_ids: List[str],
                frame: np.ndarray,
                now: float) -> None:
        """
        For each phone detection, check if it is close to a visible employee.
        """
        # Map employee_id → person detection (reuse visible_employee_ids ordering).
        # We pair by index; in a full implementation this would use tracked IDs.
        emp_person_pairs: List[Tuple[str, Detection]] = [
            (eid, persons[i])
            for i, eid in enumerate(visible_employee_ids)
            if i < len(persons)
        ]

        phones_near_employee: Dict[str, bool] = {}
        for phone_det in phones:
            for eid, person_det in emp_person_pairs:
                dist = phone_det.center_distance(person_det)
                if dist <= config.PHONE_PROXIMITY_PIXELS:
                    phones_near_employee[eid] = True

        # Update timers and check threshold.
        # First, clear timers for employees who are no longer visible in this
        # frame — the phone detection chain is broken and must restart from zero.
        for eid in list(self._phone_since.keys()):
            if eid not in visible_employee_ids:
                self._phone_since.pop(eid, None)
                self._abuse_logged.pop(eid, None)

        for eid in visible_employee_ids:
            has_phone = phones_near_employee.get(eid, False)

            if has_phone:
                if eid not in self._phone_since:
                    self._phone_since[eid]  = now
                    self._abuse_logged[eid] = False
                duration = now - self._phone_since[eid]

                if duration >= config.PHONE_ABUSE_SECONDS and not self._abuse_logged[eid]:
                    emp_info = next(
                        (e for e in config.EMPLOYEES if e["employee_id"] == eid), {}
                    )
                    self._store.log_event("PHONE_ABUSE", {
                        "employee_id":            eid,
                        "employee_name":          emp_info.get("name", eid),
                        "phone_duration_seconds": round(duration, 1),
                        "severity":               "WARNING",
                    })
                    self._abuse_logged[eid] = True   # one event per episode
            else:
                # Phone gone — reset timer so next pick-up starts fresh.
                self._phone_since.pop(eid, None)
                self._abuse_logged.pop(eid, None)

    def phone_duration(self, employee_id: str) -> float:
        """Seconds the given employee has been continuously holding a phone."""
        if employee_id in self._phone_since:
            return time.time() - self._phone_since[employee_id]
        return 0.0


# ═══════════════════════════════════════════════════════════════════════════
# C. Customer & Security Monitor
# ═══════════════════════════════════════════════════════════════════════════

class CustomerSecurityMonitor:
    """
    Counts customers in the customer zone and checks detected faces
    against the blacklist.
    """

    def __init__(self, store: DataStore) -> None:
        self._store        = store
        self._last_count_event: float  = 0.0
        self._blacklist_cooldown: Dict[str, float] = {}  # {bl_id: last_logged_time}
        self._current_count: int = 0

    def process(
        self,
        frame: np.ndarray,
        persons: List[Detection],
        visible_employee_ids: List[str],
        matched_employee_detections: List[Detection],
        now: float,
    ) -> int:
        """
        Returns the true customer count in the customer zone.

        Parameters
        ----------
        matched_employee_detections :
            Detection objects that EmployeeTracker confirmed as employees.
            These are excluded from the customer count even when standing
            inside the customer zone.
        """
        # Build a set of (cx, cy) centers belonging to identified employees
        # so we can exclude them from the customer tally.
        employee_centers = {(d.cx, d.cy) for d in matched_employee_detections}

        customer_count = 0
        for det in persons:
            if not _point_in_zone(det.cx, det.cy, config.CUSTOMER_ZONE):
                continue
            if (det.cx, det.cy) in employee_centers:
                continue   # this person is an identified employee, not a customer
            customer_count += 1

        self._current_count = customer_count

        # Periodic customer count event.
        if now - self._last_count_event >= config.CUSTOMER_COUNT_INTERVAL_SECONDS:
            zone_area = (
                (config.CUSTOMER_ZONE[2] - config.CUSTOMER_ZONE[0]) *
                (config.CUSTOMER_ZONE[3] - config.CUSTOMER_ZONE[1])
            )
            density = round(self._current_count / max(zone_area, 1) * 10000, 4)
            self._store.log_event("CUSTOMER_COUNT_UPDATE", {
                "customer_count":         self._current_count,
                "customer_density_score": density,
                "zone":                   "CUSTOMER_ZONE",
            })
            self._last_count_event = now

        # Blacklist check.
        for det in persons:
            emb = _extract_mock_embedding(frame, det)
            for entry in self._store.blacklist:
                sim = _cosine_similarity(emb, entry["mock_embedding"])
                if sim >= config.BLACKLIST_SIMILARITY_THRESHOLD:
                    bl_id = entry["blacklist_id"]
                    last  = self._blacklist_cooldown.get(bl_id, 0.0)
                    if now - last >= 30.0:   # re-alert at most every 30 s
                        self._store.log_event("BLACKLIST_SPOTTED", {
                            "blacklist_id":    bl_id,
                            "alias":           entry.get("alias", "UNKNOWN"),
                            "risk_level":      entry.get("risk_level", "HIGH"),
                            "reason":          entry.get("reason", ""),
                            "similarity_score": round(sim, 3),
                            "location_x":      det.cx,
                            "location_y":      det.cy,
                        })
                        log.warning("⚠ BLACKLIST SPOTTED: %s (sim=%.2f)",
                                    entry.get("alias"), sim)
                        self._blacklist_cooldown[bl_id] = now

        return self._current_count

    @property
    def current_count(self) -> int:
        return self._current_count


# ═══════════════════════════════════════════════════════════════════════════
# Visualiser — draws on frame and prints CLI dashboard
# ═══════════════════════════════════════════════════════════════════════════

class Visualiser:
    """Handles all output: OpenCV window and CLI dashboard."""

    def __init__(self, enable_gui: bool = config.ENABLE_GUI) -> None:
        self._gui = enable_gui and self._check_display()
        if self._gui:
            cv2.namedWindow(config.GUI_WINDOW_TITLE, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(config.GUI_WINDOW_TITLE,
                             config.FRAME_WIDTH, config.FRAME_HEIGHT)

    @staticmethod
    def _check_display() -> bool:
        """Detect whether a display server is available."""
        # On Linux, check $DISPLAY; on other OSes, assume available.
        if os.name == "posix":
            return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        return True

    def annotate(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        visible_employee_ids: List[str],
        phone_detections: List[Detection],
        phone_detector: "PhoneAbuseDetector",
        customer_count: int,
        employee_tracker: "EmployeeTracker",
    ) -> np.ndarray:
        """Draw bounding boxes, zone overlays and labels on the frame."""
        out = frame.copy()

        # Zone overlays.
        for zone, label in [
            (config.REGISTER_ZONE, "Kassa 1"),
            (config.CUSTOMER_ZONE, "Customer Zone"),
        ]:
            cv2.rectangle(out, (zone[0], zone[1]), (zone[2], zone[3]),
                          config.COLOR_ZONE, 1)
            cv2.putText(out, label, (zone[0] + 4, zone[1] + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, config.COLOR_ZONE, 1)

        # Person boxes.
        for i, det in enumerate(detections):
            if det.class_id != config.COCO_PERSON_CLASS:
                continue
            eid   = visible_employee_ids[i] if i < len(visible_employee_ids) else None
            color = config.COLOR_EMPLOYEE if eid else config.COLOR_CUSTOMER
            cv2.rectangle(out, (det.x1, det.y1), (det.x2, det.y2), color, 2)

            if eid:
                emp = next((e for e in config.EMPLOYEES
                            if e["employee_id"] == eid), {})
                label = f"{emp.get('name', eid)} ({emp.get('role', '')})"
                ph_dur = phone_detector.phone_duration(eid)
                if ph_dur >= 1.0:
                    label += f" 📱{ph_dur:.0f}s"
            else:
                label = "Customer"

            cv2.putText(out, label, (det.x1, det.y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, config.COLOR_TEXT, 1)

        # Phone boxes.
        for det in phone_detections:
            cv2.rectangle(out, (det.x1, det.y1), (det.x2, det.y2),
                          config.COLOR_PHONE, 2)
            cv2.putText(out, "PHONE", (det.x1, det.y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, config.COLOR_PHONE, 1)

        # HUD.
        hud_lines = [
            f"Customers: {customer_count}",
            f"Employees visible: {len(visible_employee_ids)}",
            datetime.utcnow().strftime("UTC %H:%M:%S"),
        ]
        for j, line in enumerate(hud_lines):
            cv2.putText(out, line, (10, 20 + j * 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, config.COLOR_TEXT, 1)

        return out

    def show(self, frame: np.ndarray) -> bool:
        """Show frame in window. Returns False if user pressed 'q'."""
        if not self._gui:
            return True
        cv2.imshow(config.GUI_WINDOW_TITLE, frame)
        return cv2.waitKey(1) & 0xFF != ord("q")

    def print_dashboard(
        self,
        frame_num: int,
        fps: float,
        customer_count: int,
        visible_employee_ids: List[str],
        presence: Dict[str, float],
        store: DataStore,
    ) -> None:
        """Print a concise CLI status table."""
        now_str  = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        divider  = "─" * 60
        print(f"\n{divider}")
        print(f"  CCTV AI Engine  |  Frame #{frame_num}  |  {fps:.1f} FPS  |  {now_str}")
        print(divider)
        print(f"  Customers in zone : {customer_count}")
        print(f"  Employees visible : {', '.join(visible_employee_ids) or 'NONE'}")
        print("  Presence totals:")
        for emp in config.EMPLOYEES:
            eid  = emp["employee_id"]
            secs = presence.get(eid, 0.0)
            mins = secs / 60
            print(f"    {emp['name']:<20}  {mins:5.1f} min")
        counts = store.get_event_counts()
        if counts:
            print("  Event counts (session):")
            for etype, cnt in sorted(counts.items()):
                print(f"    {etype:<28} {cnt:>4}")
        print(divider)

    def cleanup(self) -> None:
        if self._gui:
            cv2.destroyAllWindows()


# ═══════════════════════════════════════════════════════════════════════════
# Main Engine Loop
# ═══════════════════════════════════════════════════════════════════════════

class CCTVEngine:
    """
    Orchestrates all sub-systems in the main processing loop.
    """

    def __init__(self, source: str | int = config.CAMERA_SOURCE,
                 enable_gui: bool = config.ENABLE_GUI) -> None:
        log.info("Initialising CCTV AI Core Engine…")
        self.store      = DataStore()
        self.video      = VideoSource(source)
        self.detector   = YOLODetector()
        self.emp_track  = EmployeeTracker(self.store)
        self.phone_det  = PhoneAbuseDetector(self.store)
        self.cust_mon   = CustomerSecurityMonitor(self.store)
        self.vis        = Visualiser(enable_gui)

        self._running     = False
        self._frame_count = 0
        self._fps_window: List[float] = []

    def run(self) -> None:
        """
        Start the main processing loop.  Runs until the user presses 'q'
        (GUI mode) or sends SIGINT (Ctrl-C).
        """
        log.info("Engine started.  Press Ctrl-C to stop.")
        if self.video.is_synthetic:
            log.info("Running in SYNTHETIC MODE — no real camera connected.")

        self._running    = True
        t_loop_start     = time.time()

        try:
            while self._running:
                t_frame_start = time.time()
                ok, frame     = self.video.read()
                if not ok:
                    log.warning("Frame read failed — retrying…")
                    time.sleep(0.05)
                    continue

                self._frame_count += 1
                now = time.time()

                # ── YOLO inference ──────────────────────────────────────
                all_dets  = self.detector.detect(frame)
                persons   = [d for d in all_dets
                             if d.class_id == config.COCO_PERSON_CLASS]
                phones    = [d for d in all_dets
                             if d.class_id == config.COCO_CELL_PHONE_CLASS]

                # ── A: Employee tracking ────────────────────────────────
                visible_emp_ids, matched_emp_dets = self.emp_track.process(
                    frame, persons, now
                )

                # ── B: Phone abuse ──────────────────────────────────────
                self.phone_det.process(phones, persons, visible_emp_ids,
                                       frame, now)

                # ── C: Customer & security ──────────────────────────────
                customer_count = self.cust_mon.process(
                    frame, persons, visible_emp_ids, matched_emp_dets, now
                )

                # ── Visualisation ───────────────────────────────────────
                annotated = self.vis.annotate(
                    frame, persons, visible_emp_ids, phones,
                    self.phone_det, customer_count, self.emp_track,
                )
                keep_running = self.vis.show(annotated)
                if not keep_running:
                    log.info("User pressed 'q' — shutting down.")
                    break

                # ── CLI dashboard ───────────────────────────────────────
                if self._frame_count % config.CLI_REFRESH_EVERY_N_FRAMES == 0:
                    fps = self._calc_fps()
                    self.vis.print_dashboard(
                        self._frame_count, fps, customer_count,
                        visible_emp_ids, self.emp_track.presence_summary,
                        self.store,
                    )

                # ── FPS throttle ────────────────────────────────────────
                if config.TARGET_FPS > 0:
                    elapsed = time.time() - t_frame_start
                    sleep   = (1.0 / config.TARGET_FPS) - elapsed
                    if sleep > 0:
                        time.sleep(sleep)

        except KeyboardInterrupt:
            log.info("Keyboard interrupt — stopping engine.")
        finally:
            self._shutdown()

    def _calc_fps(self) -> float:
        now = time.time()
        self._fps_window.append(now)
        # Keep a rolling 5-second window.
        cutoff = now - 5.0
        self._fps_window = [t for t in self._fps_window if t >= cutoff]
        n = len(self._fps_window)
        return (n - 1) / 5.0 if n > 1 else 0.0

    def _shutdown(self) -> None:
        log.info("Shutting down…")
        self.video.release()
        self.vis.cleanup()
        # Final presence summary to DB.
        for eid, secs in self.emp_track.presence_summary.items():
            emp = next((e for e in config.EMPLOYEES
                        if e["employee_id"] == eid), {})
            self.store.log_event("SESSION_SUMMARY", {
                "employee_id":      eid,
                "employee_name":    emp.get("name", eid),
                "total_presence_s": round(secs, 1),
                "total_frames":     self._frame_count,
            })
        log.info("Session saved.  Total frames processed: %d", self._frame_count)


# ═══════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CCTV AI Core Processing Engine — Retail Monitor",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--source", default=config.CAMERA_SOURCE,
        help="Camera index (0,1,…), RTSP URL, or video file path."
    )
    parser.add_argument(
        "--no-gui", action="store_true",
        help="Disable OpenCV display (headless / server mode)."
    )
    parser.add_argument(
        "--model", default=config.YOLO_MODEL,
        help="YOLO model filename (e.g. yolov8n.pt, yolov8s.pt)."
    )
    parser.add_argument(
        "--confidence", type=float, default=config.DETECTION_CONFIDENCE,
        help="YOLO confidence threshold."
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # Override config from CLI args.
    try:
        source = int(args.source)
    except (ValueError, TypeError):
        source = args.source

    config.YOLO_MODEL             = args.model
    config.DETECTION_CONFIDENCE   = args.confidence

    engine = CCTVEngine(
        source=source,
        enable_gui=not args.no_gui,
    )
    engine.run()


if __name__ == "__main__":
    main()
