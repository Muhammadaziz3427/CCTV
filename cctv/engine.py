"""
<<<<<<< HEAD
engine_v2.py — Next-Gen CCTV AI Core Processing Engine
Fully Autonomous Retail Management & Loss Prevention System
=======
engine.py — Main AI Vision Loop for CCTV Core
Ushbu modul kamera tasvirini tahlil qiladi, odamlar va telefonlarni aniqlaydi,
yuzlarni tanishni amalga oshiradi va natijalarni bazaga yozadi.
>>>>>>> 7dc4e432 (feat: add identity manager, supabase client and update engine logic)
"""

import cv2
import time
import logging
import numpy as np
<<<<<<< HEAD
from datetime import datetime
from typing import Dict, List, Any

# Tizim markazlashtirilgan bazaga (masalan, Supabase) ulanishga tayyor
# from database.supabase_client import SupabaseManager 

try:
    from ultralytics import YOLO
except ImportError:
    raise ImportError("YOLOv8 is strictly required for the Next-Gen Engine. Run 'pip install ultralytics'")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] AI_CORE — %(message)s")
log = logging.getLogger("AI_CORE")

# ═══════════════════════════════════════════════════════════════════════════
# 1. AI Vision Subsystems (Yuz, Skelet va Obyekt)
# ═══════════════════════════════════════════════════════════════════════════

class AIVisionEngine:
    """Tizimning ko'rish va analiz qilish markazi."""
    def __init__(self):
        log.info("Loading Next-Gen AI Models...")
        # 1. Asosiy obyekt va odamlarni kuzatuvchi model (Tracking bilan)
        self.tracker = YOLO("yolov8m.pt") 
        
        # 2. Inson skeleti va harakatlarini tahlil qiluvchi model (Pose Estimation)
        self.pose_model = YOLO("yolov8m-pose.pt")
        
        # 3. Yuz va shaxsni aniq tanish tizimi (Placeholder: InsightFace yoki shunga o'xshash)
        # self.face_recognizer = FaceRecognitionModel() 

    def process_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        """Bitta kadrni to'liq AI tahlilidan o'tkazish."""
        
        # ByteTrack algoritmi orqali odamlarni ID bilan kuzatish
        track_results = self.tracker.track(frame, persist=True, classes=[0], verbose=False)
        
        # Harakatlar tahlili (Telefon ishlatish yoki shubhali harakatlar uchun)
        pose_results = self.pose_model(frame, verbose=False)
        
        return {
            "tracking": track_results[0] if track_results else None,
            "pose": pose_results[0] if pose_results else None
        }

# ═══════════════════════════════════════════════════════════════════════════
# 2. Autonomous Event Managers
# ═══════════════════════════════════════════════════════════════════════════

class BehaviorAnalyzer:
    """Odamlarning xatti-harakatlarini tahlil qiluvchi aqlli modul."""
    
    def __init__(self):
        self.active_phones = {} # ID: start_time
        
    def detect_phone_abuse(self, pose_data, frame_time: float) -> List[dict]:
        alerts = []
        if not pose_data or not pose_data.keypoints:
            return alerts
            
        # YOLO-Pose orqali inson skeleti nuqtalarini (keypoints) olish
        for i, keypoints in enumerate(pose_data.keypoints.data):
            # Agar qo'l (bilak) nuqtalari quloq yoki ko'z hududiga uzoq vaqt yaqin tursa
            # va obyekt xodim bo'lsa, bu haqiqiy telefon ishlatish deb baholanadi.
            is_using_phone = self._analyze_arm_head_angle(keypoints)
            
            person_id = int(pose_data.boxes.id[i]) if pose_data.boxes.id is not None else f"unknown_{i}"
            
            if is_using_phone:
                if person_id not in self.active_phones:
                    self.active_phones[person_id] = frame_time
                duration = frame_time - self.active_phones[person_id]
                
                if duration > 10.0: # 10 soniyadan ortiq telefonga qarasa
                    alerts.append({"person_id": person_id, "duration": duration, "type": "PHONE_ABUSE"})
            else:
                self.active_phones.pop(person_id, None)
                
        return alerts

    def _analyze_arm_head_angle(self, keypoints) -> bool:
        """
        Skelet geometriyasi asosida telefon ishlatilayotganini aniqlash.
        (Matematik trigonometriya qismi bu yerda amalga oshiriladi)
        """
        # Hozircha logikani qisqa ushlab turamiz
        return False 

class LossPreventionEngine:
    """O'g'irlik va noodatiy harakatlarni aniqlovchi modul."""
    def analyze_trajectory(self, tracks) -> None:
        # Mijoz do'kon bo'ylab qanday yuryapti?
        # Agar bitta vitrina oldida uzoq vaqt aylanib yursa (Loitering) -> Security alert!
        pass

# ═══════════════════════════════════════════════════════════════════════════
# 3. Main Central Controller
# ═══════════════════════════════════════════════════════════════════════════

class CentralCCTVController:
    def __init__(self, stream_url: str):
        self.cap = cv2.VideoCapture(stream_url)
        self.ai = AIVisionEngine()
        self.behavior = BehaviorAnalyzer()
        self.loss_prevention = LossPreventionEngine()
        
        # self.db = SupabaseManager() # Bulutga jo'natish uchun
        log.info("System Initialized. Awaiting video feed...")

    def run(self):
        while self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                break
                
            current_time = time.time()
            
            # 1. To'liq AI Tahlil
            ai_data = self.ai.process_frame(frame)
            
            # 2. Xulq-atvor tahlili (Telefon, mijozlarga xizmat ko'rsatish sifati)
            behavior_alerts = self.behavior.detect_phone_abuse(ai_data["pose"], current_time)
            
            # 3. Yo'qotishlarning oldini olish (Mijozlar traektoriyasi)
            if ai_data["tracking"] and ai_data["tracking"].boxes.id is not None:
                self.loss_prevention.analyze_trajectory(ai_data["tracking"])
            
            # 4. Voqealarni ma'lumotlar bazasiga yozish
            for alert in behavior_alerts:
                log.warning(f"ALERT TRIGGERED: {alert['type']} by ID {alert['person_id']} ({alert['duration']:.1f}s)")
                # self.db.insert_event("employee_alerts", alert)
            
            # (Vizualizatsiya qismi serverda emas, faqat test uchun kerak bo'ladi)
            if ai_data["tracking"]:
                annotated_frame = ai_data["tracking"].plot()
                cv2.imshow("Next-Gen Retail AI", annotated_frame)
                
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
        self.cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    # Haqiqiy IP kamera RTSP ssilkasi yoziladi
    engine = CentralCCTVController(stream_url=0)
    engine.run()
=======
from ultralytics import YOLO

import config
from data_store import DataStore
from identity_manager import IdentityManager

# Loglarni sozlash
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] AI_CORE — %(message)s")
log = logging.getLogger("AI_ENGINE")

class AIEngine:
    def __init__(self):
        log.info("AI Tizimi initsializatsiya qilinmoqda...")
        
        # 1. Modellarni yuklash
        self.model = YOLO(config.YOLO_MODEL)
        self.id_manager = IdentityManager()
        
        # 2. Database ulanishi
        self.db = DataStore() 
        
        # 3. Video manbasini ochish
        self.cap = cv2.VideoCapture(config.CAMERA_SOURCE)
        
        # Holatlarni kuzatish
        self.phone_abuse_start = None
        self.last_customer_count_time = time.time()
        
    def is_in_zone(self, box, zone) -> bool:
        """Obyekt berilgan zona (x1, y1, x2, y2) ichida ekanligini tekshiradi."""
        x1, y1, x2, y2 = box
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        zx1, zy1, zx2, zy2 = zone
        return zx1 <= cx <= zx2 and zy1 <= cy <= zy2

    def run(self):
        log.info("Kamera oqimi boshlandi! Dasturni to'xtatish uchun 'q' ni bosing.")
        
        while self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                log.warning("Kadr olinmadi. Kamera uzildi yoki video tugadi.")
                break
            
            frame = cv2.resize(frame, (config.FRAME_WIDTH, config.FRAME_HEIGHT))
            
            # YOLO inference
            results = self.model(frame, verbose=False, conf=config.DETECTION_CONFIDENCE, 
                                 classes=[config.COCO_PERSON_CLASS, config.COCO_CELL_PHONE_CLASS])
            
            cashier_present = False
            phone_in_register = False
            customer_count = 0
            
            # Kadrni tahlil qilish
            for r in results:
                for box in r.boxes:
                    cls = int(box.cls[0])
                    xyxy = box.xyxy[0].tolist()
                    
                    # Agar ODAM topilsa
                    if cls == config.COCO_PERSON_CLASS:
                        # Face Recognition simulyatsiyasi (haqiqiy loyihada bu yerda frame crop qilib yuboriladi)
                        mock_embedding = [0.9, 0.1, 0.8, 0.2, 0.7, 0.3, 0.6, 0.4] 
                        identity = self.id_manager.match_face(mock_embedding)
                        label = f"{identity['name']} ({identity['type']})"
                        
                        if self.is_in_zone(xyxy, config.REGISTER_ZONE):
                            cashier_present = True
                            self._draw_box(frame, xyxy, label, config.COLOR_EMPLOYEE)
                        else:
                            customer_count += 1
                            self._draw_box(frame, xyxy, "CUSTOMER", config.COLOR_CUSTOMER)
                            
                    # Agar TELEFON topilsa
                    elif cls == config.COCO_CELL_PHONE_CLASS:
                        if self.is_in_zone(xyxy, config.REGISTER_ZONE):
                            phone_in_register = True
                            self._draw_box(frame, xyxy, "PHONE", config.COLOR_PHONE)

            # Qoidabuzarlikni tekshirish
            if cashier_present and phone_in_register:
                if self.phone_abuse_start is None:
                    self.phone_abuse_start = time.time()
                elif time.time() - self.phone_abuse_start > config.PHONE_ABUSE_SECONDS:
                    log.warning("QOIDABUZARLIK! Kassir telefondan foydalanmoqda.")
                    self.db.log_event("PHONE_ABUSE", {"zone": "REGISTER"})
                    self.phone_abuse_start = None 
            else:
                self.phone_abuse_start = None

            # Mijozlar soni bazaga
            if time.time() - self.last_customer_count_time > config.CUSTOMER_COUNT_INTERVAL_SECONDS:
                self.db.log_event("CUSTOMER_COUNT_UPDATE", {"count": customer_count})
                self.last_customer_count_time = time.time()

            # GUI
            if config.ENABLE_GUI:
                self._draw_gui_overlays(frame, customer_count)
                cv2.imshow(config.GUI_WINDOW_TITLE, frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                    
        self.cap.release()
        cv2.destroyAllWindows()

    def _draw_box(self, frame, xyxy, label, color):
        x1, y1, x2, y2 = map(int, xyxy)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    def _draw_gui_overlays(self, frame, customer_count):
        zx1, zy1, zx2, zy2 = config.REGISTER_ZONE
        cv2.rectangle(frame, (zx1, zy1), (zx2, zy2), config.COLOR_ZONE, 2)
        cv2.putText(frame, "REGISTER ZONE", (zx1 + 10, zy1 + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, config.COLOR_ZONE, 2)

if __name__ == "__main__":
    app = AIEngine()
    app.run()
>>>>>>> 7dc4e432 (feat: add identity manager, supabase client and update engine logic)
