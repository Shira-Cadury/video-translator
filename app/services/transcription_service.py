import whisper
import os
import json
import time
import logging

logger = logging.getLogger(__name__)

class TranscriptionService:
    _model = None  

    def __init__(self):
        self.load_model()

    def load_model(self):
        if TranscriptionService._model is None:
            logger.info("Loading Whisper model ('large')...")
            try:
                TranscriptionService._model = whisper.load_model("large")
                logger.info("Model loaded.")
            except Exception as e:
                logger.error(f"Failed to load model: {e}")
                TranscriptionService._model = None

        self.model = TranscriptionService._model

    def transcribe(self, audio_path, json_path=None):
        if json_path and os.path.exists(json_path):
            cached = self._load_from_cache(json_path)
            if cached:
                logger.info("Using cached transcription")
                return cached

        if self.model is None:
            return {"success": False, "error": "Model not loaded"}

        if not os.path.exists(audio_path):
            return {"success": False, "error": "Audio file not found"}

        logger.info(f"Transcribing: {audio_path}")
        start = time.time()
        MAX_TIME = 1200

        try:
            result = self.model.transcribe(audio_path, fp16 =False, language="en")
            elapsed = time.time() - start
            
            if elapsed > MAX_TIME:
                logger.error(f"[TIMEOUT] Transcription took too long: {elapsed:.2f}s")
                raise Exception (f"Transcription timeout (Exceeded {MAX_TIME}s)")

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
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info("Saved transcription to cache")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")