import numpy as np
import logging

log = logging.getLogger("AI_CORE.Geometry")

class PoseGeometryAnalyzer:
    """
    Dunyoda yagona 'Spatio-Temporal' tahlil uchun skelet geometriyasi yadrosi.
    Kamera burchagi va masofasidan mutlaqo mustaqil ishlaydi (Scale-Invariant).
    """
    
    # YOLOv8 Pose indekslari (COCO formati bo'yicha 17 ta asosiy nuqta)
    NOSE = 0; L_EYE = 1; R_EYE = 2; L_EAR = 3; R_EAR = 4
    L_SHOULDER = 5; R_SHOULDER = 6; L_ELBOW = 7; R_ELBOW = 8
    L_WRIST = 9; R_WRIST = 10; L_HIP = 11; R_HIP = 12

    def __init__(self):
        # Qat'iy matematik chegaralar (Thresholds)
        self.PHONE_ANGLE_THRESHOLD = 115.0  # Tirsakning maksimal yozilish burchagi (gradusda)
        self.WRIST_TO_EAR_RATIO = 0.45      # Bilak va quloq orasidagi maksimal nisbiy masofa
        self.HEAD_DOWNCAST_RATIO = 0.18     # Boshning pastga egilish darajasi

    @staticmethod
    def calculate_angle(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
        """
        Uchta nuqta (p1, p2, p3) o'rtasidagi 2D/3D burchakni topadi (p2 - tirsak/markaz).
        Vektorlar kosinusi yordamida har qanday rakursda aniq ishlaydi.
        """
        v1 = p1 - p2
        v2 = p3 - p2
        
        dot_product = np.dot(v1, v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        
        if norm_v1 == 0 or norm_v2 == 0:
            return 180.0
            
        cos_theta = dot_product / (norm_v1 * norm_v2)
        # NaN (Float hatoliklari) ning oldini olish uchun qiymatni qisib qo'yamiz
        cos_theta = np.clip(cos_theta, -1.0, 1.0) 
        
        return float(np.degrees(np.arccos(cos_theta)))

    def analyze_pose(self, keypoints: np.ndarray) -> dict:
        """
        Berilgan 17 ta skelet nuqtalaridan kompleks xulq-atvor xususiyatlarini ajratib oladi.
        Qaytariladigan ma'lumot Semantic Engine uchun asos bo'ladi.
        """
        features = {
            "is_holding_phone": False,
            "head_gaze_downcast": False,
            "confidence": True
        }
        
        # Agar asosiy qismlar (yelkalar) aniqlanmagan bo'lsa, xato ma'lumot bermaslik uchun rad etiladi
        if keypoints[self.L_SHOULDER][2] < 0.5 or keypoints[self.R_SHOULDER][2] < 0.5:
            features["confidence"] = False
            return features

        # Nuqtalarni faqat X, Y koordinatalari bo'yicha vektor shaklida ajratib olish
        kpts = {
            'nose': keypoints[self.NOSE][:2],
            'l_ear': keypoints[self.L_EAR][:2],
            'r_ear': keypoints[self.R_EAR][:2],
            'l_shoulder': keypoints[self.L_SHOULDER][:2],
            'r_shoulder': keypoints[self.R_SHOULDER][:2],
            'l_elbow': keypoints[self.L_ELBOW][:2],
            'r_elbow': keypoints[self.R_ELBOW][:2],
            'l_wrist': keypoints[self.L_WRIST][:2],
            'r_wrist': keypoints[self.R_WRIST][:2]
        }

        # 1. Kameradan mustaqil masofa o'lchovi (Scale Normalization)
        # Barcha masofalar odamning yelka kengligiga nisbatan o'lchanadi. 
        # Shu sababli odam kameraga yaqin yoki uzoq bo'lsa ham aniqlik buzilmaydi.
        shoulder_width = np.linalg.norm(kpts['l_shoulder'] - kpts['r_shoulder']) + 1e-6

        # 2. Qo'l trigonometriyasi (Tirsak burchagi va bilak masofasi)
        l_arm_angle = self.calculate_angle(kpts['l_shoulder'], kpts['l_elbow'], kpts['l_wrist'])
        r_arm_angle = self.calculate_angle(kpts['r_shoulder'], kpts['r_elbow'], kpts['r_wrist'])

        l_wrist_to_ear = np.linalg.norm(kpts['l_wrist'] - kpts['l_ear']) / shoulder_width
        r_wrist_to_ear = np.linalg.norm(kpts['r_wrist'] - kpts['r_ear']) / shoulder_width

        # MANTIQ: Agar qo'l ma'lum burchak ostida egilgan bo'lsa va bilak quloqqa/yuzga yaqinlashsa
        if (l_arm_angle < self.PHONE_ANGLE_THRESHOLD and l_wrist_to_ear < self.WRIST_TO_EAR_RATIO) or \
           (r_arm_angle < self.PHONE_ANGLE_THRESHOLD and r_wrist_to_ear < self.WRIST_TO_EAR_RATIO):
            features["is_holding_phone"] = True

        # 3. 3D Bosh egilishi (Gaze Downcast Heuristics)
        # Burun va yelka o'rtasidagi vertikal Y-o'qi masofasini tekshiramiz
        shoulder_center = (kpts['l_shoulder'] + kpts['r_shoulder']) / 2.0
        nose_to_shoulder_y = kpts['nose'][1] - shoulder_center[1] 
        
        # Agar burun yelka chizig'iga nisbatan sezilarli pastga tushsa, bosh egilgan deb baholanadi
        if nose_to_shoulder_y > (shoulder_width * self.HEAD_DOWNCAST_RATIO):
            features["head_gaze_downcast"] = True

        return features