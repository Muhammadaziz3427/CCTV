import json
import os
import cv2
from datetime import datetime

class BlackBoxRecorder:
    """
    Tizimning "Qora qutisi". Har bir kritik qaror uchun dalillarni arxivlaydi.
    Hech kim "Nega bunday qaror qilding?" deb shubha bildira olmaydi.
    """
    def __init__(self, log_dir="black_box_archives"):
        self.log_dir = log_dir
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def record_decision(self, event_type: str, person_id: str, ai_confidence: float, evidence_data: dict, frame: None):
        """
        Kritik qarorni tasdiqlovchi dalillar to'plami.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        record_id = f"{event_type}_{person_id}_{timestamp}"
        
        # 1. Metama'lumotlarni saqlash (Nega bu qaror qabul qilindi?)
        log_payload = {
            "record_id": record_id,
            "timestamp": str(datetime.now()),
            "event_type": event_type,
            "subject_id": person_id,
            "ai_confidence": ai_confidence,
            "reasoning": evidence_data, # Skelet burchaklari, harakat tezligi va h.k.
        }
        
        with open(f"{self.log_dir}/{record_id}.json", "w") as f:
            json.dump(log_payload, f, indent=4)
            
        # 2. Videokadrni saqlash (Dalil sifatida)
        if frame is not None:
            cv2.imwrite(f"{self.log_dir}/{record_id}.jpg", frame)
            
        return record_id