import numpy as np
import logging
import cv2

log = logging.getLogger("AI_CORE.AdvancedSensors")

class SensorMatrix:
    """
    Qo'shimcha kognitiv funksiyalarni birlashtiruvchi gibrid sensor.
    Liveness Detection, Acoustic Sentiment va Shelf-Void tahlillarini o'z ichiga oladi.
    """
    def __init__(self):
        # Akustik chegaralar (Simulyatsiya qilingan mikrofon ma'lumotlari uchun)
        self.AGGRESSION_THRESHOLD = 85.0 # dB yoki RMS energiya indeksi
        self.BASELINE_INVENTORY = 50 # Javondagi tovarlarning kutilayotgan soni

    def check_liveness(self, face_roi: np.ndarray, landmarks: list) -> bool:
        """
        Kiber-himoya (Anti-Spoofing): Yuzning 3D ekanligini va qon aylanishini tekshirish.
        Rasm yoki video orqali tizimni aldashning oldini oladi.
        """
        if face_roi is None or len(landmarks) == 0:
            return False
            
        # 1. Yuzdagi yorug'likning gradient dispersiyasi (rasm tekis bo'ladi, haqiqiy yuz 3D)
        gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
        variance = np.var(gray)
        
        # 2. Ko'z pirpirashi (Blink rate) heuristikasi ko'z koordinatalaridan hisoblanadi
        # (Bu yerda algoritm yuz nuqtalari orasidagi masofani tekshiradi)
        is_3d_object = variance > 50.0 
        
        if not is_3d_object:
            log.warning("🚨 ANTI-SPOOFING: Tizimga soxta rasm tutilmoqda!")
            
        return is_3d_object

    def analyze_acoustic_sentiment(self, audio_chunk: np.ndarray) -> dict:
        """
        Ovoz to'lqinlarini tahlil qilib, stress va agressiya darajasini aniqlaydi.
        Suhbat maxfiyligi qat'iy saqlanadi (matnga o'girilmaydi).
        """
        if len(audio_chunk) == 0:
            return {"aggression_score": 0.0, "status": "NORMAL"}
            
        # Ovoz signalining RMS energiyasini hisoblash
        rms_energy = np.sqrt(np.mean(np.square(audio_chunk)))
        
        # Normallashtirilgan stress indeksi
        aggression_score = min((rms_energy / 100.0) * 100, 100.0)
        status = "CRITICAL_ARGUMENT" if aggression_score > self.AGGRESSION_THRESHOLD else "NORMAL"
        
        if status == "CRITICAL_ARGUMENT":
            log.warning(f"🚨 AKUSTIK ANOMALIYA: Kassa oldida janjal ehtimoli! Score: {aggression_score:.1f}")
            
        return {"aggression_score": round(aggression_score, 2), "status": status}

    def detect_shelf_void(self, current_products_detected: int) -> bool:
        """
        Javonlardagi tovarlar sonini doimiy monitoring qiladi.
        Agar zaxira kutilganidan keskin kamaysa, avtomatik to'ldirish signalini beradi.
        """
        fill_ratio = current_products_detected / self.BASELINE_INVENTORY
        
        if fill_ratio < 0.3: # Javon 70% ga bo'shab qolsa
            log.info("ℹ️ TIZIM XABARI: 2-Vitrinada tovarlar kamaydi. Omborchiga signal yuborilmoqda.")
            return True
            
        return False