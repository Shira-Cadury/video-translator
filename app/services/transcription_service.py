from app.config import MODEL_SIZE
from app.services.audio_chunk_service import split_audio
import whisper
import os
import json
import time
import logging

logger = logging.getLogger(__name__)

MAX_AUDIO_DURATION_SEC = 7200  

class TranscriptionService:
    _model = None

    def __init__(self):
        self.load_model()

    def load_model(self):
        if TranscriptionService._model is None:
            logger.info(f"Loading Whisper model ('{MODEL_SIZE}')...")
            try:
                TranscriptionService._model = whisper.load_model(MODEL_SIZE)
                logger.info(f"Model {MODEL_SIZE} loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load model: {e}")
                TranscriptionService._model = None

        self.model = TranscriptionService._model

    def transcribe(self, audio_path, json_path=None, language="en", storage_manager=None, job_id=None, job_manager=None):
        if language == "iw":
            language = "he"
        if json_path and os.path.exists(json_path):
            if storage_manager:
                storage_manager.touch_file(json_path)
            cached = self._load_from_cache(json_path)
            if cached:
                logger.info("Using cached transcription")
                return cached

        if self.model is None:
            return {"success": False, "error": "Model not loaded"}

        if not os.path.exists(audio_path):
            return {"success": False, "error": "Audio file not found"}

        
        duration = self._get_audio_duration(audio_path)
        if duration and MAX_AUDIO_DURATION_SEC and duration > MAX_AUDIO_DURATION_SEC:
            logger.error(f"[REJECTED] Audio too long: {duration:.0f}s (max {MAX_AUDIO_DURATION_SEC}s)")
            return {"success": False, "error": f"Audio exceeds maximum duration of {MAX_AUDIO_DURATION_SEC // 60} minutes"}

        logger.info(f"Transcribing: {audio_path}")
        start = time.time()

        try:
            seconds_per_chunk = 10 * 60
            if duration > 900:
                logger.info(f"[CHUNKER] File is long ({duration:.0f}s), splitting into chunks...")
                
                chunks = split_audio(audio_path)
                all_segments = []
                full_text = ""
                total_chunks = len(chunks)
                
                for i, chunk_path in enumerate(chunks):
                    logger.info(f"Processing chunk {i+1}/{len(chunks)}: {chunk_path}")
                    
                    if job_id and job_manager:
                        current_progress = 30 + int((i / total_chunks) * 30)
                        job_manager.update_progress(job_id, current_progress)
                    
                    chunks_res = self.model.transcribe(chunk_path, fp16=False, language=language)
                    
                    offset = i * seconds_per_chunk
                    
                    current_segments = chunks_res.get("segments", [])
                    for seg in current_segments:
                        seg["start"] += offset
                        seg["end"] += offset
                    
                    all_segments.extend(chunks_res.get("segments", []))
                    full_text += chunks_res.get("text", "") + " "
                    os.remove(chunk_path)
                    
                result = {
                    "segments": all_segments,
                    "text": full_text.strip()
                }  
            else:
                logger.info(f"Processing short file directly...")   
                result = self.model.transcribe(audio_path, fp16=False, language=language)  

            if json_path:
                self._save_to_cache(result, json_path)

            logger.info(f"[TIME] Transcription: {time.time() - start:.2f}s")

            return {
                **result,
                "success": True,
                "from_cache": False
            }

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return {"success": False, "error": str(e)}

    def _get_audio_duration(self, audio_path: str):
        """Returns audio duration in seconds, or None if it can't be determined."""
        try:
            import mutagen
            audio = mutagen.File(audio_path)
            if audio and audio.info:
                return audio.info.length
        except Exception as e:
            logger.warning(f"Could not read audio duration: {e}")
        return None

    def _load_from_cache(self, json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    **data,
                    "success": True,
                    "from_cache": True
                }
        except Exception:
            logger.warning(f"Cache corrupted or missing at {json_path}")
            return None

    def _save_to_cache(self, data, json_path):
        try:
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info("Saved transcription to cache")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
