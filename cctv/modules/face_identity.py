import numpy as np
from insightface.app import FaceAnalysis
from supabase import create_client

class IdentityManager:
    def __init__(self, supabase_client):
        self.app = FaceAnalysis(name='buffalo_l')
        self.app.prepare(ctx_id=0, det_size=(640, 640))
        self.db = supabase_client
        self.employees = [] # Baza ma'lumotlari

    def load_employees_from_db(self):
        """Bazadan barcha xodimlarni yuklab olish."""
        response = self.db.table("employees").select("full_name, face_embedding").execute()
        self.employees = response.data
        print(f"🔄 {len(self.employees)} ta xodim bazadan yuklandi.")

    def identify_person(self, face_crop):
        faces = self.app.get(face_crop)
        if not faces: return "Unknown"
        
        current_embedding = faces[0].embedding
        
        best_match = "Unknown"
        max_score = 0
        
        # Bazadagi vektorlar bilan solishtirish
        for emp in self.employees:
            db_embedding = np.array(emp['face_embedding'])
            score = np.dot(current_embedding, db_embedding) / (
                np.linalg.norm(current_embedding) * np.linalg.norm(db_embedding)
            )
            if score > 0.6 and score > max_score: # 0.6 aniqlik chegarasi
                max_score = score
                best_match = emp['full_name']
                
        return best_match