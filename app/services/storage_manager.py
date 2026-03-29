import shutil
import logging
import os

logger = logging.getLogger(__name__)

class StorageManager:
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        os.makedirs(self.storage_path, exist_ok=True)
        
        
    def get_disk_usage_percent(self) -> float:
        try:
            total, used, free = shutil.disk_usage(storage_path)
            usage_per = (used / total) * 100
            return usage_per
        except Exception as e:
            logger.error(f"[STORAGE] Error checking disk usage: {e}")
            return 0.0
        
        
    def delete_oldest_files(self, limit_percent=85):
        while self.get_disk_usage_percent() > limit_percent:
            files = [os.path.join(self.storage_path, f) for f in os.listdir(self.storage_path)]
            
            if not files:
                logger.warning("[STORAGE] Disk is full but no files found to delete!")
                break
            
            oldest_file = min(files, key=os.path.getatime)
            
            try:
                os.remove(oldest_file)
                logger.info(f"[STORAGE] LRU Policy: Deleted oldest file: {oldest_file}")
            except Exception as e:
                logger.error(f"[STORAGE] Failed to delete {oldest_file}")
                break
            
            
    def cleanup_if_needed(self):
        if self.get_disk_usage_percent() > 85:
            logger.info("[STORAGE] Disk usage high, starting cleanup")
            self.delete_oldest_files(85)            
            
            
    def touch_file(self, file_path):
        if os.path.exists(file_path):
            os.utime(file_path, None)        