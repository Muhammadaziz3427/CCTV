import sqlite3
import json
import threading
import time
import logging
from typing import Dict, Any

log = logging.getLogger("AI_CORE.EdgeCache")

class EdgeCacheManager:
    """
    Internet uzilganda ma'lumotlarni yo'qotmaslik uchun avtonom mahalliy xotira.
    Tarmoq tiklanishi bilan bulutga (Supabase) sinxronizatsiya qiluvchi mikroxizmat.
    """
    def __init__(self, db_path="local_survival_matrix.db"):
        self.db_path = db_path
        self._init_local_db()
        self.is_online = True
        
        # Orqa fonda sinxronizatsiya qiluvchi avtonom jarayon
        self.sync_thread = threading.Thread(target=self._background_sync_worker, daemon=True)
        self.sync_thread.start()

    def _init_local_db(self):
        """Mahalliy xavfsiz ma'lumotlar bazasini yaratish."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pending_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_type TEXT NOT NULL,
                        payload JSON NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        sync_attempts INTEGER DEFAULT 0
                    )
                """)
                conn.commit()
        except Exception as e:
            log.error(f"Mahalliy xotirani yaratishda kritik xato: {e}")

    def save_event_locally(self, event_type: str, data: Dict[str, Any]):
        """Internet yo'qligida voqeani mahalliy xotiraga muhrlash."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO pending_events (event_type, payload) VALUES (?, ?)",
                    (event_type, json.dumps(data))
                )
                conn.commit()
            log.info(f"Avtonom xotiraga saqlandi: {event_type}")
        except Exception as e:
            log.error(f"Keshga yozishda xatolik: {e}")

    def push_to_supabase(self, event_type: str, payload: dict) -> bool:
        """
        Bu yerda Supabase'ga ma'lumot yuborish mantiqi bo'ladi.
        Agar internet yo'q bo'lsa False qaytaradi.
        """
        # Hozircha bu funksiya SupabaseClient moduliga ulanishi kerak
        # Simulyatsiya:
        try:
            # supabase.table(event_type).insert(payload).execute()
            return True
        except Exception:
            return False

    def _background_sync_worker(self):
        """
        Tizim orqa fonda tinimsiz internet aloqasini tekshiradi va
        uzilish vaqtida yig'ilgan dalillarni bulutga yuklaydi.
        """
        while True:
            time.sleep(10) # Har 10 soniyada tekshirish
            
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    # Yuklanmagan ma'lumotlarni olish
                    cursor.execute("SELECT id, event_type, payload FROM pending_events ORDER BY timestamp ASC LIMIT 50")
                    rows = cursor.fetchall()

                    if not rows:
                        continue

                    for row in rows:
                        event_id, event_type, payload_str = row
                        payload = json.loads(payload_str)
                        
                        # Supabase'ga yuklashga urinish
                        success = self.push_to_supabase(event_type, payload)
                        
                        if success:
                            # Yuklash muvaffaqiyatli bo'lsa, xotiradan tozalash
                            cursor.execute("DELETE FROM pending_events WHERE id = ?", (event_id,))
                            conn.commit()
                            log.info(f"Sinxronizatsiya muvaffaqiyatli: {event_type}")
                        else:
                            # Yuklab bo'lmasa, urinishlar sonini oshirish
                            cursor.execute("UPDATE pending_events SET sync_attempts = sync_attempts + 1 WHERE id = ?", (event_id,))
                            conn.commit()
                            break # Internet haliyam yo'q, keyingi tsiklni kutish

            except Exception as e:
                log.error(f"Sinxronizatsiya jarayonida xatolik: {e}")