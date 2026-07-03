import numpy as np
import config
from typing import List, Dict, Any

class IdentityManager:
    def __init__(self):
        self.employees = config.EMPLOYEES

    def match_face(self, detected_embedding: List[float]) -> Dict[str, Any]:
        best_match = {"id": None, "name": "Unknown", "type": "Visitor", "score": 0}
        for emp in self.employees:
            score = self._cosine_similarity(detected_embedding, emp["mock_embedding"])
            if score > config.FACE_SIMILARITY_THRESHOLD and score > best_match["score"]:
                best_match = {"id": emp["employee_id"], "name": emp["name"], "type": "Employee", "score": score}
        return best_match

    def _cosine_similarity(self, a, b):
        a, b = np.array(a), np.array(b)
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))