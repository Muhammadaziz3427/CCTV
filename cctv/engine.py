import cv2
import time
from ultralytics import YOLO
from supabase import create_client

# Modullar (Katalog tuzilishingizga qarab import qiling)
from modules.eometry_analyzer import PoseGeometryAnalyzer
from modules.threat_intelligence import PreCrimePredictor
from modules.supabase_client import CloudDataStore
from modules.offline_cache import EdgeCacheManager
from modules.advanced_sensors import SensorMatrix
from modules.safety_monitor import SafetyMonitor
from modules.shelf_monitor import ShelfMonitor
from modules.deterrence_system import DeterrenceSystem
from modules.face_identity import IdentityManager

class MasterCCTVEngine:
    def __init__(self, stream_url=0):
        # AI Modellari
        self.tracker = YOLO("yolov8m.pt")
        self.pose = YOLO("yolov8m-pose.pt")
        
        # Initsializatsiya
        self.geo = PoseGeometryAnalyzer()
        self.pre_crime = PreCrimePredictor()
        self.cloud = CloudDataStore()
        self.cache = EdgeCacheManager()
        self.sensors = SensorMatrix()
        
        # Yangi Modullar
        self.safety = SafetyMonitor()
        self.shelf = ShelfMonitor(shelves_config={"zone_1": [0, 0, 100, 100]})
        self.deterrence = DeterrenceSystem()
        self.identity = IdentityManager(supabase_client=self.cloud.supabase)
        
        self.cap = cv2.VideoCapture(stream_url)
        self.frame_count = 0
        
        # Bazadan xodimlarni yuklash
        self.identity.load_employees_from_db()
        self.known_ids = {}

    def run(self):
        print("🚀 Tizim ishga tushdi: To'liq avtonom rejim...")
        
        while self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret: break
            self.frame_count += 1
            
            # 1. Vizual Tahlil (Track + Pose)
            track_res = self.tracker.track(frame, persist=True)
            pose_res = self.pose(frame)
            
            # 2. Xavfsizlik va Bashorat sikli
            for i, box in enumerate(track_res[0].boxes):
                p_id = int(box.id) if box.id is not None else i
                
                # Face ID (Caching)
                if p_id not in self.known_ids:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    self.known_ids[p_id] = self.identity.identify_person(frame[y1:y2, x1:x2])
                
                person_name = self.known_ids[p_id]
                
                # Geometriya va Xavf
                pose_data = pose_res[0].keypoints.data[i]
                geo_features = self.geo.analyze_pose(pose_data)
                threat = self.pre_crime.calculate_threat_score(str(p_id))
                
                # Yiqilishni tekshirish
                fall = self.safety.detect_fall(p_id, pose_data)
                if fall: self.cloud.send_alert(f"{person_name} - {fall}")

                # Qoidabuzarlik
                if geo_features["is_holding_phone"] or threat["is_critical"]:
                    self.cloud.log_critical_event(frame, person_name, 5.0)
                    self.deterrence.trigger_warning(threat["score"])
            
            # 3. Biznes tahlili
            if self.frame_count % 100 == 0:
                for alert in self.shelf.check_stock(frame):
                    self.cloud.send_alert(alert)
            
            # 4. Vizualizatsiya
            cv2.imshow("Smart Retail Matrix - OPERATIONAL", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
            
        self.cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    engine = MasterCCTVEngine()
    engine.run()