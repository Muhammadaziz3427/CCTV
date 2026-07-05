"""
supabase_client.py — Asynchronous Cloud Sync Layer for CCTV AI Engine.
Inherits from the base DataStore to guarantee local-first telemetry storage.
"""

import threading
import queue
import logging
import time
from typing import Dict, Any
from datetime import datetime

from supabase import create_client, Client

import config
from data_store import DataStore

log = logging.getLogger(__name__)

class CloudDataStore(DataStore):
    """
    Drop-in replacement for the native DataStore.
    Intercepts calls to log_event, flushes them to local storage,
    and dispatches them asynchronously to Supabase.
    """
    def __init__(self, *args, **kwargs) -> None:
        # data_store.py dagi konfiguratsiyalarni avtomatik initsializatsiya qilish
        super().__init__(
            db_path=config.SQLITE_DB_PATH,
            json_path=config.JSON_LOG_PATH,
            blacklist_path=config.BLACKLIST_PATH
        )
        
        # Supabase API sozlamalari
        self._url = config.SUPABASE_URL
        self._key = config.SUPABASE_KEY
        
        if "BU_YERGA" in self._url or not self._url.startswith("http"):
            log.warning("Supabase credentials are using default mock placeholders!")
            
        self.supabase: Client = create_client(self._url, self._key)
        self.sync_queue: queue.Queue = queue.Queue()
        
        # Orqa fondagi uzatuvchi daemon thread'ni ishga tushirish
        self._start_cloud_worker()
        log.info("CloudDataStore initialised. Supabase thread bridge activated.")

    def log_event(self, event_type: str, details: Dict[str, Any]) -> None:
        """Saves telemetry locally with 0 latency, then enqueues for Supabase."""
        # 1. Local SQLite + Local NDJSON faylga darhol yozish (Sizning kodingiz)
        super().log_event(event_type, details)
        
        # 2. Cloud payload yaratish (Supabase real-time qidiruv uchun qulay formatda)
        cloud_payload = {
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "event_type": event_type,
            "details": details,
            "branch_id": "BRANCH_001"  # Markazlashtirilgan do'kon ID raqami
        }
        
        # 3. Queue'ga otish
        self.sync_queue.put(cloud_payload)

    def _start_cloud_worker(self) -> None:
        worker = threading.Thread(target=self._sync_loop, daemon=True)
        worker.name = "SupabaseSyncWorker"
        worker.start()

    def _sync_loop(self) -> None:
        """Thread worker that processes the queue and handles connection drops."""
        while True:
            payload = self.sync_queue.get()
            success = False
            retries = 0
            max_retries = 3
            
            while not success and retries < max_retries:
                try:
                    # Supabase DB ga ma'lumot kiritish
                    self.supabase.table("telemetry_events").insert(payload).execute()
                    log.debug("Cloud sync transaction complete: %s", payload["event_type"])
                    success = True
                except Exception as e:
                    retries += 1
                    log.error("Cloud sync exception (Attempt %d/%d): %s", retries, max_retries, e)
                    if retries < max_retries:
                        time.sleep(2 ** retries)  # Exponential backoff (2s, 4s, 8s)
            
            if not success:
                log.critical("Data persistence failure: Event %s dropped from sync queue.", payload["event_type"])
                
            self.sync_queue.task_done()

if __name__ == "__main__":
    # Mustaqil test qilish qismi
    logging.basicConfig(level=logging.INFO)
    log.info("Testing CloudDataStore pipeline...")
    
    db = CloudDataStore()
    db.log_event("PHONE_ABUSE", {"employee_id": "EMP001", "phone_duration_seconds": 7.4, "zone": "REGISTER"})
    
    # Ma'lumot serverga yetib borishi uchun biroz kutamiz
    time.sleep(3)
    log.info("Test complete.")