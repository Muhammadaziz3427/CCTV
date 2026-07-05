import os

class DeterrenceSystem:
    def trigger_warning(self, threat_level):
        if threat_level > 0.8:
            # Tizim ovozli faylni ijro etadi yoki dinamikka signal yuboradi
            os.system("play sounds/warning_alert.mp3") 
            return "AUDIO_WARNING_PLAYED"