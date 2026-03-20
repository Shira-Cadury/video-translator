import os
import json

class SubtitleService:
    def __init__(self):
        os.makedirs("storage/subtitles", exist_ok=True)
        

    def generate_srt(self, segments, output_path):
        if not segments:
            raise ValueError("No segments provided for subtitle generation")
        
        if os.path.exists(output_path):
            self._handle_existing_srt(output_path)
            return

        srt_content = self._build_srt_content(segments)
        
        self._write_to_file(srt_content, output_path)
        print(f"SRT saved: {output_path}")
        
        vtt_path = output_path.replace(".srt", ".vtt")
        self.convert_srt_to_vtt(output_path, vtt_path)

    def convert_srt_to_vtt(self, srt_path, vtt_path):
        if os.path.exists(vtt_path) or not os.path.exists(srt_path):
            return
        
        with open(srt_path, "r", encoding="utf-8") as f:
            srt_lines = f.readlines()
            
        vtt_content = "WEBVTT\n\n"
        for line in srt_lines:
            vtt_content += line.replace(",", ".") if "-->" in line else line
            
        self._write_to_file(vtt_content, vtt_path)
        print(f"VTT created: {vtt_path}")

    def save_transcript_json(self, transcription_result, output_path):
        if os.path.exists(output_path):
            return
            
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(transcription_result, f, indent=2, ensure_ascii=False)
        print(f"JSON saved: {output_path}")


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
            start = self._format_time(segment["start"])
            end = self._format_time(segment["end"])
            text = segment["text"].strip()
            content += self._build_srt_block(i, start, end, text)
        return content

    def _write_to_file(self, content, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _handle_existing_srt(self, srt_path):
        print(f"[CACHE] SRT exists: {srt_path}")
        vtt_path = srt_path.replace(".srt", ".vtt")
        if not os.path.exists(vtt_path):
            self.convert_srt_to_vtt(srt_path, vtt_path)