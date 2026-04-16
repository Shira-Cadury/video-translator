import os
import json
import time
import logging
import threading
from groq import Groq
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

MAX_AUDIO_DURATION_SEC = 7200
MAX_RETRIES = 2
CHUNK_LENGTH_MS = 5 * 60 * 1000  
CHUNK_SIZE_MB = 25  
API_RATE_LIMIT_DELAY = 0.5  

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logger.warning("[TRANSCRIPTION] pydub not installed. Install with: pip install pydub")


class TranscriptionService:
    def __init__(self):
        self.client = Groq(api_key=os.environ.get("gsk_Rl568JDgOWseQN2jwOLWGdyb3FYdZPiKJnsG5tsUPFxHmWPAfag"))
        self._lock = threading.Lock()  
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

        if not PYDUB_AVAILABLE:
            logger.error("[TRANSCRIPTION] pydub is required for chunking")
            logger.error("Install with: pip install pydub")
            return {"success": False, "error": "pydub not installed"}

        logger.info(f"[TRANSCRIPTION] Starting transcription: {audio_path}")
        start_time = time.time()

        try:
            audio = self._load_audio_safely(audio_path)
            if not audio:
                return {"success": False, "error": "Failed to load audio file"}

            audio_duration_sec = len(audio) / 1000.0
            if audio_duration_sec > MAX_AUDIO_DURATION_SEC:
                return {
                    "success": False,
                    "error": f"Audio file too long: {audio_duration_sec}s (max: {MAX_AUDIO_DURATION_SEC}s)"
                }

            chunks = self._create_chunks(audio)
            logger.info(f"[TRANSCRIPTION] Created {len(chunks)} chunks from {audio_duration_sec:.1f}s audio")

            all_segments = self._process_chunks_parallel(chunks, audio_path)

            all_segments.sort(key=lambda s: s.get("start", 0))

            full_text = " ".join([s.get("text", "") for s in all_segments])

            final_result = {"segments": all_segments, "text": full_text.strip()}

            if json_path:
                self._save_to_cache(final_result, json_path)

            elapsed = time.time() - start_time
            logger.info(f"[TRANSCRIPTION] ✓ Done in {elapsed:.1f}s — {len(all_segments)} segments")
            return {**final_result, "success": True, "from_cache": False, "duration_seconds": elapsed}

        except Exception as e:
            logger.error(f"[TRANSCRIPTION] Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "error": str(e)}

    def _load_audio_safely(self, audio_path):
        """Load audio with error handling (no .format attribute)."""
        try:
            audio = AudioSegment.from_file(audio_path)
            logger.info(f"[TRANSCRIPTION] Loaded audio: {len(audio)}ms")  
            return audio
        except Exception as e:
            logger.error(f"[TRANSCRIPTION] Failed to load audio: {e}")
            return None

    def _create_chunks(self, audio):
        chunks = []
        for i in range(0, len(audio), CHUNK_LENGTH_MS):
            chunk = audio[i:i + CHUNK_LENGTH_MS]
            if len(chunk) > 0:
                idx = i // CHUNK_LENGTH_MS
                offset_sec = i / 1000.0  
                chunks.append((idx, chunk, offset_sec))

        logger.info(f"[TRANSCRIPTION] Chunk sizes: {[len(c[1]) for c in chunks]}ms")
        return chunks

    def _process_chunks_parallel(self, chunks, audio_path):
        all_segments = []

        num_chunks = len(chunks)
        max_workers = min(3, max(1, num_chunks // 2))
        logger.info(f"[TRANSCRIPTION] Using {max_workers} parallel workers for {num_chunks} chunks")

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self._process_single_chunk, chunk, idx, offset_sec, audio_path): idx
                    for idx, chunk, offset_sec in chunks
                }

                completed = 0
                results = {}

                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        result = future.result()
                        results[idx] = result
                        completed += 1
                        logger.info(f"[TRANSCRIPTION] [{completed}/{num_chunks}] Chunk {idx} done")
                    except Exception as e:
                        logger.error(f"[TRANSCRIPTION] Chunk {idx} failed: {e}")
                        results[idx] = None

            for idx in sorted(results.keys()):
                if results[idx]:
                    all_segments.extend(results[idx])

            if not all_segments:
                logger.warning("[TRANSCRIPTION] No segments produced!")

            return all_segments

        except Exception as e:
            logger.error(f"[TRANSCRIPTION] Parallel processing failed: {e}")
            logger.info("[TRANSCRIPTION] Falling back to serial processing...")
            return self._process_chunks_serial(chunks, audio_path)

    def _process_chunks_serial(self, chunks, audio_path):
        all_segments = []
        for idx, chunk, offset_sec in chunks:
            try:
                logger.info(f"[TRANSCRIPTION] Processing chunk {idx}...")
                result = self._process_single_chunk(chunk, idx, offset_sec, audio_path)
                if result:
                    all_segments.extend(result)
            except Exception as e:
                logger.error(f"[TRANSCRIPTION] Chunk {idx} failed: {e}")
                continue
        return all_segments

    def _process_single_chunk(self, chunk, index, offset_sec, audio_path):
        chunk_path = f"{audio_path}_chunk_{index}.mp3"

        try:
            chunk.export(chunk_path, format="mp3", bitrate="192k")

            with self._lock:
                time.sleep(API_RATE_LIMIT_DELAY)

            result = self._transcribe_with_retry(chunk_path, MAX_RETRIES)

            if not result:
                logger.warning(f"[TRANSCRIPTION] Chunk {index} returned no results")
                return []

            for seg in result["segments"]:
                seg["start"] = round(seg["start"] + offset_sec, 3)
                seg["end"] = round(seg["end"] + offset_sec, 3)

            return result["segments"]

        except Exception as e:
            logger.error(f"[TRANSCRIPTION] Chunk {index} processing failed: {e}")
            return []

        finally:
            if os.path.exists(chunk_path):
                try:
                    os.remove(chunk_path)
                except Exception as e:
                    logger.warning(f"[TRANSCRIPTION] Failed to remove chunk file: {e}")

    def _transcribe_with_retry(self, chunk_path, max_retries):
        for attempt in range(max_retries):
            try:
                with open(chunk_path, "rb") as file:
                    file_size_mb = os.path.getsize(chunk_path) / (1024 * 1024)
                    if file_size_mb > CHUNK_SIZE_MB:
                        logger.warning(f"[TRANSCRIPTION] Chunk {file_size_mb:.1f}MB > {CHUNK_SIZE_MB}MB limit")

                    response = self.client.audio.transcriptions.create(
                        file=(os.path.basename(chunk_path), file.read()),
                        model="whisper-large-v3",
                        response_format="verbose_json",
                    )
                return self._process_response(response)

            except Exception as e:
                logger.warning(f"[TRANSCRIPTION] Attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info(f"[TRANSCRIPTION] Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"[TRANSCRIPTION] Failed after {max_retries} attempts")

        return None

    def _process_response(self, response):
        segments = []
        full_text = response.text if hasattr(response, 'text') else ""

        try:
            if hasattr(response, 'segments') and response.segments:
                for seg in response.segments:
                    segments.append({
                        "start": round(seg.get('start', 0), 3),
                        "end": round(seg.get('end', 0), 3),
                        "text": seg.get('text', '').strip()
                    })
            else:
                logger.warning("[TRANSCRIPTION] No segments in response, using full text")
        except Exception as e:
            logger.warning(f"[TRANSCRIPTION] Error processing segments: {e}")

        return {
            "segments": segments,
            "text": full_text.strip()
        }

    def _load_from_cache(self, json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                logger.info("[TRANSCRIPTION] Loaded from cache")
                return {**cached_data, "success": True, "from_cache": True}
        except Exception as e:
            logger.debug(f"[TRANSCRIPTION] Cache load failed: {e}")
            return None

    def _save_to_cache(self, data, json_path):
        try:
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info("[TRANSCRIPTION] Saved to cache")
        except Exception as e:
            logger.error(f"[TRANSCRIPTION] Failed to save cache: {e}")
