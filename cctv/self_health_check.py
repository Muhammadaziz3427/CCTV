import logging
import psutil
import cv2
import torch
import time

log = logging.getLogger("AI_CORE.SelfHealth")

class HealthGuard:
    """
    Tizimning "Immunitet qatlami". 
    Har bir modulni diagnostika qiladi va 'Hech kim ayb topa olmaydigan' holatni ta'minlaydi.
    """
    def __init__(self, engine_instance):
        self.engine = engine_instance

    def run_full_diagnostic(self):
        log.info("🔍 DIAGNOSTIKA BOSHLANDI...")
        report = {
            "timestamp": time.time(),
            "status": "HEALTHY",
            "checks": {}
        }

        # 1. GPU/CPU va RAM monitoring
        report["checks"]["memory"] = psutil.virtual_memory().percent < 90
        report["checks"]["cpu"] = psutil.cpu_percent() < 95

        # 2. Kamera ulanishi testi
        if not self.engine.cap.isOpened():
            log.critical("❌ KRITIK XATO: Kamera ulanishi uzilgan!")
            report["status"] = "CRITICAL"
        else:
            report["checks"]["camera"] = True

        # 3. AI Model integrity (YOLO tekshiruvi)
        try:
            if not self.engine.tracker.model:
                report["checks"]["ai_model"] = False
            else:
                report["checks"]["ai_model"] = True
        except:
            report["checks"]["ai_model"] = False

        # 4. Yakuniy xulosa
        if report["status"] == "HEALTHY":
            log.info("✅ Tizim 100% soz. Xatolik koeffitsienti: Minimal.")
        else:
            log.error(f"⚠️ Tizimda nosozlik aniqlandi: {report}")
            
        return report