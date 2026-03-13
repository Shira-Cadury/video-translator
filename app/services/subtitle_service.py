import os
import json

class SubtitleService:
    def __init__(self):
        os.makedirs("storage/subtitles", exist_ok=True)
        
        
    def generate_srt(self, segments, output_path):
        if not segments:
            raise ValueError("No segments provided for subtitle generation")
        
        with open(output_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(segments, start=1):
                start = self.format_time(segment["start"])
                end = self.format_time(segment["end"])
                text = segment["text"].strip()
                
                f.write(f"{i}\n")
                f.write(f"{start} --> {end}\n")
                f.write(f"{text}\n\n")   
            print(f"SRT subtitles saved: {output_path}")     
                
    def format_time(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"
    
    
    def save_transcript_json(self, transcription_result, output_path):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(transcription_result, f, indent=2, ensure_ascii=False)
        print(f"Transcript JSON saved: {output_path}")    
                    