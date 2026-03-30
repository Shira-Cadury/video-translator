from pydub import AudioSegment
import os
import uuid
import logging

logger = logging.getLogger(__name__)
CHUNK_MINUTES = 10

def split_audio(audio_path, minutes=CHUNK_MINUTES):
    try:
        logger.info(f"[CHUNKER] Loading audio file: {audio_path}")
        audio = AudioSegment.from_file(audio_path)
        
        chunk_length_ms = minutes * 60 * 1000
        chunk_paths = []
        
        storage_dir = os.path.dirname(audio_path)
        
        for i in range(0, len(audio), chunk_length_ms):
            chunk = audio[i:i + chunk_length_ms]
            chunk_filename = f"chunk_{uuid.uuid4().hex}.wav"
            path = os.path.join(storage_dir, chunk_filename)
            
            chunk.export(path, format="wav")
            chunk_paths.append(path)
            
        logger.info(f"[CHUNKER] Split into {len(chunk_paths)} chunks")
        return chunk_paths
    except Exception as e:
        logger.error(f"[CHUNKER] Error splitting audio: {e}")
        return []    
    