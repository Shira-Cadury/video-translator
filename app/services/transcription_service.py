import os
import json
import time
import logging
import threading
from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential
from app.services.audio_chunk_service import split_audio 

logger = logging.getLogger(__name__)

MAX_AUDIO_DURATION_SEC = 7200
CHUNK_SIZE_MB = 25 

class TranscriptionService:
    def __init__(self):
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is missing in environment variables!")
        
        self.client = Groq(api_key=api_key)
        self._lock = threading.Lock()  
        logger.info("[TRANSCRIPTION] Groq API initialized successfully.")

    def transcribe(self, audio_path, json_path=None, language="en", storage_manager=None, job_id=None, job_manager=None):
        if json_path and os.path.exists(json_path):
            cached = self._load_from_cache(json_path)
            if cached:
                logger.info("[TRANSCRIPTION] Using cached transcription")
                return cached

        if not os.path.exists(audio_path):
            return {"success": False, "error": "Audio file not found"}

        logger.info(f"[TRANSCRIPTION] Starting memory-efficient transcription: {audio_path}")
        start_time = time.time()

        try:
            chunks = split_audio(audio_path)
            if not chunks:
                return {"success": False, "error": "Failed to split audio into chunks"}

            all_segments = []
            num_chunks = len(chunks)

            for idx, (chunk_path, offset_sec) in enumerate(chunks):
                logger.info(f"[TRANSCRIPTION] Processing chunk {idx + 1}/{num_chunks}...")
                
                result = self._transcribe_with_retry(chunk_path)
                
                if result and "segments" in result:
                    for seg in result["segments"]:
                        seg["start"] = round(seg["start"] + offset_sec, 3)
                        seg["end"] = round(seg["end"] + offset_sec, 3)
                        all_segments.append(seg)
                
                if os.path.exists(chunk_path):
                    os.remove(chunk_path)

            all_segments.sort(key=lambda s: s.get("start", 0))
            full_text = " ".join([s.get("text", "") for s in all_segments])
            final_result = {"segments": all_segments, "text": full_text.strip()}

            if json_path:
                self._save_to_cache(final_result, json_path)

            elapsed = time.time() - start_time
            logger.info(f"[TRANSCRIPTION] ✓ Done in {elapsed:.1f}s")
            return {**final_result, "success": True, "duration_seconds": elapsed}

        except Exception as e:
            logger.error(f"[TRANSCRIPTION] Error: {e}")
            return {"success": False, "error": str(e)}

    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _call_groq_api(self, chunk_path):
        with open(chunk_path, "rb") as file:
            response = self.client.audio.transcriptions.create(
                file=(os.path.basename(chunk_path), file.read()),
                model="whisper-large-v3",
                response_format="verbose_json",
            )
        return response

    def _transcribe_with_retry(self, chunk_path):
        try:
            response = self._call_groq_api(chunk_path)
            return self._process_response(response)
        except Exception as e:
            logger.error(f"[TRANSCRIPTION] Groq API failed for {chunk_path}: {e}")
            return None

    def _process_response(self, response):
        segments = []
        full_text = response.text if hasattr(response, 'text') else ""
        if hasattr(response, 'segments') and response.segments:
            for seg in response.segments:
                segments.append({
                    "start": round(seg.get('start', 0), 3),
                    "end": round(seg.get('end', 0), 3),
                    "text": seg.get('text', '').strip()
                })
        return {"segments": segments, "text": full_text.strip()}

    def _load_from_cache(self, json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return {**json.load(f), "success": True, "from_cache": True}
        except: return None

    def _save_to_cache(self, data, json_path):
        try:
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[TRANSCRIPTION] Cache save failed: {e}")