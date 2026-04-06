import shutil
import logging
import os

logger = logging.getLogger(__name__)

SUBDIRS = ["video", "audio", "subtitles"]

class StorageManager:
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        os.makedirs(self.storage_path, exist_ok=True)

    def get_disk_usage_percent(self) -> float:
        try:
            total, used, free = shutil.disk_usage(self.storage_path)
            usage_per = (used / total) * 100
            return usage_per
        except Exception as e:
            logger.error(f"[STORAGE] Error checking disk usage: {e}")
            return 0.0

    def _collect_all_files(self) -> list:
        all_files = []
        for subdir in SUBDIRS:
            dir_path = os.path.join(self.storage_path, subdir)
            if not os.path.exists(dir_path):
                continue
            for f in os.listdir(dir_path):
                full_path = os.path.join(dir_path, f)
                if os.path.isfile(full_path):
                    all_files.append(full_path)
        return all_files

    def delete_oldest_files(self, limit_percent=85):
        all_files = self._collect_all_files()
        if not all_files:
            logger.warning("[STORAGE] Disk almost full but no files found to delete!")
            return
        
        all_files.sort(key=os.path.getatime)
         
        for file_path in all_files:

            if self.get_disk_usage_percent() <= limit_percent:
                logger.info(f"[STORAGE] Cleanup finished. Current usage: {self.get_disk_usage_percent():.1f}%")
                break

            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"[STORAGE] LRU Policy: Deleted oldest file: {file_path}")
            except Exception as e:
                logger.error(f"[STORAGE] Failed to delete {file_path}: {e}")
                continue

    def cleanup_if_needed(self):
        usage = self.get_disk_usage_percent()
        if usage > 85:
            logger.info(f"[STORAGE] Disk usage {usage:.1f}%, starting cleanup")
            self.delete_oldest_files(85)

    def touch_file(self, file_path):
        if os.path.exists(file_path):
            os.utime(file_path, None)
