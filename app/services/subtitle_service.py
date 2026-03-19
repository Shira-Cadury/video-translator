import os
import json

class SubtitleService:
    def __init__(self):
        os.makedirs("storage/subtitles", exist_ok=True)
        
    def generate_srt(self, segments, output_path):
        if not segments:
            raise ValueError("No segments provided for subtitle generation")
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(segments, start=1):
                start = self.format_time(segment["start"])
                end = self.format_time(segment["end"])
                text = segment["text"].strip()
                
                f.write(f"{i}\n")
                f.write(f"{start} --> {end}\n")
                f.write(f"{text}\n\n")   
        print(f"SRT subtitles saved: {output_path}")
        
        vtt_path = output_path.replace(".srt", ".vtt")
        self.convert_srt_to_vtt(output_path, vtt_path)
          
    def format_time(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"
    
    def convert_srt_to_vtt(self, srt_path, vtt_path):
        if not os.path.exists(srt_path):
            print(f"Warning: SRT file not found: {srt_path}")
            return
        
        os.makedirs(os.path.dirname(vtt_path), exist_ok=True)
        
        with open(srt_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        with open(vtt_path, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n") 
            
            for line in lines:
                if "-->" in line:
                    f.write(line.replace(",", "."))
                else:
                    f.write(line) 
        print(f"VTT subtitles created: {vtt_path}")