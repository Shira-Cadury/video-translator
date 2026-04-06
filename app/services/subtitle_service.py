import os
import json
import logging
from app.config import STORAGE_PATH

logger = logging.getLogger(__name__)

class SubtitleService:
    def __init__(self):
        self.subtitles_dir = os.path.join(STORAGE_PATH, "subtitles")
        os.makedirs(self.subtitles_dir, exist_ok=True)

    def generate_srt(self, segments, output_path, storage_manager=None):
        if not segments:
            raise ValueError("No segments provided for subtitle generation")

        if os.path.exists(output_path):
            self._handle_existing_srt(output_path, storage_manager)
            return

        srt_content = self._build_srt_content(segments)
        self._write_to_file(srt_content, output_path)
        logger.info(f"[SAVED] SRT created: {output_path}")

        vtt_path = output_path.replace(".srt", ".vtt")
        self.convert_srt_to_vtt(output_path, vtt_path, storage_manager)

    def convert_srt_to_vtt(self, srt_path, vtt_path, storage_manager=None):
        if os.path.exists(vtt_path):
            if storage_manager:
                storage_manager.touch_file(vtt_path)
            return
            
        if not os.path.exists(srt_path):
            return

        with open(srt_path, "r", encoding="utf-8") as f:
            srt_lines = f.readlines()

        vtt_content = "WEBVTT\n\n"
        for line in srt_lines:
            vtt_content += line.replace(",", ".") if "-->" in line else line

        self._write_to_file(vtt_content, vtt_path)
        logger.info(f"[SAVED] VTT created: {vtt_path}")

    def save_transcript_json(self, transcription_result, output_path, storage_manager=None):
        if os.path.exists(output_path):
            if storage_manager:
                storage_manager.touch_file(output_path)
            return

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(transcription_result, f, indent=2, ensure_ascii=False)
        logger.info(f"[SAVED] JSON saved: {output_path}")

    def _format_time(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

    def _build_srt_block(self, index, start, end, text):
        return f"{index}\n{start} --> {end}\n{text}\n\n"

    def _build_srt_content(self, segments):
        content = ""
        for i, segment in enumerate(segments, start=1):
            start = self._format_time(segment.get("start", 0))
            end = self._format_time(segment.get("end", 0))
            text = segment.get("text", "").strip()
            content += self._build_srt_block(i, start, end, text)
        return content

    def _write_to_file(self, content, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _handle_existing_srt(self, srt_path, storage_manager):
        logger.info(f"[CACHE] SRT exists: {srt_path}")
        if storage_manager:
            storage_manager.touch_file(srt_path)
        
        vtt_path = srt_path.replace(".srt", ".vtt")
        self.convert_srt_to_vtt(srt_path, vtt_path, storage_manager)