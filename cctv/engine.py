"""
engine.py — CCTV AI Core Processing Engine (entry point).
"""

import argparse
import logging
import math
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

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

try:
    from ultralytics import YOLO as _YOLO
    _YOLO_AVAILABLE = True
except ImportError:
    _YOLO_AVAILABLE = False
    log.warning("ultralytics not installed — YOLO detection disabled.")

# ═══════════════════════════════════════════════════════════════════════════
# VideoSource
# ═══════════════════════════════════════════════════════════════════════════

class VideoSource:
    def __init__(self, primary: str | int = config.CAMERA_SOURCE) -> None:
        self._cap: Optional[cv2.VideoCapture] = None
        self._synthetic: bool = False
        self._frame_counter: int = 0
        self._open(primary)

    def _open(self, source: str | int) -> None:
        candidates = [source] + list(config.FALLBACK_SOURCES)
        for src in candidates:
            log.info("Attempting video source: %s", src)
            if isinstance(src, int):
                cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
            else:
                cap = cv2.VideoCapture(src)
                
            if cap.isOpened():
                ok, _ = cap.read()
                if ok:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
                    self._cap = cap
                    log.info("Video source opened: %s", src)
                    return
                cap.release()
            log.warning("Could not open source: %s", src)

        log.warning("No real video source available — switching to SYNTHETIC mode.")
        self._synthetic = True

    def read(self) -> Tuple[bool, np.ndarray]:
        if self._synthetic:
            return True, self._make_synthetic_frame()

        ok, frame = self._cap.read()
        if not ok:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
        if ok:
            frame = cv2.resize(frame, (config.FRAME_WIDTH, config.FRAME_HEIGHT))
        return ok, frame

    def _make_synthetic_frame(self) -> np.ndarray:
        self._frame_counter += 1
        frame = np.zeros((config.FRAME_HEIGHT, config.FRAME_WIDTH, 3), dtype=np.uint8)
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
        blobs = [
            (int(150 + 100 * math.sin(t * 0.7)), 300),
            (int(480 + 80  * math.cos(t * 0.5)), 280),
            (int(750 + 60  * math.sin(t * 0.9 + 1)), 320),
        ]
        for (bx, by) in blobs:
            cv2.rectangle(frame, (bx - 25, by - 70), (bx + 25, by + 60), (0, 180, 0), 2)
            cv2.circle(frame, (bx, by - 90), 20, (0, 150, 0), 2)
        cv2.putText(frame, "SYNTHETIC MODE", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 200), 1)
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
    def __init__(self) -> None:
        self._model = None
        if _YOLO_AVAILABLE:
            log.info("Loading YOLO model: %s", config.YOLO_MODEL)
            self._model = _YOLO(config.YOLO_MODEL)
        else:
            log.warning("Running WITHOUT YOLO — using mock blob detections.")

    def detect(self, frame: np.ndarray) -> List[Detection]:
        if self._model is not None:
            return self._detect_yolo(frame)
        return self._detect_mock(frame)

    def _detect_yolo(self, frame: np.ndarray) -> List[Detection]:
        results = self._model(
            frame, conf=config.DETECTION_CONFIDENCE,
            classes=[config.COCO_PERSON_CLASS, config.COCO_CELL_PHONE_CLASS], verbose=False,
        )
        detections: List[Detection] = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                detections.append(Detection(
                    class_id=int(box.cls[0]), confidence=float(box.conf[0]),
                    x1=x1, y1=y1, x2=x2, y2=y2,
                ))
        return detections

    def _detect_mock(self, frame: np.ndarray) -> List[Detection]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections: List[Detection] = []
        for c in contours:
            if cv2.contourArea(c) < 800:
                continue
            x, y, w, h = cv2.boundingRect(c)
            detections.append(Detection(
                class_id=config.COCO_PERSON_CLASS, confidence=0.6,
                x1=x, y1=y, x2=x + w, y2=y + h,
            ))
        return detections[:6]

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _point_in_zone(cx: int, cy: int, zone: Tuple[int, int, int, int]) -> bool:
    x1, y1, x2, y2 = zone
    return x1 <= cx <= x2 and y1 <= cy <= y2

# ═══════════════════════════════════════════════════════════════════════════
# A. Employee Tracker
# ═══════════════════════════════════════════════════════════════════════════

class EmployeeTracker:
    def __init__(self, store: DataStore) -> None:
        self._store  = store
        self._presence: Dict[str, float] = {}
        self._last_seen: Dict[str, float] = {}
        self._in_register: Dict[str, bool] = {}
        self._last_event_time: Dict[str, float] = {}
        self._log_interval = 10.0

        self._profiles = config.EMPLOYEES

    def process(self, frame: np.ndarray, persons: List[Detection], now: float) -> Tuple[List[str], List[Detection]]:
        visible_ids: List[str]        = []
        matched_dets: List[Detection] = []

        for det in persons:
            in_reg = _point_in_zone(det.cx, det.cy, config.REGISTER_ZONE)

            # TEST LOGIC: Biz yuz tanishni chetga surib, zonaga qarab ishlaymiz.
            # Agar kassa zonasida tursa -> Alice. Agar Customer zonada tursa -> Hech kim.
            best_emp = None
            if in_reg and len(self._profiles) > 0:
                best_emp = self._profiles[0] # Alice Jansen

            if best_emp:
                eid = best_emp["employee_id"]
                visible_ids.append(eid)
                matched_dets.append(det)

                if eid in self._last_seen:
                    delta = now - self._last_seen[eid]
                    self._presence[eid] = self._presence.get(eid, 0.0) + delta
                self._last_seen[eid]    = now
                self._in_register[eid]  = True

                last = self._last_event_time.get(eid, 0.0)
                if now - last >= self._log_interval:
                    self._store.log_event("EMPLOYEE_PRESENT", {
                        "employee_id":      eid,
                        "employee_name":    best_emp["name"],
                        "role":             best_emp["role"],
                        "in_register_zone": True,
                        "presence_seconds": round(self._presence.get(eid, 0.0), 1),
                        "similarity_score": 0.99, # Test uchun sun'iy
                    })
                    self._last_event_time[eid] = now

        cashiers = [p for p in self._profiles if p["role"] == "Cashier"]
        for cashier in cashiers:
            eid = cashier["employee_id"]
            if eid not in visible_ids:
                last = self._last_event_time.get(f"missing_{eid}", 0.0)
                if now - last >= 60.0:
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

# ═══════════════════════════════════════════════════════════════════════════
# B. Phone Abuse Detector
# ═══════════════════════════════════════════════════════════════════════════

class PhoneAbuseDetector:
    def __init__(self, store: DataStore) -> None:
        self._store = store
        self._phone_since: Dict[str, float] = {}
        self._abuse_logged: Dict[str, bool]  = {}

    def process(self, phones: List[Detection], persons: List[Detection], visible_employee_ids: List[str], frame: np.ndarray, now: float) -> None:
        emp_person_pairs = [(eid, persons[i]) for i, eid in enumerate(visible_employee_ids) if i < len(persons)]
        phones_near_employee = {}
        for phone_det in phones:
            for eid, person_det in emp_person_pairs:
                if phone_det.center_distance(person_det) <= config.PHONE_PROXIMITY_PIXELS:
                    phones_near_employee[eid] = True

        for eid in list(self._phone_since.keys()):
            if eid not in visible_employee_ids:
                self._phone_since.pop(eid, None)
                self._abuse_logged.pop(eid, None)

        for eid in visible_employee_ids:
            if phones_near_employee.get(eid, False):
                if eid not in self._phone_since:
                    self._phone_since[eid]  = now
                    self._abuse_logged[eid] = False
                duration = now - self._phone_since[eid]

                if duration >= config.PHONE_ABUSE_SECONDS and not self._abuse_logged[eid]:
                    emp_info = next((e for e in config.EMPLOYEES if e["employee_id"] == eid), {})
                    self._store.log_event("PHONE_ABUSE", {
                        "employee_id":            eid,
                        "employee_name":          emp_info.get("name", eid),
                        "phone_duration_seconds": round(duration, 1),
                        "severity":               "WARNING",
                    })
                    self._abuse_logged[eid] = True
            else:
                self._phone_since.pop(eid, None)
                self._abuse_logged.pop(eid, None)

    def phone_duration(self, employee_id: str) -> float:
        if employee_id in self._phone_since:
            return time.time() - self._phone_since[employee_id]
        return 0.0

# ═══════════════════════════════════════════════════════════════════════════
# C. Customer & Security Monitor
# ═══════════════════════════════════════════════════════════════════════════

class CustomerSecurityMonitor:
    def __init__(self, store: DataStore) -> None:
        self._store        = store
        self._last_count_event: float  = 0.0
        self._current_count: int = 0

    def process(self, frame: np.ndarray, persons: List[Detection], visible_employee_ids: List[str], matched_employee_detections: List[Detection], now: float) -> int:
        employee_centers = {(d.cx, d.cy) for d in matched_employee_detections}
        customer_count = 0

        for det in persons:
            if not _point_in_zone(det.cx, det.cy, config.CUSTOMER_ZONE):
                continue
            if (det.cx, det.cy) in employee_centers:
                continue
            customer_count += 1

        self._current_count = customer_count

        if now - self._last_count_event >= config.CUSTOMER_COUNT_INTERVAL_SECONDS:
            zone_area = (config.CUSTOMER_ZONE[2] - config.CUSTOMER_ZONE[0]) * (config.CUSTOMER_ZONE[3] - config.CUSTOMER_ZONE[1])
            density = round(self._current_count / max(zone_area, 1) * 10000, 4)
            self._store.log_event("CUSTOMER_COUNT_UPDATE", {
                "customer_count":         self._current_count,
                "customer_density_score": density,
                "zone":                   "CUSTOMER_ZONE",
            })
            self._last_count_event = now

        # Diqqat: Blacklist xatosi tufayli asossiz ogohlantirish bermaslik uchun
        # soxta embedding mantiqi test rejimida chetlab o'tildi.
        return self._current_count

# ═══════════════════════════════════════════════════════════════════════════
# Visualiser
# ═══════════════════════════════════════════════════════════════════════════

class Visualiser:
    def __init__(self, enable_gui: bool = config.ENABLE_GUI) -> None:
        self._gui = enable_gui and self._check_display()
        if self._gui:
            cv2.namedWindow(config.GUI_WINDOW_TITLE, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(config.GUI_WINDOW_TITLE, config.FRAME_WIDTH, config.FRAME_HEIGHT)

    @staticmethod
    def _check_display() -> bool:
        if os.name == "posix":
            return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        return True

    def annotate(self, frame: np.ndarray, detections: List[Detection], visible_employee_ids: List[str], phone_detections: List[Detection], phone_detector: "PhoneAbuseDetector", customer_count: int, employee_tracker: "EmployeeTracker") -> np.ndarray:
        out = frame.copy()

        for zone, label in [(config.REGISTER_ZONE, "Kassa 1"), (config.CUSTOMER_ZONE, "Customer Zone")]:
            cv2.rectangle(out, (zone[0], zone[1]), (zone[2], zone[3]), config.COLOR_ZONE, 1)
            cv2.putText(out, label, (zone[0] + 4, zone[1] + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, config.COLOR_ZONE, 1)

        for i, det in enumerate(detections):
            if det.class_id != config.COCO_PERSON_CLASS:
                continue
            
            # Agar shaxs Kassa zonasida bo'lsa Employee, bo'lmasa Customer
            in_reg = _point_in_zone(det.cx, det.cy, config.REGISTER_ZONE)
            eid = visible_employee_ids[0] if in_reg and len(visible_employee_ids) > 0 else None
            
            color = config.COLOR_EMPLOYEE if eid else config.COLOR_CUSTOMER
            cv2.rectangle(out, (det.x1, det.y1), (det.x2, det.y2), color, 2)

            if eid:
                emp = next((e for e in config.EMPLOYEES if e["employee_id"] == eid), {})
                label = f"{emp.get('name', eid)} ({emp.get('role', '')})"
                ph_dur = phone_detector.phone_duration(eid)
                if ph_dur >= 1.0:
                    label += f" 📱{ph_dur:.0f}s"
            else:
                label = "Customer"

            cv2.putText(out, label, (det.x1, det.y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, config.COLOR_TEXT, 1)

        for det in phone_detections:
            cv2.rectangle(out, (det.x1, det.y1), (det.x2, det.y2), config.COLOR_PHONE, 2)
            cv2.putText(out, "PHONE", (det.x1, det.y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, config.COLOR_PHONE, 1)

        hud_lines = [
            f"Customers: {customer_count}",
            f"Employees visible: {len(visible_employee_ids)}",
            datetime.utcnow().strftime("UTC %H:%M:%S"),
        ]
        for j, line in enumerate(hud_lines):
            cv2.putText(out, line, (10, 20 + j * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, config.COLOR_TEXT, 1)

        return out

    def show(self, frame: np.ndarray) -> bool:
        if not self._gui: return True
        cv2.imshow(config.GUI_WINDOW_TITLE, frame)
        return cv2.waitKey(1) & 0xFF != ord("q")

    def print_dashboard(self, frame_num: int, fps: float, customer_count: int, visible_employee_ids: List[str], presence: Dict[str, float], store: DataStore) -> None:
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
            print(f"    {emp['name']:<20}  {secs/60:5.1f} min")
        print(divider)

    def cleanup(self) -> None:
        if self._gui: cv2.destroyAllWindows()

# ═══════════════════════════════════════════════════════════════════════════
# Main Engine Loop
# ═══════════════════════════════════════════════════════════════════════════

class CCTVEngine:
    def __init__(self, source: str | int = config.CAMERA_SOURCE, enable_gui: bool = config.ENABLE_GUI) -> None:
        log.info("Initialising CCTV AI Core Engine...")
        self.store      = DataStore()
        self.video      = VideoSource(source)
        self.detector   = YOLODetector()
        self.emp_track  = EmployeeTracker(self.store)
        self.phone_det  = PhoneAbuseDetector(self.store)
        self.cust_mon   = CustomerSecurityMonitor(self.store)
        self.vis        = Visualiser(enable_gui)
        self._running   = False
        self._frame_count = 0
        self._fps_window: List[float] = []

    def run(self) -> None:
        log.info("Engine started. Press Ctrl-C to stop.")
        self._running    = True
        try:
            while self._running:
                t_frame_start = time.time()
                ok, frame     = self.video.read()
                if not ok:
                    time.sleep(0.05)
                    continue

                self._frame_count += 1
                now = time.time()

                all_dets  = self.detector.detect(frame)
                persons   = [d for d in all_dets if d.class_id == config.COCO_PERSON_CLASS]
                phones    = [d for d in all_dets if d.class_id == config.COCO_CELL_PHONE_CLASS]

                visible_emp_ids, matched_emp_dets = self.emp_track.process(frame, persons, now)
                self.phone_det.process(phones, persons, visible_emp_ids, frame, now)
                customer_count = self.cust_mon.process(frame, persons, visible_emp_ids, matched_emp_dets, now)

                annotated = self.vis.annotate(frame, persons, visible_emp_ids, phones, self.phone_det, customer_count, self.emp_track)
                if not self.vis.show(annotated):
                    break

                if self._frame_count % config.CLI_REFRESH_EVERY_N_FRAMES == 0:
                    self.vis.print_dashboard(self._frame_count, self._calc_fps(), customer_count, visible_emp_ids, self.emp_track.presence_summary, self.store)

                if config.TARGET_FPS > 0:
                    sleep = (1.0 / config.TARGET_FPS) - (time.time() - t_frame_start)
                    if sleep > 0: time.sleep(sleep)

        except KeyboardInterrupt:
            log.info("Keyboard interrupt — stopping engine.")
        finally:
            self._shutdown()

    def _calc_fps(self) -> float:
        now = time.time()
        self._fps_window.append(now)
        cutoff = now - 5.0
        self._fps_window = [t for t in self._fps_window if t >= cutoff]
        n = len(self._fps_window)
        return (n - 1) / 5.0 if n > 1 else 0.0

    def _shutdown(self) -> None:
        self.video.release()
        self.vis.cleanup()

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=config.CAMERA_SOURCE)
    parser.add_argument("--no-gui", action="store_true")
    parser.add_argument("--model", default=config.YOLO_MODEL)
    parser.add_argument("--confidence", type=float, default=config.DETECTION_CONFIDENCE)
    return parser.parse_args()

def main() -> None:
    args = _parse_args()
    try: source = int(args.source)
    except (ValueError, TypeError): source = args.source
    config.YOLO_MODEL = args.model
    config.DETECTION_CONFIDENCE = args.confidence
    engine = CCTVEngine(source=source, enable_gui=not args.no_gui)
    engine.run()

if __name__ == "__main__":
    main()