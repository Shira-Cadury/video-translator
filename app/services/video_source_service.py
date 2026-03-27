import os
import uuid
import shutil
import logging

logger = logging.getLogger(__name__)

class VideoSourceService:
    def __init__(self, storage_path: str):
        self.video_storage = os.path.join(storage_path, "video")
        os.makedirs(self.video_storage, exist_ok=True)
        
        
    def save_uploaded_file(self, upload_file) -> str:
        file_id = str(uuid.uuid4())[:8]
        
        _, ext = os.path.splitext(upload_file.filename)
        filename = f"{file_id}{ext}"
        file_path = os.path.join(self.video_storage, filename)
        
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(upload_file.file, buffer)
            
            logger.info(f"[SOURCE SERVICE] File saved successfully: {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"[SOURCE SERVICE] Failed to save file: {e}")
            raise Exception("Could not save the uploaded file to storage.")
        
        
    def is_url(self, source: str) -> bool:
        return source.startswith("http://") or source.startswith("https://")            
        
