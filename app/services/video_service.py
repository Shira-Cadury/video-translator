import yt_dlp
import os
import logging
import shutil
from app.config import STORAGE_PATH

logger = logging.getLogger(__name__)

MAX_DURATION_SEC = 7200  

class VideoService:
    def __init__(self):
        self.audio_path = os.path.join(STORAGE_PATH, "audio")
        self.video_path = os.path.join(STORAGE_PATH, "video")

        for path in [self.audio_path, self.video_path]:
            os.makedirs(path, exist_ok=True)

    def _get_common_opts(self):
        node_path = shutil.which('node')
        return {
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'javascript_executor': node_path or 'node', 
        }

    def _extract_info(self, url: str) -> dict | None:
        try:
            with yt_dlp.YoutubeDL(self._get_common_opts()) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as e:
            logger.error(f"[YOUTUBE] Failed to extract info: {e}")
            return None

    def download_audio(self, url, info: dict = None, storage_manager=None):
        ydl_opts = {
            **self._get_common_opts(),
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(self.audio_path, '%(id)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }

        try:
            if info is None:
                info = self._extract_info(url)
            
            if not info: raise Exception("Could not get video info")

            video_id = info.get('id')
            title = info.get('title')
            file_path = os.path.join(self.audio_path, f"{video_id}.mp3")

            if os.path.exists(file_path):
                logger.info(f"[CACHE] Audio hit: {video_id}")
                if storage_manager:
                    storage_manager.touch_file(file_path)
                return {"status": "success", "file_path": file_path, "title": title}

            if info.get('duration', 0) > MAX_DURATION_SEC:
                return {"status": "error", "message": f"Video too long ({info.get('duration')}s)"}

            logger.info(f"[DOWNLOAD] Audio: {title}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            return {"status": "success", "file_path": file_path, "title": title}

        except Exception as e:
            logger.error(f"[STORAGE] Audio error: {e}")
            return {"status": "error", "message": str(e)}

    def download_video(self, url, info: dict = None, storage_manager=None):
        ydl_opts = {
            **self._get_common_opts(),
            'format': 'best[ext=mp4]',
            'outtmpl': os.path.join(self.video_path, '%(id)s.%(ext)s'),
        }

        try:
            if info is None:
                info = self._extract_info(url)
            
            if not info: raise Exception("Could not get video info")

            video_id = info.get('id')
            title = info.get('title')
            ext = info.get("ext") or "mp4"
            file_path = os.path.join(self.video_path, f"{video_id}.{ext}")

            if os.path.exists(file_path):
                logger.info(f"[CACHE] Video hit: {video_id}")
                if storage_manager:
                    storage_manager.touch_file(file_path)
                return {"status": "success", "file_path": file_path, "title": title}

            if info.get('duration', 0) > MAX_DURATION_SEC:
                return {"status": "error", "message": "Video too long"}

            logger.info(f"[DOWNLOAD] Video: {title}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            return {"status": "success", "file_path": file_path, "title": title}

        except Exception as e:
            logger.error(f"[STORAGE] Video error: {e}")
            return {"status": "error", "message": str(e)}

    def download_both(self, url, storage_manager=None):
        info = self._extract_info(url)
        if not info:
            err = {"status": "error", "message": "Could not fetch info"}
            return err, err
        
        video_res = self.download_video(url, info=info, storage_manager=storage_manager)
        audio_res = self.download_audio(url, info=info, storage_manager=storage_manager)
        return video_res, audio_res