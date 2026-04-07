import os
import json
import time
import logging
from groq import Groq

logger = logging.getLogger(__name__)

MAX_AUDIO_DURATION_SEC = 7200  
MAX_RETRIES = 2

class TranscriptionService:
    def __init__(self):
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        logger.info("[TRANSCRIPTION] Groq API initialized.")

    def transcribe(self, audio_path, json_path=None, language="en", storage_manager=None, job_id=None, job_manager=None):
        if json_path and os.path.exists(json_path):
            if storage_manager:
                storage_manager.touch_file(json_path)
            cached = self._load_from_cache(json_path)
            if cached:
                logger.info("[TRANSCRIPTION] Using cached transcription")
                return cached

        if not os.path.exists(audio_path):
            return {"success": False, "error": "Audio file not found"}

        logger.info(f"[TRANSCRIPTION] Sending to Groq: {audio_path}")
        start_time = time.time()

        try:
            with open(audio_path, "rb") as file:
                response = self.client.audio.transcriptions.create(
                    file=(os.path.basename(audio_path), file.read()),
                    model="whisper-large-v3",
                    response_format="verbose_json", 
                )

            result = self._process_response(response)

            if json_path:
                self._save_to_cache(result, json_path)

            logger.info(f"[TRANSCRIPTION] Done in {time.time() - start_time:.1f}s — {len(result['segments'])} segments")
            return {**result, "success": True, "from_cache": False}

        except Exception as e:
            logger.error(f"[TRANSCRIPTION] Groq API Error: {e}")
            return {"success": False, "error": str(e)}

    def _process_response(self, response):
        segments = []
        full_text = response.text
        
        if hasattr(response, 'segments'):
            for seg in response.segments:
                segments.append({
                    "start": round(seg['start'], 3),
                    "end": round(seg['end'], 3),
                    "text": seg['text'].strip()
                })
        
        return {"segments": segments, "text": full_text.strip()}

    def _load_from_cache(self, json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return {**json.load(f), "success": True, "from_cache": True}
        except:
            return None

    def _save_to_cache(self, data, json_path):
        try:
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info("[TRANSCRIPTION] Saved to cache")
        except Exception as e:
            logger.error(f"[TRANSCRIPTION] Failed to save cache: {e}")