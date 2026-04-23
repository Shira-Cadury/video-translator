import os
import re
import uuid
import subprocess
import logging

logger = logging.getLogger(__name__)

CHUNK_MINUTES = 10
MAX_CHUNK_SECONDS = CHUNK_MINUTES * 60

def _detect_silences(audio_path: str, noise_db: int = -30, min_duration: float = 0.5) -> list[float]:
    logger.info(f"[CHUNKER] Scanning for silences in {audio_path}...")
    
    cmd = [
        "ffmpeg", "-i", audio_path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
        "-f", "null", "-"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stderr
        
        silences = []
        matches = re.finditer(r"silence_end:\s*([\d\.]+)", output)
        for match in matches:
            silences.append(float(match.group(1)))
            
        return sorted(silences)
        
    except Exception as e:
        logger.error(f"[CHUNKER] Silence detection failed: {e}")
        return []

def _get_duration_ffprobe(audio_path: str) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path
            ],
            capture_output=True, text=True, check=True
        )
        return float(result.stdout.strip())
    except Exception as e:
        logger.error(f"[CHUNKER] ffprobe error: {e}")
        return None

def split_audio(audio_path: str, max_minutes: int = CHUNK_MINUTES) -> list[tuple[str, float]]:
    if not os.path.exists(audio_path):
        logger.error(f"[CHUNKER] File not found: {audio_path}")
        return []

    storage_dir = os.path.dirname(audio_path)
    max_chunk_seconds = max_minutes * 60
    chunk_paths = []

    duration = _get_duration_ffprobe(audio_path)
    if duration is None:
        logger.error("[CHUNKER] Could not determine audio duration via ffprobe")
        return []

    silences = _detect_silences(audio_path)
    logger.info(f"[CHUNKER] Found {len(silences)} potential silence split points.")

    start = 0.0
    index = 0
    
    while start < duration:
        target_end = start + max_chunk_seconds
        
        if target_end >= duration:
            actual_duration = duration - start
        else:
            valid_silences = [s for s in silences if start < s <= target_end]
            
            if valid_silences:
                best_silence = valid_silences[-1]
                actual_duration = best_silence - start
                logger.debug(f"[CHUNKER] Smart cut at {best_silence}s (saved {target_end - best_silence:.1f}s from being cut mid-word)")
            else:
                logger.warning(f"[CHUNKER] No silence found between {start:.1f} and {target_end:.1f}. Using hard cut.")
                actual_duration = max_chunk_seconds

        chunk_filename = f"chunk_{uuid.uuid4().hex}.mp3"
        chunk_path = os.path.join(storage_dir, chunk_filename)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-t", str(actual_duration), 
            "-i", audio_path,
            "-vn",
            "-ar", "16000",       
            "-ac", "1",           
            "-b:a", "64k",        
            chunk_path,
            "-loglevel", "error"
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
                chunk_paths.append((chunk_path, start))   
                logger.info(f"[CHUNKER] Chunk {index + 1}: {start:.0f}s → {start + actual_duration:.0f}s → {chunk_filename}")
            else:
                logger.warning(f"[CHUNKER] Empty chunk at {start}s, skipping")
        except subprocess.CalledProcessError as e:
            logger.error(f"[CHUNKER] ffmpeg failed on chunk at {start}s: {e.stderr.decode()}")

        start += actual_duration
        index += 1

    logger.info(f"[CHUNKER] Split into {len(chunk_paths)} smart chunks")
    return chunk_paths