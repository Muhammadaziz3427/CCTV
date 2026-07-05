import time

class SafetyMonitor:
    def __init__(self):
        self.fallen_tracker = {} # {person_id: start_time}

    def detect_fall(self, person_id, pose_keypoints):
        # Skeletdan yelka va tovon koordinatalarini olamiz
        # Agar odam gorizontal holatda va 3 soniyadan ortiq qolsa
        is_horizontal = self._check_horizontal(pose_keypoints)
        
        if is_horizontal:
            if person_id not in self.fallen_tracker:
                self.fallen_tracker[person_id] = time.time()
            elif time.time() - self.fallen_tracker[person_id] > 3:
                return "EMERGENCY_FALL_DETECTED"
        else:
            self.fallen_tracker.pop(person_id, None)
        return None