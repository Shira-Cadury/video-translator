import os
import uuid
import subprocess
import logging

logger = logging.getLogger(__name__)

CHUNK_MINUTES = 10


def split_audio(audio_path: str, minutes: int = CHUNK_MINUTES) -> list[str]:
    """
    Split audio into chunks using ffmpeg directly (no file loaded into RAM).

    FIX: The old pydub implementation loaded the ENTIRE audio file into memory
    before splitting — for a 1-hour MP3 that's ~600MB+ RAM, which caused the
    crash on chunk 2 (memory exhausted after chunk 1's transcription).

    ffmpeg splits the file by seeking to timestamps without decompressing
    everything upfront. RAM usage stays near zero regardless of file length.

    FIX: Output format changed from WAV to MP3.
    WAV is uncompressed — a 10-minute WAV chunk is ~100MB.
    MP3 chunks are ~10MB, and Whisper reads them just as well.
    """
    if not os.path.exists(audio_path):
        logger.error(f"[CHUNKER] File not found: {audio_path}")
        return []

    storage_dir = os.path.dirname(audio_path)
    chunk_seconds = minutes * 60
    chunk_paths = []

    # get total duration with ffprobe
    duration = _get_duration_ffprobe(audio_path)
    if duration is None:
        logger.error("[CHUNKER] Could not determine audio duration via ffprobe")
        return []

    start = 0.0
    index = 0
    while start < duration:
        chunk_filename = f"chunk_{uuid.uuid4().hex}.mp3"
        chunk_path = os.path.join(storage_dir, chunk_filename)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-t", str(chunk_seconds),
            "-i", audio_path,
            "-vn",
            "-ar", "16000",       # 16kHz — what Whisper expects
            "-ac", "1",           # mono
            "-b:a", "64k",        # compact bitrate is fine for speech
            chunk_path,
            "-loglevel", "error"
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
                chunk_paths.append((chunk_path, start))   # store (path, start_offset)
                logger.info(f"[CHUNKER] Chunk {index + 1}: {start:.0f}s → {min(start + chunk_seconds, duration):.0f}s → {chunk_path}")
            else:
                logger.warning(f"[CHUNKER] Empty chunk at {start}s, skipping")
        except subprocess.CalledProcessError as e:
            logger.error(f"[CHUNKER] ffmpeg failed on chunk at {start}s: {e.stderr.decode()}")

        start += chunk_seconds
        index += 1

    logger.info(f"[CHUNKER] Split into {len(chunk_paths)} chunks")
    return chunk_paths   # list of (path, start_offset_seconds)


def _get_duration_ffprobe(audio_path: str) -> float | None:
    """Use ffprobe to get audio duration in seconds without loading the file."""
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
