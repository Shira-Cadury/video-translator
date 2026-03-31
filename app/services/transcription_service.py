from app.config import MODEL_SIZE
from app.services.audio_chunk_service import split_audio
from faster_whisper import WhisperModel
import os
import json
import time
import logging

logger = logging.getLogger(__name__)

MAX_AUDIO_DURATION_SEC = 7200
CHUNK_THRESHOLD_SEC = 900
MAX_RETRIES = 2
CHUNK_TIMEOUT_SEC = 3600

class TranscriptionService:
    _model = None

    def __init__(self):
        self.load_model()

    def load_model(self):
        if TranscriptionService._model is None:
            logger.info(f"[TRANSCRIPTION] Loading faster-whisper model '{MODEL_SIZE}' on CPU (int8)...")
            try:
                TranscriptionService._model = WhisperModel(
                    MODEL_SIZE,
                    device="cpu",
                    compute_type="int8"
                )
                logger.info(f"[TRANSCRIPTION] Model '{MODEL_SIZE}' loaded successfully.")
            except Exception as e:
                logger.error(f"[TRANSCRIPTION] Failed to load model: {e}")
                TranscriptionService._model = None
        self.model = TranscriptionService._model

    def transcribe(self, audio_path, json_path=None, language="en", storage_manager=None, job_id=None, job_manager=None):
        if language in ("iw", "he"):
            logger.warning("[TRANSCRIPTION] Received 'he'/'iw' as audio language — defaulting to 'en'.")
            language = "en"

        if json_path and os.path.exists(json_path):
            if storage_manager:
                storage_manager.touch_file(json_path)
            cached = self._load_from_cache(json_path)
            if cached:
                logger.info("[TRANSCRIPTION] Using cached transcription")
                return cached

        if self.model is None:
            return {"success": False, "error": "Model not loaded"}

        if not os.path.exists(audio_path):
            return {"success": False, "error": "Audio file not found"}

        duration = self._get_audio_duration(audio_path)
        if duration and duration > MAX_AUDIO_DURATION_SEC:
            return {"success": False, "error": f"Audio exceeds maximum duration"}

        logger.info(f"[TRANSCRIPTION] Starting: {audio_path}")
        start = time.time()

        try:
            if duration and duration > CHUNK_THRESHOLD_SEC:
                result = self._transcribe_chunked(audio_path, language, duration, job_id, job_manager)
            else:
                result = self._transcribe_single(audio_path, language)

            if json_path:
                self._save_to_cache(result, json_path)

            logger.info(f"[TRANSCRIPTION] Done in {time.time() - start:.1f}s")
            return {**result, "success": True, "from_cache": False}
        except Exception as e:
            logger.error(f"[TRANSCRIPTION] Error: {e}")
            return {"success": False, "error": str(e)}

    def _transcribe_single(self, audio_path: str, language: str) -> dict:
        logger.info("[TRANSCRIPTION] Processing file directly...")
        segments_gen, _ = self.model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500}
        )
        return self._collect_segments(segments_gen)

    def _transcribe_chunked(self, audio_path: str, language: str, duration: float, job_id, job_manager) -> dict:
        logger.info(f"[CHUNKER] splitting into chunks...")
        chunks = split_audio(audio_path)
        if not chunks:
            raise Exception("Audio splitting failed")

        all_segments = []
        full_text = ""
        total_chunks = len(chunks)
        start_time = time.time()

        for i, (chunk_path, offset_sec) in enumerate(chunks):
            logger.info(f"[CHUNKER] Chunk {i + 1}/{total_chunks}")
            if job_id and job_manager:
                progress = 30 + int((i / total_chunks) * 30)
                job_manager.update_progress(job_id, progress)

            attempt = 0
            chunk_result = None
            while attempt <= MAX_RETRIES:
                try:
                    chunk_exec_start = time.time()
                    segments_gen, _ = self.model.transcribe(
                        chunk_path, language=language, beam_size=5, vad_filter=True
                    )
                    chunk_result = self._collect_segments(segments_gen)
                    
                    exec_duration = time.time() - chunk_exec_start
                    if exec_duration > CHUNK_TIMEOUT_SEC:
                        logger.error(f"[TIMEOUT] Chunk {i + 1} took too long: {exec_duration:.1f}s")
                        raise Exception(f"Chunk execution exceeded timeout of {CHUNK_TIMEOUT_SEC}s")
                    break
                except Exception as e:
                    attempt += 1
                    if attempt > MAX_RETRIES:
                        raise e
                    time.sleep(2)

            if job_id and job_manager:
                elapsed = time.time() - start_time
                avg = elapsed / (i + 1)
                eta = int(avg * (total_chunks - (i + 1)))
                job_manager.update_eta(job_id, eta)
                logger.info(f"[ETA] {eta}s remaining")

            for seg in chunk_result["segments"]:
                seg["start"] += offset_sec
                seg["end"] += offset_sec
            all_segments.extend(chunk_result["segments"])
            full_text += chunk_result["text"] + " "
            
            if os.path.exists(chunk_path):
                os.remove(chunk_path)

        return {"segments": all_segments, "text": full_text.strip()}

    def _collect_segments(self, segments_gen) -> dict:
        segments = []
        full_text = ""
        for seg in segments_gen:
            segments.append({
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip()
            })
            full_text += seg.text + " "
        return {"segments": segments, "text": full_text.strip()}

    def _get_audio_duration(self, audio_path: str) -> float | None:
        try:
            import mutagen
            audio = mutagen.File(audio_path)
            return audio.info.length if audio else None
        except: return None

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
        except: pass