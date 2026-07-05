import numpy as np
import time
import logging

log = logging.getLogger("AI_CORE.ThreatIntelligence")

class PreCrimePredictor:
    """
    Kognitiv jinoyat bashorati moduli.
    Odamning xatti-harakatlaridagi mikroskopik anomaliyalarni topib,
    o'g'irlik yoki sabotajni sodir bo'lishidan oldin aniqlaydi.
    """
    
    def __init__(self):
        # Matematik koeffitsientlar (Og'irliklar)
        self.WEIGHT_SPEED = 0.35
        self.WEIGHT_GAZE = 0.40
        self.WEIGHT_DWELL = 0.25
        
        # Qat'iy chegaralar (Thresholds)
        self.THREAT_THRESHOLD = 75.0 # Xavf 75% dan oshsa signal beradi
        self.MAX_DWELL_TIME = 120.0 # Bir joyda 2 daqiqadan ortiq turish shubhali
        
        # Vaqtinchalik xotira (Har bir odamning trayektoriyasi)
        self.subject_histories = {}

    def update_subject_state(self, subject_id: str, current_pos: tuple, head_angle: float, timestamp: float):
        """Odamning joriy holatini xotiraga yozish va tahlilga tayyorlash."""
        if subject_id not in self.subject_histories:
            self.subject_histories[subject_id] = {
                "positions": [],
                "head_angles": [],
                "first_seen": timestamp,
                "last_seen": timestamp
            }
        
        history = self.subject_histories[subject_id]
        history["positions"].append((current_pos, timestamp))
        history["head_angles"].append((head_angle, timestamp))
        history["last_seen"] = timestamp
        
        # Xotirani ortiqcha to'lib ketishidan saqlash (Oxirgi 30 ta kadrni saqlash)
        if len(history["positions"]) > 30:
            history["positions"].pop(0)
            history["head_angles"].pop(0)

    def calculate_threat_score(self, subject_id: str) -> dict:
        """
        Subyektning tarixiy ma'lumotlari asosida kompleks xavf darajasini hisoblaydi.
        """
        if subject_id not in self.subject_histories:
            return {"threat_score": 0.0, "is_critical": False}
            
        history = self.subject_histories[subject_id]
        
        if len(history["positions"]) < 10:
            # Yeterli ma'lumot yig'ilmagan
            return {"threat_score": 0.0, "is_critical": False}

        # 1. Tezlik anomaliyasini hisoblash (\Delta v)
        pos_start = np.array(history["positions"][0][0])
        pos_end = np.array(history["positions"][-1][0])
        time_diff = history["positions"][-1][1] - history["positions"][0][1]
        
        velocity = np.linalg.norm(pos_end - pos_start) / (time_diff + 1e-6)
        # Agar odam vitrina oldida to'satdan tezlashsa, indeks oshadi
        speed_factor = min(velocity / 50.0, 1.0) * 100 

        # 2. Atrofga alanglash (Gaze Variance - Asabiylik belgisi)
        angles = [a[0] for a in history["head_angles"]]
        angle_variance = np.var(angles)
        # Agar bosh doimiy ravishda keskin turli burchaklarga burilsa (nazoratchi qidirilsa)
        gaze_factor = min(angle_variance / 500.0, 1.0) * 100 

        # 3. Bir joyda qotib turish (Dwell Time)
        dwell_time = history["last_seen"] - history["first_seen"]
        dwell_factor = min(dwell_time / self.MAX_DWELL_TIME, 1.0) * 100

        # Kompleks Xavf Formulasi (Weighted Sum)
        threat_score = (
            (self.WEIGHT_SPEED * speed_factor) +
            (self.WEIGHT_GAZE * gaze_factor) +
            (self.WEIGHT_DWELL * dwell_factor)
        )
        
        is_critical = threat_score >= self.THREAT_THRESHOLD
        
        if is_critical:
            log.warning(f"🚨 POTENSIAL JINOYAT ANIQLANDI! Subyekt: {subject_id}, Xavf: {threat_score:.1f}%")

        return {
            "threat_score": round(threat_score, 2),
            "is_critical": is_critical,
            "metrics": {
                "velocity": round(velocity, 2),
                "gaze_variance": round(angle_variance, 2),
                "dwell_time": round(dwell_time, 1)
            }
        }